"""Tests for the strekliste PDF parser.

Fixtures are single pages cut from a real R26 strekliste (no personal data):
side1.pdf holds 1201-1206, side7.pdf holds 1313-N05 .. 1320 incl. night duties
with a +24t continuation row.
"""

import os

import pdfplumber
import pytest

from app.utils.pdf import strekliste_parser as sp

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "strekliste")
SIDE1 = os.path.join(FIXTURES, "side1.pdf")
SIDE7 = os.path.join(FIXTURES, "side7.pdf")


@pytest.fixture(scope="module")
def side1():
    with pdfplumber.open(SIDE1) as pdf:
        yield pdf.pages[0]


@pytest.fixture(scope="module")
def side7():
    with pdfplumber.open(SIDE7) as pdf:
        yield pdf.pages[0]


# ── Geometry ───────────────────────────────────────────────────────────

def test_geometri_reads_hour_axis_from_the_page(side1):
    geo = sp._geometri(side1)
    assert geo.h0 == pytest.approx(101.5, abs=0.2)
    assert geo.pt_per_hour == pytest.approx(19.52, abs=0.05)


def test_geometri_converts_x_to_clock_time(side1):
    geo = sp._geometri(side1)
    # The bold start line of 1201 sits at x=209.8 and the page prints 5:33 there.
    assert geo.tid(209.8) == "05:33"
    assert geo.tid(388.1) == "14:41"


# ── Legend ─────────────────────────────────────────────────────────────

def test_legende_maps_pattern_tiles_to_their_labels(side1):
    typer = set(sp._legende(side1).values())
    assert {"Togaktivitet", "Passreise", "Snu/stå", "Reserve",
            "Frammøte/Avslutning"} <= typer


# ── Duty headers ───────────────────────────────────────────────────────

def test_side1_lists_every_duty_with_days_and_stock():
    res = sp.parse_strekliste(SIDE1)
    hoder = [(d["nr"], d["kjoredager"], d["materiell"]) for d in res.duties]
    assert hoder == [
        ("1201", "1", "(OP.BM72 OP.BM75)"),
        ("1202", "12345", "(OP.BM75 OP.BM74-BM75)"),
        ("1203-Mod_1", "5", "(OP.BM69 OP.BM75 OP.BM74-BM75)"),
        ("1203-Mod_1", "1234", "(OP.BM69 OP.BM75 OP.BM74-BM75)"),
        ("1204", "12345", "(OP.BM74-BM75 OP.BM72)"),
        ("1205", "12345", "(OP.BM74-BM75 OP.BM69)"),
        ("1206", "4", "(OP.BM72 OP.BM75 OP.BM69)"),
    ]


def test_side1_duties_carry_station_page_and_times():
    res = sp.parse_strekliste(SIDE1)
    d = res.duties[0]
    assert d["stasjoneringssted"] == "OSL"
    assert d["side"] == 1
    assert (d["start"], d["slutt"], d["slutt_neste_dag"]) == ("05:33", "14:41", 0)
    assert [(x["start"], x["slutt"]) for x in res.duties] == [
        ("05:33", "14:41"), ("05:41", "14:19"), ("06:11", "15:01"),
        ("06:11", "15:01"), ("06:15", "14:06"), ("06:21", "13:34"),
        ("06:35", "15:09"),
    ]


def test_side1_reads_the_nine_timer_columns():
    res = sp.parse_strekliste(SIDE1)
    assert res.duties[0]["beregninger"] == {
        "KLT-NE": "8:13", "P-AML": "0:10", "GT-AML": "0:45", "AML": "9:08",
        "GT": None, "NT": "0:07", "ST": None, "PASS": None, "Tj.t": "9:15",
    }


# ── Activities ─────────────────────────────────────────────────────────

def _rader(d):
    return [(a["fra_tid"], a["til_tid"], a["fra_stasjon"], a["til_stasjon"],
             a["type"], a["tognumre"]) for a in d["aktiviteter"]]


