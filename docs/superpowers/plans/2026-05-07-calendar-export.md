# Calendar Export (.ics) from Min Tur — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Eksporter til kalender" button to the min tur page that generates a downloadable .ics file of the user's full turnus year, importable into Google Calendar or Outlook.

**Architecture:** A new `GET /mintur/export_ical` route in `app/routes/shifts.py` reuses data loading extracted into `_load_mintur_data()`. A new `_classify_shift_type()` pure function maps shift start/end times to Norwegian labels. The modal in `mintur.html` lets users choose a fixed label ("Jobb") or auto-classification prefix ("Vy: Tidlig", "Vy: Natt").

**Tech Stack:** `icalendar` (new), `openpyxl` (existing), `pytz` (existing), Bootstrap 5 modal (existing), vanilla JS (inline script in template)

---

## File Map

| File | Change |
|------|--------|
| `requirements.txt` | Add `icalendar` |
| `app/routes/shifts.py` | Add `_classify_shift_type()`, extract `_load_mintur_data()`, add `export_ical` route |
| `app/templates/mintur.html` | Add export button (×2) + Bootstrap modal + inline `<script>` |
| `tests/test_mintur_export.py` | New test file |

---

## Task 1: Add `icalendar` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency**

Add `icalendar` as a new line in `requirements.txt` (after `itsdangerous==2.2.0`):

```
icalendar
```

- [ ] **Step 2: Install it**

```bash
pip install icalendar
```

Expected: `Successfully installed icalendar-...`

- [ ] **Step 3: Verify it imports**

```bash
python -c "import icalendar; print(icalendar.__version__)"
```

Expected: version string printed, no error.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add icalendar dependency for .ics calendar export"
```

---

## Task 2: Add `_classify_shift_type()` with tests

**Files:**
- Modify: `app/routes/shifts.py`
- Create: `tests/test_mintur_export.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mintur_export.py`:

```python
"""Tests for calendar export: shift classification and route behaviour."""
import pytest
from app.routes.shifts import _classify_shift_type


class TestClassifyShiftType:
    def test_before_6_is_tidlig(self):
        assert _classify_shift_type("05:30", "13:30") == "Tidlig"

    def test_6_to_8_is_tidlig(self):
        assert _classify_shift_type("07:00", "15:00") == "Tidlig"

    def test_boundary_8_is_dag(self):
        assert _classify_shift_type("08:00", "16:00") == "Dag"

    def test_midday_is_dag(self):
        assert _classify_shift_type("10:30", "18:30") == "Dag"

    def test_afternoon_is_ettermiddag(self):
        assert _classify_shift_type("14:00", "22:00") == "Ettermiddag"

    def test_overnight_ends_after_4_is_natt(self):
        assert _classify_shift_type("22:00", "06:00") == "Natt"

    def test_overnight_ends_before_4_is_ettermiddag(self):
        # Crosses midnight but ends 03:30 — still classified Ettermiddag
        assert _classify_shift_type("23:00", "03:30") == "Ettermiddag"

    def test_overnight_ends_exactly_4_is_natt(self):
        assert _classify_shift_type("22:00", "04:00") == "Natt"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mintur_export.py::TestClassifyShiftType -v
