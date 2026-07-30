"""Tests for SqlAlchemySessionInterface."""

import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "testadmin123")

import json
import logging
import pickle
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, session
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FlaskSessionModel


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_sessions(test_engine):
    """Wipe flask_sessions table before each test."""
    Session = sessionmaker(bind=test_engine)
    db = Session()
    db.query(FlaskSessionModel).delete()
    db.commit()
    db.close()


@pytest.fixture()
def app(test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker as sm
    TestSession = sm(bind=test_engine)
    monkeypatch.setattr("app.utils.sa_session_interface.SessionLocal", TestSession)

    from app.utils.sa_session_interface import SqlAlchemySessionInterface

    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.config["TESTING"] = True
    flask_app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=31)
    flask_app.session_interface = SqlAlchemySessionInterface()

    @flask_app.route("/set")
    def set_session():
        session["key"] = "value"
        return "set"

    @flask_app.route("/get")
    def get_session():
        return session.get("key", "missing")

    @flask_app.route("/clear")
    def clear_session():
        session.clear()
        return "cleared"

    @flask_app.route("/set-permanent")
    def set_permanent():
        session.permanent = True
        session["key"] = "value"
        return "set"

    @flask_app.route("/read-and-touch")
    def read_and_touch():
        # Mimics csrf_token(), which real pages render on every request: it
        # writes to the session, so even a "read-only" page view makes the
        # session non-empty and therefore saveable. Necessary to reproduce the
        # cookie-overwrite path in the DB-error tests below.
        session.setdefault("csrf_token", "tok")
        return session.get("key", "missing")

    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _count_sessions(test_engine):
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        return db.query(FlaskSessionModel).count()
    finally:
        db.close()


def _get_session_row(test_engine):
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        return db.query(FlaskSessionModel).first()
    finally:
        db.close()


def test_new_session_sets_cookie(client):
    rv = client.get("/set")
    assert rv.status_code == 200
    assert "session" in rv.headers.get("Set-Cookie", "")


def test_session_data_stored_as_json(client, test_engine):
    client.get("/set")
    row = _get_session_row(test_engine)
    assert row is not None
    # Sessions are serialized as JSON (not pickle) — no deserialization gadget.
    data = json.loads(row.data)
    assert data.get("key") == "value"
    with pytest.raises((pickle.UnpicklingError, KeyError, EOFError, ValueError)):
        pickle.loads(row.data)


def test_legacy_pickle_row_yields_fresh_session(client, test_engine):
    """A row written by the old pickle serializer must not crash the app; it
    fails to parse as JSON and is treated as a new empty session (the one-time
    global logout on the JSON cut-over)."""
    client.get("/set")
    row = _get_session_row(test_engine)
    sid = row.session_id
    # Overwrite the DB row with legacy pickle bytes for the same sid.
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        legacy = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
        legacy.data = pickle.dumps({"key": "legacy-value"})
        db.commit()
    finally:
        db.close()
    # The still-valid cookie points at the pickled row; it must not load it.
    rv = client.get("/get")
    assert rv.data == b"missing"


def test_existing_session_loads_data(client):
    client.get("/set")
    rv = client.get("/get")
    assert rv.data == b"value"


def test_empty_session_deletes_db_row(client, test_engine):
    client.get("/set")
    assert _count_sessions(test_engine) == 1
    client.get("/clear")
    assert _count_sessions(test_engine) == 0


def test_empty_session_clears_cookie(client):
    client.get("/set")
    rv = client.get("/clear")
    set_cookie = rv.headers.get("Set-Cookie", "")
    # Flask delete_cookie sets Max-Age=0
    assert "Max-Age=0" in set_cookie


def test_expired_session_returns_new_empty_session(client, test_engine):
    client.get("/set")
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        row = db.query(FlaskSessionModel).first()
        row.expiry = datetime(2000, 1, 1)
        db.commit()
    finally:
        db.close()
    rv = client.get("/get")
    assert rv.data == b"missing"


