"""The review report: every parsed duty beside its PNG, warnings first."""

import os

import pytest

from app.models import TurnusSet
from app.services import strekliste_service
from app.utils import strekliste_rapport as rapport

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


@pytest.fixture()
def dagsverk(patch_db, db_session):
    ts = TurnusSet(name="R26", year_identifier="R26")
    db_session.add(ts)
    db_session.commit()
    strekliste_service.import_strekliste(ts.id, os.path.join(FIXTURES, "side7.pdf"))
    return [strekliste_service.hent_dagsverk(ts.id, d["nr"], ukedag=None) | {"kjoredager": d["kjoredager"]}
            for d in strekliste_service.list_dagsverk(ts.id)]


def test_report_lists_every_duty_with_its_image_and_rows(dagsverk, tmp_path):
    (tmp_path / "png").mkdir()
    (tmp_path / "png" / "1320.png").write_bytes(b"png")
    html = rapport.bygg_gjennomgang(dagsverk, str(tmp_path / "png"), "R26")
    assert html.count('class="dagsverk"') == len(dagsverk)
    assert 'src="png/1320.png"' in html
    assert "11935" in html and "Frammøte/Avslutning" in html
    assert "Bilde mangler" in html           # 1313-N05_5 has no PNG in this temp dir


def test_duties_with_warnings_come_first_and_are_listed_in_the_jump_list(dagsverk, tmp_path):
    html = rapport.bygg_gjennomgang(dagsverk, str(tmp_path), "R26")
    forste = html.index('class="dagsverk"')
    assert 'id="dv-1320-5"' in html[forste:forste + 400]        # 1320 carries the only warning on page 7
    assert "etikett klippet ved døgnskiftet" in html
    assert html.index("Med advarsler") < html.index("Uten advarsler")


def test_report_can_be_written_next_to_the_png_folder(dagsverk, tmp_path):
    ut = rapport.skriv_gjennomgang(dagsverk, str(tmp_path / "png"), "R26",
                                   str(tmp_path / "gjennomgang_r26.html"))
    assert os.path.exists(ut)
    assert open(ut, encoding="utf-8").read().startswith("<!DOCTYPE html>")


def test_image_lookup_tolerates_the_generators_naming_quirks(tmp_path):
    (tmp_path / "png").mkdir()
    for navn in ("1411-N05_3_5.png", "3049!.png", "5002-bm73-_F_N05_5.png", "1310.png"):
        (tmp_path / "png" / navn).write_bytes(b"png")
    finn = rapport.bildeoppslag(str(tmp_path / "png"))
    assert finn("1411-N05_3_5") == "1411-N05_3_5.png"
    assert finn("3049") == "3049!.png"
    assert finn("5002-bm73-F_N05_5") == "5002-bm73-_F_N05_5.png"
    assert finn("1310-M") is None
