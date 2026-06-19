"""Tests for self-registration with NLF-medlemsnummer and the check API."""

import pytest

from app.models import DBUser
from app.services.user_service import hash_password


@pytest.fixture()
def member_stub(patch_db, db_session):
    """An unactivated stub from the member list import."""
    stub = DBUser(
        username="__stub_m60011",
        password=hash_password("unusable"),
        name="Nordmann, Ola",
        medlemsnummer="60011",
        is_stub=1,
        email_verified=0,
    )
    db_session.add(stub)
    db_session.commit()
    return {"id": stub.id, "medlemsnummer": "60011"}


@pytest.fixture()
def no_email(monkeypatch):
    """Capture outgoing verification emails instead of sending them."""
    sent = []
    monkeypatch.setattr(
        "app.utils.email_utils.send_verification_email",
        lambda email, token: sent.append((email, token)) or True,
    )
    return sent


class TestRegister:
    def test_valid_medlemsnummer_activates_stub(
        self, client, member_stub, db_session, no_email
    ):
        resp = client.post("/register", data={
            "username": "olanordmann",
            "medlemsnummer": "60011",
            "rullenummer": "12345",
            "email": "ola@example.com",
            "password": "passord123",
            "confirm_password": "passord123",
        })
        assert resp.status_code == 200
        db_session.expire_all()
        user = db_session.query(DBUser).filter_by(id=member_stub["id"]).first()
        assert user.is_stub == 0
        assert user.username == "olanordmann"
        assert user.email == "ola@example.com"
        assert len(no_email) == 1

    def test_unknown_medlemsnummer_rejected(self, client, patch_db, db_session, no_email):
        resp = client.post("/register", data={
            "username": "hacker",
            "medlemsnummer": "99999",
            "email": "hacker@example.com",
            "password": "passord123",
            "confirm_password": "passord123",
        })
        assert resp.status_code == 200
        assert "ikke autorisert".encode() in resp.data
        assert db_session.query(DBUser).filter_by(username="hacker").first() is None
        assert no_email == []

    def test_already_registered_medlemsnummer_rejected(
        self, client, member_stub, db_session, no_email
    ):
        user = db_session.query(DBUser).filter_by(id=member_stub["id"]).first()
        user.is_stub = 0
        user.username = "taken"
        user.email = "taken@example.com"
        db_session.commit()

        resp = client.post("/register", data={
            "username": "someoneelse",
            "medlemsnummer": "60011",
            "email": "other@example.com",
            "password": "passord123",
            "confirm_password": "passord123",
        })
        assert resp.status_code == 200
        assert "ikke autorisert".encode() in resp.data
        assert no_email == []


class TestCheckMedlemsnummerApi:
    def test_valid_stub_found(self, client, member_stub):
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=60011")
        data = resp.get_json()
        assert data["found"] is True
        assert "rullenummer" in data

    def test_already_registered(self, client, member_stub, db_session):
        user = db_session.query(DBUser).filter_by(id=member_stub["id"]).first()
        user.is_stub = 0
        db_session.commit()
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=60011")
        assert resp.get_json() == {"found": False, "reason": "already_registered"}

    def test_unknown_number(self, client, patch_db):
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=11111")
        assert resp.get_json() == {"found": False, "reason": "not_authorized"}

    def test_empty_number(self, client, patch_db):
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=")
        assert resp.get_json() == {"found": False, "reason": "not_authorized"}
