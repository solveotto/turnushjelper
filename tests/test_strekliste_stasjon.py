"""A strekliste PDF is split by stasjoneringssted at upload.

The employer's "ALLE" edition holds every depot (159 pages, 13 stations for
R27). Generating from it on staging rendered 960 images and parsed 1 084
duties, ran past gunicorn's 300 s timeout twice, and would have put every
depot's duties into the Oslo set. Upload now keeps one station's pages as
``{version}_streker_{STED}.pdf`` and the original as ``{version}_streker_alle.pdf``.
"""

import io
import os

import fitz
import pytest

from app.models import TurnusSet
from app.utils.pdf import strekliste_generator as sg
from tests.conftest import login_user

FAKE_YEAR = "T99"
VERSION = FAKE_YEAR.lower()


def _pdf_bytes(stations):
    """A PDF with one page per entry, each headed like the real streklister."""
    doc = fitz.open()
    for i, sted in enumerate(stations):
        page = doc.new_page()
        header = f"Stasjoneringssted: {sted} Kommentarer:" if sted else "Ingen overskrift"
        page.insert_text((50, 50), header)
        page.insert_text((50, 80), f"side {i}")
        page.insert_text((50, 110), "Gjø")  # non-ASCII survives the split
    data = doc.tobytes()
    doc.close()
    return data


def _write_pdf(path, stations):
    with open(path, "wb") as f:
        f.write(_pdf_bytes(stations))
    return str(path)


def _page_texts(path):
    with fitz.open(path) as doc:
        return [page.get_text() for page in doc]


class _Upload:
    """Stands in for werkzeug's FileStorage: only .save() is used."""

    def __init__(self, data):
        self.data = data

    def save(self, dst):
        with open(dst, "wb") as f:
            f.write(self.data)


@pytest.fixture(autouse=True)
def data_store(tmp_path, monkeypatch):
    """Never touch the real turnusdata/."""
    import app.routes.admin.turnus as route_mod
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(sg.AppConfig, "turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(route_mod.AppConfig, "turnusfiler_dir", str(tmp_path))
    streklister = tmp_path / VERSION / "streklister"
    streklister.mkdir(parents=True)
    return streklister


class TestFindStations:
    def test_groups_pages_by_station_in_first_seen_order(self, tmp_path):
        pdf = _write_pdf(tmp_path / "x.pdf", ["SKN", "SKN", "OSL", "OSL", "OSL", "GJØ"])
        assert sg.find_stations(pdf) == {"SKN": [0, 1], "OSL": [2, 3, 4], "GJØ": [5]}

    def test_pages_without_a_header_are_left_out(self, tmp_path):
        pdf = _write_pdf(tmp_path / "x.pdf", ["OSL", None, "OSL"])
        assert sg.find_stations(pdf) == {"OSL": [0, 2]}

    def test_no_headers_at_all_gives_nothing(self, tmp_path):
        pdf = _write_pdf(tmp_path / "x.pdf", [None, None])
        assert sg.find_stations(pdf) == {}


class TestGetPaths:
    def test_prefers_the_station_pdf(self, data_store):
        _write_pdf(data_store / f"{VERSION}_streker.pdf", ["OSL"])
        _write_pdf(data_store / f"{VERSION}_streker_OSL.pdf", ["OSL"])
        paths = sg.get_paths(VERSION)
        assert paths["pdf_path"] == str(data_store / f"{VERSION}_streker_OSL.pdf")
        assert paths["stasjoneringssted"] == "OSL"
        assert paths["pdf_exists"]

    def test_falls_back_to_the_unsplit_name(self, data_store):
        _write_pdf(data_store / f"{VERSION}_streker.pdf", ["OSL"])
        paths = sg.get_paths(VERSION)
        assert paths["pdf_path"] == str(data_store / f"{VERSION}_streker.pdf")
        assert paths["stasjoneringssted"] is None

    def test_the_original_and_a_pending_upload_are_never_read(self, data_store):
        _write_pdf(data_store / f"{VERSION}_streker_alle.pdf", ["OSL", "SKN"])
        _write_pdf(data_store / f"{VERSION}_streker_opplastet.pdf", ["OSL", "SKN"])
        paths = sg.get_paths(VERSION)
        assert paths["pdf_path"] == str(data_store / f"{VERSION}_streker.pdf")
        assert not paths["pdf_exists"]


class TestUpload:
    def test_mixed_pdf_keeps_only_the_chosen_station(self, data_store):
        staged = sg.stage_uploaded_pdf(_Upload(_pdf_bytes(["SKN", "OSL", "OSL", "DRM"])), VERSION)
        assert staged == {"success": True, "stations": {"SKN": 1, "OSL": 2, "DRM": 1}}

        result = sg.finish_uploaded_pdf(VERSION, "OSL")

        assert result["success"]
        assert (result["pages"], result["total_pages"]) == (2, 4)
        assert result["other_stations"] == ["SKN", "DRM"]
        texts = _page_texts(data_store / f"{VERSION}_streker_OSL.pdf")
        assert ["side 1" in texts[0], "side 2" in texts[1]] == [True, True]
        assert "Gjø" in texts[0]
        assert len(_page_texts(data_store / f"{VERSION}_streker_alle.pdf")) == 4
        assert not (data_store / f"{VERSION}_streker_opplastet.pdf").exists()

    def test_choosing_a_station_replaces_an_earlier_station_pdf(self, data_store):
        _write_pdf(data_store / f"{VERSION}_streker_SKN.pdf", ["SKN"])
        sg.stage_uploaded_pdf(_Upload(_pdf_bytes(["SKN", "OSL"])), VERSION)
        sg.finish_uploaded_pdf(VERSION, "OSL")
        assert not (data_store / f"{VERSION}_streker_SKN.pdf").exists()
        assert sg.get_paths(VERSION)["stasjoneringssted"] == "OSL"

    def test_a_station_not_in_the_upload_is_refused(self, data_store):
        sg.stage_uploaded_pdf(_Upload(_pdf_bytes(["SKN", "OSL"])), VERSION)
        result = sg.finish_uploaded_pdf(VERSION, "DRM")
        assert not result["success"]
        assert not (data_store / f"{VERSION}_streker_DRM.pdf").exists()
        assert (data_store / f"{VERSION}_streker_opplastet.pdf").exists()

    def test_pdf_without_station_headers_is_refused_and_old_file_kept(self, data_store):
        _write_pdf(data_store / f"{VERSION}_streker_OSL.pdf", ["OSL"])
        before = (data_store / f"{VERSION}_streker_OSL.pdf").read_bytes()

        staged = sg.stage_uploaded_pdf(_Upload(_pdf_bytes([None, None])), VERSION)

        assert not staged["success"]
        assert (data_store / f"{VERSION}_streker_OSL.pdf").read_bytes() == before
        assert not (data_store / f"{VERSION}_streker_opplastet.pdf").exists()

    def test_cancel_drops_the_pending_upload(self, data_store):
        sg.stage_uploaded_pdf(_Upload(_pdf_bytes(["SKN", "OSL"])), VERSION)
        sg.discard_uploaded_pdf(VERSION)
        assert not (data_store / f"{VERSION}_streker_opplastet.pdf").exists()


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name=FAKE_YEAR, year_identifier=FAKE_YEAR)
    db_session.add(ts)
    db_session.commit()
    return ts


