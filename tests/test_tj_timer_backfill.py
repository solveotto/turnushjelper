"""The script that adds per-shift Tj.t to a stored schedule, and nothing else.

It runs on production data, so these tests are about what it must not do: change
any existing value, write after a mismatch, leave a half-written file, or touch
the database. A fake year and a data store in tmp_path are used throughout.
"""

import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import stat

import pytest

from app.models import DBUser, Favorites, SoknadsskjemaChoice, TurnusSet
from app.services import redusert_stilling_service
from app.services.tj_timer_backfill import backfill
from app.utils.shift_stats import Turnus
from app.utils.timeskjema_parser import parse_timeskjema

FAKE_YEAR = "T99"
ROOT = os.path.dirname(os.path.dirname(__file__))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "timeskjema_sample.xls")
SCRIPT = os.path.join(ROOT, "scripts", "backfill_tj_timer.py")
# 2 turnuser in the fixture x 42 days.
CELLS = 84


def strip_cells(turnuser):
    copied = json.loads(json.dumps(turnuser))
    for entry in copied:
        for turnus in entry.values():
            for week in turnus.values():
                if isinstance(week, dict):
                    for cell in week.values():
                        cell.pop("tj_timer", None)
    return copied


def as_stored():
    """The fixture as a stored schedule from before this key existed."""
    return strip_cells(parse_timeskjema(FIXTURE).turnuser)


def write_stored(store, data):
    # The same call the import and Oppdater writers use.
    with open(store / f"turnus_schedule_{FAKE_YEAR}.json", "w") as f:
        json.dump(data, f, indent=4)


def schedule_path(store):
    return store / f"turnus_schedule_{FAKE_YEAR}.json"