def test_1201_activities_in_full():
    res = sp.parse_strekliste(SIDE1)
    d = next(x for x in res.duties if x["nr"] == "1201")
    assert _rader(d) == [
        ("05:33", "05:43", "OSL", "OSL", "Frammøte/Avslutning", ""),
        ("05:43", "06:16", "OSL", "MOS", "Togaktivitet", "11508"),
        ("06:16", "06:43", "MOS", "MOS", "Snu/stå", ""),
        ("06:43", "07:20", "MOS", "OSL", "Togaktivitet", "1508"),
        ("07:20", "07:36", "OSL", "OSL", "Snu/stå", ""),
        ("07:36", "07:47", "OSL", "SKI", "Togaktivitet", "1511"),
        ("07:47", "08:00", "SKI", "SKI", "Snu/stå", ""),
        ("08:00", "08:12", "SKI", "OSL", "Togaktivitet", "1590"),
        ("08:12", "08:18", "OSL", "OSL", "Snu/stå", ""),
        ("08:18", "08:23", "OSL", "LOD", "Togaktivitet", "1590"),
        ("08:23", "08:31", "LOD", "LOD", "Fra/Ins", "1590,1591"),
        ("08:31", "09:06", "LOD", "OSL", "Gangtid", ""),
        ("09:06", "09:24", "OSL", "OSL", "Opphold", ""),
        ("09:24", "09:34", "OSL", "LLS", "Passreise", "808"),
        ("09:34", "09:40", "LLS", "LLS", "Opphold", ""),
        ("09:40", "09:55", "LLS", "LLS", "Snu/stå", ""),
        ("09:55", "10:24", "LLS", "OSL", "Togaktivitet", "2121"),
        ("10:24", "11:26", "OSL", "OSL", "Opphold", ""),
        ("11:26", "11:55", "OSL", "LLS", "Togaktivitet", "2126"),
        ("11:55", "12:10", "LLS", "LLS", "Snu/stå", ""),
        ("12:10", "13:33", "LLS", "SPI", "Togaktivitet", "2231"),
        ("13:33", "13:46", "SPI", "SPI", "Snu/stå", ""),
        ("13:46", "14:39", "SPI", "OSL", "Togaktivitet", "2240"),
        ("14:39", "14:41", "OSL", "OSL", "Frammøte/Avslutning", ""),
    ]
    assert [a["radnr"] for a in d["aktiviteter"]] == list(range(1, 25))
    assert d["advarsler"] == []


def test_1201_keeps_the_raw_label_text_and_pattern():
    res = sp.parse_strekliste(SIDE1)
    d = next(x for x in res.duties if x["nr"] == "1201")
    akt = {a["fra_tid"]: a for a in d["aktiviteter"]}
    assert akt["08:23"]["tekst"] == "Fra/Ins[1590-1591] LOD"
    assert akt["08:31"]["tekst"] == "Gangtid OSL"
    assert akt["08:31"]["monster"] == "Passreise"
    assert akt["09:24"]["tekst"] == "808Passreise"
    assert akt["09:06"]["monster"] is None


# ── Page 7: night duties and +24t ──────────────────────────────────────

def test_side7_headers_including_duties_that_cross_midnight():
    res = sp.parse_strekliste(SIDE7)
    assert [(d["nr"], d["kjoredager"], d["start"], d["slutt"], d["slutt_neste_dag"])
            for d in res.duties] == [
        ("1313-N05_5", "12345", "15:01", "21:58", 0),
        ("1314-N05_3", "5", "15:51", "23:54", 0),
        ("1315", "5", "15:48", "23:22", 0),
        ("1318", "5", "14:46", "23:58", 0),
        ("1319", "124", "14:46", "00:40", 1),
        ("1319-O", "3", "14:46", "00:17", 1),
        ("1320", "5", "20:14", "08:58", 1),
    ]


def test_minute_marks_never_leak_into_label_text():
    for sti in (SIDE1, SIDE7):
        for d in sp.parse_strekliste(sti).duties:
            for a in d["aktiviteter"]:
                assert "'" not in a["tekst"], (d["nr"], a)


def test_both_fixture_pages_parse_without_warnings():
    res = sp.parse_strekliste(SIDE1)
    assert res.warnings == []
    assert [(d["nr"], d["advarsler"]) for d in res.duties if d["advarsler"]] == []
    res = sp.parse_strekliste(SIDE7)
    assert res.warnings == []
    # 1320 prints "11935" whole and cut to "1935" at the 00:00 edge; the cut
    # one is reported, and nothing else on the page is.
    assert [(d["nr"], d["advarsler"]) for d in res.duties if d["advarsler"]] == [
        ("1320", ["etikett klippet ved døgnskiftet: «1935»"]),
    ]


