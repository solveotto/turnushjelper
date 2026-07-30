"""
Load / stress tests for the Shift Rotation Organizer.

Two modes:
  Local (default)  — Flask test client + ThreadPoolExecutor
  Remote           — real HTTP via ``requests``

Usage:
  pytest tests/test_load.py -v                       # local
  LOAD_TEST_URL=https://hetzner.turnushjelper.no pytest tests/test_load.py -v  # remote
"""

import os
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
REMOTE_URL = os.environ.get("LOAD_TEST_URL", "").rstrip("/")
WORKERS = int(os.environ.get("LOAD_TEST_WORKERS", "10"))
REQUESTS = int(os.environ.get("LOAD_TEST_REQUESTS", "50"))

is_remote = bool(REMOTE_URL)

if is_remote:
    import requests as http_lib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(client_or_url, method, path, **kwargs):
    """Send a single request and return (status_code, elapsed_seconds).

    Works with both Flask's test client (local) and the requests library
    (remote).  ``client_or_url`` is either a Flask test-client instance or
    a base-URL string.
    """
    if isinstance(client_or_url, str):
        url = client_or_url + path
        start = time.perf_counter()
        resp = getattr(http_lib, method)(url, timeout=30, **kwargs)
        elapsed = time.perf_counter() - start
        return resp.status_code, elapsed

    # Flask test client
    fn = getattr(client_or_url, method)
    start = time.perf_counter()
    resp = fn(path, **kwargs)
    elapsed = time.perf_counter() - start
    return resp.status_code, elapsed


def _fire_requests(target, method, path, n_requests, workers, **kwargs):
    """Run *n_requests* concurrently and collect results."""
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(make_request, target, method, path, **kwargs)
            for _ in range(n_requests)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())
    return results