def test_expired_session_old_row_deleted(client, test_engine):
    client.get("/set")
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        row = db.query(FlaskSessionModel).first()
        original_sid = row.session_id
        row.expiry = datetime(2000, 1, 1)
        db.commit()
    finally:
        db.close()
    client.get("/get")
    Session2 = sessionmaker(bind=test_engine)
    db2 = Session2()
    try:
        old_row = db2.query(FlaskSessionModel).filter_by(session_id=original_sid).first()
        assert old_row is None
    finally:
        db2.close()


def test_non_permanent_session_no_cookie_expiry(client):
    rv = client.get("/set")
    set_cookie = rv.headers.get("Set-Cookie", "")
    # Non-permanent: cookie should not carry an Expires/Max-Age (browser session cookie)
    assert "Max-Age" not in set_cookie
    assert "Expires" not in set_cookie


def test_permanent_session_sets_cookie_expiry(client):
    rv = client.get("/set-permanent")
    set_cookie = rv.headers.get("Set-Cookie", "")
    assert "Expires" in set_cookie or "Max-Age" in set_cookie


def test_non_permanent_session_expiry_in_db_matches_permanent_lifetime(client, test_engine):
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    client.get("/set")
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    row = _get_session_row(test_engine)
    assert row is not None
    # Non-permanent uses app.permanent_session_lifetime (31 days in test config)
    expected_min = before + timedelta(days=30)
    expected_max = after + timedelta(days=32)
    assert expected_min <= row.expiry <= expected_max


def test_permanent_session_expiry_in_db_is_31_days(client, test_engine):
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    client.get("/set-permanent")
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    row = _get_session_row(test_engine)
    assert row is not None
    expected_min = before + timedelta(days=30)
    expected_max = after + timedelta(days=32)
    assert expected_min <= row.expiry <= expected_max


# ── Cookie hardening flags (fix #2) ─────────────────────────────────────────
# The interface reads Secure/HttpOnly/SameSite from Flask config, so these
# assert the wiring that AppConfig sets in production actually reaches the
# Set-Cookie header.

def test_secure_flag_set_when_configured(app, client):
    app.config["SESSION_COOKIE_SECURE"] = True
    set_cookie = client.get("/set").headers.get("Set-Cookie", "")
    assert "Secure" in set_cookie


def test_secure_flag_absent_when_disabled(app, client):
    app.config["SESSION_COOKIE_SECURE"] = False
    set_cookie = client.get("/set").headers.get("Set-Cookie", "")
    assert "Secure" not in set_cookie


def test_samesite_flag_applied(app, client):
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    set_cookie = client.get("/set").headers.get("Set-Cookie", "")
    assert "SameSite=Lax" in set_cookie


def test_httponly_flag_set_by_default(app, client):
    # Flask defaults SESSION_COOKIE_HTTPONLY to True; the interface must honor it.
    set_cookie = client.get("/set").headers.get("Set-Cookie", "")
    assert "HttpOnly" in set_cookie


# ── Transient DB errors must not destroy a valid session ────────────────────
# open_session used to catch bare Exception and return a fresh session. Because
# csrf_token() renders on every page, that fresh session is never empty, so
# save_session then INSERTed a row under the new sid and overwrote the still
# valid cookie — orphaning the real row and turning one transient read error
# into a permanent logout.

class _RaisingSession:
    """Stands in for a SQLAlchemy session whose query hits a dead connection."""

    def __init__(self, exc):
        self._exc = exc

    def query(self, *args, **kwargs):
        raise self._exc

    def rollback(self):
        pass

    def close(self):
        pass


def _db_error():
    return OperationalError("SELECT 1", {}, Exception("connection lost"))


def test_db_read_error_propagates_instead_of_resetting_session(app, client, monkeypatch):
    """A DB failure must surface, not masquerade as "no session"."""
    client.get("/set")  # need a valid cookie, or open_session returns before the DB read
    monkeypatch.setattr(
        "app.utils.sa_session_interface.SessionLocal",
        lambda: _RaisingSession(_db_error()),
    )
    with pytest.raises(OperationalError):
        client.get("/get")