def test_1320_night_duty_in_full():
    res = sp.parse_strekliste(SIDE7)
    d = next(x for x in res.duties if x["nr"] == "1320")
    assert _rader(d) == [
        ("20:14", "20:22", "OSL", "OSL", "Frammøte/Avslutning", ""),
        ("20:22", "20:33", "OSL", "SKI", "Passreise", "1161"),
        ("20:33", "20:44", "SKI", "SKI", "Opphold", ""),
        ("20:44", "20:56", "SKI", "OSL", "Togaktivitet", "1934"),
        ("20:56", "22:00", "OSL", "OSL", "Snu/stå", ""),
        ("22:00", "23:11", "OSL", "RST", "Togaktivitet", "1935"),
        ("23:11", "23:19", "RST", "RST", "Snu/stå", ""),
        ("23:19", "00:10", "RST", "SKI", "Togaktivitet", "11935"),
        ("00:10", "00:16", "SKI", "SKI", "Snu/stå", ""),
        ("00:16", "00:18", "SKI", "SKH", "Togaktivitet", "21935I"),
        ("00:18", "00:31", "SKH", "SKH", "Fra/Ins", "21935I"),
        ("00:31", "01:00", "SKH", "SKH", "Opphold", ""),
        ("01:00", "02:00", "SKH", "MYS", "Taxi", ""),
        ("02:00", "06:34", "MYS", "MYS", "Dagsverk opphold", ""),
        ("06:34", "06:39", "MYS", "MYS", "Opphold", ""),
        ("06:39", "06:41", "MYS", "MYH", "Gangtid", ""),
        ("06:41", "07:11", "MYH", "MYH", "Uttak", "11910U"),
        ("07:11", "07:16", "MYH", "MYH", "Til_plf", "11910U"),
        ("07:16", "07:18", "MYH", "MYS", "Togaktivitet", "11910U"),
        ("07:18", "07:23", "MYS", "MYS", "Togaktivitet", "11910U"),
        ("07:23", "07:35", "MYS", "RST", "Togaktivitet", "11910"),
        ("07:35", "07:45", "RST", "RST", "Snu/stå", ""),
        ("07:45", "08:56", "RST", "OSL", "Togaktivitet", "1910"),
        ("08:56", "08:58", "OSL", "OSL", "Frammøte/Avslutning", ""),
    ]


def test_1320_marks_which_activities_fall_on_the_next_day():
    res = sp.parse_strekliste(SIDE7)
    d = next(x for x in res.duties if x["nr"] == "1320")
    flagg = [(a["fra_tid"], a["fra_neste_dag"], a["til_neste_dag"]) for a in d["aktiviteter"]]
    assert flagg[6] == ("23:11", 0, 0)
    assert flagg[7] == ("23:19", 0, 1)      # the train that crosses midnight
    assert flagg[8] == ("00:10", 1, 1)
    assert all(f == 1 and t == 1 for _, f, t in flagg[8:])
    taxi = d["aktiviteter"][12]
    assert (taxi["monster"], taxi["tekst"]) == ("Passreise", "M-TAXI")


def test_1204_reads_tilsyn_skjoting_and_deling_from_their_labels():
    res = sp.parse_strekliste(SIDE1)
    d = next(x for x in res.duties if x["nr"] == "1204")
    rader = _rader(d)
    assert ("07:02", "07:15", "LLH", "LLH", "Tilsyn", "2106I,2111U") in rader
    assert ("07:17", "07:21", "LLS", "LLS", "Skjøting", "2111U,2208,2111") in rader
    assert ("10:02", "10:10", "MOS", "MOS", "Deling", "1117,1117I,1126") in rader
    tilsyn = next(a for a in d["aktiviteter"] if a["type"] == "Tilsyn")
    assert tilsyn["monster"] == "Togaktivitet"
    assert tilsyn["tekst"] == "Tilsyn[2106I-2111U]"


