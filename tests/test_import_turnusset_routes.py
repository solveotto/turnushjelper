"""Route tests for the timeskjema import flow (create, review, approve, cancel).

Uses the committed timeskjema fixture as upload payload. The PDF verification
scraper is faked at its definition site (it is imported function-locally in the
route), fed with data derived from the same fixture so diffs are controlled.
"""

import copy
import io
import json
import os

import pytest

from app.utils.timeskjema_parser import parse_timeskjema
from tests.conftest import login_user

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "timeskjema_sample.xls")


def fixture_bytes():
    with open(FIXTURE, "rb") as f:
        return f.read()


@pytest.fixture()
def import_env(app, monkeypatch, tmp_path):
    """Isolate all filesystem side effects: instance dir and static dir."""
    instance_dir = tmp_path / "instance"
    static_dir = tmp_path / "static"
    instance_dir.mkdir()
    static_dir.mkdir()
    app.instance_path = str(instance_dir)
    monkeypatch.setattr("config.AppConfig.static_dir", str(static_dir))
    return {"instance": instance_dir, "static": static_dir}


class FakeScraper:
    """Stand-in for ShiftScraper in the verification path."""

    pdf_turnuser = []  # set per test via monkeypatch on the class attribute

    def __init__(self):
        self.turnuser = []

    def scrape_pdf(self, pdf_path, year_id=None):
        self.turnuser = copy.deepcopy(type(self).pdf_turnuser)


def upload(client, data_bytes, filename="R26 endelig.xls", verify_pdf=None, year_id="R26"):
    form = {
        "name": "Testsett R26",
        "year_identifier": year_id,
        "schedule_file": (io.BytesIO(data_bytes), filename),
    }
    if verify_pdf is not None:
        form["verify_pdf_file"] = (io.BytesIO(verify_pdf), "verify.pdf")
    return client.post(
        "/admin/create-turnus-set",
        data=form,
        content_type="multipart/form-data",
        follow_redirects=True,
    )


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


class TestTimeskjemaUpload:
    def test_happy_path_creates_set(self, admin_client, import_env):
        resp = upload(admin_client, fixture_bytes())
        assert resp.status_code == 200
        assert "Turnussett R26 opprettet".encode() in resp.data

        from app.services import turnus_service

        turnus_set = turnus_service.get_turnus_set_by_year("R26")
        assert turnus_set is not None

        version_dir = import_env["static"] / "turnusfiler" / "r26"
        schedule = json.load(open(version_dir / "turnus_schedule_R26.json"))
        assert len(schedule) == 2
        assert (version_dir / "turnuser_R26.xls").exists()
        assert (version_dir / "turnus_stats_R26.json").exists()
        # Nothing left pending
        assert not (import_env["instance"] / "pending_import" / "R26").exists()

    def test_unknown_format_refused(self, admin_client, import_env):
        resp = upload(admin_client, b"dette er hverken timeskjema eller pdf")
        assert "Ukjent filformat".encode() in resp.data

        from app.services import turnus_service

        assert turnus_service.get_turnus_set_by_year("R26") is None

    def test_parse_error_flashes_validation_failure(self, admin_client, import_env):
        broken = fixture_bytes().replace(b"Tirsdag\t3007", b"Mandag\t3007", 1)
        resp = upload(admin_client, broken)
        assert "Validering feilet".encode() in resp.data

    def test_pdf_upload_routes_to_scraper_path(self, admin_client, import_env):
        # A minimal (unscrapable) PDF must be routed to the PDF path, not
        # refused as unknown format.
        resp = upload(admin_client, b"%PDF-1.4 not really a pdf", filename="t.pdf")
        assert "Ukjent filformat".encode() not in resp.data