def _post_upload(client, ts_id, data):
    return client.post(
        f"/admin/upload-strekliste/{ts_id}",
        data={"pdf_file": (io.BytesIO(data), "streker.pdf")},
        content_type="multipart/form-data",
    )


class TestUploadRoutes:
    def test_mixed_upload_asks_which_station_with_osl_preselected(self, admin_client, turnus_set):
        resp = _post_upload(admin_client, turnus_set.id, _pdf_bytes(["SKN", "OSL", "OSL"]))
        assert resp.status_code == 302
        assert f"/admin/strekliste-stasjon/{turnus_set.id}" in resp.headers["Location"]

        page = admin_client.get(f"/admin/strekliste-stasjon/{turnus_set.id}").get_data(as_text=True)
        assert "SKN" in page and "OSL" in page
        assert 'value="OSL" checked' in page

    def test_choosing_a_station_saves_it(self, admin_client, turnus_set, data_store):
        _post_upload(admin_client, turnus_set.id, _pdf_bytes(["SKN", "OSL", "OSL"]))
        resp = admin_client.post(f"/admin/strekliste-stasjon/{turnus_set.id}",
                                 data={"stasjoneringssted": "OSL", "lagre": "Lagre"})
        assert resp.status_code == 302
        assert len(_page_texts(data_store / f"{VERSION}_streker_OSL.pdf")) == 2

    def test_single_station_upload_is_saved_without_asking(self, admin_client, turnus_set, data_store):
        resp = _post_upload(admin_client, turnus_set.id, _pdf_bytes(["OSL", "OSL"]))
        assert resp.status_code == 302
        assert "/admin/turnus-sets" in resp.headers["Location"]
        assert len(_page_texts(data_store / f"{VERSION}_streker_OSL.pdf")) == 2
        assert not (data_store / f"{VERSION}_streker_opplastet.pdf").exists()

    def test_cancel_keeps_the_old_pdf(self, admin_client, turnus_set, data_store):
        _write_pdf(data_store / f"{VERSION}_streker_OSL.pdf", ["OSL"])
        _post_upload(admin_client, turnus_set.id, _pdf_bytes(["SKN", "OSL", "OSL"]))
        admin_client.post(f"/admin/strekliste-stasjon/{turnus_set.id}", data={"avbryt": "Avbryt"})
        assert len(_page_texts(data_store / f"{VERSION}_streker_OSL.pdf")) == 1
        assert not (data_store / f"{VERSION}_streker_opplastet.pdf").exists()
