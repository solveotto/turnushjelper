"""Tests for cross-source diffing and dagsverk enrichment."""

import copy

from app.utils.pdf.scraper_validator import validate_turnus_json
from app.utils.turnus_diff import diff_turnus_data, enrich_dagsverk


def make_day(tid=None, dagsverk=""):
    tid = tid or []
    if len(tid) == 2:
        start, slutt = tid[0], tid[1]
    else:
        start, slutt = list(tid), ""
    return {
        "ukedag": "Mandag",
        "tid": list(tid),
        "start": start,
        "slutt": slutt,
        "dagsverk": dagsverk,
        "is_consecutive_shift": False,
        "is_consecutive_receiver": False,
    }


def make_turnus(day_overrides=None, kl_timer="203:26", tj_timer="223:11"):
    """Minimal 6x7 turnus; day_overrides maps (uke, dag) -> day dict."""
    ukedager = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
    turnus = {}
    for uke in range(1, 7):
        turnus[uke] = {}
        for dag in range(1, 8):
            day = make_day()
            day["ukedag"] = ukedager[dag - 1]
            turnus[uke][dag] = day
    for (uke, dag), day in (day_overrides or {}).items():
        day["ukedag"] = ukedager[dag - 1]
        turnus[uke][dag] = day
    turnus["kl_timer"] = kl_timer
    turnus["tj_timer"] = tj_timer
    return turnus


def dataset(**turnuser):
    return [{name: data} for name, data in turnuser.items()]


class TestDiffTurnusData:
    def test_identical_data_yields_empty_diff(self):
        a = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006")}))
        diff = diff_turnus_data(a, copy.deepcopy(a))
        assert diff["is_empty"]

    def test_suffix_vs_base_number_is_not_a_diff(self):
        xls = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006")}))
        pdf = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006_SKNO")}))
        diff = diff_turnus_data(xls, pdf)
        assert diff["is_empty"]

    def test_tid_difference_reported(self):
        xls = dataset(OSL_01=make_turnus({(3, 7): make_day(["7:02", "14:33"], "3140")}))
        pdf = dataset(OSL_01=make_turnus({(3, 7): make_day(["7:01", "14:33"], "3140")}))
        diff = diff_turnus_data(xls, pdf)
        assert not diff["is_empty"]
        (cell,) = diff["cells"]
        assert (cell["turnus"], cell["uke"], cell["dag"]) == ("OSL_01", 3, 7)
        assert cell["primary_tid"] == ["7:02", "14:33"]
        assert cell["secondary_tid"] == ["7:01", "14:33"]

    def test_dagsverk_base_difference_reported(self):
        xls = dataset(OSL_01=make_turnus({(5, 7): make_day(["12:48", "21:41"], "1720")}))
        pdf = dataset(OSL_01=make_turnus({(5, 7): make_day(["12:48", "21:41"], "3156")}))
        diff = diff_turnus_data(xls, pdf)
        (cell,) = diff["cells"]
        assert cell["primary_dagsverk"] == "1720"
        assert cell["secondary_dagsverk"] == "3156"

    def test_totals_difference_reported(self):
        xls = dataset(OSL_01=make_turnus(kl_timer="203:26", tj_timer="223:11"))
        pdf = dataset(OSL_01=make_turnus(kl_timer="203:27", tj_timer="223:14"))
        diff = diff_turnus_data(xls, pdf)
        (total,) = diff["totals"]
        assert total["turnus"] == "OSL_01"
        assert total["primary_kl_timer"] == "203:26"
        assert total["secondary_kl_timer"] == "203:27"

    def test_turnus_only_on_one_side(self):
        xls = dataset(OSL_01=make_turnus(), OSL_02=make_turnus())
        pdf = dataset(OSL_01=make_turnus())
        diff = diff_turnus_data(xls, pdf)
        assert diff["only_primary"] == ["OSL_02"]
        assert diff["only_secondary"] == []
        assert not diff["is_empty"]

    def test_diff_is_json_serializable(self):
        import json

        xls = dataset(OSL_01=make_turnus({(1, 1): make_day(["6:00", "14:00"], "1111")}))
        pdf = dataset(OSL_01=make_turnus({(1, 1): make_day(["6:01", "14:00"], "1111")}))
        json.dumps(diff_turnus_data(xls, pdf))


class TestEnrichDagsverk:
    def test_matching_base_adopts_pdf_string(self):
        xls = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006")}))
        pdf = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006_SKNO")}))
        enriched = enrich_dagsverk(xls, pdf)
        assert enriched[0]["OSL_01"][1][1]["dagsverk"] == "3006_SKNO"

    def test_differing_base_keeps_xls_value(self):
        xls = dataset(OSL_01=make_turnus({(5, 7): make_day(["12:48", "21:41"], "1720")}))
        pdf = dataset(OSL_01=make_turnus({(5, 7): make_day(["14:23", "23:08"], "3156_LHM")}))
        enriched = enrich_dagsverk(xls, pdf)
        assert enriched[0]["OSL_01"][5][7]["dagsverk"] == "1720"

    def test_turnus_missing_from_pdf_untouched(self):
        xls = dataset(OSL_02=make_turnus({(1, 1): make_day(["6:00", "14:00"], "5001")}))
        pdf = dataset(OSL_01=make_turnus({(1, 1): make_day(["6:00", "14:00"], "5001_HLD")}))
        enriched = enrich_dagsverk(xls, pdf)
        assert enriched[0]["OSL_02"][1][1]["dagsverk"] == "5001"

    def test_retimed_same_number_still_enriched(self):
        xls = dataset(OSL_01=make_turnus({(3, 7): make_day(["7:02", "14:33"], "3140")}))
        pdf = dataset(OSL_01=make_turnus({(3, 7): make_day(["7:01", "14:33"], "3140_LHM")}))
        enriched = enrich_dagsverk(xls, pdf)
        assert enriched[0]["OSL_01"][3][7]["dagsverk"] == "3140_LHM"

    def test_fridag_and_blank_cells_untouched(self):
        xls = dataset(OSL_01=make_turnus({(1, 3): make_day(["X"]), (2, 2): make_day()}))
        pdf = dataset(OSL_01=make_turnus({(1, 3): make_day(["X"]), (2, 2): make_day()}))
        enriched = enrich_dagsverk(xls, pdf)
        assert enriched[0]["OSL_01"][1][3]["dagsverk"] == ""
        assert enriched[0]["OSL_01"][2][2]["dagsverk"] == ""

    def test_input_not_mutated(self):
        xls = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006")}))
        pdf = dataset(OSL_01=make_turnus({(1, 1): make_day(["13:13", "19:01"], "3006_SKNO")}))
        snapshot = copy.deepcopy(xls)
        enrich_dagsverk(xls, pdf)
        assert xls == snapshot

    def test_enriched_output_passes_validator(self):
        import json
        import os

        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "timeskjema_sample.xls"
        )
        from app.utils.timeskjema_parser import parse_timeskjema

        result = parse_timeskjema(fixture)
        # Simulate a PDF loaded from disk: JSON round-trip gives string keys,
        # which diff/enrich must tolerate alongside the parser's int keys.
        pdf = json.loads(json.dumps(result.turnuser))
        pdf[0]["OSL_01"]["1"]["1"]["dagsverk"] = "3006_SKNO"
        enriched = enrich_dagsverk(result.turnuser, pdf)
        assert enriched[0]["OSL_01"][1][1]["dagsverk"] == "3006_SKNO"
        valid, errors = validate_turnus_json(enriched)
        assert valid, errors
