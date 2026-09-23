"""generate-strekliste also parses the PDF into strekliste_dagsverk."""

import os

import pytest

from app.models import StreklisteDagsverk, TurnusSet
from tests.conftest import login_user

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name="R26", year_identifier="R26")
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def stubbed_generator(monkeypatch, tmp_path):
    """The PNG generator and the double-shift scan are not under test."""
    (tmp_path / "r26").mkdir()
    import app.routes.admin.turnus as mod
    # Patch the AppConfig object the route actually holds, not just
    # config.AppConfig: a test that reloads the config module earlier in the
    # run leaves the route with the old class, and the route's double-shift
    # write would then land in the real turnusdata/ (it did, once).
    monkeypatch.setattr(mod.AppConfig, "turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(mod.strekliste_generator, "get_paths",
                        lambda v: {"pdf_exists": True, "pdf_path": os.path.join(FIXTURES, "side1.pdf")})
    monkeypatch.setattr(mod.strekliste_generator, "generate_all_images",
                        lambda v, force=False: {"success": True, "generated": [], "skipped": [],
                                                "errors": [], "total": 0})
    monkeypatch.setattr(mod, "scan_double_shifts", lambda p: {})
    monkeypatch.setattr(mod.df_utils, "invalidate_turnus_cache", lambda i: None)
    return mod


def test_generate_strekliste_parses_the_pdf_into_the_database(admin_client, turnus_set,
                                                               stubbed_generator, db_session):
    resp = admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["strekliste_dagsverk"] == 7
    assert data["strekliste_advarsler"] == 0
    assert db_session.query(StreklisteDagsverk).filter_by(turnus_set_id=turnus_set.id).count() == 7


def test_generate_strekliste_reports_a_failed_parse_without_failing(admin_client, turnus_set,
                                                                     stubbed_generator, monkeypatch):
    def boom(turnus_set_id, pdf_path):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(stubbed_generator.strekliste_service, "import_strekliste", boom)
    resp = admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}")
    data = resp.get_json()
    assert resp.status_code == 200 and data["status"] == "success"
    assert "kaputt" in data["strekliste_error"]
