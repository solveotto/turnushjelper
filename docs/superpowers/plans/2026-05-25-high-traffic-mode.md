# High-Traffic Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace filesystem session storage with a custom SQLAlchemy-backed session interface, and add a gunicorn config for VPS/manual deployment.

**Architecture:** A custom `SessionInterface` subclass reads/writes sessions to a `flask_sessions` DB table using the existing `SessionLocal` from `app/database.py`. No new dependencies. Flask-Session package is removed. Gunicorn config is a standalone file at the project root.

**Tech Stack:** Python 3.12, Flask 3.x, SQLAlchemy 2.0, SQLite (dev) / MySQL (prod), Alembic, Gunicorn 25.x

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/models.py` | Modify | Add `FlaskSessionModel` ORM class |
| `migrations/versions/011_flask_sessions.py` | Create | Alembic migration for `flask_sessions` table |
| `app/utils/sa_session_interface.py` | Create | Custom `SessionInterface` implementation |
| `tests/test_sa_session_interface.py` | Create | Tests for all session interface edge cases |
| `app/__init__.py` | Modify | Swap flask-session config for custom interface |
| `requirements.txt` | Modify | Remove `Flask-Session==0.8.0` |
| `gunicorn.conf.py` | Create | Gunicorn worker config for VPS/manual use |
| `docs/guides/HIGH_TRAFFIC_MODE.md` | Create | Operator runbook |

---

## Task 1: Add FlaskSessionModel to app/models.py

**Files:**
- Modify: `app/models.py`

- [ ] **Step 1: Add LargeBinary to imports and add the model class**

In `app/models.py`, change the sqlalchemy import line (line 4) from:
```python
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, func, ForeignKey
```
to:
```python
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, UniqueConstraint, func, ForeignKey
```

Then add the following class **before** the `User` class (after `Innplassering`, line 127):

```python
class FlaskSessionModel(Base):
    __tablename__ = 'flask_sessions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(LargeBinary, nullable=False)
    expiry = Column(DateTime, nullable=False, index=True)
```

- [ ] **Step 2: Verify no import errors**

```bash
python -c "from app.models import FlaskSessionModel; print('OK')"
```
Expected output: `OK`

---

## Task 2: Write failing tests for the session interface

**Files:**
- Create: `tests/test_sa_session_interface.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for SqlAlchemySessionInterface."""

import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "testadmin123")

import pickle
from datetime import datetime, timedelta

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


def test_session_data_stored_in_db(client, test_engine):
    client.get("/set")
    row = _get_session_row(test_engine)
    assert row is not None
    data = pickle.loads(row.data)
    assert data.get("key") == "value"


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
    # Old row should be gone; a new one may or may not exist (only if /get writes)
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


def test_non_permanent_session_expiry_in_db_is_1_hour(client, test_engine):
    before = datetime.utcnow()
    client.get("/set")
    after = datetime.utcnow()
    row = _get_session_row(test_engine)
    assert row is not None
    expected_min = before + timedelta(minutes=59)
    expected_max = after + timedelta(hours=1, minutes=1)
    assert expected_min <= row.expiry <= expected_max


def test_permanent_session_expiry_in_db_is_31_days(client, test_engine):
    before = datetime.utcnow()
    client.get("/set-permanent")
    after = datetime.utcnow()
    row = _get_session_row(test_engine)
    assert row is not None
    expected_min = before + timedelta(days=30)
    expected_max = after + timedelta(days=32)
    assert expected_min <= row.expiry <= expected_max
```

- [ ] **Step 2: Run tests to confirm they fail (module not yet created)**

```bash
pytest tests/test_sa_session_interface.py -v
```
Expected: All tests fail with `ModuleNotFoundError: No module named 'app.utils.sa_session_interface'`

---

## Task 3: Create the Alembic migration

**Files:**
- Create: `migrations/versions/011_flask_sessions.py`

- [ ] **Step 1: Create the migration file**

```python
"""add flask_sessions table

Revision ID: 011_flask_sessions
Revises: 010_add_performance_indexes
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_flask_sessions"
down_revision: Union[str, None] = "010_add_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flask_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(255), unique=True, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("expiry", sa.DateTime, nullable=False),
    )
    op.create_index("ix_flask_sessions_sid", "flask_sessions", ["session_id"])
    op.create_index("ix_flask_sessions_expiry", "flask_sessions", ["expiry"])


def downgrade() -> None:
    op.drop_index("ix_flask_sessions_expiry", table_name="flask_sessions")
    op.drop_index("ix_flask_sessions_sid", table_name="flask_sessions")
    op.drop_table("flask_sessions")
