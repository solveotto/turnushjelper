"""TRANSITION_NOTICE: between two ruteterminer the browsing pages show a
notice instead of the old set, while mintur keeps working."""

import pytest

from app.models import TurnusSet
from tests.conftest import login_user

NOTICE = "Venter på R27 turnuser. Forventet onsdag 21. oktober."

PAGES = {
    "/turnusliste": 'data-tour-page="turnusliste"',
    "/favorites": 'data-tour-page="favorites"',
    "/oversikt": 'data-tour-page="compare"',
    "/soknadsskjema": 'data-tour-page="soknadsskjema"',
}


@pytest.fixture()
def active_set(db_session):
    ts = TurnusSet(name="T26", year_identifier="T26", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def notice_on(monkeypatch):
    monkeypatch.setattr("config.AppConfig.TRANSITION_NOTICE", NOTICE)


@pytest.fixture()
def notice_off(monkeypatch):
    monkeypatch.setattr("config.AppConfig.TRANSITION_NOTICE", "")


@pytest.mark.parametrize("path, marker", list(PAGES.items()))
def test_page_shows_notice_instead_of_content(client, sample_user, active_set,
                                              notice_on, path, marker):
    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.get(path)
    assert resp.status_code == 200
    body = resp.data.decode()
    assert NOTICE in body
    assert marker not in body


def test_soknadsskjema_post_is_blocked_too(client, sample_user, active_set, notice_on):
    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.post("/soknadsskjema", data={})
    assert resp.status_code == 200
    assert NOTICE in resp.data.decode()


def test_pages_are_normal_without_notice(client, sample_user, active_set, notice_off):
    login_user(client, sample_user["username"], sample_user["password"])
    body = client.get("/turnusliste").data.decode()
    assert NOTICE not in body
    assert PAGES["/turnusliste"] in body


def test_mintur_is_untouched(client, sample_user, active_set, notice_on, monkeypatch):
    login_user(client, sample_user["username"], sample_user["password"])
    fake = {
        "shift_title": "OSL_01", "linjenummer": 1, "year_identifier": "T26",
        "turnus_set_id": active_set.id,
        "turnus_set": {"id": active_set.id, "year_identifier": "T26"},
        "available_sets": [{"id": active_set.id, "year_identifier": "T26"}],
        "groups": [], "template_found": False, "raw": {}, "dm": _FakeDm(),
    }
    monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data",
                        lambda uid, turnus_set_id=None: fake)
    monkeypatch.setattr("app.routes.shifts.mintur.count_kompdager", lambda sid: None)
    resp = client.get("/mintur")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert NOTICE not in body
    assert 'data-tour-page="mintur"' in body


class _FakeDm:
    import pandas as pd
    df = pd.DataFrame()
