"""Tests for ORM models and the User wrapper class."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import DBUser, TurnusSet, Favorites, User
from app.services.user_service import hash_password


class TestDBUser:
    def test_create_and_query(self, patch_db, db_session):
        """Insert a DBUser and read it back."""
        user = DBUser(username="alice", password=hash_password("pw"), is_auth=0, email_verified=0)
        db_session.add(user)
        db_session.commit()

        result = db_session.query(DBUser).filter_by(username="alice").first()
        assert result is not None
        assert result.username == "alice"
        assert result.is_auth == 0

    def test_unique_username(self, patch_db, db_session):
        """Duplicate usernames should raise IntegrityError."""
        db_session.add(DBUser(username="bob", password="x", is_auth=0, email_verified=0))
        db_session.commit()

        db_session.add(DBUser(username="bob", password="y", is_auth=0, email_verified=0))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestTurnusSet:
    def test_unique_year_identifier(self, patch_db, db_session):
        """Duplicate year_identifier should raise IntegrityError."""
        db_session.add(TurnusSet(name="Set A", year_identifier="R25"))
        db_session.commit()

        db_session.add(TurnusSet(name="Set B", year_identifier="R25"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestFavorites:
    def test_unique_constraint(self, patch_db, db_session):
        """Duplicate user+shift+turnus_set should raise IntegrityError."""
        db_session.add(Favorites(user_id=1, shift_title="D1", turnus_set_id=1, order_index=0))
        db_session.commit()

        db_session.add(Favorites(user_id=1, shift_title="D1", turnus_set_id=1, order_index=1))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestUserWrapper:
    def test_verify_password(self):
        """User.verify_password should match correct passwords and reject wrong ones."""
        hashed = hash_password("secret")
        assert User.verify_password(hashed, "secret") is True
        assert User.verify_password(hashed, "wrong") is False