```

Expected: `ImportError` or `AttributeError` — `_classify_shift_type` does not exist yet.

- [ ] **Step 3: Add `_classify_shift_type` to `app/routes/shifts.py`**

Add the function immediately after the `_turnusliste_cache_key` function (before line 40 where `shifts = Blueprint(...)` is defined):

```python
def _classify_shift_type(start_str: str, end_str: str) -> str:
    """Map shift start/end times to a Norwegian shift-type label.

    Uses a simplified 4-label system intentionally different from the
    5-class color system in shift-classifier.js — all pre-08:00 starts
    are "Tidlig" regardless of whether they start before or after 06:00.
    """
    sh, sm = int(start_str[:2]), int(start_str[3:5])
    eh, em = int(end_str[:2]), int(end_str[3:5])
    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em
    overnight = end_mins < start_mins  # end time wraps past midnight

    if start_mins < 8 * 60:
        return "Tidlig"
    if start_mins < 12 * 60:
        return "Dag"
    if overnight and end_mins >= 4 * 60:
        return "Natt"
    return "Ettermiddag"
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
pytest tests/test_mintur_export.py::TestClassifyShiftType -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routes/shifts.py tests/test_mintur_export.py
git commit -m "feat: add _classify_shift_type for calendar export labelling"
```

---

## Task 3: Extract `_load_mintur_data()` helper and update `mintur()`

**Files:**
- Modify: `app/routes/shifts.py` (lines 65–199)
- Modify: `tests/test_mintur_export.py`

The `mintur()` route currently inlines all data-loading logic. We extract this into `_load_mintur_data()` so `export_ical` can reuse it without duplication. We also add two new keys to the data structures that `export_ical` needs:
- `tid` key in each cell dict (raw `["HH:MM", "HH:MM"]` array)
- `date_obj` key in each date dict (raw Python `date` object for arithmetic)

- [ ] **Step 1: Write failing tests for `_load_mintur_data` return-None paths**

Add to `tests/test_mintur_export.py`:

```python
from tests.conftest import login_user
from app.models import TurnusSet


