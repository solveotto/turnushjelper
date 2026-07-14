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


class TestDeleteUserCleansUpSoknadsskjema:
    def test_delete_user_removes_soknadsskjema_choices(self, patch_db, db_session):
        from app.models import DBUser, SoknadsskjemaChoice, TurnusSet
        from app.services.user_service import hash_password

        ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
        db_session.add(ts)
        db_session.commit()

        user = DBUser(
            username="todelete", password=hash_password("pw"), is_auth=0
        )
        db_session.add(user)
        db_session.commit()

        choice = SoknadsskjemaChoice(
            user_id=user.id, turnus_set_id=ts.id, shift_title="D1"
        )
        db_session.add(choice)
        db_session.commit()

        success, _ = user_service.delete_user(user.id)
        assert success is True

        orphans = (
            db_session.query(SoknadsskjemaChoice)
            .filter_by(user_id=user.id)
            .count()
        )
        assert orphans == 0


class TestDeleteUserCleansUpAllPersonalData:
    def test_delete_user_removes_all_related_personal_data(self, patch_db, db_session):
        from datetime import datetime, timedelta

        from app.models import (
            DBUser,
            EmailVerificationToken,
            Favorites,
            Innplassering,
            Shifts,
            SoknadsskjemaChoice,
            TurnusSet,
            UserActivity,
        )
        from app.services.user_service import hash_password

        ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
        db_session.add(ts)
        db_session.commit()

        db_session.add(Shifts(title="D1", turnus_set_id=ts.id))
        db_session.commit()

        user = DBUser(
            username="gdprdelete",
            password=hash_password("pw"),
            is_auth=0,
            rullenummer="12345",
        )
        db_session.add(user)
        db_session.commit()

        db_session.add_all([
            Favorites(user_id=user.id, shift_title="D1", turnus_set_id=ts.id),
            SoknadsskjemaChoice(user_id=user.id, turnus_set_id=ts.id, shift_title="D1"),
            EmailVerificationToken(
                user_id=user.id,
                token="tok-123",
                expires_at=datetime.now() + timedelta(hours=1),
            ),
            UserActivity(user_id=user.id, event_type="login"),
            Innplassering(turnus_set_id=ts.id, rullenummer="12345", shift_title="D1"),
        ])
        db_session.commit()

        success, _ = user_service.delete_user(user.id)
        assert success is True

        assert db_session.query(DBUser).filter_by(id=user.id).count() == 0
        assert db_session.query(Favorites).filter_by(user_id=user.id).count() == 0
        assert db_session.query(SoknadsskjemaChoice).filter_by(user_id=user.id).count() == 0
        assert db_session.query(EmailVerificationToken).filter_by(user_id=user.id).count() == 0
        assert db_session.query(UserActivity).filter_by(user_id=user.id).count() == 0
        assert db_session.query(Innplassering).filter_by(rullenummer="12345").count() == 0


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


class TestGetUserDataExactMatch:
    def test_exact_username_lookup(self, patch_db):
        user_service.create_user("exactuser", "pw")
        data = user_service.get_user_data("exactuser")
        assert data is not None
        assert data["username"] == "exactuser"

    def test_returns_none_for_nonexistent(self, patch_db):
        assert user_service.get_user_data("doesnotexist") is None


class TestRullenummerUniqueness:
    """A rullenummer must not be claimed by two users — otherwise the
    innplassering lookup (joins on the rullenummer string) would show one user
    another person's shift assignment."""

    def _make_user(self, db_session, **kwargs):
        from app.models import DBUser
        defaults = dict(username="owner", password="x", is_auth=0)
        defaults.update(kwargs)
        user = DBUser(**defaults)
        db_session.add(user)
        db_session.commit()
        return user

    def test_activate_stub_rejects_taken_rullenummer(self, patch_db, db_session):
        from app.models import DBUser
        # User A already owns rullenummer 12345.
        self._make_user(db_session, username="owner_a", rullenummer="12345")
        # Stub B tries to claim the same rullenummer on activation.
        stub = self._make_user(db_session, username="__stub_b", is_stub=1)

        success, msg, uid = user_service.activate_stub_user(
            user_id=stub.id, username="realb", email="b@test.com",
            password="pw123456", rullenummer="12345",
        )
        assert success is False
        assert "allerede i bruk" in msg
        assert uid is None
        # B's rullenummer must be untouched.
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=stub.id).first()
        assert updated.rullenummer is None

    def test_activate_stub_accepts_free_rullenummer(self, patch_db, db_session):
        from app.models import DBUser
        stub = self._make_user(db_session, username="__stub_c", is_stub=1)

        success, msg, uid = user_service.activate_stub_user(
            user_id=stub.id, username="realc", email="c@test.com",
            password="pw123456", rullenummer="99999",
        )
        assert success is True
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=stub.id).first()
        assert updated.rullenummer == "99999"
        assert updated.is_stub == 0

    def test_create_user_with_email_rejects_taken_rullenummer(
        self, patch_db, db_session
    ):
        self._make_user(db_session, username="owner_d", rullenummer="54321")

        success, msg, uid = user_service.create_user_with_email(
            email="d@test.com", username="reald", password="pw123456",
            rullenummer="54321",
        )
        assert success is False
        assert "allerede i bruk" in msg
        assert uid is None


