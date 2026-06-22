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
        from app.models import DBUser, Favorites, TurnusSet, Shifts
        # Seed a TurnusSet with 6 shifts so favorites actually get created
        ts = TurnusSet(name="Turnus 2025", year_identifier="R25", is_active=1)
        db_session.add(ts)
        db_session.commit()
        for i in range(6):
            db_session.add(Shifts(title=f"D{i}", turnus_set_id=ts.id))
        db_session.commit()

        user_service.create_test_user_with_favorites()
        user_service.create_test_user_with_favorites()  # second call resets

        user = db_session.query(DBUser).filter_by(username="testbruker").first()
        assert user is not None
        fav_count = db_session.query(Favorites).filter_by(user_id=user.id).count()
        # Should be exactly 5 (min(5, 6)), not 10 (accumulated from 2 calls)
        assert fav_count == 5


class TestGetUserByMedlemsnummer:
    def test_found(self, patch_db, db_session):
        from app.models import DBUser
        db_session.add(DBUser(
            username="__stub_m60011", password="x", name="Nordmann, Ola",
            medlemsnummer="60011", is_stub=1,
        ))
        db_session.commit()
        user = user_service.get_user_by_medlemsnummer("60011")
        assert user is not None
        assert user["medlemsnummer"] == "60011"
        assert user["is_stub"] == 1

    def test_not_found(self, patch_db):
        assert user_service.get_user_by_medlemsnummer("99999") is None

    def test_int_argument(self, patch_db, db_session):
        from app.models import DBUser
        db_session.add(DBUser(
            username="__stub_m60012", password="x", medlemsnummer="60012", is_stub=1,
        ))
        db_session.commit()
        assert user_service.get_user_by_medlemsnummer(60012) is not None


class TestCreateStubUserMedlemsnummer:
    def test_create_with_medlemsnummer(self, patch_db, db_session):
        from app.models import DBUser
        success, msg = user_service.create_stub_user(
            etternavn="Nordmann", fornavn="Ola", medlemsnummer="60013",
        )
        assert success is True
        stub = db_session.query(DBUser).filter_by(medlemsnummer="60013").first()
        assert stub.username == "__stub_m60013"
        assert stub.is_stub == 1
        assert stub.rullenummer is None

    def test_rullenummer_is_optional_extra(self, patch_db, db_session):
        from app.models import DBUser
        success, _ = user_service.create_stub_user(
            etternavn="Nordmann", fornavn="Kari",
            medlemsnummer="60014", rullenummer="12345",
        )
        assert success is True
        stub = db_session.query(DBUser).filter_by(medlemsnummer="60014").first()
        assert stub.rullenummer == "12345"
        assert stub.username == "__stub_m60014"

    def test_missing_medlemsnummer_fails(self, patch_db):
        success, msg = user_service.create_stub_user(
            etternavn="Nordmann", fornavn="Ola", medlemsnummer="",
        )
        assert success is False
        assert "NLF-medlemsnummer" in msg

    def test_duplicate_medlemsnummer_fails(self, patch_db):
        user_service.create_stub_user(
            etternavn="A", fornavn="B", medlemsnummer="60015",
        )
        success, msg = user_service.create_stub_user(
            etternavn="C", fornavn="D", medlemsnummer="60015",
        )
        assert success is False
        assert "finnes allerede" in msg


class TestUpdateUserFullFields:
    def _make_user(self, db_session, **kwargs):
        from app.models import DBUser
        defaults = dict(username="edituser", password="x", is_auth=0)
        defaults.update(kwargs)
        user = DBUser(**defaults)
        db_session.add(user)
        db_session.commit()
        return user

    def test_update_all_fields(self, patch_db, db_session):
        from app.models import DBUser
        user = self._make_user(db_session)
        success, _ = user_service.update_user(
            user_id=user.id, username="renamed", email="new@test.com",
            name="Etter, For", medlemsnummer="60020", rullenummer="222",
            stasjoneringssted="OSL", ans_dato="01.01.2021",
            fodt_dato="03.03.1993", seniority_nr=9,
            is_auth=1, email_verified=1, is_stub=0,
        )
        assert success is True
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=user.id).first()
        assert updated.username == "renamed"
        assert updated.email == "new@test.com"
        assert updated.name == "Etter, For"
        assert updated.medlemsnummer == "60020"
        assert updated.rullenummer == "222"
        assert updated.stasjoneringssted == "OSL"
        assert updated.seniority_nr == 9
        assert updated.is_auth == 1

    def test_unset_fields_untouched(self, patch_db, db_session):
        from app.models import DBUser
        user = self._make_user(
            db_session, name="Keep, Me", medlemsnummer="60021",
            stasjoneringssted="OSL",
        )
        success, _ = user_service.update_user(user_id=user.id, username="edituser")
        assert success is True
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=user.id).first()
        assert updated.name == "Keep, Me"
        assert updated.medlemsnummer == "60021"
        assert updated.stasjoneringssted == "OSL"

    def test_explicit_none_clears(self, patch_db, db_session):
        from app.models import DBUser
        user = self._make_user(db_session, medlemsnummer="60022", name="Clear, Me")
        success, _ = user_service.update_user(
            user_id=user.id, username="edituser",
            medlemsnummer=None, name=None,
        )
        assert success is True
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=user.id).first()
        assert updated.medlemsnummer is None
        assert updated.name is None

    def test_medlemsnummer_conflict(self, patch_db, db_session):
        from app.models import DBUser
        self._make_user(db_session, username="owner", medlemsnummer="60023")
        user = self._make_user(db_session, username="claimer")
        success, msg = user_service.update_user(
            user_id=user.id, username="claimer", medlemsnummer="60023",
        )
        assert success is False
        assert "allerede i bruk" in msg
