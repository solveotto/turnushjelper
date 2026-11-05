"""A driver's plan for a reduced position on Min Tur.

The numbers come from R27 OSL 01, read off the Timeskjema by hand: total
223:20, 5003 is 8:46, and the double duty 5021<<5022 is 6:43 + 6:06. A fake year
identifier and a data store in tmp_path are used throughout, because the admin
delete route removes a real year's PNGs.
"""

import datetime
import html as html_module
import json
import math
import os
import re

import openpyxl
import pytest

from app.models import (
    DBUser,
    Favorites,
    Innplassering,
    RedusertStilling,
    Shifts,
    SoknadsskjemaChoice,
    TurnusSet,
)
# Imported at collection on purpose. A route module first imported inside a test
# binds that test's session factory for the rest of the run (see conftest.patch_db).
from app.routes.shifts import mintur as _mintur  # noqa: F401
from app.services import redusert_stilling_service as service
from app.services import turnus_service, user_service
from tests.conftest import WEEKDAYS_NB, login_user

FAKE_YEAR = "T99"
TITLE = "OSL_01"
REDUSERT_CSS = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "app", "static", "css", "mintur-redusert.css"
)
ROUTE = "/mintur/redusert-stilling"
FIRST_MONDAY = datetime.date(2026, 12, 14)
UNDER_VARSEL = "Du er under 180:00 Tj.t (80 %)."


def work(dv, tj, start="8:00", end="16:00", first=False, receiver=False):
    return {
        "ukedag": "",
        "tid": [start, end],
        "start": start,
        "slutt": end,
        "dagsverk": dv,
        "tj_timer": tj,
        "is_consecutive_shift": first,
        "is_consecutive_receiver": receiver,
    }


def free(code="X"):
    return {
        "ukedag": "",
        "tid": [code],
        "start": [code],
        "slutt": "",
        "dagsverk": "",
        "tj_timer": "",
        "is_consecutive_shift": False,
        "is_consecutive_receiver": False,
    }


def make_raw(cells, total="223:20"):
    """A tur with the given {"uke-dag": cell} on a background of free days."""
    raw = {"kl_timer": "201:53", "tj_timer": total}
    for uke in range(1, 7):
        raw[str(uke)] = {}
        for dag in range(1, 8):
            cell = dict(cells.get(f"{uke}-{dag}") or free())
            cell["ukedag"] = WEEKDAYS_NB[dag - 1]
            raw[str(uke)][str(dag)] = cell
    return raw


# What the page and the export read, with double-duty flags set by hand for the
# service tests. The route tests get their flags from a real double-shift file.
RAW = make_raw(
    {
        "1-1": work("5003", "8:46", "6:32", "15:18"),
        "2-3": work("5021", "6:43", "16:21", "22:27", first=True),
        "2-4": work("5022", "6:06", "6:25", "12:31", receiver=True),
        "3-7": work("5053", "9:30", "8:32", "18:02", receiver=True),
        "4-1": work("9348", "9:34", "23:45", "7:45"),
    }
)


H_RAW = make_raw(
    {
        "1-1": work("5003", "8:46", "6:32", "15:18"),
        "1-6": work("6001", "8:00", "8:00", "16:00"),
        "3-6": work("6003", "8:00", "8:00", "16:00"),
        "5-6": work("6005", "8:00", "8:00", "16:00"),
        "6-5": work("9908001700-H", "9:00", "8:00", "17:00"),
    }
)


def weekend(dv):
    return work(dv, "8:00", "8:00", "16:00")


# Weekends 1, 3 and 5 have work, the pattern 56 of 57 R26 turer have. Weekend 1 has
# two shifts, so losing one of them still leaves work hours.
WEEKENDS = {
    "1-6": weekend("6001"),
    "1-7": weekend("6002"),
    "3-6": weekend("6003"),
    "5-7": weekend("6005"),
    "6-2": work("9908001700-H", "9:00", "8:00", "17:00"),
}


