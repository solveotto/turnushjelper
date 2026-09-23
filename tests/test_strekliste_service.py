"""Storage of parsed streklister: replace-per-turnus-set, and the keys."""

import os

import pytest

from app.models import StreklisteAktivitet, StreklisteDagsverk, TurnusSet
from app.services import strekliste_service
from app.utils.pdf.strekliste_parser import ParseResult

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")


def _duty(nr, dager, start="05:33", slutt="14:41", aktiviteter=None):
    return {
        "stasjoneringssted": "OSL", "nr": nr, "kjoredager": dager, "materiell": "(OP.BM75)",
        "start": start, "slutt": slutt, "slutt_neste_dag": 0, "side": 1,
        "beregninger": {"Tj.t": "9:15"}, "kommentar": None, "advarsler": [],
        "aktiviteter": aktiviteter if aktiviteter is not None else [
            {"radnr": 1, "fra_tid": "05:43", "til_tid": "06:16", "fra_neste_dag": 0,
             "til_neste_dag": 0, "fra_stasjon": "OSL", "til_stasjon": "MOS",
             "type": "Togaktivitet", "monster": "Togaktivitet", "tognumre": "11508",
             "tekst": "11508"},
        ],
    }


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name="R26", year_identifier="R26")
    db_session.add(ts)
    db_session.commit()
    return ts


def test_lagre_writes_duties_and_activities(turnus_set, db_session):
    res = ParseResult(duties=[_duty("1201", "1"), _duty("1310", "25"), _duty("1310", "34")])
    rapport = strekliste_service.lagre_parse(turnus_set.id, res)
    assert rapport["dagsverk"] == 3 and rapport["aktiviteter"] == 3
    rader = db_session.query(StreklisteDagsverk).order_by(StreklisteDagsverk.nr,
                                                            StreklisteDagsverk.kjoredager).all()
    assert [(r.nr, r.kjoredager) for r in rader] == [("1201", "1"), ("1310", "25"), ("1310", "34")]
    akt = db_session.query(StreklisteAktivitet).filter_by(dagsverk_id=rader[0].id).all()
    assert [(a.radnr, a.fra_tid, a.til_tid, a.til_stasjon, a.type, a.tognumre) for a in akt] == [
        (1, "05:43", "06:16", "MOS", "Togaktivitet", "11508"),
    ]
    assert rader[0].beregninger == {"Tj.t": "9:15"}


def test_lagre_replaces_the_turnus_sets_rows_wholesale(turnus_set, db_session):
    strekliste_service.lagre_parse(turnus_set.id, ParseResult(duties=[_duty("1201", "1")]))
    strekliste_service.lagre_parse(turnus_set.id, ParseResult(duties=[_duty("1202", "12345")]))
    assert [r.nr for r in db_session.query(StreklisteDagsverk).all()] == ["1202"]
    assert db_session.query(StreklisteAktivitet).count() == 1


def test_lagre_keeps_the_parsers_warnings_on_the_duty(turnus_set, db_session):
    d = _duty("1404", "12345")
    d["advarsler"] = ["minuttmerke 3' ved 06:30"]
    rapport = strekliste_service.lagre_parse(turnus_set.id, ParseResult(duties=[d], warnings=["x"]))
    rad = db_session.query(StreklisteDagsverk).one()
    assert rad.advarsler == ["minuttmerke 3' ved 06:30"]
    assert rapport["advarsler"] == 1 and rapport["sidevarsler"] == ["x"]


def test_import_strekliste_parses_a_pdf_and_stores_it(turnus_set, db_session):
    rapport = strekliste_service.import_strekliste(turnus_set.id, os.path.join(FIXTURES, "side1.pdf"))
    assert rapport["dagsverk"] == 7
    assert rapport["per_sted"] == {"OSL": 7}
    assert db_session.query(StreklisteDagsverk).filter_by(nr="1201").one().start == "05:33"


def test_hent_dagsverk_returns_activities_in_order(turnus_set, db_session):
    strekliste_service.import_strekliste(turnus_set.id, os.path.join(FIXTURES, "side1.pdf"))
    d = strekliste_service.hent_dagsverk(turnus_set.id, "1201")
    assert d["start"] == "05:33"
    assert [a["radnr"] for a in d["aktiviteter"]] == list(range(1, 25))
    assert d["aktiviteter"][1]["tognumre"] == "11508"
    assert strekliste_service.hent_dagsverk(turnus_set.id, "9999") is None


def test_hent_dagsverk_picks_the_variant_for_a_weekday(turnus_set, db_session):
    res = ParseResult(duties=[_duty("1310", "25", start="06:00"), _duty("1310", "34", start="07:00")])
    strekliste_service.lagre_parse(turnus_set.id, res)
    assert strekliste_service.hent_dagsverk(turnus_set.id, "1310", ukedag=2)["start"] == "06:00"
    assert strekliste_service.hent_dagsverk(turnus_set.id, "1310", ukedag=4)["start"] == "07:00"
    assert strekliste_service.hent_dagsverk(turnus_set.id, "1310", ukedag=6) is None