class TestLoadMinturData:
    def test_returns_none_when_no_active_set(self, monkeypatch):
        from app.routes.shifts import _load_mintur_data
        monkeypatch.setattr("app.routes.shifts.db_utils.get_active_turnus_set", lambda: None)
        monkeypatch.setattr(
            "app.routes.shifts.get_innplassering_for_user", lambda uid: []
        )
        assert _load_mintur_data(1) is None

    def test_returns_none_when_no_records(self, monkeypatch):
        from app.routes.shifts import _load_mintur_data
        monkeypatch.setattr(
            "app.routes.shifts.db_utils.get_active_turnus_set",
            lambda: {"id": 1, "year_identifier": "T26", "name": "Test"},
        )
        monkeypatch.setattr(
            "app.routes.shifts.get_innplassering_for_user", lambda uid: []
        )
        assert _load_mintur_data(1) is None
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mintur_export.py::TestLoadMinturData -v
```

Expected: `ImportError` or `AttributeError` — `_load_mintur_data` does not exist yet.

- [ ] **Step 3: Replace the body of `mintur()` with a call to the new helper**

In `app/routes/shifts.py`, add `_load_mintur_data` before `mintur()` and rewrite `mintur()` to call it. Replace lines 65–199 with the following:

```python
def _load_mintur_data(user_id: int) -> dict | None:
    """Load all data needed by both mintur() and export_ical().

    Returns a dict with keys: shift_title, linjenummer, year_identifier,
    turnus_set_id, active_set, groups, template_found.
    Returns None if the user has no innplassering or no active turnus set.

    Each cell dict in groups includes a 'tid' key (raw ["HH:MM","HH:MM"] list).
    Each date dict in groups includes a 'date_obj' key (Python date or None).
    """
    import os

    import openpyxl

    from config import AppConfig

    active_set = db_utils.get_active_turnus_set()
    records = get_innplassering_for_user(user_id)
    if not records or not active_set:
        return None

    user_record = next(
        (r for r in records if r["turnus_set_id"] == active_set["id"]), None
    )
    if not user_record:
        return None

    shift_title = user_record["shift_title"]
    linjenummer = user_record["linjenummer"]
    turnus_set_id = active_set["id"]
    year_identifier = active_set["year_identifier"]

    dm = df_utils.DataframeManager(turnus_set_id)
    raw = next((t[shift_title] for t in dm.turnus_data if shift_title in t), None)
    if not raw:
        return None

    linje_shifts = {}
    for uke_nr, ukedata in sorted(
        [(k, v) for k, v in raw.items() if isinstance(v, dict)],
        key=lambda x: int(x[0]),
    ):
        linje = int(uke_nr)
        linje_shifts[linje] = {}
        for dag_nr, dag_data in ukedata.items():
            if not isinstance(dag_data, dict):
                continue
            tid = dag_data.get("tid", [])
            value = (
                f"{tid[0]} - {tid[1]}" if len(tid) >= 2 else (tid[0] if tid else "")
            )
            linje_shifts[linje][int(dag_nr)] = {
                "value": value,
                "dagsverk": dag_data.get("dagsverk", ""),
                "tid": tid,
            }

    dag_names = ["Man", "Tirs", "Ons", "Tors", "Fre", "Lør", "Søn"]
    template_path = os.path.join(
        AppConfig.turnusfiler_dir,
        year_identifier.lower(),
        f"turnusnøkkel_{year_identifier}_org.xlsx",
    )
    template_found = os.path.exists(template_path)
    groups = []

    _empty_cell = {"value": "", "dagsverk": "", "tid": []}

    if template_found:
        wb = openpyxl.load_workbook(template_path, data_only=True)
        sheet = wb["Turnusnøkkel"]
        all_rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=48)]
        wb.close()
        for g in range(6):
            uke_labels = [
                str(c.value) for c in all_rows[g * 8][7:16] if c.value is not None
            ]
            day_rows = []
            for d in range(7):
                cells = [
                    linje_shifts.get((g + j - 1) % 6 + 1, {}).get(d + 1, _empty_cell)
                    for j in range(1, 7)
                ]
                dates = [
                    {
                        "value": c.value.strftime("%d.%m.%y")
                        if hasattr(c.value, "strftime")
                        else "",
                        "holiday": bool(
                            c.font
                            and c.font.color
                            and c.font.color.type == "rgb"
                            and c.font.color.rgb == "FFFF0000"
                        ),
                        "date_obj": c.value if hasattr(c.value, "strftime") else None,
                    }
                    for c in all_rows[g * 8 + 1 + d][7:16]
                ]
                day_rows.append({"name": dag_names[d], "cells": cells, "dates": dates})
            groups.append({"uke_labels": uke_labels, "day_rows": day_rows})
    else:
        for g in range(6):
            day_rows = [
                {
                    "name": dag_names[d],
                    "cells": [
                        linje_shifts.get((g + j - 1) % 6 + 1, {}).get(
                            d + 1, _empty_cell
                        )
                        for j in range(1, 7)
                    ],
                    "dates": [],
                }
                for d in range(7)
            ]
            groups.append(
                {
                    "uke_labels": [f"Linje {g + 1}"],
                    "day_rows": day_rows,
                }
            )

    return {
        "shift_title": shift_title,
        "linjenummer": linjenummer,
        "year_identifier": year_identifier,
        "turnus_set_id": turnus_set_id,
        "active_set": active_set,
        "groups": groups,
        "template_found": template_found,
        "raw": raw,
        "dm": dm,
    }


@shifts.route("/mintur")
@login_required
def mintur():
    data = _load_mintur_data(int(current_user.get_id()))
    if not data:
        return redirect(url_for("shifts.turnusliste"))

    linje_labels = ["Linje 1", "Linje 2", "Linje 3", "Linje 4", "Linje 5", "Linje 6"]
    df_records = (
        data["dm"].df.to_dict(orient="records") if not data["dm"].df.empty else []
    )
    df_row = next(
        (r for r in df_records if r.get("turnus") == data["shift_title"]), None
    )

    return render_template(
        "mintur.html",
        page_name="Min Turnus",
        shift_title=data["shift_title"],
        linjenummer=data["linjenummer"],
        turnus_data={data["shift_title"]: data["raw"]},
        df_row=df_row,
        linje_labels=linje_labels,
        groups=data["groups"],
        template_found=data["template_found"],
        year_identifier=data["year_identifier"],
        turnus_set_id=data["turnus_set_id"],
        active_set=data["active_set"],
        current_turnus_set=data["active_set"],
        all_turnus_sets=[],
    )