@pytest.fixture()
def turnus_set(patch_db, db_session):
    ts = TurnusSet(name=FAKE_YEAR, year_identifier=FAKE_YEAR, is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def user(patch_db, db_session):
    u = DBUser(username="planbruker", password="x", is_auth=0)
    db_session.add(u)
    db_session.commit()
    return u


def plan_rows(db_session):
    db_session.expire_all()
    return db_session.query(RedusertStilling).all()


class TestSummary:
    def test_target_is_225_hours_times_the_percentage(self):
        result = service.summary(RAW, {"prosent": 80, "fjernet": {}})
        assert result["total"] == "225:00"
        assert result["target"] == "180:00"
        assert result["remaining"] == "223:20"

    def test_total_is_always_225_hours_and_remaining_is_the_turs_own(self):
        raw = make_raw({"1-1": work("5003", "8:46")}, "222:04")
        result = service.summary(raw, {"prosent": None, "fjernet": {}})
        assert result["total"] == "225:00"
        assert result["remaining"] == "222:04"

    def test_target_does_not_depend_on_what_the_tur_adds_up_to(self):
        raw = make_raw({"1-1": work("5003", "8:46")}, "222:04")
        assert service.summary(raw, {"prosent": 80, "fjernet": {}})["target"] == "180:00"

    def test_removing_a_shift_lowers_what_remains(self):
        result = service.summary(RAW, {"prosent": 80, "fjernet": {"1-1": "5003"}})
        assert result["remaining"] == "214:34"

    def test_a_decimal_percentage_rounds_to_the_nearest_minute(self):
        # 13 500 minutes x 73.37 % = 9 904.95, which rounds up, not down.
        result = service.summary(RAW, {"prosent": 73.37, "fjernet": {}})
        assert result["target"] == "165:05"

    def test_status_over_the_target(self):
        result = service.summary(RAW, {"prosent": 80, "fjernet": {}})
        assert result["status"] == "Gjenstående timer til 80 %: 43:20"

    def test_status_writes_a_decimal_percentage_with_a_comma(self):
        result = service.summary(RAW, {"prosent": 73.2, "fjernet": {}})
        assert result["target"] == "164:42"
        assert result["status"] == "Gjenstående timer til 73,2 %: 58:38"

    def test_status_under_the_target(self):
        cells = {"1-1": work("5003", "123:10")}
        result = service.summary(make_raw(cells, "225:00"), {"prosent": 50, "fjernet": {"1-1": "5003"}})
        assert result["status"] == "10:40 under målet"

    def test_exactly_on_the_target_is_neither_over_nor_under(self):
        cells = {"1-1": work("5003", "112:30")}
        result = service.summary(make_raw(cells, "225:00"), {"prosent": 50, "fjernet": {"1-1": "5003"}})
        assert result["remaining"] == result["target"]
        assert "over" not in result["status"]
        assert "under" not in result["status"]

    @pytest.mark.parametrize("prosent", [None, 50, 80, 95])
    def test_warns_below_180_whatever_the_target(self, prosent):
        cells = {"1-1": work("5003", "45:01")}
        result = service.summary(make_raw(cells, "225:00"), {"prosent": prosent, "fjernet": {"1-1": "5003"}})
        assert result["remaining"] == "179:59"
        assert result["under_varsel"] == UNDER_VARSEL

    @pytest.mark.parametrize("prosent", [None, 80, 95])
    def test_no_warning_at_exactly_180(self, prosent):
        cells = {"1-1": work("5003", "45:00")}
        result = service.summary(make_raw(cells, "225:00"), {"prosent": prosent, "fjernet": {"1-1": "5003"}})
        assert result["remaining"] == "180:00"
        assert result["under_varsel"] == ""

    def test_no_warning_above_180_even_when_under_a_higher_target(self):
        cells = {"1-1": work("5003", "30:00")}
        result = service.summary(make_raw(cells, "225:00"), {"prosent": 95, "fjernet": {"1-1": "5003"}})
        assert result["remaining"] == "195:00"
        assert result["status"] == "18:45 under målet"
        assert result["under_varsel"] == ""

    def test_no_warning_before_anything_is_removed(self):
        raw = make_raw({"1-1": work("5003", "8:46")}, "170:00")
        assert service.summary(raw, {"prosent": 80, "fjernet": {}})["under_varsel"] == ""

    def test_set_without_per_shift_data_has_no_under_warning(self):
        raw = make_raw({"1-1": dict(work("5003", "8:46"), tj_timer="")})
        assert service.summary(raw, {"prosent": 80, "fjernet": {}})["under_varsel"] == ""

    @pytest.mark.parametrize(
        "valgt, skjema, jobb",
        [(None, False, False), (None, True, True), (False, True, False), (True, False, True)],
    )
    def test_the_choice_on_min_tur_goes_before_the_form(self, valgt, skjema, jobb):
        plan = {"prosent": None, "fjernet": {}, "h_dag_jobb": valgt}
        assert service.summary(H_RAW, plan, h_dag_i_skjema=skjema)["h_dag_jobb"] is jobb

    def test_no_percentage_means_no_target(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["target"] is None
        assert result["remaining"] == "214:34"

    def test_status_without_a_target_says_what_the_shifts_come_to(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["status"] == "Tilsvarer 95,4 %"

    def test_no_status_without_a_target_or_removals(self):
        assert service.summary(RAW, {"prosent": None, "fjernet": {}})["status"] == ""

    def test_works_out_the_percentage_the_remaining_hours_come_to(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["beregnet_prosent"] == "95,4"

    def test_whole_percentage_has_no_decimal(self):
        raw = make_raw({"1-1": work("5003", "45:00")}, "225:00")
        result = service.summary(raw, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["beregnet_prosent"] == "80"

    def test_worked_out_percentage_counts_only_active_removals(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "1234"}})
        assert result["beregnet_prosent"] == ""

    def test_unworked_h_dag_still_counts_its_hours(self):
        result = service.summary(H_RAW, {"prosent": None, "fjernet": {}})
        assert result["h_dager"] == ["6-5"]
        assert result["h_fri"] == ["6-5"]
        assert result["h_dag_jobb"] is False
        assert result["fjernet"] == []
        assert result["total"] == "225:00"
        assert result["remaining"] == "223:20"

    def test_unworked_h_dag_does_not_lower_the_percentage(self):
        assert service.summary(H_RAW, {"prosent": None, "fjernet": {}})["beregnet_prosent"] == ""

    @pytest.mark.parametrize("jobb", [False, True])
    def test_h_dag_choice_changes_no_numbers(self, jobb):
        plan = {"prosent": 80, "fjernet": {"1-1": "5003"}, "h_dag_jobb": jobb}
        result = service.summary(H_RAW, plan)
        assert result["total"] == "225:00"
        assert result["remaining"] == "214:34"
        assert result["beregnet_prosent"] == "95,4"
        assert result["target"] == "180:00"

    def test_unworked_h_dag_counts_as_left_out_of_the_export(self):
        assert service.summary(H_RAW, {"prosent": None, "fjernet": {}})["utelatt"] == "1 vakt er utelatt"

    def test_worked_h_dag_counts_like_any_shift(self):
        result = service.summary(H_RAW, {"prosent": None, "fjernet": {}, "h_dag_jobb": True})
        assert result["h_dag_jobb"] is True
        assert result["h_fri"] == []
        assert result["remaining"] == "223:20"
        assert result["beregnet_prosent"] == ""
        assert result["utelatt"] == ""

    def test_a_stored_removal_on_the_h_dag_is_ignored(self):
        plan = {"prosent": None, "fjernet": {"6-5": "9908001700"}, "h_dag_jobb": True}
        result = service.summary(H_RAW, plan)
        assert result["fjernet"] == []
        assert result["remaining"] == "223:20"

    def test_tur_without_an_h_dag_lists_none(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {}})
        assert result["h_dager"] == []
        assert result["h_fri"] == []
        assert result["remaining"] == "223:20"

    def test_set_without_per_shift_data_leaves_the_h_dag_alone(self):
        raw = make_raw({"6-5": dict(work("9908001700-H", "9:00"), tj_timer="")})
        result = service.summary(raw, {"prosent": None, "fjernet": {}})
        assert result["h_dager"] == []
        assert result["h_fri"] == []

    def test_nothing_removed_works_out_no_percentage(self):
        assert service.summary(RAW, {"prosent": None, "fjernet": {}})["beregnet_prosent"] == ""

    def test_set_without_per_shift_data_works_out_no_percentage(self):
        raw = make_raw({"1-1": dict(RAW["1"]["1"], tj_timer="")})
        result = service.summary(raw, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["beregnet_prosent"] == ""

    def test_utelatt_counts_the_removed_shifts(self):
        one = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "5003"}})
        two = service.summary(
            RAW, {"prosent": None, "fjernet": {"2-3": "5021", "2-4": "5022"}}
        )
        none = service.summary(RAW, {"prosent": None, "fjernet": {}})
        assert one["utelatt"] == "1 vakt er utelatt"
        assert two["utelatt"] == "2 vakter er utelatt"
        assert none["utelatt"] == ""


