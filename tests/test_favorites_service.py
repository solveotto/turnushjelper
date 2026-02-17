"""Tests for app.services.favorites_service."""

from app.services import favorites_service
from app.models import TurnusSet


class TestAddAndGetFavorites:
    def test_add_and_get(self, patch_db, db_session, sample_user):
        # Create a turnus set for the favorites
        ts = TurnusSet(name="Test Set", year_identifier="T25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        favorites_service.add_favorite(sample_user["id"], "D1", 0, ts.id)
        favorites_service.add_favorite(sample_user["id"], "N2", 1, ts.id)

        lst = favorites_service.get_favorite_lst(sample_user["id"], ts.id)
        assert lst == ["D1", "N2"]

    def test_remove_favorite(self, patch_db, db_session, sample_user):
        ts = TurnusSet(name="Test Set", year_identifier="T25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        favorites_service.add_favorite(sample_user["id"], "D1", 0, ts.id)
        favorites_service.remove_favorite(sample_user["id"], "D1", ts.id)

        lst = favorites_service.get_favorite_lst(sample_user["id"], ts.id)
        assert lst == []


class TestDuplicateHandling:
    def test_add_duplicate_is_idempotent(self, patch_db, db_session, sample_user):
        ts = TurnusSet(name="Test Set", year_identifier="T25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        favorites_service.add_favorite(sample_user["id"], "D1", 0, ts.id)
        # Adding same favorite again should succeed without duplicating
        favorites_service.add_favorite(sample_user["id"], "D1", 1, ts.id)

        lst = favorites_service.get_favorite_lst(sample_user["id"], ts.id)
        assert lst.count("D1") == 1


class TestMaxOrderIndex:
    def test_get_max_ordered_index(self, patch_db, db_session, sample_user):
        ts = TurnusSet(name="Test Set", year_identifier="T25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        # Empty should return 0
        assert favorites_service.get_max_ordered_index(sample_user["id"], ts.id) == 0

        favorites_service.add_favorite(sample_user["id"], "D1", 5, ts.id)
        assert favorites_service.get_max_ordered_index(sample_user["id"], ts.id) == 5