def digest(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def backups(store):
    return [name for name in os.listdir(store) if ".bak-" in name]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.tj_timer_backfill.AppConfig.turnusfiler_dir", str(tmp_path))
    directory = tmp_path / FAKE_YEAR.lower()
    directory.mkdir()
    shutil.copy(FIXTURE, directory / f"turnuser_{FAKE_YEAR}.xls")
    (directory / f"double_shifts_{FAKE_YEAR.lower()}.json").write_text("{}", encoding="utf-8")
    write_stored(directory, as_stored())
    return directory


class TestDryRun:
    def test_reports_what_it_would_do(self, store):
        result = backfill(FAKE_YEAR)
        assert result["problems"] == []
        assert result["cells_to_fill"] == CELLS
        assert result["written"] is False

    def test_changes_no_file_and_makes_no_backup(self, store):
        before = digest(schedule_path(store))
        listing = sorted(os.listdir(store))
        backfill(FAKE_YEAR)
        assert digest(schedule_path(store)) == before
        assert sorted(os.listdir(store)) == listing


class TestWrite:
    def test_adds_the_value_from_the_timeskjema(self, store):
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"] == []
        assert result["written"] is True
        osl01 = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert osl01["1"]["1"]["tj_timer"] == "5:48"
        assert osl01["5"]["6"]["tj_timer"] == "13:38"

    def test_free_days_get_an_empty_value(self, store):
        backfill(FAKE_YEAR, write=True)
        osl01 = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert osl01["1"]["3"]["tj_timer"] == ""
        assert osl01["2"]["2"]["tj_timer"] == ""

    def test_removing_the_key_gives_back_the_original_byte_for_byte(self, store):
        original = schedule_path(store).read_text()
        backfill(FAKE_YEAR, write=True)
        stripped = strip_cells(json.loads(schedule_path(store).read_text()))
        assert json.dumps(stripped, indent=4) == original

    def test_the_file_only_gains_lines(self, store):
        original = schedule_path(store).read_text().splitlines()
        backfill(FAKE_YEAR, write=True)
        changed = schedule_path(store).read_text().splitlines()
        marks = [line[0] for line in difflib.ndiff(original, changed) if line[0] in "+-"]
        assert marks.count("-") == 0
        assert marks.count("+") == CELLS

    def test_the_stats_come_out_the_same(self, store):
        before = Turnus(str(schedule_path(store))).stats_df.to_json()
        backfill(FAKE_YEAR, write=True)
        assert Turnus(str(schedule_path(store))).stats_df.to_json() == before

    def test_an_enriched_dagsverk_keeps_its_suffix(self, store):
        data = as_stored()
        data[0]["OSL_01"]["1"]["1"]["dagsverk"] = "3006_SKNO"
        write_stored(store, data)
        assert backfill(FAKE_YEAR, write=True)["problems"] == []
        osl01 = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert osl01["1"]["1"]["dagsverk"] == "3006_SKNO"
        assert osl01["1"]["1"]["tj_timer"] == "5:48"

    def test_keeps_a_backup_of_the_original(self, store):
        original = schedule_path(store).read_bytes()
        result = backfill(FAKE_YEAR, write=True)
        assert backups(store) == [os.path.basename(result["backup"])]
        assert (store / backups(store)[0]).read_bytes() == original

    def test_keeps_the_files_permissions(self, store):
        os.chmod(schedule_path(store), 0o640)
        backfill(FAKE_YEAR, write=True)
        assert stat.S_IMODE(os.stat(schedule_path(store)).st_mode) == 0o640

    def test_keeps_the_files_group(self, store):
        # A host may give the app read access through the group. A new file gets
        # the writer's default group, and the app would then see an empty set.
        other_groups = [g for g in os.getgroups() if g != os.stat(schedule_path(store)).st_gid]
        if not other_groups:
            pytest.skip("this user is only in one group")
        os.chown(schedule_path(store), -1, other_groups[0])
        backfill(FAKE_YEAR, write=True)
        assert os.stat(schedule_path(store)).st_gid == other_groups[0]

    def test_the_feature_sees_the_set_as_having_per_shift_data(self, store):
        before = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert redusert_stilling_service.has_per_shift_data(before) is False
        backfill(FAKE_YEAR, write=True)
        after = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert redusert_stilling_service.has_per_shift_data(after) is True


def changed_duty(data):
    data[0]["OSL_01"]["1"]["1"]["dagsverk"] = "9999"


def changed_times(data):
    data[0]["OSL_01"]["1"]["1"]["tid"] = ["13:13", "19:02"]


def work_became_free(data):
    data[0]["OSL_01"]["1"]["1"].update(tid=["X"], start=["X"], slutt="", dagsverk="")


def free_became_work(data):
    data[0]["OSL_01"]["1"]["3"].update(tid=["8:00", "16:00"], dagsverk="1234")


def free_code_changed(data):
    data[0]["OSL_01"]["1"]["3"]["tid"] = ["O"]


def missing_title(data):
    del data[1]


def extra_title(data):
    data.append({"OSL_99": data[0]["OSL_01"]})


def changed_total(data):
    data[0]["OSL_01"]["tj_timer"] = "200:00"


def existing_value_differs(data):
    data[0]["OSL_01"]["1"]["1"]["tj_timer"] = "1:00"


def missing_cell(data):
    del data[0]["OSL_01"]["1"]["1"]


class TestRefusals:
    @pytest.mark.parametrize(
        "change",
        [
            changed_duty,
            changed_times,
            work_became_free,
            free_became_work,
            free_code_changed,
            missing_title,
            extra_title,
            changed_total,
            existing_value_differs,
            missing_cell,
        ],
    )
    @pytest.mark.parametrize("write", [False, True])
    def test_any_mismatch_is_a_refusal_with_the_file_untouched(self, store, change, write):
        data = as_stored()
        change(data)
        write_stored(store, data)
        before = digest(schedule_path(store))
        result = backfill(FAKE_YEAR, write=write)
        assert result["problems"]
        assert result["written"] is False
        assert digest(schedule_path(store)) == before
        assert backups(store) == []

    @pytest.mark.parametrize(
        "name",
        [
            f"turnuser_{FAKE_YEAR}.xls",
            f"double_shifts_{FAKE_YEAR.lower()}.json",
            f"turnus_schedule_{FAKE_YEAR}.json",
        ],
    )
    def test_a_missing_file_is_a_refusal(self, store, name):
        os.remove(store / name)
        result = backfill(FAKE_YEAR, write=True)
        assert any(name in problem for problem in result["problems"])
        assert result["written"] is False

    def test_an_unreadable_timeskjema_is_a_refusal(self, store):
        (store / f"turnuser_{FAKE_YEAR}.xls").write_bytes(b"ikke et timeskjema")
        before = digest(schedule_path(store))
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"]
        assert digest(schedule_path(store)) == before

    def test_an_unreadable_schedule_is_a_refusal(self, store):
        schedule_path(store).write_text("{ikke json", encoding="utf-8")
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"]
        assert schedule_path(store).read_text() == "{ikke json"

    def test_a_file_owned_by_someone_else_is_a_refusal(self, store, monkeypatch):
        owner = os.stat(schedule_path(store)).st_uid
        monkeypatch.setattr("app.services.tj_timer_backfill.os.getuid", lambda: owner + 1)
        before = digest(schedule_path(store))
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"]
        assert digest(schedule_path(store)) == before


class TestRerun:
    def test_a_second_run_does_nothing_and_makes_no_second_backup(self, store):
        backfill(FAKE_YEAR, write=True)
        before = digest(schedule_path(store))
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"] == []
        assert result["cells_to_fill"] == 0
        assert result["written"] is False
        assert digest(schedule_path(store)) == before
        assert len(backups(store)) == 1

    def test_a_partly_filled_file_gets_the_rest(self, store):
        data = as_stored()
        data[0]["OSL_01"]["1"]["1"]["tj_timer"] = "5:48"
        write_stored(store, data)
        result = backfill(FAKE_YEAR, write=True)
        assert result["cells_to_fill"] == CELLS - 1
        osl01 = json.loads(schedule_path(store).read_text())[0]["OSL_01"]
        assert osl01["1"]["2"]["tj_timer"] == "5:52"


class TestFailedWrite:
    @pytest.mark.parametrize("step", ["replace", "chown"])
    def test_the_original_is_intact_and_nothing_is_left_behind(self, store, monkeypatch, step):
        def fail(*args):
            raise OSError("disk full")

        monkeypatch.setattr(f"app.services.tj_timer_backfill.os.{step}", fail)
        before = digest(schedule_path(store))
        listing = sorted(os.listdir(store))
        result = backfill(FAKE_YEAR, write=True)
        assert result["problems"]
        assert result["written"] is False
        assert digest(schedule_path(store)) == before
        assert sorted(os.listdir(store)) == listing


class TestDatabaseIsNeverTouched:
    def test_works_with_no_database_and_user_data_is_unchanged(self, store, patch_db, db_session, monkeypatch):
        turnus_set = TurnusSet(name=FAKE_YEAR, year_identifier=FAKE_YEAR, is_active=1)
        user = DBUser(username="favbruker", password="x", is_auth=0)
        db_session.add_all([turnus_set, user])
        db_session.commit()
        db_session.add(
            Favorites(user_id=user.id, shift_title="OSL_01", turnus_set_id=turnus_set.id, order_index=0)
        )
        db_session.add(
            SoknadsskjemaChoice(user_id=user.id, shift_title="OSL_01", turnus_set_id=turnus_set.id)
        )
        db_session.commit()

        def no_database(*args, **kwargs):
            raise AssertionError("the backfill opened a database session")

        monkeypatch.setattr("app.database.SessionLocal", no_database)
        monkeypatch.setattr("app.database.get_db_session", no_database)

        assert backfill(FAKE_YEAR, write=True)["written"] is True

        db_session.expire_all()
        assert db_session.query(Favorites).count() == 1
        assert db_session.query(SoknadsskjemaChoice).count() == 1


class TestScript:
    @pytest.fixture()
    def script(self):
        spec = importlib.util.spec_from_file_location("backfill_tj_timer", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_clean_dry_run_exits_0_and_writes_nothing(self, store, script, capsys):
        before = digest(schedule_path(store))
        assert script.main(["--year", FAKE_YEAR]) == 0
        assert digest(schedule_path(store)) == before
        assert str(CELLS) in capsys.readouterr().out

    def test_write_flag_writes(self, store, script):
        before = digest(schedule_path(store))
        assert script.main(["--year", FAKE_YEAR, "--write"]) == 0
        assert digest(schedule_path(store)) != before

    def test_a_refusal_exits_1_and_says_why(self, store, script, capsys):
        os.remove(store / f"double_shifts_{FAKE_YEAR.lower()}.json")
        assert script.main(["--year", FAKE_YEAR, "--write"]) == 1
        assert f"double_shifts_{FAKE_YEAR.lower()}.json" in capsys.readouterr().out

    def test_the_year_is_case_insensitive(self, store, script):
        assert script.main(["--year", FAKE_YEAR.lower()]) == 0
