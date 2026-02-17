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
    monkeypatch.setattr("app.database.create_tables", lambda: None)
    monkeypatch.setattr("app.services.user_service.init_default_admin", lambda: None)

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost"

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
