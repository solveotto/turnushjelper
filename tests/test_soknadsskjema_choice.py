"""Kolonne 3 (linjeprioritering) in the søknadsskjema.

Since 2026-10 Kolonne 3 holds only the linjer the driver picked, typed in the
skjema or clicked in turnusnøkkel, normalised to "3 1" form. A marked
Kolonne 2 (helg) hides Kolonne 3 without deleting it, because the form treats
the two as alternatives.
"""

import json
import os

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import Favorites, SoknadsskjemaChoice, TurnusSet
from config import AppConfig
from tests.conftest import login_user


@pytest.fixture()
def active_set(db_session, monkeypatch):
    monkeypatch.setattr("config.AppConfig.TRANSITION_NOTICE", "")
    ts = TurnusSet(name="T99", year_identifier="T99", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


def _post_choice(client, field, value, shift_title="OSL_01"):
    return client.post(
        "/api/soknadsskjema-choice",
        data=json.dumps({"shift_title": shift_title, "field": field, "value": value}),
        content_type="application/json",
    )


def _stored(db_session, user_id, shift_title="OSL_01"):
    db_session.expire_all()
    return (
        db_session.query(SoknadsskjemaChoice)
        .filter_by(user_id=user_id, shift_title=shift_title)
        .first()
    )


class TestLinjeprioriteringApi:
    @pytest.mark.parametrize(
        "typed, saved",
        [
            ("3,1", "3 1"),
            ("31", "3 1"),
            ("3 3 7 1x", "3 1"),
            ("3 1 2 4 5 6", "3 1 2 4 5 6"),  # rows padded by the old rule
        ],
    )
    def test_value_is_normalised(self, client, db_session, sample_user, active_set,
                                 typed, saved):
        login_user(client, sample_user["username"], sample_user["password"])

        data = _post_choice(client, "linjeprioritering", typed).get_json()

        assert data["status"] == "success"
        assert data["value"] == saved
        assert _stored(db_session, sample_user["id"]).linjeprioritering == saved

    def test_empty_value_clears(self, client, db_session, sample_user, active_set):
        login_user(client, sample_user["username"], sample_user["password"])
        _post_choice(client, "linjeprioritering", "3 1")

        data = _post_choice(client, "linjeprioritering", "").get_json()

        assert data["value"] == ""
        assert _stored(db_session, sample_user["id"]).linjeprioritering is None

    def test_bool_fields_unaffected(self, client, db_session, sample_user, active_set):
        login_user(client, sample_user["username"], sample_user["password"])

        data = _post_choice(client, "h_dag", True).get_json()

        assert data["status"] == "success"
        assert _stored(db_session, sample_user["id"]).h_dag == 1


class TestSkjemaPage:
    @pytest.fixture(autouse=True)
    def _route_session(self, db_session, monkeypatch):
        # soknadsskjema.py imports get_db_session directly; patch the use site
        TestSession = sessionmaker(bind=db_session.get_bind())
        monkeypatch.setattr(
            "app.routes.shifts.soknadsskjema.get_db_session", lambda: TestSession()
        )

    def _seed(self, db_session, user_id, ts, **choice):
        db_session.add(Favorites(user_id=user_id, shift_title="OSL_01",
                                 turnus_set_id=ts.id, order_index=0))
        db_session.add(SoknadsskjemaChoice(user_id=user_id, turnus_set_id=ts.id,
                                           shift_title="OSL_01", **choice))
        db_session.commit()

    def test_kolonne3_is_an_editable_input(self, client, db_session, sample_user,
                                           active_set):
        self._seed(db_session, sample_user["id"], active_set,
                   linjeprioritering="3 1")
        login_user(client, sample_user["username"], sample_user["password"])

        html = client.get("/soknadsskjema").get_data(as_text=True)

        assert '<td class="priori-cell"><input type="text" class="priori-input"' in html
        assert 'data-shift="OSL_01" data-saved="3 1" value="3 1"' in html
        assert '<span class="print-val">3 1</span>' in html

    def test_kolonne2_hides_but_keeps_kolonne3(self, client, db_session, sample_user,
                                               active_set):
        self._seed(db_session, sample_user["id"], active_set,
                   linje_135=1, linjeprioritering="3 1")
        login_user(client, sample_user["username"], sample_user["password"])

        html = client.get("/soknadsskjema").get_data(as_text=True)

        assert '<td class="priori-cell suppressed">' in html
        # The value is still there, so removing the X brings it back
        assert 'value="3 1"' in html

    def test_print_and_download_go_through_reminder(self, client, sample_user,
                                                    active_set):
        login_user(client, sample_user["username"], sample_user["password"])

        html = client.get("/soknadsskjema").get_data(as_text=True)

        assert 'id="skjema-reminder-modal"' in html
        assert "Du er selv ansvarlig for å sjekke" in html
        # Toolbar and mobile-menu print are bound in JS, behind the reminder
        assert 'onclick="window.print()' not in html
        assert html.count("data-skjema-print>") == 2


_R26_NOKKEL = os.path.join(AppConfig.turnusfiler_dir, "r26", "turnusnøkkel_R26_org.xlsx")


@pytest.mark.skipif(not os.path.exists(_R26_NOKKEL), reason="turnusdata/r26 is not present")
class TestTurnusnokkelNote:
    NOTE = "Kolonne 2 (helg) er merket i søknadsskjemaet"

    def _get(self, client, db_session, sample_user, monkeypatch, **choice):
        ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
        db_session.add(ts)
        db_session.commit()
        if choice:
            db_session.add(SoknadsskjemaChoice(user_id=sample_user["id"],
                                               turnus_set_id=ts.id,
                                               shift_title="OSL_01", **choice))
            db_session.commit()
        TestSession = sessionmaker(bind=db_session.get_bind())
        monkeypatch.setattr(
            "app.routes.shifts.turnusnokkel.get_db_session", lambda: TestSession()
        )
        login_user(client, sample_user["username"], sample_user["password"])
        return client.get(f"/turnusnokkel/{ts.id}/OSL_01").get_data(as_text=True)

    def test_note_when_kolonne2_marked(self, client, db_session, sample_user, monkeypatch):
        html = self._get(client, db_session, sample_user, monkeypatch,
                         linje_246=1, linjeprioritering="3 1")
        assert self.NOTE in html

    def test_no_note_otherwise(self, client, db_session, sample_user, monkeypatch):
        html = self._get(client, db_session, sample_user, monkeypatch,
                         linjeprioritering="3 1")
        assert self.NOTE not in html
