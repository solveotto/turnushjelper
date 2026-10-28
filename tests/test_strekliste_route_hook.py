"""generate-strekliste also parses the PDF into strekliste_dagsverk.

Since the work moved out of the request (see test_strekliste_job.py), the
route only starts it; here the started process is run inline, so the whole
path is exercised: button -> job -> parse -> status the page polls.
"""

import os

import pytest

from app.models import StreklisteDagsverk, TurnusSet
from app.services import strekliste_job
from tests.conftest import login_user

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name="T98", year_identifier="T98")
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def stubbed_generator(monkeypatch, tmp_path):
    """The PNG generator and the double-shift scan are not under test, and the
    started process runs inline instead of being spawned."""
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(strekliste_job.AppConfig, "turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(strekliste_job.AppConfig, "log_dir", str(tmp_path / "logs"))
    paths = {"pdf_exists": True, "pdf_path": os.path.join(FIXTURES, "side1.pdf"),
             "stasjoneringssted": "OSL", "images_dir": str(tmp_path / "png")}
    import app.routes.admin.turnus as route_mod
    monkeypatch.setattr(route_mod.strekliste_generator, "get_paths", lambda v: paths)
    monkeypatch.setattr(strekliste_job.strekliste_generator, "generate_all_images",
                        lambda v, force=False: {"success": True, "generated": [], "skipped": [],
                                                "errors": [], "total": 0})
    monkeypatch.setattr(strekliste_job, "scan_double_shifts", lambda p: {})

    class InlinePopen:
        def __init__(self, cmd, **kwargs):
            year = cmd[cmd.index("--year") + 1]
            strekliste_job.run(year, force="--keep-images" not in cmd, log=lambda *a: None)

    monkeypatch.setattr(strekliste_job.subprocess, "Popen", InlinePopen)


def _job(client, ts_id):
    return client.get(f"/admin/strekliste-progress/{ts_id}").get_json()["data"]["job"]


def test_generate_strekliste_parses_the_pdf_into_the_database(admin_client, turnus_set,
                                                               stubbed_generator, db_session):
    resp = admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}")
    assert resp.status_code == 202
    job = _job(admin_client, turnus_set.id)
    assert job["state"] == "done"
    assert job["result"]["strekliste_dagsverk"] == 7
    assert job["result"]["strekliste_advarsler"] == 0
    assert db_session.query(StreklisteDagsverk).filter_by(turnus_set_id=turnus_set.id).count() == 7


def test_generate_strekliste_reports_a_failed_parse_without_failing(admin_client, turnus_set,
                                                                     stubbed_generator, monkeypatch):
    def boom(turnus_set_id, pdf_path):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(strekliste_job.strekliste_service, "import_strekliste", boom)
    admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}")
    job = _job(admin_client, turnus_set.id)
    assert job["state"] == "done"
    assert "kaputt" in job["result"]["strekliste_error"]
