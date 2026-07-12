"""Tests for /oversikt cache key function."""
import pytest

from app.models import TurnusSet
from tests.conftest import login_user


class TestOversiktCacheKey:
    def test_returns_per_user_per_ts_key(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: {"id": 42, "name": "R26"},
        )
        # Pin the generation so the key is deterministic regardless of any
        # generation bumps left in the shared SimpleCache by other tests.
        monkeypatch.setattr(
            "app.utils.df_utils.get_turnus_cache_generation", lambda tsid: 0
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/42/g0"

    def test_bypasses_cache_when_flashes_pending(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: {"id": 42, "name": "R26"},
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr(
            "app.routes.shifts.oversikt.session",
            {"_flashes": [("info", "saved")]},
        )

        key = _oversikt_cache_key()
        assert key.startswith("view/oversikt/7/42/flash/")

    def test_handles_no_turnus_set(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: None,
        )
        monkeypatch.setattr(
            "app.utils.df_utils.get_turnus_cache_generation", lambda tsid: 0
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/none/g0"


class TestOversiktViewCacheInvalidation:
    def test_turnus_refresh_rerenders_cached_page(
        self, client, sample_user, db_session, monkeypatch
    ):
        """A turnus refresh bumps the view-cache generation, so the next
        /oversikt request re-renders instead of serving the stale cached page.

        SimpleCache cannot enumerate keys, so per-user page caches can't be
        deleted directly; the generation counter baked into the key is what
        makes the invalidation reach every user at once.
        """
        from app.utils import df_utils
        import app.routes.shifts.oversikt as oversikt_mod

        ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
        db_session.add(ts)
        db_session.commit()

        # Isolate the cache behaviour from the innplassering DB lookup, whose
        # service binds its own get_db_session reference (not patched here).
        monkeypatch.setattr(
            oversikt_mod, "get_innplassering_for_user", lambda uid: []
        )

        # Spy on the view body: render_template runs on a cache miss, not a hit.
        render_calls = {"n": 0}
        real_render = oversikt_mod.render_template

        def counting_render(*args, **kwargs):
            render_calls["n"] += 1
            return real_render(*args, **kwargs)

        monkeypatch.setattr(oversikt_mod, "render_template", counting_render)

        login_user(client, sample_user["username"], sample_user["password"])

        assert client.get("/oversikt").status_code == 200
        assert render_calls["n"] == 1  # first load rendered the page

        assert client.get("/oversikt").status_code == 200
        assert render_calls["n"] == 1  # second load served from cache

        df_utils.invalidate_turnus_cache(ts.id)

        assert client.get("/oversikt").status_code == 200
        assert render_calls["n"] == 2  # generation bump forced a re-render
