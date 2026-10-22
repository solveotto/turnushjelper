"""TURNUSLISTE_NOTICE: an optional .env message shown as a dismissible
yellow banner above the turnusliste, without replacing the page."""

import pytest

from app.models import TurnusSet
from tests.conftest import login_user

NOTICE = "Husk fristen for søknadsskjema: fredag 30. oktober."


@pytest.fixture()
def active_set(db_session):
    ts = TurnusSet(name="T26", year_identifier="T26", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


def test_banner_shown_above_list_when_set(client, sample_user, active_set, monkeypatch):
    monkeypatch.setattr("config.AppConfig.TURNUSLISTE_NOTICE", NOTICE)
    login_user(client, sample_user["username"], sample_user["password"])
    body = client.get("/turnusliste").data.decode()
    assert NOTICE in body
    assert 'id="turnusliste-notice"' in body
    assert 'data-tour-page="turnusliste"' in body  # page itself still renders


def test_no_banner_when_unset(client, sample_user, active_set, monkeypatch):
    monkeypatch.setattr("config.AppConfig.TURNUSLISTE_NOTICE", "")
    login_user(client, sample_user["username"], sample_user["password"])
    body = client.get("/turnusliste").data.decode()
    assert 'id="turnusliste-notice"' not in body


def test_notice_is_escaped(client, sample_user, active_set, monkeypatch):
    monkeypatch.setattr("config.AppConfig.TURNUSLISTE_NOTICE", "<b>x</b>")
    login_user(client, sample_user["username"], sample_user["password"])
    body = client.get("/turnusliste").data.decode()
    assert "&lt;b&gt;x&lt;/b&gt;" in body
