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
