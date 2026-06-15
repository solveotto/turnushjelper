"""Tests for admin user administration: full edit/create and member-list upload."""

import io

import pytest
from openpyxl import Workbook

from app.models import DBUser
from app.services.user_service import hash_password
from tests.conftest import login_user


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


def make_xlsx_bytes(rows, header=("Navn", "Medlemsnr")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestEditUser:
    def test_full_field_update_persists(self, admin_client, db_session):
        user = DBUser(
            username="member", password=hash_password("pw"),
            email="member@example.com", email_verified=1,
        )
        db_session.add(user)
        db_session.commit()
        user_id = user.id

        resp = admin_client.post(f"/admin/edit_user/{user_id}", data={
            "username": "member",
            "name": "Nordmann, Ola",
            "email": "member@example.com",
            "medlemsnummer": "60030",
            "rullenummer": "333",
            "stasjoneringssted": "OSLO",
            "ans_dato": "01.01.2020",
            "fodt_dato": "02.02.1990",
            "seniority_nr": "12",
            "is_auth": "",
            "email_verified": "y",
        }, follow_redirects=False)
        assert resp.status_code == 302

        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=user_id).first()
        assert updated.name == "Nordmann, Ola"
        assert updated.medlemsnummer == "60030"
        assert updated.rullenummer == "333"
        assert updated.stasjoneringssted == "OSLO"
        assert updated.ans_dato == "01.01.2020"
        assert updated.fodt_dato == "02.02.1990"
        assert updated.seniority_nr == 12
        assert updated.email_verified == 1
        assert updated.is_stub == 0

    def test_invalid_date_format_rejected(self, admin_client, db_session):
        user = DBUser(username="member2", password=hash_password("pw"))
        db_session.add(user)
        db_session.commit()

        resp = admin_client.post(f"/admin/edit_user/{user.id}", data={
            "username": "member2",
            "ans_dato": "2020-01-01",
        })
        assert resp.status_code == 200
        assert "DD.MM.YYYY".encode() in resp.data

    def test_requires_admin(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get(f"/admin/edit_user/{sample_user['id']}")
        assert resp.status_code in (302, 403)


class TestCreateUser:
    def test_create_full_user(self, admin_client, db_session):
        resp = admin_client.post("/admin/create_user", data={
            "username": "nyansatt",
            "password": "passord123",
            "confirm_password": "passord123",
            "email": "ny@example.com",
            "name": "Ny, Ansatt",
            "medlemsnummer": "60031",
        }, follow_redirects=False)
        assert resp.status_code == 302

        user = db_session.query(DBUser).filter_by(username="nyansatt").first()
        assert user is not None
        assert user.medlemsnummer == "60031"
        assert user.is_stub == 0
        assert user.email_verified == 1

    def test_create_stub(self, admin_client, db_session):
        resp = admin_client.post("/admin/create_user", data={
            "is_stub": "y",
            "name": "Stub, Person",
            "medlemsnummer": "60032",
        }, follow_redirects=False)
        assert resp.status_code == 302

        stub = db_session.query(DBUser).filter_by(medlemsnummer="60032").first()
        assert stub is not None
        assert stub.username == "__stub_m60032"
        assert stub.is_stub == 1

    def test_stub_without_medlemsnummer_rejected(self, admin_client, db_session):
        resp = admin_client.post("/admin/create_user", data={
            "is_stub": "y",
            "name": "Stub, Person",
        })
        assert resp.status_code == 200
        assert "NLF-medlemsnummer".encode() in resp.data
        assert db_session.query(DBUser).filter_by(name="Stub, Person").first() is None

    def test_full_user_without_credentials_rejected(self, admin_client, db_session):
        resp = admin_client.post("/admin/create_user", data={
            "name": "Mangler, Alt",
        })
        assert resp.status_code == 200
        assert db_session.query(DBUser).filter_by(name="Mangler, Alt").first() is None


class TestUploadMemberExcel:
    @pytest.fixture(autouse=True)
    def excel_path(self, tmp_path, monkeypatch):
        path = tmp_path / "medlemsliste.xlsx"
        monkeypatch.setattr(
            "app.routes.admin.employees._member_excel_path", lambda: str(path)
        )
        return path

    def test_upload_imports_members(self, admin_client, db_session):
        buf = make_xlsx_bytes([
            ("Nordmann, Ola", 60040),
            ("Hansen, Kari", 60041),
        ])
        resp = admin_client.post(
            "/admin/upload-medlemsliste",
            data={"excel_file": (buf, "medlemmer.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert (
            db_session.query(DBUser).filter_by(medlemsnummer="60040").count() == 1
        )
        assert (
            db_session.query(DBUser).filter_by(medlemsnummer="60041").count() == 1
        )

    def test_wrong_extension_rejected(self, admin_client, db_session):
        resp = admin_client.post(
            "/admin/upload-medlemsliste",
            data={"excel_file": (io.BytesIO(b"not excel"), "medlemmer.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert "Kun Excel-filer".encode() in resp.data
        assert db_session.query(DBUser).filter(
            DBUser.medlemsnummer.isnot(None)
        ).count() == 0

    def test_employees_page_shows_import_report(self, admin_client, db_session):
        buf = make_xlsx_bytes([("Nordmann, Ola", 60043)])
        resp = admin_client.post(
            "/admin/upload-medlemsliste",
            data={"excel_file": (buf, "m.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Importrapport".encode() in resp.data
        assert "NLF medlemsliste".encode() in resp.data

    def test_employees_page_renders(self, admin_client):
        resp = admin_client.get("/admin/employees")
        assert resp.status_code == 200
        assert "NLF medlemsliste".encode() in resp.data

    def test_upload_requires_admin(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        buf = make_xlsx_bytes([("A, B", 60042)])
        resp = client.post(
            "/admin/upload-medlemsliste",
            data={"excel_file": (buf, "m.xlsx")},
            content_type="multipart/form-data",
        )
        assert resp.status_code in (302, 403)
