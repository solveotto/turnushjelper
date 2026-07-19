"""
Test configuration and shared fixtures.

Uses an in-memory SQLite database with connection-level transaction
rollback so every test starts with a clean slate.
"""

import os

# Set environment variables BEFORE any app imports (config.py reads at import time)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "testadmin123")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DBUser
from app.services.user_service import hash_password

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_engine():
    """Create an in-memory SQLite engine and build all tables once."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    """
    Per-test session using connection + transaction rollback pattern.
    Opens a connection, begins a transaction, yields a session,
    then rolls back everything so the next test starts clean.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def patch_db(db_session, monkeypatch):
    """
    Monkeypatch ``get_db_session`` in every module that imports it so all
    code paths use the test database.

    Also clears the Flask-Caching cache so memoized values from one test
    don't bleed into the next.

    The service functions follow this pattern:
        session = get_db_session()
        try:
            ...
            session.commit()
        finally:
            session.close()

    Each call to ``get_db_session()`` must return a *new* session object
    bound to the **same connection / transaction** so that:
      1. ``session.close()`` in finally blocks doesn't destroy the connection.
      2. The outer transaction can be rolled back to reset state between tests.
    """

    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass

    # Grab the connection that db_session is already using.
    # Binding new sessions to this connection means:
    #  - .close() only releases the session, NOT the connection
    #  - .commit() flushes to the connection's transaction (visible to other sessions)
    #  - The outer transaction.rollback() in db_session resets everything
    connection = db_session.get_bind()
    TestSession = sessionmaker(bind=connection)

    def make_session():
        return TestSession()

    modules_to_patch = [
        "app.database",
        "app.models",
        "app.services.user_service",
        "app.services.auth_service",
        "app.services.activity_service",
        "app.services.favorites_service",
        "app.services.turnus_service",
        "app.utils.db_utils",
    ]
    for mod in modules_to_patch:
        monkeypatch.setattr(f"{mod}.get_db_session", make_session)

    yield db_session


# ---------------------------------------------------------------------------
# App / client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(patch_db, monkeypatch):
    """Create a Flask test app with patched DB and disabled CSRF."""
    monkeypatch.setattr("app.services.user_service.init_default_admin", lambda: None)

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost"

    # Disable rate limiting at runtime, NOT via RATELIMIT_ENABLED config:
    # with the config flag off, init_app returns before creating the storage
    # backend, and the limiter can never be re-enabled for the 429 tests.
    # init_app above ran with the flag on, so storage exists (and is rebuilt
    # per test app, isolating counters); this just switches enforcement off.
    # login_user() runs far more than 10 logins/minute across the suite.
    from app.extensions import limiter
    limiter.enabled = False

    yield app


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Seed-data helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_user(patch_db, db_session):
    """Insert a regular user and return their dict."""
    user = DBUser(
        username="testuser",
        email="testuser@example.com",
        password=hash_password("password123"),
        is_auth=0,
        email_verified=1,
    )
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": "testuser", "password": "password123"}


@pytest.fixture()
def admin_user(patch_db, db_session):
    """Insert an admin user and return their dict."""
    user = DBUser(
        username="adminuser",
        email="admin@example.com",
        password=hash_password("adminpass123"),
        is_auth=1,
        email_verified=1,
    )
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": "adminuser", "password": "adminpass123"}


def login_user(client, username, password):
    """Helper: log a user in via the login route."""
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Turnus-schedule factories (shared by validator and shift_stats tests)
# ---------------------------------------------------------------------------

WEEKDAYS_NB = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]


def make_work_day(day_nr, start, slutt, dagsverk):
    """A single work day: a 2-time shift with mirrored start/slutt."""
    return {
        "ukedag": WEEKDAYS_NB[day_nr - 1],
        "tid": [start, slutt],
        "start": start,
        "slutt": slutt,
        "dagsverk": dagsverk,
        "is_consecutive_shift": False,
        "is_consecutive_receiver": False,
    }


def make_free_day(day_nr, code="X"):
    """A single free day (X/O/T): one free code, empty dagsverk and slutt."""
    return {
        "ukedag": WEEKDAYS_NB[day_nr - 1],
        "tid": [code],
        "start": [code],
        "slutt": "",
        "dagsverk": "",
        "is_consecutive_shift": False,
        "is_consecutive_receiver": False,
    }


def make_valid_turnus_data(shift=("8:00", "15:00"), kl_timer="210:00", tj_timer="220:00"):
    """A structurally valid turnus that passes the full validator.

    Mon–Fri of all 6 weeks are identical 7h work shifts (30 days × 7h = 210h,
    matching the default kl_timer), Sat/Sun are free. Tests mutate one field of
    the returned dict to exercise a single failure path.
    """
    start, slutt = shift
    data = {}
    for w in range(1, 7):
        week = {}
        for d in range(1, 8):
            if d <= 5:
                week[str(d)] = make_work_day(d, start, slutt, f"D{w}{d}")
            else:
                week[str(d)] = make_free_day(d)
        data[str(w)] = week
    data["kl_timer"] = kl_timer
    data["tj_timer"] = tj_timer
    return data


def turnus_list(*data_by_name):
    """Wrap (name, data) pairs into the top-level list the validator expects."""
    return [{name: data} for name, data in data_by_name]


def single_shift_schedule(name, start, end):
    """A minimal schedule with one work shift on W1D1 and 41 free days.

    Totals are omitted (shift_stats ignores them); not validator-valid on its
    own. Used for shift_stats night-classification tests.
    """
    data = {}
    for w in range(1, 7):
        week = {}
        for d in range(1, 8):
            if w == 1 and d == 1:
                week["1"] = {"ukedag": "Mandag", "tid": [start, end], "dagsverk": "TEST"}
            else:
                week[str(d)] = {"ukedag": WEEKDAYS_NB[d - 1], "tid": ["X"], "dagsverk": "X"}
        data[str(w)] = week
    return [{name: data}]
