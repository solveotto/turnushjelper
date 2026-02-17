"""
Load / stress tests for the Shift Rotation Organizer.

Two modes:
  Local (default)  — Flask test client + ThreadPoolExecutor
  Remote           — real HTTP via ``requests``

Usage:
  pytest tests/test_load.py -v                       # local
  LOAD_TEST_URL=https://x.pythonanywhere.com pytest tests/test_load.py -v  # remote
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


@pytest.fixture()
def authed_client(client, sample_user):
    """A Flask test client that is already logged in."""
    client.post(
        "/login",
        data={"username": sample_user["username"],
              "password": sample_user["password"]},
        follow_redirects=True,
    )
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
            authed_client, "post", "/toggle_favorite",
            n_requests=20, workers=WORKERS,
            json={"favorite": True, "shift_title": "D2"},
            content_type="application/json",
        )
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
