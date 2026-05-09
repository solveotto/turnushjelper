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


from tests.conftest import login_user
from app.models import TurnusSet


class TestLoadMinturData:
    def test_returns_none_when_no_active_set(self, monkeypatch):
        from app.routes.shifts.mintur import _load_mintur_data
        monkeypatch.setattr("app.routes.shifts.mintur.db_utils.get_active_turnus_set", lambda: None)
        monkeypatch.setattr(
            "app.routes.shifts.mintur.get_innplassering_for_user", lambda uid: []
        )
        assert _load_mintur_data(1) is None

    def test_returns_none_when_no_records(self, monkeypatch):
        from app.routes.shifts.mintur import _load_mintur_data
        monkeypatch.setattr(
            "app.routes.shifts.mintur.db_utils.get_active_turnus_set",
            lambda: {"id": 1, "year_identifier": "T26", "name": "Test"},
        )
        monkeypatch.setattr(
            "app.routes.shifts.mintur.get_innplassering_for_user", lambda uid: []
        )
        assert _load_mintur_data(1) is None


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
        monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=fixed&label=Jobb")
        assert resp.status_code == 200
        assert "text/calendar" in resp.content_type
        body = resp.data.decode("utf-8")
        assert "SUMMARY:Jobb" in body
        assert "BEGIN:VEVENT" in body
        assert "PRODID:-//Turnushjelper//NO" in body
        assert "X-WR-CALNAME:Turnus" in body
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
        monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data", lambda uid: fake_data)

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
        monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data", lambda uid: fake_data)

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
        monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data", lambda uid: fake_data)

        resp = client.get("/mintur/export_ical?mode=fixed&label=Jobb")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "BEGIN:VEVENT" not in body
