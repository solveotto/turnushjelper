"""Render tests for the active-set badge and non-active-set warning banner."""

from app.models import TurnusSet
from tests.conftest import login_user


def test_active_badge_and_warning(client, sample_user, db_session):
    active = TurnusSet(name="R26", year_identifier="R26", is_active=1)
    other = TurnusSet(name="Old", year_identifier="R98", is_active=0)
    db_session.add_all([active, other])
    db_session.commit()

    login_user(client, sample_user["username"], sample_user["password"])

    resp = client.get("/favorites")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert ">aktiv</span>" in html  # badge on active set in dropdown
    assert "ikke det aktive turnussettet" not in html  # viewing active set: no warning

    # Switch to the non-active set and check the warning appears
    client.get(f"/switch-year/{other.id}")
    resp = client.get("/favorites")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "ikke det aktive turnussettet" in html
