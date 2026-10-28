"""Cached turnus data follows the files it was built from, in every worker.

The turnus data and kompdag caches are per gunicorn worker (SimpleCache).
An admin action used to clear them only in the worker that served it, so the
other worker kept serving the old data for up to an hour after Oppdater,
Generer or a nøkkel upload, and the service had to be restarted. The cached
entries now carry the size and mtime of their source files and are rebuilt
when those change, whichever worker changed them.
"""

import json
import os
import shutil

import pytest

from app.models import TurnusSet
from app.utils import df_utils, kompdag_utils

FAKE_YEAR = "T99"
VERSION = FAKE_YEAR.lower()
REAL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "turnusdata", "r27")


def _touch_later(path):
    """Rewrite-proof mtime bump: a same-second rewrite must still be seen."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("config.AppConfig.turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(df_utils.AppConfig, "turnusfiler_dir", str(tmp_path))
    monkeypatch.setattr(kompdag_utils.AppConfig, "turnusfiler_dir", str(tmp_path))
    d = tmp_path / VERSION
    d.mkdir()
    shutil.copy(os.path.join(REAL, "turnus_schedule_R27.json"), d / f"turnus_schedule_{FAKE_YEAR}.json")
    shutil.copy(os.path.join(REAL, "turnus_stats_R27.json"), d / f"turnus_stats_{FAKE_YEAR}.json")
    return d


@pytest.fixture()
def turnus_set(app, db_session, data_dir):
    ts = TurnusSet(
        name=FAKE_YEAR, year_identifier=FAKE_YEAR,
        turnus_file_path=str(data_dir / f"turnus_schedule_{FAKE_YEAR}.json"),
        df_file_path=str(data_dir / f"turnus_stats_{FAKE_YEAR}.json"),
    )
    db_session.add(ts)
    db_session.commit()
    with app.app_context():
        yield ts


def _drop_last_turnus(path):
    with open(path) as f:
        data = json.load(f)
    with open(path, "w") as f:
        json.dump(data[:-1], f)
    _touch_later(path)
    return len(data) - 1


def _flagged_cells(turnus_data):
    return sum(
        1
        for entry in turnus_data
        for weeks in entry.values() if isinstance(weeks, dict)
        for days in weeks.values() if isinstance(days, dict)
        for cell in days.values()
        if isinstance(cell, dict) and (cell.get("is_consecutive_shift") or cell.get("is_consecutive_receiver"))
    )


class TestTurnusData:
    def test_a_changed_schedule_is_reloaded(self, turnus_set, data_dir):
        before = len(df_utils.DataframeManager(turnus_set.id).turnus_data)
        expected = _drop_last_turnus(data_dir / f"turnus_schedule_{FAKE_YEAR}.json")
        after = len(df_utils.DataframeManager(turnus_set.id).turnus_data)
        assert (before, after) == (expected + 1, expected)

    def test_a_new_double_shift_file_is_applied(self, turnus_set, data_dir):
        assert _flagged_cells(df_utils.DataframeManager(turnus_set.id).turnus_data) == 0
        shutil.copy(os.path.join(REAL, "double_shifts_r27.json"), data_dir / f"double_shifts_{VERSION}.json")
        assert _flagged_cells(df_utils.DataframeManager(turnus_set.id).turnus_data) > 0

    def test_unchanged_files_are_served_from_the_cache(self, turnus_set, monkeypatch):
        reads = []
        real_read_json = df_utils.pd.read_json
        monkeypatch.setattr(df_utils.pd, "read_json", lambda p: reads.append(p) or real_read_json(p))
        df_utils.DataframeManager(turnus_set.id)
        df_utils.DataframeManager(turnus_set.id)
        assert len(reads) == 1


class TestKompdager:
    @pytest.fixture()
    def position_reads(self, monkeypatch, data_dir):
        (data_dir / f"turnusnøkkel_{FAKE_YEAR}_org.xlsx").write_bytes(b"nokkel")
        calls = []
        monkeypatch.setattr(kompdag_utils, "get_holiday_positions", lambda y: calls.append(y) or [])
        return calls

    def test_unchanged_files_are_served_from_the_cache(self, turnus_set, position_reads):
        kompdag_utils.count_kompdager(turnus_set.id)
        kompdag_utils.count_kompdager(turnus_set.id)
        assert len(position_reads) == 1

    def test_a_new_nokkel_is_counted_again(self, turnus_set, position_reads, data_dir):
        kompdag_utils.count_kompdager(turnus_set.id)
        _touch_later(data_dir / f"turnusnøkkel_{FAKE_YEAR}_org.xlsx")
        kompdag_utils.count_kompdager(turnus_set.id)
        assert len(position_reads) == 2

    def test_a_changed_schedule_is_counted_again(self, turnus_set, position_reads, data_dir):
        first = kompdag_utils.count_kompdager(turnus_set.id)
        _drop_last_turnus(data_dir / f"turnus_schedule_{FAKE_YEAR}.json")
        second = kompdag_utils.count_kompdager(turnus_set.id)
        assert len(second) == len(first) - 1