# ── Edge cases from the full file ──────────────────────────────────────

def _side(n):
    return os.path.join(FIXTURES, f"side{n}.pdf")


def test_hour_axis_is_read_from_the_tick_row_only():
    # Page 18 has stray short lines near the axis; the scale must still be
    # the one the minute marks agree with (every page prints the same axis).
    with pdfplumber.open(_side(18)) as pdf:
        geo = sp._geometri(pdf.pages[0])
    assert geo.pt_per_hour == pytest.approx(19.52, abs=0.05)
    res = sp.parse_strekliste(_side(18))
    assert [(d["nr"], d["advarsler"]) for d in res.duties if d["advarsler"]] == []


def test_clock_label_far_below_its_bar_still_ends_that_bar():
    # 1384 on page 10: the first bar's start label 22:14 sits 28 pt under it.
    res = sp.parse_strekliste(_side(10))
    d = next(x for x in res.duties if x["nr"] == "1384")
    assert (d["start"], d["slutt"], d["slutt_neste_dag"]) == ("22:14", "07:20", 1)
    assert d["advarsler"] == []


def test_labels_clipped_at_the_24_hour_edge_are_reported_not_placed():
    # 1454 on page 16 has two label fragments ("2", "S") starting on the edge.
    res = sp.parse_strekliste(_side(16))
    d = next(x for x in res.duties if x["nr"] == "1454")
    assert sorted(d["advarsler"]) == ["etikett klippet ved sidekanten: «2»",
                                      "etikett klippet ved sidekanten: «S»"]
    assert not any("S" in (a["fra_stasjon"], a["til_stasjon"]) for a in d["aktiviteter"])


def test_end_station_printed_after_the_end_line_closes_the_last_leg():
    res = sp.parse_strekliste(_side(4))
    d = next(x for x in res.duties if x["nr"] == "1239")
    assert d["advarsler"] == []
    assert d["aktiviteter"][-1]["til_stasjon"] == "OSL"


def test_unlabelled_legs_inherit_the_train_they_continue():
    res = sp.parse_strekliste(SIDE1)
    d = next(x for x in res.duties if x["nr"] == "1204")
    rader = _rader(d)
    assert ("08:49", "08:51", "STB", "STB", "Togaktivitet", "1116") in rader   # dwell
    assert ("08:53", "09:03", "HVK", "HVK", "Togaktivitet", "1116") in rader
    assert ("09:05", "09:06", "HVK", "STB", "Togaktivitet", "1117") in rader
    leg = next(a for a in d["aktiviteter"] if a["fra_tid"] == "08:49")
    assert leg["tekst"] == ""   # inherited, not printed


def test_plus24_mark_belongs_to_the_nearest_bar_even_on_a_short_band():
    # 9305 on page 58 is a reserve duty 17:50 -> 02:00 drawn on two bars so
    # close together that the +24t mark is within reach of both.
    res = sp.parse_strekliste(_side(58))
    d = next(x for x in res.duties if x["nr"] == "9305")
    assert (d["start"], d["slutt"], d["slutt_neste_dag"]) == ("17:50", "02:00", 1)
    assert d["advarsler"] == []
    reserve = [a for a in d["aktiviteter"] if a["type"] == "Reserve"]
    assert [(a["fra_tid"], a["til_tid"], a["til_neste_dag"]) for a in reserve] == [
        ("18:00", "02:00", 1),   # frammøte 17:50-18:00, then one block past midnight
    ]


def test_touching_station_labels_split_into_three_letter_codes():
    # 1522 on turnushjelper's own rendition: "SKØSKI" is SKØ then SKI, and
    # the boundary that happens to sit under the Ø must not win the split.
    res = sp.parse_strekliste(_side("22_th"))
    d = next(x for x in res.duties if x["nr"] == "1522")
    koder = {a["fra_stasjon"] for a in d["aktiviteter"]} | {a["til_stasjon"] for a in d["aktiviteter"]}
    assert "SKØ" in koder and "SKI" in koder
    assert not {"SK", "ØSKI"} & koder