```

- [ ] **Step 4: Run tests to confirm the None-path tests pass and existing tests still pass**

```bash
pytest tests/test_mintur_export.py::TestLoadMinturData -v
pytest tests/ -v --tb=short -q
```

Expected: `TestLoadMinturData` — 2 PASSED. Full suite — no new failures.

- [ ] **Step 5: Commit**

```bash
git add app/routes/shifts.py tests/test_mintur_export.py
git commit -m "refactor: extract _load_mintur_data helper from mintur() route"
```

---

## Task 4: Add `export_ical` route with tests

**Files:**
- Modify: `app/routes/shifts.py`
- Modify: `tests/test_mintur_export.py`

- [ ] **Step 1: Write failing tests for the route**

Add to `tests/test_mintur_export.py`:

```python
class TestExportIcal:
    def test_requires_login(self, client):
        resp = client.get("/mintur/export_ical")
        assert resp.status_code == 302  # redirect to login

    def test_404_when_no_innplassering(self, client, db_session, sample_user):
        # sample_user has no rullenummer → get_innplassering_for_user returns []
        from app.models import TurnusSet
        ts = TurnusSet(name="Test Set", year_identifier="T26", is_active=1)
        db_session.add(ts)
        db_session.commit()
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get("/mintur/export_ical")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Ingen turnusdata funnet"

    def test_404_when_no_active_set(self, client, db_session, sample_user):
        # No active turnus set in DB → 404
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get("/mintur/export_ical")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Ingen turnusdata funnet"

    def test_ics_content_fixed_mode(self, client, monkeypatch, db_session, sample_user):
        """With mocked data, fixed mode produces valid .ics with correct SUMMARY."""
        from datetime import date
        login_user(client, sample_user["username"], sample_user["password"])

        fake_data = {
            "shift_title": "OSL_01",
            "linjenummer": 1,
            "year_identifier": "T26",
            "turnus_set_id": 1,
            "active_set": {"id": 1, "year_identifier": "T26"},
            "template_found": True,
            "groups": [
                {
                    "uke_labels": ["10"],
                    "day_rows": [
                        {
                            "name": "Man",
                            "cells": [
                                {"value": "07:30 - 15:30", "dagsverk": "3006", "tid": ["07:30", "15:30"]},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                            ],
                            "dates": [
                                {"value": "02.03.26", "holiday": False, "date_obj": date(2026, 3, 2)},
                            ],
                        }
                    ],
                }
            ],
        }
        monkeypatch.setattr("app.routes.shifts._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=fixed&label=Jobb")
        assert resp.status_code == 200
        assert "text/calendar" in resp.content_type
        body = resp.data.decode("utf-8")
        assert "SUMMARY:Jobb" in body
        assert "BEGIN:VEVENT" in body
        assert "PRODID:-//Turnushjelper//NO" in body
        assert "X-WR-CALNAME:Turnusplan T26" in body
        assert "turnusplan_t26.ics" in resp.headers["Content-Disposition"]

    def test_ics_content_auto_mode(self, client, monkeypatch, db_session, sample_user):
        """Auto mode with prefix 'Vy' produces 'Vy: Dag' summary for 09:00–17:00 shift."""
        from datetime import date
        login_user(client, sample_user["username"], sample_user["password"])

        fake_data = {
            "shift_title": "OSL_01",
            "linjenummer": 1,
            "year_identifier": "T26",
            "turnus_set_id": 1,
            "active_set": {"id": 1, "year_identifier": "T26"},
            "template_found": True,
            "groups": [
                {
                    "uke_labels": ["10"],
                    "day_rows": [
                        {
                            "name": "Man",
                            "cells": [
                                {"value": "09:00 - 17:00", "dagsverk": "3006", "tid": ["09:00", "17:00"]},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                            ],
                            "dates": [
                                {"value": "02.03.26", "holiday": False, "date_obj": date(2026, 3, 2)},
                            ],
                        }
                    ],
                }
            ],
        }
        monkeypatch.setattr("app.routes.shifts._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=auto&label=Vy")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "SUMMARY:Vy: Dag" in body

    def test_overnight_shift_spans_two_days(self, client, monkeypatch, db_session, sample_user):
        """Overnight shift (22:00–06:00) has DTEND on the next calendar day."""
        from datetime import date
        login_user(client, sample_user["username"], sample_user["password"])

        fake_data = {
            "shift_title": "OSL_01",
            "linjenummer": 1,
            "year_identifier": "T26",
            "turnus_set_id": 1,
            "active_set": {"id": 1, "year_identifier": "T26"},
            "template_found": True,
            "groups": [
                {
                    "uke_labels": ["10"],
                    "day_rows": [
                        {
                            "name": "Man",
                            "cells": [
                                {"value": "22:00 - 06:00", "dagsverk": "3006", "tid": ["22:00", "06:00"]},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                            ],
                            "dates": [
                                {"value": "02.03.26", "holiday": False, "date_obj": date(2026, 3, 2)},
                            ],
                        }
                    ],
                }
            ],
        }
        monkeypatch.setattr("app.routes.shifts._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=fixed&label=Nattjobb")
        body = resp.data.decode("utf-8")
        # DTEND must be on 20260303 (the day after 20260302)
        assert "20260303T060000" in body

    def test_days_off_excluded(self, client, monkeypatch, db_session, sample_user):
        """Days with empty tid produce no VEVENT."""
        from datetime import date
        login_user(client, sample_user["username"], sample_user["password"])

        fake_data = {
            "shift_title": "OSL_01",
            "linjenummer": 1,
            "year_identifier": "T26",
            "turnus_set_id": 1,
            "active_set": {"id": 1, "year_identifier": "T26"},
            "template_found": True,
            "groups": [
                {
                    "uke_labels": ["10"],
                    "day_rows": [
                        {
                            "name": "Man",
                            "cells": [
                                {"value": "", "dagsverk": "", "tid": []},  # day off
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                                {"value": "", "dagsverk": "", "tid": []},
                            ],
                            "dates": [
                                {"value": "02.03.26", "holiday": False, "date_obj": date(2026, 3, 2)},
                            ],
                        }
                    ],
                }
            ],
        }
        monkeypatch.setattr("app.routes.shifts._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=fixed&label=Jobb")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "BEGIN:VEVENT" not in body
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mintur_export.py::TestExportIcal -v
```

Expected: route tests fail with 404 (route doesn't exist yet).

- [ ] **Step 3: Add the `export_ical` route to `app/routes/shifts.py`**

Add immediately after the `mintur()` function (before the `turnusliste` route at line ~202):

```python
@shifts.route("/mintur/export_ical")
@login_required
def export_ical():
    from datetime import datetime, timedelta

    import pytz
    from icalendar import Calendar, Event

    mode = request.args.get("mode", "fixed")
    label = request.args.get("label", "Jobb")

    data = _load_mintur_data(int(current_user.get_id()))
    if not data or not data["template_found"]:
        from flask import jsonify
        return jsonify({"error": "Ingen turnusdata funnet"}), 404

    _COLORS = {
        "Tidlig": "#4986E7",
        "Dag": "#33B679",
        "Ettermiddag": "#F6BF26",
        "Natt": "#616161",
    }

    oslo = pytz.timezone("Europe/Oslo")
    cal = Calendar()
    cal.add("prodid", "-//Turnushjelper//NO")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Turnusplan {data['year_identifier']}")
    cal.add("x-wr-timezone", "Europe/Oslo")

    linjenummer = data["linjenummer"]
    shift_title = data["shift_title"]

    for group in data["groups"]:
        for day_row in group["day_rows"]:
            cell = day_row["cells"][linjenummer - 1]
            tid = cell.get("tid", [])
            if len(tid) < 2:
                continue

            start_str, end_str = tid[0], tid[1]
            sh, sm = int(start_str[:2]), int(start_str[3:5])
            eh, em = int(end_str[:2]), int(end_str[3:5])
            overnight = (eh * 60 + em) < (sh * 60 + sm)

            for date_entry in day_row["dates"]:
                date_obj = date_entry.get("date_obj")
                if not date_obj:
                    continue

                work_date = date_obj.date() if hasattr(date_obj, "date") else date_obj
                end_date = work_date + timedelta(days=1) if overnight else work_date

                start_dt = oslo.localize(
                    datetime(work_date.year, work_date.month, work_date.day, sh, sm)
                )
                end_dt = oslo.localize(
                    datetime(end_date.year, end_date.month, end_date.day, eh, em)
                )

                if mode == "auto":
                    shift_type = _classify_shift_type(start_str, end_str)
                    summary = f"{label}: {shift_type}"
                    color = _COLORS.get(shift_type)
                else:
                    summary = label
                    color = None

                event = Event()
                event.add("summary", summary)
                event.add("dtstart", start_dt)
                event.add("dtend", end_dt)
                event.add(
                    "uid",
                    f"{shift_title}-{work_date.strftime('%Y%m%d')}@turnushjelper",
                )
                if color:
                    event.add("color", color)
                cal.add_component(event)

    filename = f"turnusplan_{data['year_identifier'].lower()}.ics"
    from flask import current_app
    return current_app.response_class(
        cal.to_ical(),
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/test_mintur_export.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
pytest tests/ -q
```

Expected: no failures introduced.

- [ ] **Step 6: Commit**

```bash
git add app/routes/shifts.py tests/test_mintur_export.py
git commit -m "feat: add /mintur/export_ical route for .ics calendar download"
```

---

## Task 5: Add button and modal to `mintur.html`

**Files:**
- Modify: `app/templates/mintur.html`

- [ ] **Step 1: Add the export button to the `mobile_print` block**

In `app/templates/mintur.html`, find the `{% block mobile_print %}` block (lines 3–16). Add the export button after the "Skriv ut turnusnøkkel" `<li>`, inside the same `{% if template_found %}` guard:

```html
{% if template_found %}
<li>
    <a class="dropdown-item" href="{{ url_for('shifts.turnusnokkel_view', turnus_set_id=turnus_set_id, turnus_name=shift_title) }}" target="_blank">
        <i class="bi bi-printer"></i> Skriv ut turnusnøkkel
    </a>
</li>
<li>
    <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#exportCalModal">
        <i class="bi bi-calendar-plus"></i> Eksporter til kalender
    </a>
</li>
{% endif %}
```

- [ ] **Step 2: Add a desktop-visible button in the main content header**

Find the title `<div>` in the main content area (around line 41–52) — it contains the shift title and the "Linje X" badge. Add a button after the badge, still inside the `{% if template_found %}` context (wrap it if needed):

```html
<!-- Title -->
<div class="d-flex align-items-center justify-content-between py-1 mb-2">
    <div data-turnus="{{ shift_title }}">
        <h5 class="h4-hover t-name">
            {{ shift_title | display_name }}
        </h5>
    </div>
    <div class="d-flex align-items-center gap-2">
        <span class="badge bg-primary">Linje {{ linjenummer }}</span>
        {% if template_found %}
        <button
            type="button"
            class="btn btn-sm btn-outline-secondary d-none d-sm-inline-flex align-items-center gap-1"
            data-bs-toggle="modal"
            data-bs-target="#exportCalModal"
        >
            <i class="bi bi-calendar-plus"></i> Eksporter til kalender
        </button>
        {% endif %}
    </div>
</div>
```

- [ ] **Step 3: Add the Bootstrap modal and inline script before `{% endblock %}`**

Add before the closing `{% endblock %}` tag at the end of `mintur.html` (before the existing `<script type="module">` block):

```html
{% if template_found %}
<!-- Calendar export modal -->
<div class="modal fade" id="exportCalModal" tabindex="-1" aria-labelledby="exportCalModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="exportCalModalLabel">
                    <i class="bi bi-calendar-plus me-2"></i>Eksporter til kalender
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Lukk"></button>
            </div>
            <div class="modal-body">

                <!-- Step 1 -->
                <p class="fw-semibold mb-1">Steg 1 — Opprett en egen kalender</p>
                <p class="small text-muted mb-1">
                    Opprett en ny kalender kalt
                    <code>Turnusplan {{ year_identifier }}</code>
                    i Google Calendar eller Outlook <em>før</em> du importerer.
                </p>
                <p class="small text-muted mb-3">
                    <i class="bi bi-arrow-counterclockwise me-1"></i>
                    <strong>For å angre:</strong> slett hele
                    <code>Turnusplan {{ year_identifier }}</code>-kalenderen.
                    Dette påvirker ikke andre kalendere.
                </p>

                <!-- Step 2 -->
                <p class="fw-semibold mb-1">Steg 2 — Velg hendelsestittel</p>
                <div class="mb-2">
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="calExportMode"
                               id="calModeFixed" value="fixed" checked>
                        <label class="form-check-label" for="calModeFixed">Fast tekst</label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="calExportMode"
                               id="calModeAuto" value="auto">
                        <label class="form-check-label" for="calModeAuto">Automatisk skifttype</label>
                    </div>
                </div>

                <div id="calFixedInput" class="mb-3">
                    <input type="text" class="form-control form-control-sm" id="calFixedLabel"
                           value="Jobb" placeholder="Jobb" maxlength="60">
                    <div class="form-text">Alle hendelser får denne tittelen.</div>
                </div>

                <div id="calAutoInput" class="mb-3 d-none">
                    <input type="text" class="form-control form-control-sm" id="calAutoPrefix"
                           value="Vy" placeholder="Vy" maxlength="40">
                    <div class="form-text">
                        Eksempel:
                        <span id="calAutoPreview" class="fw-semibold">Vy: Tidlig, Vy: Natt</span>
                    </div>
                </div>

                <!-- Step 3 -->
                <p class="fw-semibold mb-1">Steg 3 — Last ned</p>
                <a id="calDownloadBtn" href="#" class="btn btn-primary btn-sm mb-3">
                    <i class="bi bi-download me-1"></i>Last ned .ics-fil
                </a>

                <!-- Step 4: import instructions -->
                <div class="accordion accordion-flush" id="calImportAccordion">
                    <div class="accordion-item">
                        <h2 class="accordion-header">
                            <button class="accordion-button collapsed py-2 small" type="button"
                                    data-bs-toggle="collapse" data-bs-target="#calImportInstructions">
                                Hvordan importere?
                            </button>
                        </h2>
                        <div id="calImportInstructions" class="accordion-collapse collapse"
                             data-bs-parent="#calImportAccordion">
                            <div class="accordion-body small">
                                <p class="fw-semibold mb-1">Google Calendar</p>
                                <ol class="mb-3 ps-3">
                                    <li>Åpne Google Calendar på PC</li>
                                    <li>Klikk tannhjulet → <em>Innstillinger</em></li>
                                    <li>Velg <em>Importer &amp; eksporter</em> → <em>Importer</em></li>
                                    <li>Velg den nedlastede filen og kalender <code>Turnusplan {{ year_identifier }}</code></li>
                                </ol>
                                <p class="fw-semibold mb-1">Outlook</p>
                                <ol class="ps-3">
                                    <li>Åpne Outlook</li>
                                    <li>Fil → <em>Åpne og eksporter</em> → <em>Importer/eksporter</em></li>
                                    <li>Velg <em>Importer en iCalendar-fil (.ics)</em></li>
                                    <li>Velg den nedlastede filen</li>
                                </ol>
                            </div>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </div>
</div>

<script>
(function () {
    const fixedRadio = document.getElementById("calModeFixed");
    const autoRadio = document.getElementById("calModeAuto");
    const fixedInput = document.getElementById("calFixedInput");
    const autoInput = document.getElementById("calAutoInput");
    const fixedLabel = document.getElementById("calFixedLabel");
    const autoPrefix = document.getElementById("calAutoPrefix");
    const preview = document.getElementById("calAutoPreview");
    const downloadBtn = document.getElementById("calDownloadBtn");

    function updatePreview() {
        const p = autoPrefix.value.trim() || "Vy";
        preview.textContent = `${p}: Tidlig, ${p}: Dag, ${p}: Ettermiddag, ${p}: Natt`;
    }

    function updateDownloadUrl() {
        const mode = autoRadio.checked ? "auto" : "fixed";
        const label = autoRadio.checked
            ? encodeURIComponent(autoPrefix.value.trim() || "Vy")
            : encodeURIComponent(fixedLabel.value.trim() || "Jobb");
        downloadBtn.href = `/mintur/export_ical?mode=${mode}&label=${label}`;
    }

    function toggleMode() {
        if (autoRadio.checked) {
            fixedInput.classList.add("d-none");
            autoInput.classList.remove("d-none");
        } else {
            autoInput.classList.add("d-none");
            fixedInput.classList.remove("d-none");
        }
        updatePreview();
        updateDownloadUrl();
    }

    fixedRadio.addEventListener("change", toggleMode);
    autoRadio.addEventListener("change", toggleMode);
    fixedLabel.addEventListener("input", updateDownloadUrl);
    autoPrefix.addEventListener("input", function () {
        updatePreview();
        updateDownloadUrl();
    });

    // Set initial URL
    updateDownloadUrl();
})();
</script>
{% endif %}
```

- [ ] **Step 4: Verify the page renders without errors**

Start the dev server and navigate to `/mintur` as a logged-in user with innplassering:

```bash
python run.py
```

Open `http://localhost:8080/mintur`. Check:
- "Eksporter til kalender" button visible in header (desktop) and mobile menu
- Clicking it opens the modal
- Toggling the radio hides/shows the correct input
- Typing in the prefix field updates the preview label live
- The download link has the correct URL (inspect in browser)

- [ ] **Step 5: Test the full download flow**

1. In the modal, leave "Fast tekst" selected with label "Jobb" and click "Last ned .ics-fil"
2. Open the downloaded file in a text editor — verify:
   - `PRODID:-//Turnushjelper//NO` present
   - `X-WR-CALNAME:Turnusplan {year_identifier}` present
   - At least one `BEGIN:VEVENT` block
   - `SUMMARY:Jobb` in each event
   - Dates match the turnusnøkkel dates shown on the page

3. Switch to "Automatisk skifttype", type prefix "Vy", download again
4. Open the file — verify events have summaries like `SUMMARY:Vy: Tidlig` or `SUMMARY:Vy: Natt`

- [ ] **Step 6: Import into Google Calendar to verify**

1. Create a calendar called "Turnusplan Test" in Google Calendar
2. Import the downloaded .ics
3. Confirm events appear on the correct dates with correct times
4. Confirm existing events are unaffected

- [ ] **Step 7: Commit**

```bash
git add app/templates/mintur.html
git commit -m "feat: add calendar export button and modal to min tur page"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass, including all 8 `TestClassifyShiftType`, 2 `TestLoadMinturData`, and 6 `TestExportIcal`.

- [ ] **Step 2: Manual edge cases**

- Navigate to `/mintur/export_ical` directly (not logged in) → should redirect to login
- Log in as a user with no `rullenummer` set → `/mintur/export_ical` returns `{"error": "Ingen turnusdata funnet"}` (404)
- Verify the mintur page still renders identically to before (the refactor to use `_load_mintur_data()` should be transparent)
