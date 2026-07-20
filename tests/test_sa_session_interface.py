"""Tests for SqlAlchemySessionInterface."""

import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "testadmin123")

import json
import pickle
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, session
from sqlalchemy import create_engine
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
