"""A nøkkel whose groups start in different columns must read the same.

The R27 draft from the union (2026-10-22) had groups 1-4 starting in column I
with H blank, while groups 5-6 started in H like every R26 group. The three
readers of the file — the turnusnøkkel page, the mintur date index and the
kompdag counter — hardcoded H-P, so the page showed an empty first column with
the week labels slid one step left, and weeks 48 and 49 vanished from the
page and from mintur. These tests shift the real R26 file the same way and
require every reader to be unaffected.
"""

import os
import re
import shutil

import openpyxl
import pytest
from sqlalchemy.orm import sessionmaker

from app.models import TurnusSet
from app.utils import kompdag_utils, turnuskalender as tk
from config import AppConfig
from tests.conftest import login_user

_R26_DIR = os.path.join(AppConfig.turnusfiler_dir, "r26")
_R26_NOKKEL = os.path.join(_R26_DIR, "turnusnøkkel_R26_org.xlsx")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_R26_NOKKEL), reason="turnusdata/r26 is not present"
)


def _shift_groups_right(src, dst, groups=(0, 1, 2, 3)):
    """Copy the nøkkel with the given groups moved one column to the right."""
    wb = openpyxl.load_workbook(src)
    ws = wb[tk.SHEET_NAME]
    for g in groups:
        for r in range(g * 8 + 1, g * 8 + 9):
            for c in range(20, 7, -1):  # right to left so nothing is overwritten
                ws.cell(row=r, column=c + 1).value = ws.cell(row=r, column=c).value
            ws.cell(row=r, column=8).value = None
    wb.save(dst)


@pytest.fixture
def shifted_store(tmp_path, monkeypatch):
    """A data store whose r26 is the real one, except for the shifted nøkkel."""
    store = tmp_path / "turnusdata"
    (store / "r26").mkdir(parents=True)
    for name in ("turnus_schedule_R26.json", "turnus_stats_R26.json"):
        shutil.copy(os.path.join(_R26_DIR, name), store / "r26" / name)
    _shift_groups_right(_R26_NOKKEL, store / "r26" / "turnusnøkkel_R26_org.xlsx")
    monkeypatch.setattr(AppConfig, "turnusfiler_dir", str(store))
    return store


def test_shift_fixture_really_shifts(shifted_store):
    rows = tk.load_nokkel_rows("R26")
    assert rows[0][7].value is None and str(rows[0][8].value).startswith("Uke")
    assert str(rows[4 * 8][7].value).startswith("Uke")


def test_date_index_is_unchanged(shifted_store):
    original = tk.build_date_index(rows=_original_rows())
    assert tk.build_date_index("R26") == original
    assert len(original) == 378


def test_holiday_positions_are_unchanged(shifted_store):
    with_shift = kompdag_utils.get_holiday_positions("R26")
    assert with_shift == _original_positions()
    assert with_shift  # not an empty grid


def test_turnusnokkel_page_is_unchanged(
    client, sample_user, db_session, monkeypatch, shifted_store
):
    ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
    db_session.add(ts)
    db_session.commit()
    TestSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(
        "app.routes.shifts.turnusnokkel.get_db_session", lambda: TestSession()
    )
    login_user(client, sample_user["username"], sample_user["password"])

    html = client.get(f"/turnusnokkel/{ts.id}/OSL_01").get_data(as_text=True)

    badges = re.findall(r'linje-komp-badge[^>]*>(\d+)</span>', html)
    assert badges == ["4", "1", "3", "2", "2", "4"]
    # Every group's first week column carries a date (no blank first column)
    # and the ninth week of a shifted group is still there.
    for first_monday in ("15.12.25", "22.12.25", "29.12.25", "05.01.26"):
        assert first_monday in html
    assert "16.11.26" in html  # group 1, column Q after the shift
    assert "23.11.26" in html  # group 2, column Q after the shift


def _original_rows():
    wb = openpyxl.load_workbook(_R26_NOKKEL, data_only=True)
    try:
        return [list(r) for r in wb[tk.SHEET_NAME].iter_rows(min_row=1, max_row=48)]
    finally:
        wb.close()


def _original_positions():
    saved = AppConfig.turnusfiler_dir
    AppConfig.turnusfiler_dir = os.path.dirname(_R26_DIR)
    try:
        return kompdag_utils.get_holiday_positions("R26")
    finally:
        AppConfig.turnusfiler_dir = saved
