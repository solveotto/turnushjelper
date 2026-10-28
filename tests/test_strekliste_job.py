"""Strekliste generation runs as its own process, never inside a request.

The admin "Generer" rendered images, scanned double shifts and parsed the
duties inside one HTTP request. On the servers (sync gunicorn workers,
--timeout 300) the worker was killed partway: at 30 s for r26 before the
timeout was raised, and twice on 2026-10-27 for the 159-page R27 "ALLE" PDF.
The button now starts scripts/generate_strekliste.py and the page polls a
status file that either worker can read.
"""

import fcntl
import json
import os
import time

import pytest

from app.models import TurnusSet
from app.services import strekliste_job
from tests.conftest import login_user

FAKE_YEAR = "T99"
VERSION = FAKE_YEAR.lower()
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


@pytest.fixture(autouse=True)
def data_store(tmp_path, monkeypatch):
    """Never touch the real turnusdata/."""
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(strekliste_job.AppConfig, "turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(strekliste_job.AppConfig, "log_dir", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()
    streklister = tmp_path / VERSION / "streklister"
    streklister.mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def popen_calls(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))
            self.pid = 4242

    monkeypatch.setattr(strekliste_job.subprocess, "Popen", FakePopen)
    return calls


@pytest.fixture()
def held_lock(data_store):
    """Another generation holding the lock, as a live process would."""
    path = data_store / VERSION / "streklister" / strekliste_job.LOCK_NAME
    f = open(path, "w")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    yield
    f.close()


def _write_status(data_store, status):
    path = data_store / VERSION / "streklister" / strekliste_job.STATUS_NAME
    path.write_text(json.dumps(status))


class TestStart:
    def test_spawns_the_cli_in_its_own_session_and_marks_the_run_started(self, popen_calls):
        assert strekliste_job.start(FAKE_YEAR, force=True) is True

        (cmd, kwargs), = popen_calls
        assert cmd[1].endswith(os.path.join("scripts", "generate_strekliste.py"))
        assert cmd[2:] == ["--year", FAKE_YEAR]
        assert kwargs["start_new_session"] is True
        status = strekliste_job.read_status(VERSION)
        assert (status["state"], status["step"]) == ("running", "starter")

    def test_without_force_existing_images_are_kept(self, popen_calls):
        strekliste_job.start(FAKE_YEAR, force=False)
        (cmd, _), = popen_calls
        assert "--keep-images" in cmd

    def test_refuses_while_a_run_holds_the_lock(self, popen_calls, held_lock):
        assert strekliste_job.start(FAKE_YEAR, force=True) is False
        assert popen_calls == []


class TestReadStatus:
    def test_no_run_yet(self):
        assert strekliste_job.read_status(VERSION) is None

    def test_a_run_whose_process_died_is_reported_failed(self, data_store):
        _write_status(data_store, {"state": "running", "step": "bilder", "pid": 999999,
                                   "started_ts": time.time()})
        status = strekliste_job.read_status(VERSION)
        assert status["state"] == "failed"
        assert "stoppet" in status["error"]

    def test_a_run_that_is_still_starting_gets_a_grace_period(self, data_store):
        _write_status(data_store, {"state": "running", "step": "starter", "pid": None,
                                   "started_ts": time.time()})
        assert strekliste_job.read_status(VERSION)["state"] == "running"

    def test_a_live_run_is_running(self, data_store, held_lock):
        _write_status(data_store, {"state": "running", "step": "bilder", "pid": 4242,
                                   "started_ts": time.time() - 600})
        assert strekliste_job.read_status(VERSION)["state"] == "running"


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name=FAKE_YEAR, year_identifier=FAKE_YEAR)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def stubbed_steps(monkeypatch):
    """Images and the double-shift scan are not under test; the parse is real."""
    gen = strekliste_job.strekliste_generator
    monkeypatch.setattr(gen, "get_paths", lambda v: {
        "pdf_exists": True, "pdf_path": os.path.join(FIXTURES, "side1.pdf"),
        "stasjoneringssted": "OSL"})
    monkeypatch.setattr(gen, "generate_all_images", lambda v, force=False: {
        "success": True, "generated": ["1"] * 5, "skipped": [], "errors": [], "total": 5})
    monkeypatch.setattr(strekliste_job, "scan_double_shifts",
                        lambda p: {"dobbelt_tur": [{"first_shift": "1", "second_shift": "2"}],
                                   "delt_dagsverk": []})


