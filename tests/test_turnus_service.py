"""Tests for app.services.turnus_service."""

from app.models import TurnusSet, Shifts, Favorites
from app.services import turnus_service


class TestCreateAndGet:
    def test_create_and_get_by_year(self, patch_db):
        success, _ = turnus_service.create_turnus_set("OSL 2025", "R25", is_active=True)
        assert success is True

        result = turnus_service.get_turnus_set_by_year("R25")
        assert result is not None
        assert result["name"] == "OSL 2025"
        assert result["is_active"] == 1


class TestSetActive:
    def test_set_active_deactivates_others(self, patch_db):
        turnus_service.create_turnus_set("Set A", "A25", is_active=True)
        turnus_service.create_turnus_set("Set B", "B25", is_active=False)

        set_b = turnus_service.get_turnus_set_by_year("B25")
        turnus_service.set_active_turnus_set(set_b["id"])

        assert turnus_service.get_turnus_set_by_year("A25")["is_active"] == 0
        assert turnus_service.get_turnus_set_by_year("B25")["is_active"] == 1


class TestDelete:
    def test_delete_cascades(self, patch_db, db_session, sample_user):
        turnus_service.create_turnus_set("Del Set", "D25")
        ts = turnus_service.get_turnus_set_by_year("D25")

        # Add a shift and a favorite linked to this set
        db_session.add(Shifts(title="X1", turnus_set_id=ts["id"]))
        db_session.add(Favorites(
            user_id=sample_user["id"], shift_title="X1",
            turnus_set_id=ts["id"], order_index=0,
        ))
        db_session.commit()

        success, _ = turnus_service.delete_turnus_set(ts["id"])
        assert success is True

        assert turnus_service.get_turnus_set_by_year("D25") is None
        assert db_session.query(Shifts).filter_by(turnus_set_id=ts["id"]).count() == 0
        assert db_session.query(Favorites).filter_by(turnus_set_id=ts["id"]).count() == 0
