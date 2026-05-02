"""Tests for app.services.user_service."""

import bcrypt

from app.services import user_service


class TestCreateUser:
    def test_create_user(self, patch_db):
        success, msg = user_service.create_user("newuser", "pass123")
        assert success is True
        assert msg == "Bruker opprettet"

    def test_create_user_duplicate(self, patch_db):
        user_service.create_user("dupeuser", "pass")
        success, msg = user_service.create_user("dupeuser", "pass")
        assert success is False
        assert "finnes allerede" in msg


class TestGetUserData:
    def test_get_user_data(self, patch_db):
        user_service.create_user("lookup", "pw")
        data = user_service.get_user_data("lookup")
        assert data is not None
        assert data["username"] == "lookup"
        assert data["is_auth"] == 0

    def test_get_user_data_missing(self, patch_db):
        assert user_service.get_user_data("ghost") is None


class TestDeleteUser:
    def test_delete_user(self, patch_db):
        user_service.create_user("delme", "pw")
        data = user_service.get_user_data("delme")
        success, _ = user_service.delete_user(data["id"])
        assert success is True
        assert user_service.get_user_data("delme") is None


class TestUpdatePassword:
    def test_update_user_password(self, patch_db):
        user_service.create_user("pwuser", "oldpass")
        data = user_service.get_user_data("pwuser")

        success, _ = user_service.update_user_password(data["id"], "oldpass", "newpass")
        assert success is True

        # Old password should fail, new should work
        updated = user_service.get_user_data("pwuser")
        assert bcrypt.checkpw(b"newpass", updated["password"].encode()) is True
        assert bcrypt.checkpw(b"oldpass", updated["password"].encode()) is False


class TestCreateTestUser:
    def test_creates_user_with_correct_fields(self, patch_db, db_session):
        from app.models import DBUser
        success, msg = user_service.create_test_user_with_favorites()
        assert success is True
        user = db_session.query(DBUser).filter_by(username="testbruker").first()
        assert user is not None
        assert user.email == "testbruker@test.no"
        assert user.email_verified == 1
        assert user.is_auth == 0

    def test_adds_favorites_in_each_turnus_set(self, patch_db, db_session):
        from app.models import DBUser, TurnusSet, Shifts, Favorites
        ts1 = TurnusSet(name="Turnus 2024", year_identifier="R24", is_active=0)
        ts2 = TurnusSet(name="Turnus 2025", year_identifier="R25", is_active=1)
        db_session.add_all([ts1, ts2])
        db_session.commit()
        for i in range(8):
            db_session.add(Shifts(title=f"D{i}", turnus_set_id=ts1.id))
            db_session.add(Shifts(title=f"N{i}", turnus_set_id=ts2.id))
        db_session.commit()

        success, msg = user_service.create_test_user_with_favorites()
        assert success is True

        user = db_session.query(DBUser).filter_by(username="testbruker").first()
        favs_ts1 = db_session.query(Favorites).filter_by(user_id=user.id, turnus_set_id=ts1.id).all()
        favs_ts2 = db_session.query(Favorites).filter_by(user_id=user.id, turnus_set_id=ts2.id).all()
        assert len(favs_ts1) == 5
        assert len(favs_ts2) == 5
        assert "R24" in msg
        assert "R25" in msg

    def test_resets_existing_testbruker(self, patch_db, db_session):
        from app.models import DBUser
        user_service.create_test_user_with_favorites()
        user_service.create_test_user_with_favorites()  # second call resets
        count = db_session.query(DBUser).filter_by(username="testbruker").count()
        assert count == 1
