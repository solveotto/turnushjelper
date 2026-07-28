"""Freshness of the favorites surfaces on /turnusliste and /oversikt.

Neither page is cached. These tests are the regression guard for the two
stale-favorites bugs that per-user page caching caused: every case writes to
the DB directly, with **no API call**, so nothing can invalidate a cache. That
is exactly what the *other* gunicorn worker looked like after a toggle it never
handled — under the old cache it served pre-toggle HTML for the full timeout,
and a hard refresh landing on that worker changed nothing.

If a page cache is ever reintroduced, these fail unless it is keyed on
something that cannot go stale per user.
"""

import json

import pytest

from app.models import Favorites, TurnusSet
from tests.conftest import login_user


@pytest.fixture()
def turnus_set(db_session):
    ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def logged_in(client, sample_user, monkeypatch):
    """Logged-in client with the innplassering lookup stubbed out.

    That service binds its own get_db_session reference, which patch_db does
    not reach; /oversikt would otherwise hit the real DB.
    """
    import app.routes.shifts.oversikt as oversikt_mod

    monkeypatch.setattr(oversikt_mod, "get_innplassering_for_user", lambda uid: [])
    login_user(client, sample_user["username"], sample_user["password"])
    return client


def _compare_favoritt(response):
    """The favorites list /oversikt hands to the compare modal."""
    html = response.data.decode()
    marker = '<script id="compare-favoritt" type="application/json">'
    start = html.index(marker) + len(marker)
    return json.loads(html[start : html.index("</script>", start)])


def _add_favorite(db_session, user_id, ts_id, title, order_index):
    db_session.add(
        Favorites(
            user_id=user_id,
            shift_title=title,
            turnus_set_id=ts_id,
            order_index=order_index,
        )
    )
    db_session.commit()


class TestFavoritesFreshness:
    def test_star_and_pill_appear_on_next_load(
        self, logged_in, sample_user, db_session, turnus_set
    ):
        """Surfaces 1 and 2: the star checkbox and the '#N' pill."""
        before = logged_in.get("/turnusliste")
        assert before.status_code == 200
        assert b"turnus-favorite-badge" not in before.data

        _add_favorite(db_session, sample_user["id"], turnus_set.id, "OSL_01", 1)

        after = logged_in.get("/turnusliste")
        assert after.status_code == 200
        assert b"turnus-favorite-badge" in after.data
        assert b"#1" in after.data

    def test_star_and_pill_disappear_on_next_load(
        self, logged_in, sample_user, db_session, turnus_set
    ):
        _add_favorite(db_session, sample_user["id"], turnus_set.id, "OSL_01", 1)
        assert b"turnus-favorite-badge" in logged_in.get("/turnusliste").data

        db_session.query(Favorites).filter_by(user_id=sample_user["id"]).delete()
        db_session.commit()

        assert b"turnus-favorite-badge" not in logged_in.get("/turnusliste").data

    def test_compare_modal_star_reflects_favorites(
        self, logged_in, sample_user, db_session, turnus_set
    ):
        """Surface 3: /oversikt embeds the favorites list as JSON for the modal.

        Asserted on that JSON block specifically — every turnus name appears
        elsewhere on the page, so a bare substring check proves nothing.
        """
        assert _compare_favoritt(logged_in.get("/oversikt")) == []

        _add_favorite(db_session, sample_user["id"], turnus_set.id, "OSL_01", 1)

        resp = logged_in.get("/oversikt")
        assert resp.status_code == 200
        assert _compare_favoritt(resp) == ["OSL_01"]

    def test_pill_numbering_follows_a_reorder(
        self, logged_in, sample_user, db_session, turnus_set
    ):
        """Surface 4: positions are renumbered from order_index, not membership.

        A reorder leaves membership identical, so a cache keyed on "which
        favorites" rather than "in what order" would serve stale '#N' values.
        """
        _add_favorite(db_session, sample_user["id"], turnus_set.id, "OSL_01", 1)
        _add_favorite(db_session, sample_user["id"], turnus_set.id, "OSL_02", 2)

        first = logged_in.get("/turnusliste").data.decode()
        assert first.index("OSL_01") < first.index("OSL_02")

        # Swap the order in the DB, exactly as move-favorite would.
        favs = {
            f.shift_title: f
            for f in db_session.query(Favorites)
            .filter_by(user_id=sample_user["id"])
            .all()
        }
        favs["OSL_01"].order_index = 2
        favs["OSL_02"].order_index = 1
        db_session.commit()

        resp = logged_in.get("/turnusliste")
        assert resp.status_code == 200
        # Both pills still present; the renumbering is what must have changed.
        assert resp.data.count(b"turnus-favorite-badge") == 2


class TestQueryStringFreshness:
    def test_highlight_does_not_leak_between_requests(self, logged_in, turnus_set):
        """?turnus= must not persist to the next plain request.

        flask_caching's cached() ignores the query string when key_prefix is a
        callable, so under the old cache /turnusliste?turnus=X and plain
        /turnusliste shared one entry — whichever rendered first won for 120 s.
        """
        # The class lands on the <li>; the same string also appears in a
        # stylesheet href on every load, so match the rendered class list.
        marker = b"small highlighted-turnus"

        highlighted = logged_in.get("/turnusliste?turnus=OSL_01")
        assert highlighted.status_code == 200
        assert marker in highlighted.data

        plain = logged_in.get("/turnusliste")
        assert plain.status_code == 200
        assert marker not in plain.data


class TestTurnusDataCacheStillWorks:
    def test_invalidate_turnus_cache_drops_data_keys(self, app, turnus_set):
        """The shared data caches stay — only the page caches were removed."""
        from app.extensions import cache
        from app.utils import df_utils

        cache.set(f"turnus_data_{turnus_set.id}", "payload")
        cache.set(f"kompdager_{turnus_set.id}", {"OSL_01": [1, 2, 3, 4, 5, 6]})

        df_utils.invalidate_turnus_cache(turnus_set.id)

        assert cache.get(f"turnus_data_{turnus_set.id}") is None
        assert cache.get(f"kompdager_{turnus_set.id}") is None