class TestInitDefaultAdmin:
    """The bootstrap admin must never be created with a guessable password.

    Regression guard for the admin/admin default-credentials vulnerability:
    auto-provisioning only happens when a strong, explicit password is set.
    """

    def _set_admin_config(self, monkeypatch, username, password):
        from config import AppConfig

        monkeypatch.setattr(AppConfig, "DEFAULT_ADMIN_USERNAME", username)
        monkeypatch.setattr(AppConfig, "DEFAULT_ADMIN_PASSWORD", password)

    def test_no_password_skips_creation(self, patch_db, monkeypatch):
        self._set_admin_config(monkeypatch, "bootadmin", "")
        user_service.init_default_admin()
        assert user_service.get_user_by_username("bootadmin") is None

    def test_weak_password_refused(self, patch_db, monkeypatch):
        # The exact old insecure default must be rejected outright.
        self._set_admin_config(monkeypatch, "bootadmin", "admin")
        user_service.init_default_admin()
        assert user_service.get_user_by_username("bootadmin") is None

    def test_weak_password_refused_case_insensitively(self, patch_db, monkeypatch):
        self._set_admin_config(monkeypatch, "bootadmin", "  Admin ")
        user_service.init_default_admin()
        assert user_service.get_user_by_username("bootadmin") is None

    def test_password_equal_to_username_refused(self, patch_db, monkeypatch):
        self._set_admin_config(monkeypatch, "bootadmin", "bootadmin")
        user_service.init_default_admin()
        assert user_service.get_user_by_username("bootadmin") is None

    def test_strong_password_creates_admin(self, patch_db, monkeypatch):
        self._set_admin_config(monkeypatch, "bootadmin", "S3cure-Boot!pw")
        user_service.init_default_admin()

        data = user_service.get_user_data("bootadmin")
        assert data is not None
        assert data["is_auth"] == 1
        assert data["email_verified"] == 1
        assert bcrypt.checkpw(
            b"S3cure-Boot!pw", data["password"].encode("utf-8")
        )

    def test_idempotent_when_admin_exists(self, patch_db, db_session, monkeypatch):
        from app.models import DBUser

        self._set_admin_config(monkeypatch, "bootadmin", "S3cure-Boot!pw")
        user_service.init_default_admin()
        user_service.init_default_admin()  # second call must be a no-op

        db_session.expire_all()
        count = db_session.query(DBUser).filter_by(username="bootadmin").count()
        assert count == 1


class TestCaseInsensitiveUsernames:
    """Usernames are case-insensitive identifiers, enforced in code so SQLite
    (dev) behaves like MySQL (prod) instead of relying on DB collation. The
    stored value keeps its original case for display."""

    def test_get_user_data_case_insensitive(self, patch_db):
        user_service.create_user("CaseUser", "pw123456")
        assert user_service.get_user_data("caseuser") is not None
        # The stored (display) case is preserved and returned.
        assert user_service.get_user_data("CASEUSER")["username"] == "CaseUser"

    def test_get_user_by_username_case_insensitive(self, patch_db):
        user_service.create_user("Bob", "pw123456")
        found = user_service.get_user_by_username("bob")
        assert found is not None
        assert found["username"] == "Bob"

    def test_create_user_rejects_case_variant_duplicate(self, patch_db):
        user_service.create_user("Alice", "pw123456")
        success, msg = user_service.create_user("alice", "pw123456")
        assert success is False
        assert "finnes allerede" in msg

    def test_create_user_with_email_rejects_case_variant_username(self, patch_db):
        user_service.create_user("Charlie", "pw123456")
        success, msg, uid = user_service.create_user_with_email(
            email="c@test.com", username="charlie", password="pw123456"
        )
        assert success is False
        assert "tatt" in msg  # "Brukernavnet er allerede tatt"
        assert uid is None

    def test_update_user_allows_changing_own_username_case(self, patch_db, db_session):
        from app.models import DBUser

        user_service.create_user("dave", "pw123456")
        u = user_service.get_user_by_username("dave")
        success, msg = user_service.update_user(user_id=u["id"], username="Dave")
        assert success is True, msg
        db_session.expire_all()
        updated = db_session.query(DBUser).filter_by(id=u["id"]).first()
        assert updated.username == "Dave"

    def test_update_user_rejects_other_users_username_case_variant(self, patch_db):
        user_service.create_user("Eve", "pw123456")
        user_service.create_user("frank", "pw123456")
        frank = user_service.get_user_by_username("frank")
        success, msg = user_service.update_user(user_id=frank["id"], username="EVE")
        assert success is False
        assert "finnes allerede" in msg
