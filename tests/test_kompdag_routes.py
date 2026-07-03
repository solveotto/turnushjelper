"""Route-level tests for kompdag display in turnusliste and turnusnøkkel.

These depend on the committed R26 static files in app/static/turnusfiler/r26/
(schedule JSON + turnusnøkkel Excel template) and the known OSL_01 per-linje
counts [4, 1, 3, 2, 2, 4] (X/O/T fridager on holidays; blank days adjacent
to night shifts excluded; Sunday holidays and holidays after 12. des of the
final year excluded).
"""

import re

from sqlalchemy.orm import sessionmaker

from app.models import TurnusSet
from tests.conftest import login_user


def _seed_r26(db_session):
    ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


def test_turnusliste_shows_kompdager_max(client, sample_user, db_session):
    _seed_r26(db_session)
    login_user(client, sample_user["username"], sample_user["password"])

    resp = client.get("/turnusliste")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Kompdager" in html
    assert "4 (L1)" in html  # OSL_01: max 4 kompdager on linje 1


def test_turnusnokkel_badges_and_computed_holidays(
    client, sample_user, db_session, monkeypatch
):
    ts = _seed_r26(db_session)
    # turnusnokkel.py imports get_db_session directly, so patch the use site
    # with a session factory bound to the test connection.
    TestSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(
        "app.routes.shifts.turnusnokkel.get_db_session", lambda: TestSession()
    )
    login_user(client, sample_user["username"], sample_user["password"])

    resp = client.get(f"/turnusnokkel/{ts.id}/OSL_01")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    badges = re.findall(r'linje-komp-badge[^>]*>(\d+)</span>', html)
    assert badges == ["4", "1", "3", "2", "2", "4"]

    # Computed §5.13.1 marking must cover days the Excel red font misses:
    # påskeaften and 1. påskedag 2026, plus jul 2025 (turnus year spans two
    # calendar years).
    for holiday in ["04.04.26", "05.04.26", "25.12.25"]:
        assert re.search(rf'date-cell holiday">{re.escape(holiday)}<', html), (
            f"{holiday} not marked as holiday"
        )
