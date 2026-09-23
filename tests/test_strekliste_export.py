"""The strekliste export: one gzipped JSON file per turnus set, for nlfstreik."""

import gzip
import json
import os

import pytest

from app.models import TurnusSet
from app.services import strekliste_export_service as eksport
from app.services import strekliste_service

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name="R26", year_identifier="R26")
    db_session.add(ts)
    db_session.commit()
    strekliste_service.import_strekliste(ts.id, os.path.join(FIXTURES, "side1.pdf"))
    return ts


def test_export_writes_every_duty_with_its_activities(turnus_set, tmp_path):
    ut = tmp_path / "strekliste_R26.json.gz"
    rapport = eksport.export(turnus_set.id, str(ut))
    with gzip.open(ut, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["kode"] == "R26"
    assert payload["eksportert_at"]
    assert rapport["dagsverk"] == len(payload["dagsverk"]) == 7
    d = next(x for x in payload["dagsverk"] if x["nr"] == "1201")
    assert (d["stasjoneringssted"], d["kjoredager"], d["start"], d["slutt"]) == ("OSL", "1", "05:33", "14:41")
    assert d["aktiviteter"][1] == {
        "radnr": 2, "fra_tid": "05:43", "til_tid": "06:16", "fra_neste_dag": 0, "til_neste_dag": 0,
        "fra_stasjon": "OSL", "til_stasjon": "MOS", "type": "Togaktivitet", "monster": "Togaktivitet",
        "tognumre": "11508", "tekst": "11508",
    }


def test_export_refuses_a_turnus_set_with_nothing_parsed(patch_db, db_session, tmp_path):
    ts = TurnusSet(name="R27", year_identifier="R27")
    db_session.add(ts)
    db_session.commit()
    with pytest.raises(ValueError):
        eksport.export(ts.id, str(tmp_path / "x.json.gz"))


def test_default_path_lives_under_the_turnus_sets_data_dir(turnus_set, monkeypatch, tmp_path):
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    sti = eksport.default_path("R26")
    assert sti == os.path.join(str(tmp_path), "r26", "strekliste_R26.json.gz")
