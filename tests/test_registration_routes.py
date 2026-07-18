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
    def test_valid_stub_found_no_pii_echo(self, client, member_stub):
        """Unauthenticated endpoint must never echo name or rullenummer."""
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=60011")
        data = resp.get_json()
        assert data == {"found": True, "has_rullenummer": False}

    def test_stub_with_rullenummer_reports_boolean_only(
        self, client, member_stub, db_session
    ):
        user = db_session.query(DBUser).filter_by(id=member_stub["id"]).first()
        user.rullenummer = "12345"
        db_session.commit()
        resp = client.get("/api/check-medlemsnummer?medlemsnummer=60011")
        data = resp.get_json()
        assert data == {"found": True, "has_rullenummer": True}

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


class TestCheckRullenummerApi:
    """The endpoint is unauthenticated: it must only return booleans, never
    the seniority-list name/seniority_nr/ans_dato (employee enumeration)."""

    @pytest.fixture()
    def seniority_user(self, patch_db, db_session):
        user = DBUser(
            username="__stub_m70022",
            password=hash_password("unusable"),
            name="Nordmann, Ola",
            medlemsnummer="70022",
            rullenummer="12345",
            seniority_nr=7,
            ans_dato="01.01.2010",
            is_stub=1,
            email_verified=0,
        )
        db_session.add(user)
        db_session.commit()
        return {"id": user.id, "rullenummer": "12345"}

    def test_found_returns_boolean_only(self, client, seniority_user):
        resp = client.get("/api/check-rullenummer?rullenummer=12345")
        assert resp.get_json() == {"found": True}

    def test_unknown_rullenummer(self, client, patch_db):
        resp = client.get("/api/check-rullenummer?rullenummer=99999")
        assert resp.get_json() == {"found": False}

    def test_name_match_via_medlemsnummer_true(
        self, client, seniority_user, member_stub, db_session
    ):
        # member_stub (60011) is also "Nordmann, Ola" → names share words.
        resp = client.get(
            "/api/check-rullenummer?rullenummer=12345&medlemsnummer=60011"
        )
        assert resp.get_json() == {"found": True, "name_match": True}

    def test_name_match_via_medlemsnummer_false(
        self, client, seniority_user, member_stub, db_session
    ):
        stub = db_session.query(DBUser).filter_by(id=member_stub["id"]).first()
        stub.name = "Hansen, Kari"
        db_session.commit()
        resp = client.get(
            "/api/check-rullenummer?rullenummer=12345&medlemsnummer=60011"
        )
        assert resp.get_json() == {"found": True, "name_match": False}

    def test_unknown_medlemsnummer_gives_no_name_match(
        self, client, seniority_user
    ):
        resp = client.get(
            "/api/check-rullenummer?rullenummer=12345&medlemsnummer=11111"
        )
        assert resp.get_json() == {"found": True}

    def test_legacy_name_param_is_ignored(self, client, seniority_user):
        """The old client sent ?name=...; it must no longer produce a match
        (nor echo anything)."""
        resp = client.get(
            "/api/check-rullenummer?rullenummer=12345&name=Ola%20Nordmann"
        )
        assert resp.get_json() == {"found": True}
