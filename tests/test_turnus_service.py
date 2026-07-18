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

        success, msg = turnus_service.delete_turnus_set(ts["id"])
        assert success is True, msg

        assert turnus_service.get_turnus_set_by_year("D25") is None
        assert db_session.query(Shifts).filter_by(turnus_set_id=ts["id"]).count() == 0
        assert db_session.query(Favorites).filter_by(turnus_set_id=ts["id"]).count() == 0

    def test_delete_removes_innplassering(self, patch_db, db_session):
        from app.models import Innplassering

        turnus_service.create_turnus_set("Del Set", "D25")
        ts = turnus_service.get_turnus_set_by_year("D25")

        db_session.add(Innplassering(
            turnus_set_id=ts["id"], rullenummer="123", shift_title="X1",
        ))
        db_session.commit()

        success, msg = turnus_service.delete_turnus_set(ts["id"])
        assert success is True, msg

        assert db_session.query(Innplassering).filter_by(turnus_set_id=ts["id"]).count() == 0


class TestDeleteTurnusSetCleansUpSoknadsskjema:
    def test_delete_turnus_set_removes_soknadsskjema_choices(self, patch_db, db_session):
        from app.models import DBUser, SoknadsskjemaChoice, TurnusSet
        from app.services.user_service import hash_password

        ts = TurnusSet(name="R26", year_identifier="R26del", is_active=1)
        db_session.add(ts)
        db_session.commit()

        user = DBUser(
            username="user_for_ts_delete", password=hash_password("pw"), is_auth=0
        )
        db_session.add(user)
        db_session.commit()

        choice = SoknadsskjemaChoice(
            user_id=user.id, turnus_set_id=ts.id, shift_title="D1"
        )
        db_session.add(choice)
        db_session.commit()

        from app.services import turnus_service
        success, _ = turnus_service.delete_turnus_set(ts.id)
        assert success is True

        orphans = (
            db_session.query(SoknadsskjemaChoice)
            .filter_by(turnus_set_id=ts.id)
            .count()
        )
        assert orphans == 0


class TestAddShiftsNoNPlusOne:
    def test_second_import_does_not_create_duplicates(self, patch_db, db_session, tmp_path):
        import json
        from app.models import TurnusSet, Shifts

        ts = TurnusSet(name="R26", year_identifier="R26n1", is_active=1)
        db_session.add(ts)
        db_session.commit()

        shifts_data = [{"D1": {"some": "data"}, "N2": {"other": "data"}}]
        f = tmp_path / "turnus.json"
        f.write_text(json.dumps(shifts_data))

        turnus_service.add_shifts_to_turnus_set(str(f), ts.id)
        turnus_service.add_shifts_to_turnus_set(str(f), ts.id)  # second run

        count = db_session.query(Shifts).filter_by(turnus_set_id=ts.id).count()
        assert count == 2  # D1 and N2, no duplicates