class TestRun:
    def test_runs_every_step_and_reports_done(self, turnus_set, stubbed_steps, data_store):
        assert strekliste_job.run(FAKE_YEAR, force=True, log=lambda *a: None) == 0

        status = strekliste_job.read_status(VERSION)
        assert status["state"] == "done"
        result = status["result"]
        assert (result["generated"], result["double_shift_count"]) == (5, 1)
        assert (result["strekliste_dagsverk"], result["strekliste_advarsler"]) == (7, 0)
        written = json.loads((data_store / VERSION / f"double_shifts_{VERSION}.json").read_text())
        assert written["dobbelt_tur"] == [{"first_shift": "1", "second_shift": "2"}]

    def test_a_failed_parse_is_reported_without_failing_the_run(self, turnus_set, stubbed_steps,
                                                               monkeypatch):
        def boom(turnus_set_id, pdf_path):
            raise RuntimeError("kaputt")
        monkeypatch.setattr(strekliste_job.strekliste_service, "import_strekliste", boom)

        assert strekliste_job.run(FAKE_YEAR, force=True, log=lambda *a: None) == 0
        status = strekliste_job.read_status(VERSION)
        assert status["state"] == "done"
        assert "kaputt" in status["result"]["strekliste_error"]

    def test_failed_image_generation_fails_the_run(self, turnus_set, stubbed_steps, monkeypatch):
        monkeypatch.setattr(strekliste_job.strekliste_generator, "generate_all_images",
                            lambda v, force=False: {"success": False, "error": "PDF not found"})
        assert strekliste_job.run(FAKE_YEAR, force=True, log=lambda *a: None) == 1
        status = strekliste_job.read_status(VERSION)
        assert status["state"] == "failed"
        assert "PDF not found" in status["error"]

    def test_a_second_run_leaves_the_running_one_alone(self, turnus_set, stubbed_steps,
                                                       data_store, held_lock, monkeypatch):
        monkeypatch.setattr(strekliste_job, "LOCK_WAIT_SECONDS", 0.2)
        _write_status(data_store, {"state": "running", "step": "bilder", "pid": 4242,
                                   "started_ts": time.time()})
        assert strekliste_job.run(FAKE_YEAR, force=True, log=lambda *a: None) == 3
        assert strekliste_job.read_status(VERSION)["step"] == "bilder"


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


class TestRoutes:
    @pytest.fixture(autouse=True)
    def pdf_present(self, monkeypatch, data_store):
        import app.routes.admin.turnus as mod
        monkeypatch.setattr(mod.strekliste_generator, "get_paths",
                            lambda v: {"pdf_exists": True, "pdf_path": "x.pdf",
                                       "stasjoneringssted": "OSL",
                                       "images_dir": str(data_store / "png"),
                                       "images_dir_exists": False})

    def test_generate_starts_the_job_and_returns_at_once(self, admin_client, turnus_set,
                                                         popen_calls):
        resp = admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}",
                                 json={"force": True})
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "started"
        assert len(popen_calls) == 1

    def test_generate_refuses_while_running(self, admin_client, turnus_set, popen_calls,
                                            held_lock):
        resp = admin_client.post(f"/admin/generate-strekliste/{turnus_set.id}",
                                 json={"force": True})
        assert resp.status_code == 409
        assert popen_calls == []

    def test_status_reports_a_running_job(self, admin_client, turnus_set, data_store, held_lock):
        _write_status(data_store, {"state": "running", "step": "bilder", "pid": 4242,
                                   "started_ts": time.time()})
        data = admin_client.get(f"/admin/strekliste-status/{turnus_set.id}").get_json()
        assert data["data"]["job"]["state"] == "running"

    def test_progress_includes_the_job_status(self, admin_client, turnus_set, data_store):
        _write_status(data_store, {"state": "done", "step": "ferdig", "result": {"generated": 3}})
        data = admin_client.get(f"/admin/strekliste-progress/{turnus_set.id}").get_json()
        assert data["data"]["job"]["state"] == "done"
        assert data["data"]["job"]["result"]["generated"] == 3