def test_db_read_error_does_not_orphan_the_session(app, client, test_engine, monkeypatch):
    """The actual regression, in its faithful shape.

    Two conditions are both required to lose a session, and this test reproduces
    both: (1) the failure is TRANSIENT — only the open_session read fails, while
    the save_session write gets a healthy connection (under a sustained outage
    the save fails too, no cookie is set, and the session survives by accident);
    and (2) the request writes to the session, which csrf_token() does on every
    real page render. Verified against the pre-fix code: it replaced the cookie
    and the session did not survive.
    """
    client.get("/set")
    original = client.get_cookie("session")
    assert original is not None

    working = sessionmaker(bind=test_engine)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        # Only the first checkout (the open_session read) is broken.
        return _RaisingSession(_db_error()) if calls["n"] == 1 else working()

    monkeypatch.setattr("app.utils.sa_session_interface.SessionLocal", factory)

    with pytest.raises(OperationalError):
        client.get("/read-and-touch")

    # The failed request must not have handed out a replacement session cookie.
    assert client.get_cookie("session").value == original.value

    # ...so the original row is still intact and the user is still logged in.
    assert client.get("/read-and-touch").data == b"value"


# ── Reason-tagged logging ───────────────────────────────────────────────────
# Four separate conditions return a fresh session; in production they were
# indistinguishable. Each now carries a distinct tag so the logs say which one
# is firing. bad_signature in particular means SECRET_KEY is unstable.

def _tags_for(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.utils.sa_session_interface"):
        client.get("/get")
    return caplog.text


def test_bad_signature_logged_distinctly(app, client, caplog):
    client.set_cookie("session", "this-is-not-a-validly-signed-sid")
    assert "bad_signature" in _tags_for(client, caplog)


def test_row_missing_logged_distinctly(app, client, test_engine, caplog):
    client.get("/set")
    # Keep the (valid) cookie but drop the row — an orphaned session.
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(FlaskSessionModel).delete()
        db.commit()
    finally:
        db.close()
    assert "row_missing" in _tags_for(client, caplog)


def test_row_expired_logged_distinctly(app, client, test_engine, caplog):
    client.get("/set")
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(FlaskSessionModel).first().expiry = datetime(2000, 1, 1)
        db.commit()
    finally:
        db.close()
    assert "row_expired" in _tags_for(client, caplog)


def test_decode_failure_logged_distinctly(app, client, test_engine, caplog):
    client.get("/set")
    db = sessionmaker(bind=test_engine)()
    try:
        db.query(FlaskSessionModel).first().data = pickle.dumps({"key": "legacy"})
        db.commit()
    finally:
        db.close()
    assert "decode_failed" in _tags_for(client, caplog)


def test_csrf_time_limit_is_eight_hours():
    """Not Flask-WTF's 1-hour default (a form open across a break fails and
    shows a misleading "session expired" warning), and deliberately not the
    30-day session lifetime, which would widen the replay window."""
    from config import AppConfig

    assert AppConfig.WTF_CSRF_TIME_LIMIT == 8 * 60 * 60


def test_appconfig_secure_defaults_on_for_mysql(monkeypatch):
    """AppConfig.SESSION_COOKIE_SECURE defaults ON in production (DB_TYPE=mysql)
    and OFF for sqlite dev, unless explicitly overridden."""
    import importlib

    import config as config_mod

    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    try:
        monkeypatch.setenv("DB_TYPE", "mysql")
        importlib.reload(config_mod)
        assert config_mod.AppConfig.SESSION_COOKIE_SECURE is True

        monkeypatch.setenv("DB_TYPE", "sqlite")
        importlib.reload(config_mod)
        assert config_mod.AppConfig.SESSION_COOKIE_SECURE is False
    finally:
        # Restore the module to the default sqlite test state.
        monkeypatch.setenv("DB_TYPE", "sqlite")
        importlib.reload(config_mod)