```

- [ ] **Step 2: Apply migration to local dev DB**

```bash
alembic upgrade head
```
Expected: `Running upgrade 010_add_performance_indexes -> 011_flask_sessions, add flask_sessions table`

---

## Task 4: Implement the session interface

**Files:**
- Create: `app/utils/sa_session_interface.py`

- [ ] **Step 1: Create the file**

```python
import os
import pickle
import random
from datetime import datetime, timedelta

from flask.sessions import SessionInterface, SessionMixin
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import CallbackDict

from app.database import SessionLocal


class FlaskSession(CallbackDict, SessionMixin):
    """Server-side session object backed by a DB row."""

    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True

        super().__init__(initial or {}, on_update)
        self.sid = sid
        self.new = new
        self.modified = False


class SqlAlchemySessionInterface(SessionInterface):
    """Stores sessions in the flask_sessions DB table via existing SQLAlchemy engine."""

    def __init__(self, cleanup_probability: float = 0.01):
        self.cleanup_probability = cleanup_probability

    def _generate_sid(self) -> str:
        return os.urandom(32).hex()

    def open_session(self, app, request) -> FlaskSession:
        sid = request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"))
        if not sid:
            return FlaskSession(sid=self._generate_sid(), new=True)

        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is None or row.expiry < datetime.utcnow():
                if row is not None:
                    db.delete(row)
                    db.commit()
                return FlaskSession(sid=self._generate_sid(), new=True)
            return FlaskSession(pickle.loads(row.data), sid=sid)
        except Exception:
            return FlaskSession(sid=self._generate_sid(), new=True)
        finally:
            db.close()

    def save_session(self, app, session, response) -> None:
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")

        if not session:
            # Empty session (e.g. after logout_user()) — delete DB row and clear cookie.
            if not session.new:
                from app.models import FlaskSessionModel

                db = SessionLocal()
                try:
                    db.query(FlaskSessionModel).filter_by(session_id=session.sid).delete()
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
            response.delete_cookie(cookie_name, domain=domain, path=path)
            return

        if session.permanent:
            expiry = datetime.utcnow() + app.permanent_session_lifetime
        else:
            # Non-permanent: short server-side TTL; cookie itself has no expiry (browser session).
            expiry = datetime.utcnow() + timedelta(hours=1)

        sid = session.sid
        data = pickle.dumps(dict(session))

        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
            else:
                db.add(FlaskSessionModel(session_id=sid, data=data, expiry=expiry))
            db.commit()
        except IntegrityError:
            # Race: two threads created the same sid concurrently.
            db.rollback()
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
                try:
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            db.rollback()
        finally:
            db.close()

        if random.random() < self.cleanup_probability:
            self._delete_expired()

        response.set_cookie(
            cookie_name,
            sid,
            expires=expiry if session.permanent else None,
            httponly=self.get_cookie_httponly(app),
            domain=domain,
            path=path,
            secure=self.get_cookie_secure(app),
            samesite=self.get_cookie_samesite(app),
        )

    def _delete_expired(self) -> None:
        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            db.query(FlaskSessionModel).filter(
                FlaskSessionModel.expiry < datetime.utcnow()
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
```

- [ ] **Step 2: Run tests — expect them to pass now**

```bash
pytest tests/test_sa_session_interface.py -v
```
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/models.py app/utils/sa_session_interface.py migrations/versions/011_flask_sessions.py tests/test_sa_session_interface.py
git commit -m "feat: add SQLAlchemy-backed session interface and flask_sessions migration"
```

---

## Task 5: Swap session config in app/__init__.py

**Files:**
- Modify: `app/__init__.py`

- [ ] **Step 1: Replace flask-session wiring**

In `app/__init__.py`:

Remove this import at the top:
```python
from flask_session import Session
```

Replace this block (lines 49–56):
```python
    # Configure server-side session storage
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = AppConfig.sessions_dir
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_KEY_PREFIX"] = "session:"

    Session(app)
```

With:
```python
    from app.utils.sa_session_interface import SqlAlchemySessionInterface
    app.session_interface = SqlAlchemySessionInterface()
```

- [ ] **Step 2: Verify the app starts**

```bash
python -c "from app import create_app; app = create_app(); print('OK')"
```
Expected: `OK` (plus "Run: Create App" is not printed since we're not running run.py)

- [ ] **Step 3: Run the full test suite**

```bash
pytest --tb=short -q
```
Expected: All existing tests pass. The new session tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/__init__.py
git commit -m "feat: wire SqlAlchemySessionInterface into Flask app"
```

---

## Task 6: Remove Flask-Session from requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Remove the line**

Delete the line:
```
Flask-Session==0.8.0
```

from `requirements.txt`.

- [ ] **Step 2: Verify the app still starts without flask-session**

```bash
python -c "from app import create_app; app = create_app(); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: remove Flask-Session dependency (replaced by custom interface)"
```

---

## Task 7: Create gunicorn.conf.py

**Files:**
- Create: `gunicorn.conf.py`

- [ ] **Step 1: Create the file**

```python
# Gunicorn config — used for VPS or manual deployment.
# PythonAnywhere's standard WSGI hosting does NOT use this file.
# To use: gunicorn -c gunicorn.conf.py run:app

workers = 2           # conservative for PythonAnywhere; tune up on a VPS with more RAM
worker_class = "gthread"
threads = 4           # 2 workers × 4 threads = 8 concurrent requests
timeout = 60
keepalive = 5
bind = "0.0.0.0:8080"
accesslog = "-"       # stdout
errorlog = "-"        # stderr
```

- [ ] **Step 2: Verify gunicorn can read the config without error**

```bash
source venv/bin/activate && gunicorn -c gunicorn.conf.py --check-config run:app
```
Expected: No errors, process exits cleanly.

- [ ] **Step 3: Commit**

```bash
git add gunicorn.conf.py
git commit -m "feat: add gunicorn.conf.py for VPS/manual deployment"
```

---

## Task 8: Write the operator runbook

**Files:**
- Create: `docs/guides/HIGH_TRAFFIC_MODE.md`

- [ ] **Step 1: Create the runbook**

```markdown
# High-Traffic Mode — Operator Runbook

This guide covers what to do when the site becomes slow or unresponsive.

## Current State (as of 2026-05-25)

These improvements are already active in `main`/`development`:

| Feature | Status |
|---|---|
| SQLAlchemy-backed sessions | Active |
| 120s route cache on `/turnusliste` | Active |
| Cache invalidation on favorite toggle | Active |
| MySQL connection pool (10/20) | Active |
| Gunicorn gthread config | Available (`gunicorn.conf.py`) |

## Step 1: Check what's slow

- PythonAnywhere dashboard → Web tab → error log
- If you see MySQL "too many connections" errors → reduce `pool_size` in `app/database.py`
- If you see slow page loads → likely the `/turnusliste` cache miss; check cache hit rate

## Step 2: Restart the app

On PythonAnywhere: Web tab → Reload.

This clears the in-process `SimpleCache` (Flask-Caching `simple` backend). Do this first — it's free.

## Step 3: Upgrade PythonAnywhere plan

If the app is consistently slow (not spiky), upgrade to a higher PythonAnywhere plan tier for more workers and RAM.

## Step 4: Move to a VPS (Hetzner / DigitalOcean)

If you need more than PythonAnywhere can offer:

1. Provision a Linux VPS (Hetzner CX22 is a good starting point)
2. Clone the repo, install dependencies: `pip install -r requirements.txt`
3. Apply migrations: `alembic upgrade head`
4. Run with gunicorn: `gunicorn -c gunicorn.conf.py run:app`

### Gunicorn tuning

`gunicorn.conf.py` default: 2 workers × 4 threads = 8 concurrent requests.

**Note:** `gunicorn.conf.py` does NOT apply on PythonAnywhere's standard WSGI hosting — only on a VPS or if you run gunicorn manually.

To scale up on a VPS with more RAM:
```python
workers = 4    # each worker uses ~150–200 MB
threads = 4
```

## Session behaviour on first deploy

When the SQLAlchemy session backend was activated, all existing filesystem sessions became invalid. Users were logged out once. This is a one-time event.

Future deploys do not log users out (sessions persist in the DB).
```

- [ ] **Step 2: Commit**

```bash
git add docs/guides/HIGH_TRAFFIC_MODE.md
git commit -m "docs: add HIGH_TRAFFIC_MODE operator runbook"
```

---

## Self-Review

**Spec coverage check:**
- ✅ SQLAlchemy sessions — Tasks 1, 2, 4, 5
- ✅ Alembic migration for flask_sessions — Task 3
- ✅ Remove Flask-Session — Task 6
- ✅ Gunicorn config with VPS-only scope note — Task 7
- ✅ Operator runbook — Task 8
- ✅ Test file — Task 2
- ✅ Empty session deletion — Task 4 `save_session()` spec
- ✅ `session.permanent` expiry branching — Task 4
- ✅ Race condition upsert (IntegrityError) — Task 4

**Placeholder scan:** None found.

**Type consistency:**
- `FlaskSessionModel` defined in Task 1, used in Tasks 2, 4 — consistent.
- `SqlAlchemySessionInterface` defined in Task 4, wired in Task 5, referenced in test `app` fixture (Task 2) — consistent.
- `SessionLocal` imported in `sa_session_interface.py`, monkeypatched in tests as `app.utils.sa_session_interface.SessionLocal` — consistent.