class TestVerificationFlow:
    def test_no_diffs_finalizes_with_enrichment(self, admin_client, import_env, monkeypatch):
        pdf_data = copy.deepcopy(parse_timeskjema(FIXTURE).turnuser)
        pdf_data[0]["OSL_01"][1][1]["dagsverk"] = "3006_SKNO"
        monkeypatch.setattr(FakeScraper, "pdf_turnuser", pdf_data)
        monkeypatch.setattr("app.utils.pdf.shiftscraper.ShiftScraper", FakeScraper)

        resp = upload(admin_client, fixture_bytes(), verify_pdf=b"%PDF-1.4 fake")
        assert "ingen avvik".encode() in resp.data
        assert "Turnussett R26 opprettet".encode() in resp.data

        version_dir = import_env["static"] / "turnusfiler" / "r26"
        schedule = json.load(open(version_dir / "turnus_schedule_R26.json"))
        assert schedule[0]["OSL_01"]["1"]["1"]["dagsverk"] == "3006_SKNO"
        # Verification PDF stored for later refresh enrichment
        assert (version_dir / "pdf" / "turnuser_R26.pdf").exists()

    def test_diffs_stage_for_review(self, admin_client, import_env, monkeypatch):
        pdf_data = copy.deepcopy(parse_timeskjema(FIXTURE).turnuser)
        pdf_data[0]["OSL_01"][1][1]["tid"] = ["13:14", "19:01"]
        monkeypatch.setattr(FakeScraper, "pdf_turnuser", pdf_data)
        monkeypatch.setattr("app.utils.pdf.shiftscraper.ShiftScraper", FakeScraper)

        resp = upload(admin_client, fixture_bytes(), verify_pdf=b"%PDF-1.4 fake")
        assert "avvik".encode() in resp.data
        assert "Godkjenn import av R26".encode() in resp.data  # review page

        from app.services import turnus_service

        assert turnus_service.get_turnus_set_by_year("R26") is None  # nothing live
        pending = import_env["instance"] / "pending_import" / "R26"
        assert (pending / "pending_import.json").exists()
        assert (pending / "pending_diff.json").exists()
        assert (pending / "pending_meta.json").exists()
        assert (pending / "turnuser_R26.xls").exists()
        assert (pending / "turnuser_R26.pdf").exists()
        # Staged data is NOT inside the public static dir
        assert not str(pending).startswith(str(import_env["static"]))

    def test_approve_finalizes(self, admin_client, import_env, monkeypatch):
        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)

        resp = admin_client.post(
            "/admin/import-turnusset/approve/R26", follow_redirects=True
        )
        assert "Turnussett R26 opprettet".encode() in resp.data

        from app.services import turnus_service

        assert turnus_service.get_turnus_set_by_year("R26") is not None
        assert not (import_env["instance"] / "pending_import" / "R26").exists()
        version_dir = import_env["static"] / "turnusfiler" / "r26"
        assert (version_dir / "turnus_schedule_R26.json").exists()

    def test_cancel_discards(self, admin_client, import_env, monkeypatch):
        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)

        resp = admin_client.post(
            "/admin/import-turnusset/cancel/R26", follow_redirects=True
        )
        assert "avbrutt".encode() in resp.data

        from app.services import turnus_service

        assert turnus_service.get_turnus_set_by_year("R26") is None
        assert not (import_env["instance"] / "pending_import" / "R26").exists()

    def test_review_page_shows_diff(self, admin_client, import_env, monkeypatch):
        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)

        resp = admin_client.get("/admin/import-turnusset/review/R26")
        assert resp.status_code == 200
        assert b"13:14" in resp.data  # the PDF-side value
        assert b"OSL_01" in resp.data

    def test_review_missing_staging_redirects(self, admin_client, import_env):
        resp = admin_client.get(
            "/admin/import-turnusset/review/R99", follow_redirects=True
        )
        assert "Ingen ventende import".encode() in resp.data

    def test_pending_indicator_on_manage_page(self, admin_client, import_env, monkeypatch):
        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)

        resp = admin_client.get("/admin/turnus-sets")
        assert "venter på godkjenning".encode() in resp.data

    def test_new_upload_overwrites_pending(self, admin_client, import_env, monkeypatch):
        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)

        meta_path = (
            import_env["instance"] / "pending_import" / "R26" / "pending_meta.json"
        )
        first_staged_at = json.load(open(meta_path))["staged_at"]

        self.test_diffs_stage_for_review(admin_client, import_env, monkeypatch)
        assert json.load(open(meta_path))["staged_at"] >= first_staged_at
