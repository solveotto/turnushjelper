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