class TestActiveRemovals:
    """A removal counts only while that day still has the same duty."""

    def test_removal_on_a_day_that_is_now_free_is_ignored(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-2": "5003"}})
        assert result["fjernet"] == []
        assert result["remaining"] == "223:20"

    def test_removal_on_a_day_with_a_different_duty_is_ignored(self):
        result = service.summary(RAW, {"prosent": None, "fjernet": {"1-1": "1234"}})
        assert result["fjernet"] == []
        assert result["remaining"] == "223:20"

    def test_a_changed_suffix_is_still_the_same_duty(self):
        raw = make_raw({"1-1": work("5003_SKNO", "8:46")})
        result = service.summary(raw, {"prosent": None, "fjernet": {"1-1": "5003"}})
        assert result["fjernet"] == ["1-1"]

    def test_a_duty_without_a_number_compares_on_its_whole_name(self):
        raw = make_raw({"1-1": work("RES", "8:00"), "1-2": work("ANNEN", "8:00")})
        result = service.summary(
            raw, {"prosent": None, "fjernet": {"1-1": "RES", "1-2": "RES"}}
        )
        assert result["fjernet"] == ["1-1"]

    def test_fjernet_is_in_rotation_order(self):
        result = service.summary(
            RAW, {"prosent": None, "fjernet": {"2-3": "5021", "1-1": "5003"}}
        )
        assert result["fjernet"] == ["1-1", "2-3"]


class TestPerShiftData:
    def test_a_set_without_per_shift_values_is_not_available(self):
        cell = work("5003", "8:46")
        del cell["tj_timer"]
        raw = make_raw({"1-1": cell})
        assert service.has_per_shift_data(raw) is False
        assert service.summary(raw, {"prosent": None, "fjernet": {}})["available"] is False

    def test_one_missing_value_makes_it_unavailable(self):
        raw = make_raw({"1-1": work("5003", "8:46"), "1-2": work("5004", "")})
        assert service.has_per_shift_data(raw) is False

    def test_a_saved_plan_is_ignored_without_per_shift_values(self):
        cell = work("5003", "8:46")
        del cell["tj_timer"]
        result = service.summary(make_raw({"1-1": cell}), {"prosent": 80, "fjernet": {"1-1": "5003"}})
        assert result["fjernet"] == []
        assert result["utelatt"] == ""

    def test_a_set_with_values_is_available(self):
        assert service.has_per_shift_data(RAW) is True
        assert service.summary(RAW, {"prosent": None, "fjernet": {}})["available"] is True


class TestSetVakt:
    def save(self, user, turnus_set, vakt, fjernet=True, raw=RAW):
        return service.set_vakt(user.id, turnus_set.id, TITLE, raw, vakt, fjernet)

    def test_stores_the_duty_number_without_its_suffix(self, user, turnus_set):
        raw = make_raw({"1-1": work("5003_SKNO", "8:46")})
        assert self.save(user, turnus_set, "1-1", raw=raw)["fjernet"] == {"1-1": "5003"}

    def test_removal_is_kept_in_the_database(self, user, turnus_set):
        self.save(user, turnus_set, "1-1")
        assert service.get_plan(user.id, turnus_set.id, TITLE)["fjernet"] == {"1-1": "5003"}

    def test_a_later_removal_keeps_the_earlier_one(self, user, turnus_set):
        self.save(user, turnus_set, "1-1")
        self.save(user, turnus_set, "4-1")
        saved = service.get_plan(user.id, turnus_set.id, TITLE)["fjernet"]
        assert saved == {"1-1": "5003", "4-1": "9348"}

    def test_first_half_removes_both(self, user, turnus_set):
        assert self.save(user, turnus_set, "2-3")["fjernet"] == {"2-3": "5021", "2-4": "5022"}

    def test_second_half_removes_both(self, user, turnus_set):
        assert self.save(user, turnus_set, "2-4")["fjernet"] == {"2-3": "5021", "2-4": "5022"}

    @pytest.mark.parametrize("half", ["2-3", "2-4"])
    def test_restoring_one_half_restores_both(self, user, turnus_set, half):
        self.save(user, turnus_set, "2-3")
        assert self.save(user, turnus_set, half, fjernet=False)["fjernet"] == {}

    @pytest.mark.parametrize("half", ["6-7", "1-1"])
    def test_double_duty_wraps_from_week_6_to_week_1(self, user, turnus_set, half):
        raw = make_raw(
            {
                "6-7": work("3006", "5:48", first=True),
                "1-1": work("3007", "5:52", receiver=True),
            }
        )
        saved = self.save(user, turnus_set, half, raw=raw)["fjernet"]
        assert saved == {"6-7": "3006", "1-1": "3007"}

    def test_flagged_receiver_with_no_first_half_before_it_goes_alone(self, user, turnus_set):
        # 5053 in R27 OSL_04_ALSTOM week 3: a number that is the second half of
        # a double duty elsewhere, here after an ordinary shift.
        assert self.save(user, turnus_set, "3-7")["fjernet"] == {"3-7": "5053"}

    def test_first_half_with_no_receiver_after_it_goes_alone(self, user, turnus_set):
        raw = make_raw({"1-1": work("3006", "5:48", first=True)})
        assert self.save(user, turnus_set, "1-1", raw=raw)["fjernet"] == {"1-1": "3006"}

    def test_removing_twice_changes_nothing(self, user, turnus_set, db_session):
        self.save(user, turnus_set, "1-1")
        assert self.save(user, turnus_set, "1-1")["fjernet"] == {"1-1": "5003"}
        assert len(plan_rows(db_session)) == 1

    def test_restoring_twice_changes_nothing(self, user, turnus_set):
        self.save(user, turnus_set, "1-1")
        self.save(user, turnus_set, "1-1", fjernet=False)
        assert self.save(user, turnus_set, "1-1", fjernet=False)["fjernet"] == {}

    def test_restoring_with_no_plan_saves_no_row(self, user, turnus_set, db_session):
        self.save(user, turnus_set, "1-1", fjernet=False)
        assert plan_rows(db_session) == []

    @pytest.mark.parametrize("vakt", ["1-2", "9-9", "1", "x-y", "", None])
    def test_a_cell_that_is_not_a_work_day_is_rejected(self, user, turnus_set, db_session, vakt):
        with pytest.raises(ValueError):
            self.save(user, turnus_set, vakt)
        assert plan_rows(db_session) == []

    def test_a_blank_sleep_off_day_is_rejected(self, user, turnus_set):
        raw = make_raw({"1-1": dict(free(), tid=[], start=[])})
        with pytest.raises(ValueError):
            self.save(user, turnus_set, "1-1", raw=raw)


class TestSetProsent:
    @pytest.mark.parametrize("value", [1, 80, 73.5, 100])
    def test_valid_percentages_are_saved(self, user, turnus_set, value):
        service.set_prosent(user.id, turnus_set.id, TITLE, value)
        assert service.get_plan(user.id, turnus_set.id, TITLE)["prosent"] == value

    def test_blank_clears_the_target_and_keeps_the_removals(self, user, turnus_set):
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)
        service.set_prosent(user.id, turnus_set.id, TITLE, 80)
        service.set_prosent(user.id, turnus_set.id, TITLE, None)
        plan = service.get_plan(user.id, turnus_set.id, TITLE)
        assert plan == {"prosent": None, "fjernet": {"1-1": "5003"}, "h_dag_jobb": None}

    @pytest.mark.parametrize(
        "value", [0, 0.5, 100.5, -1, "80", True, math.nan, math.inf, [80]]
    )
    def test_invalid_percentages_are_rejected(self, user, turnus_set, db_session, value):
        with pytest.raises(ValueError):
            service.set_prosent(user.id, turnus_set.id, TITLE, value)
        assert plan_rows(db_session) == []


class TestPlanOwnership:
    def test_users_plans_are_separate(self, user, turnus_set, db_session):
        other = DBUser(username="annenbruker", password="x", is_auth=0)
        db_session.add(other)
        db_session.commit()
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)
        assert service.get_plan(other.id, turnus_set.id, TITLE)["fjernet"] == {}

    def test_a_plan_does_not_apply_to_a_different_tur(self, user, turnus_set):
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)
        assert service.get_plan(user.id, turnus_set.id, "OSL_02")["fjernet"] == {}

    def test_a_plan_does_not_apply_to_a_different_set(self, user, turnus_set, db_session):
        other = TurnusSet(name="T98", year_identifier="T98", is_active=0)
        db_session.add(other)
        db_session.commit()
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)
        assert service.get_plan(user.id, other.id, TITLE)["fjernet"] == {}

    def test_nullstill_removes_the_row(self, user, turnus_set, db_session):
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)
        assert service.nullstill(user.id, turnus_set.id, TITLE) == {"prosent": None, "fjernet": {}, "h_dag_jobb": None}
        assert plan_rows(db_session) == []

    def test_no_plan_reads_as_empty(self, user, turnus_set):
        assert service.get_plan(user.id, turnus_set.id, TITLE) == {"prosent": None, "fjernet": {}, "h_dag_jobb": None}


class TestCleanupPaths:
    @pytest.fixture()
    def plan(self, user, turnus_set):
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "1-1", True)

    def schedule(self, tmp_path, titles):
        path = tmp_path / f"turnus_schedule_{FAKE_YEAR}.json"
        path.write_text(json.dumps([{title: {}} for title in titles]), encoding="utf-8")
        return str(path)

    def test_deleting_the_set_removes_the_plan(self, app, plan, turnus_set, db_session):
        with app.app_context():
            success, message = turnus_service.delete_turnus_set(turnus_set.id)
        assert success, message
        assert plan_rows(db_session) == []

    def test_deleting_the_user_removes_the_plan(self, plan, user, db_session):
        success, _ = user_service.delete_user(user.id)
        assert success
        assert plan_rows(db_session) == []

    def test_a_tur_rename_carries_the_plan_across(self, plan, turnus_set, db_session, tmp_path):
        db_session.add(Shifts(title=TITLE, turnus_set_id=turnus_set.id))
        db_session.commit()
        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, self.schedule(tmp_path, [f"{TITLE}_ALSTOM"])
        )
        assert [row.shift_title for row in plan_rows(db_session)] == [f"{TITLE}_ALSTOM"]

    def test_a_tur_that_is_gone_takes_its_plan_with_it(self, plan, turnus_set, db_session, tmp_path):
        db_session.add(Shifts(title=TITLE, turnus_set_id=turnus_set.id))
        db_session.commit()
        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, self.schedule(tmp_path, ["OSL_99"])
        )
        assert plan_rows(db_session) == []

    def test_a_plan_leaves_favorites_and_choices_alone(self, plan, user, turnus_set, db_session):
        db_session.add(
            Favorites(user_id=user.id, shift_title=TITLE, turnus_set_id=turnus_set.id, order_index=0)
        )
        db_session.add(
            SoknadsskjemaChoice(user_id=user.id, shift_title=TITLE, turnus_set_id=turnus_set.id)
        )
        db_session.commit()
        service.set_vakt(user.id, turnus_set.id, TITLE, RAW, "4-1", True)
        service.nullstill(user.id, turnus_set.id, TITLE)
        db_session.expire_all()
        assert db_session.query(Favorites).count() == 1
        assert db_session.query(SoknadsskjemaChoice).count() == 1


