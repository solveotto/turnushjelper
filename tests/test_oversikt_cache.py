"""Tests for /oversikt cache key function."""
import pytest


class TestOversiktCacheKey:
    def test_returns_per_user_per_ts_key(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: {"id": 42, "name": "R26"},
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/42"

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
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/none"
