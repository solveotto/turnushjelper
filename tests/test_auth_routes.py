"""Tests for auth routes (login / logout)."""

from tests.conftest import login_user


class TestLoginPage:
    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Logg inn" in resp.data


class TestLoginFlow:
    def test_login_success(self, client, sample_user):
        resp = client.post(
            "/login",
            data={"username": sample_user["username"], "password": sample_user["password"]},
            follow_redirects=False,
        )
        # Successful login should redirect (302)
        assert resp.status_code == 302

    def test_login_wrong_password(self, client, sample_user):
        resp = client.post(
            "/login",
            data={"username": sample_user["username"], "password": "wrongpass"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "mislyktes" in resp.data.decode()


class TestLoginRateLimit:
    def test_login_post_rate_limited_after_10_attempts(self, client, sample_user):
        # The limiter is disabled suite-wide via RATELIMIT_ENABLED=false in
        # conftest; enable it just for this test and clear its (process-wide,
        # in-memory) counters on both sides so no state leaks between tests.
        from app.extensions import limiter

        limiter.reset()
        limiter.enabled = True
        try:
            for _ in range(10):
                resp = client.post(
                    "/login",
                    data={"username": sample_user["username"], "password": "wrongpass"},
                )
                assert resp.status_code == 200
            resp = client.post(
                "/login",
                data={"username": sample_user["username"], "password": "wrongpass"},
            )
            assert resp.status_code == 429
        finally:
            limiter.enabled = False
            limiter.reset()

    def test_login_get_not_rate_limited(self, client):
        from app.extensions import limiter

        limiter.reset()
        limiter.enabled = True
        try:
            for _ in range(15):
                resp = client.get("/login")
                assert resp.status_code == 200
        finally:
            limiter.enabled = False
            limiter.reset()