# --- through the routes, on a data store in tmp_path --------------------------


def write_nokkel(path):
    """Two columns of the employer's layout: group g, column c is week 6c + g."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Turnusnøkkel"
    for group in range(6):
        for column in range(2):
            monday = FIRST_MONDAY + datetime.timedelta(weeks=6 * column + group)
            sheet.cell(group * 8 + 1, 8 + column, f"Uke {monday.isocalendar()[1]}")
            for day in range(7):
                date = monday + datetime.timedelta(days=day)
                sheet.cell(
                    group * 8 + 2 + day, 8 + column,
                    datetime.datetime(date.year, date.month, date.day),
                )
    workbook.save(path)


H_DAG = {"6-5": work("9908001700-H", "9:00", "8:00", "17:00")}


def route_schedule(extra=None):
    """No flags here: the data manager sets them from the double-shift file."""
    return make_raw(
        {
            "1-1": work("5003", "8:46", "6:32", "15:18"),
            "2-3": work("5021", "6:43", "16:21", "22:27"),
            "2-4": work("5022", "6:06", "6:25", "12:31"),
            "3-7": work("5053", "9:30", "8:32", "18:02"),
            **(extra or {}),
        }
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.utils.df_utils.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr("app.utils.turnuskalender.AppConfig.turnusfiler_dir", str(tmp_path))
    version_dir = tmp_path / FAKE_YEAR.lower()
    version_dir.mkdir()
    (version_dir / f"double_shifts_{FAKE_YEAR.lower()}.json").write_text(
        json.dumps(
            {
                "dobbelt_tur": [
                    {"first_shift": "5021", "second_shift": "5022"},
                    {"first_shift": "5452", "second_shift": "5053"},
                ],
                "delt_dagsverk": [],
            }
        ),
        encoding="utf-8",
    )
    write_nokkel(version_dir / f"turnusnøkkel_{FAKE_YEAR}_org.xlsx")
    return version_dir


def write_schedule(store, **turer):
    (store / f"turnus_schedule_{FAKE_YEAR}.json").write_text(
        json.dumps([{title: raw} for title, raw in turer.items()]), encoding="utf-8"
    )


@pytest.fixture()
def driver(client, store, turnus_set, db_session):
    """A driver placed on OSL_01, linje 1, and logged in."""
    write_schedule(store, OSL_01=route_schedule())
    u = DBUser(
        username="sjafor",
        email="sjafor@example.com",
        password=user_service.hash_password("password123"),
        is_auth=0,
        email_verified=1,
        rullenummer="9001",
    )
    db_session.add(u)
    db_session.add(
        Innplassering(
            turnus_set_id=turnus_set.id, rullenummer="9001", shift_title=TITLE, linjenummer=1
        )
    )
    db_session.commit()
    login_user(client, "sjafor", "password123")
    return u


def tag_for(html, vakt, name):
    tags = re.findall(rf'<{name}\b[^>]*data-vakt="{vakt}"[^>]*>', html)
    assert len(tags) == 1, f"expected one <{name}> for {vakt}, got {tags}"
    return tags[0]


def nokkel_cell_text(html, vakt):
    row = re.search(rf'<tr\b[^>]*data-vakt="{vakt}"[^>]*>.*?</tr>', html, re.S).group(0)
    cell = re.search(r"<td\s+data-nokkel-cell.*?</td>", row, re.S).group(0)
    return re.sub(r"<[^>]+>", "", cell).strip()


def css_rule(selector):
    css = open(REDUSERT_CSS, encoding="utf-8").read()
    return re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css).group(1)


def mintur(client):
    response = client.get("/mintur")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def event_dates(client):
    response = client.get("/mintur/export_ical")
    assert response.status_code == 200
    return set(re.findall(r"OSL_01-(\d{8})@turnushjelper", response.get_data(as_text=True)))


class TestRoute:
    def post(self, client, turnus_set, **body):
        return client.post(ROUTE, json={"sett": turnus_set.id, **body})

    def test_requires_login(self, client, turnus_set):
        assert self.post(client, turnus_set, vakt="1-1", fjernet=True).status_code == 302

    def test_removing_a_shift_returns_the_summary(self, client, driver, turnus_set):
        response = self.post(client, turnus_set, vakt="1-1", fjernet=True)
        assert response.status_code == 200
        body = response.get_json()
        assert body["fjernet"] == ["1-1"]
        assert body["summary"]["remaining"] == "214:34"

    def test_double_duty_comes_back_as_two_cells_with_real_flags(self, client, driver, turnus_set):
        body = self.post(client, turnus_set, vakt="2-3", fjernet=True).get_json()
        assert body["fjernet"] == ["2-3", "2-4"]
        assert body["summary"]["remaining"] == "210:31"

    def test_restoring_comes_back_empty(self, client, driver, turnus_set):
        self.post(client, turnus_set, vakt="1-1", fjernet=True)
        body = self.post(client, turnus_set, vakt="1-1", fjernet=False).get_json()
        assert body["fjernet"] == []
        assert body["summary"]["remaining"] == "223:20"

    def test_percentage_sets_the_target(self, client, driver, turnus_set):
        body = self.post(client, turnus_set, prosent=80).get_json()
        assert body["summary"]["target"] == "180:00"

    def test_blank_percentage_clears_the_target(self, client, driver, turnus_set):
        self.post(client, turnus_set, prosent=80)
        assert self.post(client, turnus_set, prosent=None).get_json()["summary"]["target"] is None

    def test_worked_out_percentage_follows_each_removal(self, client, driver, turnus_set):
        one = self.post(client, turnus_set, vakt="1-1", fjernet=True).get_json()
        assert one["summary"]["beregnet_prosent"] == "95,4"
        two = self.post(client, turnus_set, vakt="2-3", fjernet=True).get_json()
        assert two["summary"]["beregnet_prosent"] == "89,7"

    def test_worked_out_percentage_is_never_saved_as_a_target(self, client, driver, turnus_set, db_session):
        body = self.post(client, turnus_set, vakt="1-1", fjernet=True).get_json()
        assert body["summary"]["prosent"] is None
        assert body["summary"]["target"] is None
        assert plan_rows(db_session)[0].prosent is None

    def test_invalid_percentage_is_a_400_that_saves_nothing(self, client, driver, turnus_set, db_session):
        assert self.post(client, turnus_set, prosent=150).status_code == 400
        assert plan_rows(db_session) == []

    def test_nullstill_clears_everything(self, client, driver, turnus_set, db_session):
        self.post(client, turnus_set, vakt="1-1", fjernet=True)
        body = self.post(client, turnus_set, nullstill=True).get_json()
        assert body["fjernet"] == []
        assert plan_rows(db_session) == []

    def test_non_work_cell_is_a_400(self, client, driver, turnus_set):
        assert self.post(client, turnus_set, vakt="1-2", fjernet=True).status_code == 400

    @pytest.mark.parametrize("wanted", ["true", 1, None])
    def test_fjernet_must_be_a_boolean(self, client, driver, turnus_set, db_session, wanted):
        assert self.post(client, turnus_set, vakt="1-1", fjernet=wanted).status_code == 400
        assert plan_rows(db_session) == []

    def test_body_with_no_action_is_a_400(self, client, driver, turnus_set):
        assert self.post(client, turnus_set).status_code == 400

    def test_a_body_that_is_not_json_is_a_400(self, client, driver):
        response = client.post(ROUTE, data="ikke json", content_type="application/json")
        assert response.status_code == 400

    def test_a_set_the_driver_is_not_placed_in_is_a_404(self, client, driver, db_session):
        # _pick_record would fall back to the driver's newest set here.
        other = TurnusSet(name="T98", year_identifier="T98", is_active=0)
        db_session.add(other)
        db_session.commit()
        assert self.post(client, other, vakt="1-1", fjernet=True).status_code == 404
        assert plan_rows(db_session) == []

    def test_a_missing_set_is_a_404(self, client, driver):
        assert client.post(ROUTE, json={"vakt": "1-1", "fjernet": True}).status_code == 404

    def test_a_set_without_per_shift_data_is_a_404(self, client, driver, store, turnus_set, db_session):
        raw = route_schedule()
        for week in raw.values():
            if isinstance(week, dict):
                for cell in week.values():
                    del cell["tj_timer"]
        write_schedule(store, OSL_01=raw)
        assert self.post(client, turnus_set, vakt="1-1", fjernet=True).status_code == 404
        assert plan_rows(db_session) == []

    def test_the_tur_comes_from_the_placement_not_the_client(self, client, driver, store, turnus_set, db_session):
        write_schedule(store, OSL_01=route_schedule(), OSL_02=route_schedule())
        self.post(client, turnus_set, vakt="1-1", fjernet=True, shift_title="OSL_02")
        assert [row.shift_title for row in plan_rows(db_session)] == [TITLE]


class TestHelgVarsel:
    def varsel(self, cells=WEEKENDS, fjernet=(), jobb=False):
        raw = make_raw(cells)
        removed = {key: raw[key[0]][key[2]]["dagsverk"] for key in fjernet}
        plan = {"prosent": None, "fjernet": removed, "h_dag_jobb": jobb}
        return service.summary(raw, plan)["helg_varsel"]

    def test_untouched_tur_gets_no_warning(self):
        assert self.varsel() is False

    def test_removing_one_of_two_weekend_shifts_gets_no_warning(self):
        assert self.varsel(fjernet=["1-6"]) is False

    def test_removing_the_last_shift_of_a_weekend_warns(self):
        assert self.varsel(fjernet=["3-6"]) is True

    def test_removing_a_whole_weekend_warns(self):
        assert self.varsel(fjernet=["1-6", "1-7"]) is True

    def test_removing_a_weekday_shift_gets_no_warning(self):
        assert self.varsel({**WEEKENDS, "2-1": weekend("6021")}, ["2-1"]) is False

    def test_warning_stays_when_the_h_dag_is_ticked_by_hand(self):
        assert self.varsel(fjernet=["3-6"], jobb=True) is True

    def summary(self, fjernet=(), jobb=False):
        raw = make_raw(WEEKENDS)
        removed = {key: raw[key[0]][key[2]]["dagsverk"] for key in fjernet}
        return service.summary(raw, {"prosent": None, "fjernet": removed, "h_dag_jobb": jobb})

    def test_too_few_weekends_ticks_the_h_dag(self):
        result = self.summary(["3-6"])
        assert result["h_dag_jobb"] is True
        assert result["h_fri"] == []

    def test_a_forced_h_dag_is_not_counted_as_left_out_of_the_export(self):
        assert self.summary(["3-6"])["utelatt"] == "1 vakt er utelatt"

    def test_enough_weekends_leaves_the_h_dag_unticked(self):
        result = self.summary()
        assert result["h_dag_jobb"] is False
        assert result["h_fri"] == ["6-2"]

    def test_a_hand_ticked_h_dag_stays_ticked_with_enough_weekends(self):
        assert self.summary(jobb=True)["h_dag_jobb"] is True

    def test_the_other_every_second_weekend_counts_too(self):
        cells = {
            "2-6": weekend("6002"),
            "4-7": weekend("6004"),
            "6-6": weekend("6006"),
            "1-2": work("9908001700-H", "9:00", "8:00", "17:00"),
        }
        assert self.varsel(cells) is False

    def test_friday_shift_past_midnight_has_weekend_hours(self):
        cells = {**WEEKENDS, "3-5": work("6035", "8:00", "22:00", "6:00")}
        assert self.varsel(cells, ["3-6"]) is False

    def test_friday_shift_ending_at_17_has_no_weekend_hours(self):
        cells = {**WEEKENDS, "3-5": work("6035", "8:00", "9:00", "17:00")}
        assert self.varsel(cells, ["3-6"]) is True

    def test_friday_shift_ending_after_17_has_weekend_hours(self):
        cells = {**WEEKENDS, "3-5": work("6035", "8:00", "9:30", "17:30")}
        assert self.varsel(cells, ["3-6"]) is False

    def test_monday_shift_starting_before_06_has_weekend_hours(self):
        cells = {**WEEKENDS, "4-1": work("6041", "8:00", "5:40", "13:40")}
        assert self.varsel(cells, ["3-6"]) is False

    def test_monday_shift_starting_at_06_has_no_weekend_hours(self):
        cells = {**WEEKENDS, "4-1": work("6041", "8:00", "6:00", "14:00")}
        assert self.varsel(cells, ["3-6"]) is True

    def test_early_monday_in_week_1_belongs_to_the_weekend_of_week_6(self):
        cells = {
            "2-6": weekend("6002"),
            "4-7": weekend("6004"),
            "1-1": work("6011", "8:00", "5:40", "13:40"),
            "1-2": work("9908001700-H", "9:00", "8:00", "17:00"),
        }
        assert self.varsel(cells) is False
        assert self.varsel(cells, ["1-1"]) is True

    def test_early_monday_does_not_count_for_the_weekend_after_it(self):
        cells = {**WEEKENDS, "3-1": work("6031", "8:00", "5:40", "13:40")}
        assert self.varsel(cells, ["3-6"]) is True

    def test_removed_friday_shift_past_midnight_has_no_weekend_hours(self):
        cells = {**WEEKENDS, "3-5": work("6035", "8:00", "22:00", "6:00")}
        assert self.varsel(cells, ["3-5", "3-6"]) is True

    def test_tur_without_an_h_dag_gets_no_warning(self):
        cells = {key: cell for key, cell in WEEKENDS.items() if key != "6-2"}
        assert self.varsel(cells, ["3-6"]) is False

    def test_the_h_dag_itself_never_counts_as_weekend_hours(self):
        cells = {
            "1-6": weekend("6001"),
            "3-6": work("9908001700-H", "9:00", "8:00", "17:00"),
            "5-7": weekend("6005"),
        }
        assert self.varsel(cells) is True
        assert self.varsel(cells, jobb=True) is True

    def test_set_without_per_shift_data_gets_no_warning(self):
        raw = make_raw({"3-6": dict(weekend("6003"), tj_timer="")})
        assert service.summary(raw, {"prosent": None, "fjernet": {}})["helg_varsel"] is False

    def tag(self, html):
        return re.search(r'<div\b[^>]*id="redusertHelgVarsel"[^>]*>', html).group(0)

    @pytest.fixture()
    def full_tur(self, driver, store):
        extra = {**H_DAG, "1-6": weekend("6001"), "5-6": weekend("6005")}
        write_schedule(store, OSL_01=route_schedule(extra))

    def test_warning_is_hidden_while_every_second_weekend_has_work(self, client, full_tur):
        assert "d-none" in self.tag(mintur(client))

    def test_warning_shows_after_the_weekend_is_removed(self, client, full_tur, turnus_set):
        body = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True}).get_json()
        assert body["summary"]["helg_varsel"] is True
        html = mintur(client)
        assert "d-none" not in self.tag(html)
        assert "annenhver helg" in html
        assert "jobbe H-dagen" in html

    def box(self, html):
        return re.search(r'<input\b[^>]*id="redusertHdag"[^>]*>', html).group(0)

    def test_checkbox_is_free_to_change_with_enough_weekends(self, client, full_tur):
        box = self.box(mintur(client))
        assert "checked" not in box
        assert "disabled" not in box

    def test_removing_the_weekend_ticks_and_locks_the_checkbox(self, client, full_tur, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True})
        box = self.box(mintur(client))
        assert "checked" in box
        assert "disabled" in box

    def test_restoring_the_weekend_gives_the_old_choice_back(self, client, full_tur, turnus_set, db_session):
        forced = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True}).get_json()
        assert forced["summary"]["h_dag_jobb"] is True
        assert plan_rows(db_session)[0].h_dag_jobb is None
        back = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": False}).get_json()
        assert back["summary"]["h_dag_jobb"] is False
        assert back["summary"]["helg_varsel"] is False

    def test_a_forced_h_dag_cannot_be_unticked(self, client, full_tur, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True})
        body = client.post(ROUTE, json={"sett": turnus_set.id, "h_dag_jobb": False}).get_json()
        assert body["summary"]["h_dag_jobb"] is True

    def test_a_forced_h_dag_shows_as_a_normal_shift(self, client, full_tur, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True})
        cell = re.search(r"<td\b[^>]*data-h-dag[^>]*>", mintur(client)).group(0)
        assert "vakt-h-fri" not in cell

    def test_a_forced_h_dag_goes_in_the_calendar(self, client, full_tur, turnus_set):
        before = event_dates(client)
        client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "3-7", "fjernet": True})
        removed_weekend = {d for d in before if d not in event_dates(client)}
        added = event_dates(client) - before
        assert removed_weekend
        assert added

    def test_tur_without_an_h_dag_has_no_warning_box(self, client, driver):
        assert 'id="redusertHelgVarsel"' not in mintur(client)


class TestHDag:
    @pytest.fixture(autouse=True)
    def tur_with_h_dag(self, driver, store):
        extra = {**H_DAG, "1-6": weekend("6001"), "5-6": weekend("6005")}
        write_schedule(store, OSL_01=route_schedule(extra))

    def post(self, client, turnus_set, **body):
        return client.post(ROUTE, json={"sett": turnus_set.id, **body})

    def box(self, html):
        return re.search(r'<input\b[^>]*id="redusertHdag"[^>]*>', html).group(0)

    def cell(self, html):
        return re.search(r"<td\b[^>]*data-h-dag[^>]*>.*?</td>", html, re.S).group(0)

    def row(self, html):
        return re.search(r"<tr\b[^>]*data-h-dag[^>]*>.*?</tr>", html, re.S).group(0)

    def test_checkbox_sits_after_the_buttons_in_the_same_row(self, client):
        html = mintur(client)
        assert html.index('id="redusertNullstill"') < html.index('id="redusertHdag"')
        assert html.index('id="redusertHdag"') < html.index('class="redusert-tall')
        assert "Jobb H-dag" in html

    def test_checkbox_is_not_inside_its_label(self, client):
        # components/buttons.css hides every checkbox inside a label.
        html = mintur(client)
        assert not re.search(r'<label\b(?:(?!</label>).)*id="redusertHdag"', html, re.S)
        assert '<label for="redusertHdag">' in html

    def test_checkbox_is_unticked_by_default(self, client):
        assert "checked" not in self.box(mintur(client))

    def test_checkbox_follows_the_saved_choice(self, client, turnus_set):
        self.post(client, turnus_set, h_dag_jobb=True)
        assert "checked" in self.box(mintur(client))
        self.post(client, turnus_set, h_dag_jobb=False)
        assert "checked" not in self.box(mintur(client))

    def test_unworked_h_dag_shows_only_h_in_the_rotation_table(self, client):
        cell = self.cell(mintur(client))
        assert "vakt-h-fri" in cell.split(">")[0]
        assert '<div class="vakt-h">H</div>' in cell
        assert "vakt-450" not in cell

    def test_worked_h_dag_is_a_normal_cell(self, client, turnus_set):
        self.post(client, turnus_set, h_dag_jobb=True)
        cell = self.cell(mintur(client))
        assert "vakt-h-fri" not in cell.split(">")[0]
        assert "8:00" in cell

    def test_h_dag_cell_cannot_be_clicked_like_a_shift(self, client):
        assert "data-vakt" not in self.cell(mintur(client)).split(">")[0]
        assert "data-vakt" not in self.row(mintur(client)).split(">")[0]

    def test_nokkel_row_follows_the_choice(self, client, turnus_set):
        assert "vakt-h-fri" in self.row(mintur(client)).split(">")[0]
        self.post(client, turnus_set, h_dag_jobb=True)
        assert "vakt-h-fri" not in self.row(mintur(client)).split(">")[0]

    def test_nokkel_cell_text_stays_the_shift_for_the_colour_script(self, client):
        row = self.row(mintur(client))
        cell = re.search(r"<td\s+data-nokkel-cell.*?</td>", row, re.S).group(0)
        assert re.sub(r"<[^>]+>", "", cell).strip() == "8:00 - 17:00"

    def test_nokkel_shows_h(self):
        assert 'content: "H"' in css_rule("tr.vakt-h-fri td[data-nokkel-cell]::before")

    def test_unworked_h_dag_has_the_day_off_colour_in_both_tables(self):
        css = open(REDUSERT_CSS, encoding="utf-8").read()
        rule = re.search(r"([^{}]*)\{[^}]*var\(--color-shift-day-off\)[^}]*\}", css)
        assert "td.vakt-h-fri" in rule.group(1)
        assert "tr.vakt-h-fri td[data-nokkel-cell]" in rule.group(1)

    def test_unworked_h_dag_hides_its_tjt_in_selection_mode(self):
        assert "display: none" in css_rule(".vakt-velger-aktiv td.vakt-h-fri .vakt-tj")

    def test_choice_is_saved_and_changes_no_numbers(self, client, turnus_set, db_session):
        unworked = self.post(client, turnus_set, prosent=80).get_json()["summary"]
        worked = self.post(client, turnus_set, h_dag_jobb=True).get_json()["summary"]
        assert worked["h_dag_jobb"] is True
        for summary in (unworked, worked):
            assert summary["total"] == "225:00"
            assert summary["remaining"] == "223:20"
            assert summary["target"] == "180:00"
        assert plan_rows(db_session)[0].h_dag_jobb == 1

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_choice_must_be_true_or_false(self, client, turnus_set, db_session, value):
        assert self.post(client, turnus_set, h_dag_jobb=value).status_code == 400
        assert plan_rows(db_session) == []

    def test_unticking_without_a_plan_is_saved(self, client, turnus_set, db_session):
        assert self.post(client, turnus_set, h_dag_jobb=False).status_code == 200
        assert plan_rows(db_session)[0].h_dag_jobb == 0

    def mark_form(self, driver, turnus_set, db_session, title=TITLE, h_dag=1):
        db_session.add(
            SoknadsskjemaChoice(
                user_id=driver.id, turnus_set_id=turnus_set.id, shift_title=title, h_dag=h_dag
            )
        )
        db_session.commit()

    def test_j_on_the_form_ticks_the_checkbox(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session)
        html = mintur(client)
        assert "checked" in self.box(html)
        assert "vakt-h-fri" not in self.cell(html).split(">")[0]

    def test_blank_on_the_form_leaves_it_unticked(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session, h_dag=0)
        assert "checked" not in self.box(mintur(client))

    def test_j_on_another_tur_does_not_count(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session, title="OSL_02")
        assert "checked" not in self.box(mintur(client))

    def test_j_from_another_driver_does_not_count(self, client, driver, turnus_set, db_session):
        other = DBUser(username="annen", email="annen@example.com", password="x", is_auth=0)
        db_session.add(other)
        db_session.commit()
        self.mark_form(other, turnus_set, db_session)
        assert "checked" not in self.box(mintur(client))

    def test_j_on_the_form_puts_the_h_dag_in_the_calendar(self, client, driver, turnus_set, db_session):
        without = event_dates(client)
        self.mark_form(driver, turnus_set, db_session)
        assert without < event_dates(client)

    def test_the_driver_can_untick_what_the_form_ticks(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session)
        body = self.post(client, turnus_set, h_dag_jobb=False).get_json()
        assert body["summary"]["h_dag_jobb"] is False
        self.post(client, turnus_set, prosent=80)
        assert "checked" not in self.box(mintur(client))

    def test_unticking_never_changes_the_form(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session)
        self.post(client, turnus_set, h_dag_jobb=False)
        db_session.expire_all()
        assert db_session.query(SoknadsskjemaChoice).one().h_dag == 1

    def test_a_plan_without_a_choice_keeps_following_the_form(self, client, driver, turnus_set, db_session):
        self.post(client, turnus_set, vakt="1-1", fjernet=True)
        assert "checked" not in self.box(mintur(client))
        self.mark_form(driver, turnus_set, db_session)
        assert "checked" in self.box(mintur(client))

    def test_every_answer_uses_the_form(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session)
        body = self.post(client, turnus_set, prosent=80).get_json()
        assert body["summary"]["h_dag_jobb"] is True

    def test_nullstill_goes_back_to_the_form(self, client, driver, turnus_set, db_session):
        self.mark_form(driver, turnus_set, db_session)
        self.post(client, turnus_set, h_dag_jobb=False)
        body = self.post(client, turnus_set, nullstill=True).get_json()
        assert body["summary"]["h_dag_jobb"] is True

    def test_h_dag_cannot_be_removed_as_a_shift(self, client, turnus_set, db_session):
        assert self.post(client, turnus_set, vakt="6-5", fjernet=True).status_code == 400
        assert plan_rows(db_session) == []

    def test_nullstill_clears_the_choice(self, client, turnus_set):
        self.post(client, turnus_set, h_dag_jobb=True)
        body = self.post(client, turnus_set, nullstill=True).get_json()
        assert body["summary"]["h_dag_jobb"] is False

    def test_unworked_h_dag_is_not_in_the_calendar(self, client, turnus_set):
        without = event_dates(client)
        self.post(client, turnus_set, h_dag_jobb=True)
        assert without < event_dates(client)

    def test_saved_choice_survives_other_changes(self, client, turnus_set):
        self.post(client, turnus_set, h_dag_jobb=True)
        self.post(client, turnus_set, prosent=80)
        body = self.post(client, turnus_set, vakt="1-1", fjernet=True).get_json()
        assert body["summary"]["h_dag_jobb"] is True


class TestPage:
    def remove(self, client, turnus_set, vakt):
        response = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": vakt, "fjernet": True})
        assert response.status_code == 200

    def test_panel_shows_the_numbers(self, client, driver, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "prosent": 80})
        self.remove(client, turnus_set, "1-1")
        html = mintur(client)
        assert 'id="redusertPanel"' in html
        assert "225:00" in html
        assert "180:00" in html
        assert "214:34" in html
        assert "Gjenstående timer til 80 %: 34:34" in html
        assert "over målet" not in html

    def test_panel_explains_both_ways_with_clicking_first(self, client, driver):
        html = mintur(client)
        guide = html.index("klikk på vaktene du vil ta ut, så ser du hvilken stillingsprosent det blir")
        other = html.index("Du kan også skrive inn ønsket stillingsprosent")
        assert html.index('id="redusertPanel"') < guide < other < html.index('class="redusert-tall')

    def numbers_row(self, html):
        return re.search(r'<div class="redusert-tall[^"]*"', html).group(0)

    def target_parts(self, html):
        return re.findall(r'<span class="redusert-mal[^"]*"', html)

    def test_numbers_are_hidden_with_no_target_and_nothing_removed(self, client, driver):
        assert "d-none" in self.numbers_row(mintur(client))

    def test_only_the_hours_left_show_with_removals_and_no_target(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        html = mintur(client)
        assert "d-none" not in self.numbers_row(html)
        assert "Tj.t igjen" in html
        assert "214:34" in html
        parts = self.target_parts(html)
        assert len(parts) == 2
        assert all("d-none" in part for part in parts)

    def test_all_the_numbers_show_with_a_target(self, client, driver, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "prosent": 80})
        html = mintur(client)
        assert "d-none" not in self.numbers_row(html)
        parts = self.target_parts(html)
        assert len(parts) == 2
        assert not any("d-none" in part for part in parts)

    def under_varsel(self, html):
        return re.search(r'<div\b[^>]*id="redusertUnderVarsel"[^>]*>(.*?)</div>', html, re.S)

    def test_under_warning_is_hidden_above_180(self, client, driver, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "prosent": 95})
        body = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "2-3", "fjernet": True}).get_json()
        assert body["summary"]["remaining"] == "210:31"
        assert body["summary"]["under_varsel"] == ""
        assert "d-none" in self.under_varsel(mintur(client)).group(0).split(">")[0]

    def test_under_warning_shows_below_180_without_a_target(self, client, driver, store, turnus_set):
        write_schedule(store, OSL_01=route_schedule({"5-2": work("5099", "44:00")}))
        body = client.post(ROUTE, json={"sett": turnus_set.id, "vakt": "5-2", "fjernet": True}).get_json()
        assert body["summary"]["remaining"] == "179:20"
        assert body["summary"]["under_varsel"] == UNDER_VARSEL
        match = self.under_varsel(mintur(client))
        assert "d-none" not in match.group(0).split(">")[0]
        assert UNDER_VARSEL in match.group(1)

    def test_panel_gives_the_script_the_removed_cells_as_json(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "2-3")
        match = re.search(r'data-fjernet="([^"]*)"', mintur(client))
        assert json.loads(html_module.unescape(match.group(1))) == ["2-3", "2-4"]

    @pytest.mark.parametrize("saved, shown", [(80, "80"), (73.5, "73.5")])
    def test_saved_percentage_is_in_the_input(self, client, driver, turnus_set, saved, shown):
        client.post(ROUTE, json={"sett": turnus_set.id, "prosent": saved})
        tag = re.search(r'<input\b[^>]*id="redusertProsent"[^>]*>', mintur(client)).group(0)
        assert f'value="{shown}"' in tag

    def prosent_input(self, html):
        return re.search(r'<input\b[^>]*id="redusertProsent"[^>]*>', html).group(0)

    def test_field_shows_the_worked_out_percentage_without_a_target(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        tag = self.prosent_input(mintur(client))
        assert 'placeholder="95,4"' in tag
        assert 'value=""' in tag

    def test_field_shows_nothing_before_a_shift_is_removed(self, client, driver):
        assert 'placeholder=""' in self.prosent_input(mintur(client))

    def test_typed_target_stays_the_fields_value(self, client, driver, turnus_set):
        client.post(ROUTE, json={"sett": turnus_set.id, "prosent": 80})
        self.remove(client, turnus_set, "1-1")
        assert 'value="80"' in self.prosent_input(mintur(client))

    def test_field_is_labelled_redusert_stilling_with_a_percent_sign_behind(self, client, driver):
        html = mintur(client)
        label = re.search(r'<label class="redusert-prosent".*?</label>', html, re.S).group(0)
        before, after = label.split("/>")
        assert "Redusert stilling" in before
        assert "%" in after
        assert "Stillingsprosent" not in html

    def test_removed_nokkel_row_is_marked(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        assert "vakt-fjernet" in tag_for(mintur(client), "1-1", "tr")

    def test_other_nokkel_rows_are_not_marked(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        assert "vakt-fjernet" not in tag_for(mintur(client), "3-7", "tr")

    def test_removed_rotation_cell_is_marked(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        assert "vakt-fjernet" in tag_for(mintur(client), "1-1", "td")

    def test_other_rotation_cells_are_not_marked(self, client, driver, turnus_set):
        self.remove(client, turnus_set, "1-1")
        assert "vakt-fjernet" not in tag_for(mintur(client), "3-7", "td")

    def test_every_selectable_rotation_cell_can_show_450(self, client, driver):
        html = mintur(client)
        selectable = re.findall(r"<td\b[^>]*data-vakt=", html)
        assert selectable
        assert html.count('<div class="vakt-450">450</div>') == len(selectable)

    def test_rotation_cell_keeps_its_shift_text_for_the_scripts_and_for_restoring(
        self, client, driver, turnus_set
    ):
        self.remove(client, turnus_set, "1-1")
        cell = re.search(r'<td\b[^>]*data-vakt="1-1"[^>]*>.*?</td>', mintur(client), re.S).group(0)
        assert "5003" in cell
        assert 'class="time-text"' in cell

    def test_nokkel_cell_text_stays_the_shift_for_the_colour_script(self, client, driver, turnus_set):
        before = nokkel_cell_text(mintur(client), "1-1")
        self.remove(client, turnus_set, "1-1")
        after = nokkel_cell_text(mintur(client), "1-1")
        assert before
        assert after == before
        assert "450" not in after

    def test_removed_nokkel_cell_shows_450(self):
        assert 'content: "450"' in css_rule("tr.vakt-fjernet td[data-nokkel-cell]::before")

    def test_panel_text_cannot_widen_the_table(self):
        # The column shrinks to its widest content and the table fills the column,
        # so a long help line in the panel used to stretch the table.
        rule = css_rule(".redusert-panel")
        assert "width: 0" in rule
        assert "min-width: 100%" in rule

    def test_day_columns_share_one_width(self, client, driver):
        sizer = css_rule(".mintur-tabell th:not(:first-child)::after")
        assert 'content: "00:00 - 00:00"' in sizer
        assert "visibility: hidden" in sizer
        # It wraps on a phone otherwise, and stops setting the width.
        assert "white-space: nowrap" in sizer
        html = mintur(client)
        assert '<table class="mintur-tabell">' in html
        # A footer cell in a single day column would force that column wider.
        footer = re.search(r"<tfoot>.*?</tfoot>", html, re.S).group(0)
        assert re.findall(r'colspan="(\d+)"', footer) == ["4", "2", "2"]

    def test_removed_shifts_are_no_longer_gray(self):
        assert "#e5e7eb" not in open(REDUSERT_CSS, encoding="utf-8").read()

    def test_removed_shift_has_the_day_off_colour_in_both_tables(self):
        css = open(REDUSERT_CSS, encoding="utf-8").read()
        rule = re.search(r"([^{}]*)\{[^}]*var\(--color-shift-day-off\)[^}]*\}", css)
        assert "td.vakt-fjernet" in rule.group(1)
        assert "tr.vakt-fjernet td[data-nokkel-cell]" in rule.group(1)
        assert "color:" not in rule.group(0).replace("background", "")

    def test_free_days_can_not_be_selected(self, client, driver):
        assert 'data-vakt="1-2"' not in mintur(client)

    def test_rotation_cell_carries_its_tjt_outside_the_classified_text(self, client, driver):
        html = mintur(client)
        assert '<div class="vakt-tj"><span>Tj.t:</span> <b>8:46</b></div>' in html
        # shift-colors.js classifies shifts from the text of these two elements.
        for text_class in ("time-text", "custom-text"):
            for element in re.findall(rf'<div\s+class="{text_class}[^"]*"[^>]*>(.*?)</div>', html, re.S):
                assert "vakt-tj" not in element

    def test_a_stale_removal_shows_as_normal(self, client, driver, store, turnus_set):
        self.remove(client, turnus_set, "1-1")
        changed = route_schedule()
        changed["1"]["1"] = dict(changed["1"]["1"], dagsverk="1234")
        write_schedule(store, OSL_01=changed)
        html = mintur(client)
        assert "vakt-fjernet" not in tag_for(html, "1-1", "tr")
        assert "vakt-fjernet" not in tag_for(html, "1-1", "td")

    def test_panel_is_hidden_without_per_shift_data(self, client, driver, store):
        raw = route_schedule()
        for week in raw.values():
            if isinstance(week, dict):
                for cell in week.values():
                    del cell["tj_timer"]
        write_schedule(store, OSL_01=raw)
        html = mintur(client)
        assert 'id="redusertPanel"' not in html
        assert "data-vakt" not in html
        assert "vakt-450" not in html

    def test_a_saved_plan_is_ignored_without_per_shift_data_and_the_row_is_kept(
        self, client, driver, store, turnus_set, db_session
    ):
        self.remove(client, turnus_set, "1-1")
        raw = route_schedule()
        for week in raw.values():
            if isinstance(week, dict):
                for cell in week.values():
                    del cell["tj_timer"]
        write_schedule(store, OSL_01=raw)
        assert "vakt-fjernet" not in mintur(client)
        assert "20261214" in event_dates(client)
        assert len(plan_rows(db_session)) == 1

    def test_another_tur_on_the_same_driver_shows_no_removals(self, client, driver, store, turnus_set, db_session):
        self.remove(client, turnus_set, "1-1")
        write_schedule(store, OSL_01=route_schedule(), OSL_02=route_schedule())
        db_session.query(Innplassering).filter_by(rullenummer="9001").update({"shift_title": "OSL_02"})
        db_session.commit()
        assert "vakt-fjernet" not in mintur(client)

    def test_export_window_warns_only_when_shifts_are_removed(self, client, driver, turnus_set):
        def note_is_hidden(html):
            return "d-none" in re.search(r'<div\b[^>]*id="calUtelatt"[^>]*>', html).group(0)

        assert note_is_hidden(mintur(client))
        self.remove(client, turnus_set, "1-1")
        after = mintur(client)
        assert not note_is_hidden(after)
        assert "1 vakt er utelatt" in after
        assert "fjernes for hånd" in after

    def test_shared_nokkel_page_does_not_change(self, client, driver, turnus_set):
        def page():
            response = client.get(f"/turnusnokkel/{turnus_set.id}/{TITLE}")
            assert response.status_code == 200
            return re.sub(r'name="csrf-token" content="[^"]*"', "", response.get_data(as_text=True))

        before = page()
        self.remove(client, turnus_set, "1-1")
        assert page() == before
        assert "vakt-fjernet" not in before


class TestCalendarExport:
    def remove(self, client, turnus_set, vakt):
        client.post(ROUTE, json={"sett": turnus_set.id, "vakt": vakt, "fjernet": True})

    def test_removed_shift_drops_every_date_it_runs_on(self, client, driver, turnus_set):
        # Linje 1 runs rotation week 1 in group 0: Monday 14.12.26 and six weeks later.
        before = event_dates(client)
        assert {"20261214", "20270125"} <= before
        self.remove(client, turnus_set, "1-1")
        assert event_dates(client) == before - {"20261214", "20270125"}

    def test_a_double_duty_drops_both_halves(self, client, driver, turnus_set):
        # Rotation week 2 is group 1, starting 21.12.26: Wed 23.12 and Thu 24.12.
        before = event_dates(client)
        assert {"20261223", "20261224"} <= before
        self.remove(client, turnus_set, "2-3")
        assert not {"20261223", "20261224"} & event_dates(client)

    def test_a_stale_removal_keeps_the_shift(self, client, driver, store, turnus_set):
        self.remove(client, turnus_set, "1-1")
        changed = route_schedule()
        changed["1"]["1"] = dict(changed["1"]["1"], dagsverk="1234")
        write_schedule(store, OSL_01=changed)
        assert "20261214" in event_dates(client)