def test_labels_clipped_at_the_page_edge_are_dropped_with_a_warning():
    # 1246 on page 4 ends at 23:51 and its last station label is cut to "OS".
    res = sp.parse_strekliste(_side(4))
    d = next(x for x in res.duties if x["nr"] == "1246")
    koder = {a["til_stasjon"] for a in d["aktiviteter"]}
    assert "OS" not in koder
    assert any("klippet" in w and "OS" in w for w in d["advarsler"])
    # 1749 on page 37 has a train number cut to "227"; it must not become a train.
    res = sp.parse_strekliste(_side(37))
    d = next(x for x in res.duties if x["nr"] == "1749")
    assert not any("227" == nr for a in d["aktiviteter"] for nr in a["tognumre"].split(","))


def test_wrapped_duty_numbers_join_like_the_png_generator_names_them():
    # Lines of the Nr. cell, as pdfplumber rebuilds them.
    assert sp._slaa_sammen_nr(["1203-", "Mod_1"]) == "1203-Mod_1"
    assert sp._slaa_sammen_nr(["1313-", "N05 5"]) == "1313-N05_5"
    assert sp._slaa_sammen_nr(["1411-", "N05 3", "5"]) == "1411-N05_3_5"
    assert sp._slaa_sammen_nr(["1432-70", "N05 3"]) == "1432-70_N05_3"
    assert sp._slaa_sammen_nr(["3049", "!"]) == "3049"
    assert sp._slaa_sammen_nr(["3006<<3007"]) == "3006<<3007"


def test_a_double_duty_row_is_two_duties():
    # 3006<<3007 on page 34 of turnushjelper's rendition: 3006 in the afternoon
    # on days 1-4, 3007 the next morning on days 2-5, two bar rows in one band.
    res = sp.parse_strekliste(_side("34_th"))
    par = [d for d in res.duties if d["nr"] in ("3006", "3007")]
    assert [(d["nr"], d["kjoredager"], d["start"], d["slutt"], d["slutt_neste_dag"]) for d in par] == [
        ("3006", "1234", "13:13", "19:01", 0),
        ("3007", "2345", "04:24", "09:56", 0),
    ]
    assert par[0]["aktiviteter"][-1]["til_tid"] == "19:01"
    assert par[1]["aktiviteter"][0]["fra_tid"] == "04:24"
    assert par[1]["aktiviteter"][0]["fra_neste_dag"] == 0
    assert par[0]["dobbelt_tur"] == "3006<<3007" and par[1]["dobbelt_tur"] == "3006<<3007"
    assert not any("<<" in d["nr"] for d in res.duties)


def test_labels_of_a_compact_plus24_row_are_not_taken_by_the_row_above():
    # 1648-N05_3 on page 29 of turnushjelper's rendition: the continuation
    # row's labels sit only ~20 pt under the first row's bar. Found in the
    # review report, where the morning legs had lost their train numbers.
    res = sp.parse_strekliste(_side("29_th"))
    d = next(x for x in res.duties if x["nr"] == "1648-N05_3")
    tog = [(a["fra_tid"], a["type"], a["tognumre"]) for a in d["aktiviteter"] if a["tognumre"]]
    assert tog == [
        ("23:41", "Togaktivitet", "2275"),
        ("00:45", "Togaktivitet", "12295"),
        ("01:19", "Fra/Ins", "12295,12212"),
        ("06:15", "Uttak", "12216"),
        ("06:50", "Togaktivitet", "12216"),
        ("07:47", "Togaktivitet", "2216"),
    ]


def test_unlabelled_legs_before_the_labelled_one_belong_to_the_same_train():
    # 1247 on page 4 of turnushjelper's rendition: a two-minute stop at HVK
    # and a one-minute leg to STB come before the segment that carries 1179.
    res = sp.parse_strekliste(_side("4_th"))
    d = next(x for x in res.duties if x["nr"] == "1247")
    legs = [(a["fra_tid"], a["fra_stasjon"], a["til_stasjon"], a["tognumre"])
            for a in d["aktiviteter"] if a["type"] == "Togaktivitet" and a["fra_tid"] in ("00:33", "00:35", "00:36")]
    assert legs == [("00:33", "HVK", "HVK", "1179"), ("00:35", "HVK", "STB", "1179"), ("00:36", "STB", "MOS", "1179")]