def _check_results(results, threshold_p95=2.0):
    """Analyse collected (status_code, elapsed) pairs.

    Prints a summary table, then asserts:
      1. Zero 5xx server errors
      2. p95 response time is below *threshold_p95* seconds
    """
    status_codes = [s for s, _ in results]
    times = sorted(t for _, t in results)

    server_errors = sum(1 for s in status_codes if s >= 500)
    client_errors = sum(1 for s in status_codes if 400 <= s < 500)
    avg_time = statistics.mean(times)
    p95_time = times[int(len(times) * 0.95)]
    max_time = times[-1]

    print(
        f"\n{'─' * 50}"
        f"\n  Requests : {len(results)}"
        f"\n  5xx errs : {server_errors}"
        f"\n  4xx errs : {client_errors}"
        f"\n  Avg time : {avg_time:.4f}s"
        f"\n  p95 time : {p95_time:.4f}s"
        f"\n  Max time : {max_time:.4f}s"
        f"\n  Threshold: {threshold_p95:.2f}s"
        f"\n{'─' * 50}"
    )

    assert server_errors == 0, f"{server_errors}/{len(results)} requests returned 5xx"
    assert p95_time < threshold_p95, (
        f"p95 latency {p95_time:.3f}s exceeds threshold {threshold_p95:.1f}s"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def target(request):
    """Return either the remote URL or a Flask test client."""
    if is_remote:
        yield REMOTE_URL
    else:
        # Pull the ``client`` fixture from conftest
        client = request.getfixturevalue("client")
        yield client


# ---------------------------------------------------------------------------
# Thread-safe fixture stack (local mode only)
# ---------------------------------------------------------------------------
# The shared conftest fixtures deliberately bind EVERY session to one
# connection so an outer transaction can be rolled back between tests. That is
# fundamentally incompatible with real threads: SQLite refuses cross-thread use
# of a connection, and forcing it through (check_same_thread=False) does not
# make it safe -- concurrent cursor use corrupts result sets, surfacing as a
# random IndexError inside SQLAlchemy's row handling.
#
# So the concurrency tests that need an authenticated session get their own
# file-backed database with a normal connection pool: each thread checks out
# its own connection. Isolation comes from a fresh file per test instead of
# transaction rollback.
#
# Before the session interface stopped swallowing DB errors, these threaded
# requests silently received a fresh empty session, so every one of them ran
# UNAUTHENTICATED and the test passed while exercising nothing. It only became
# visible once open_session was allowed to raise.

@pytest.fixture()
def threadsafe_db(tmp_path, monkeypatch):
    """A committed, pooled, file-backed test DB. Yields the seeded user."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models import DBUser, TurnusSet
    from app.services.user_service import hash_password

    engine = create_engine(
        f"sqlite:///{tmp_path / 'loadtest.db'}",
        # Generous busy timeout: 10 threads writing the same SQLite file will
        # contend for the write lock, and the default (5s) can trip under load.
        connect_args={"timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    password = "loadtestpass123"
    db = Session()
    try:
        user = DBUser(
            username="loaduser",
            email="loaduser@example.com",
            password=hash_password(password),
            is_auth=0,
            email_verified=1,
        )
        db.add(user)
        # toggle_favorite needs a turnus set, or it returns
        # {"status": "error", "message": "No turnus set selected"} at HTTP 200.
        turnus_set = TurnusSet(name="Load Test Set", year_identifier="L99", is_active=1)
        db.add(turnus_set)
        db.commit()
        user_id = user.id
        turnus_set_id = turnus_set.id
    finally:
        db.close()

    # Same patch set as conftest's patch_db, but pointed at the pooled engine.
    for mod in (
        "app.database",
        "app.models",
        "app.services.user_service",
        "app.services.auth_service",
        "app.services.activity_service",
        "app.services.favorites_service",
        "app.services.turnus_service",
    ):
        monkeypatch.setattr(f"{mod}.get_db_session", Session)
    monkeypatch.setattr("app.database.SessionLocal", Session)
    monkeypatch.setattr("app.utils.sa_session_interface.SessionLocal", Session)

    yield {
        "id": user_id,
        "username": "loaduser",
        "password": password,
        "turnus_set_id": turnus_set_id,
    }

    engine.dispose()


@pytest.fixture()
def threadsafe_app(threadsafe_db, monkeypatch):
    monkeypatch.setattr("app.services.user_service.init_default_admin", lambda: None)

    from app import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["SERVER_NAME"] = "localhost"

    from app.extensions import cache, limiter
    limiter.enabled = False
    cache.clear()

    return flask_app


@pytest.fixture()
def authed_client(threadsafe_app, threadsafe_db):
    """A test client that is already logged in, on a thread-safe DB.

    Only used by the local-only TestConcurrentToggleFavorite class, so it has no
    remote branch.
    """
    client = threadsafe_app.test_client()
    resp = client.post(
        "/login",
        data={"username": threadsafe_db["username"], "password": threadsafe_db["password"]},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Guard against the failure mode this fixture exists to prevent: if the
    # session did not stick, every threaded request below would run
    # unauthenticated and the test would pass while testing nothing.
    assert client.get_cookie("session") is not None, "login did not set a session cookie"

    with client.session_transaction() as sess:
        sess["user_selected_turnus_set"] = threadsafe_db["turnus_set_id"]
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConcurrentLoginPage:
    """Blast the login page with parallel GETs."""

    def test_concurrent_login_page(self, target):
        results = _fire_requests(target, "get", "/login",
                                 n_requests=REQUESTS, workers=WORKERS)
        _check_results(results, threshold_p95=2.0)


class TestConcurrentLoginAttempts:
    """POST wrong credentials concurrently — no 500s allowed."""

    def test_concurrent_login_attempts(self, target):
        payload = {"username": "nobody", "password": "wrongwrong"}
        kw = ({"data": payload} if not is_remote
              else {"data": payload})
        results = _fire_requests(target, "post", "/login",
                                 n_requests=20, workers=WORKERS, **kw)
        _check_results(results, threshold_p95=3.0)


@pytest.mark.skipif(is_remote,
                    reason="toggle_favorite needs auth session — local only")
class TestConcurrentToggleFavorite:
    """Thread-safety check for the toggle_favorite endpoint."""

    def test_concurrent_toggle_favorite(self, authed_client):
        results = _fire_requests(
            authed_client, "post", "/api/toggle_favorite",
            n_requests=20, workers=WORKERS,
            json={"favorite": True, "shift_title": "D2"},
            content_type="application/json",
        )
        # This test used to pass while exercising nothing: it POSTed to
        # "/toggle_favorite" (the real route is under /api), so every request
        # 404'd — and _check_results only forbids 5xx. On top of that the
        # session was silently dropped, so the requests were unauthenticated.
        # Assert the status codes explicitly: 404 means wrong URL, 302 means the
        # session was lost.
        statuses = sorted({s for s, _ in results})
        assert statuses == [200], f"expected all 200, got {statuses}"
        _check_results(results, threshold_p95=2.0)


class TestSustainedMixedTraffic:
    """Waves of mixed GET + POST traffic."""

    def test_sustained_mixed_traffic(self, target):
        all_results = []
        waves = 5
        per_wave = REQUESTS // waves

        for _ in range(waves):
            # GET wave
            all_results.extend(
                _fire_requests(target, "get", "/login",
                               n_requests=per_wave, workers=WORKERS)
            )
            # POST wave
            payload = {"username": "nobody", "password": "wrong"}
            kw = {"data": payload}
            all_results.extend(
                _fire_requests(target, "post", "/login",
                               n_requests=per_wave, workers=WORKERS, **kw)
            )

        _check_results(all_results, threshold_p95=3.0)
