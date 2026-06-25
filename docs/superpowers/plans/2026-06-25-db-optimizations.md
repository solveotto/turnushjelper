# Database Optimization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix correctness bugs and performance issues in the MySQL production database, as identified by the database review on 2026-06-25.

**Architecture:** Changes are organized into six independent tasks. Tasks 1–3 are pure code/config and carry no migration risk. Tasks 4–5 add Alembic migrations that must be run against production (`alembic upgrade head`) after the code is deployed. Task 6 is code-only query optimizations with no schema changes. Tasks with migrations must be applied in sequence (014 → 015 → 016) because each migration's `down_revision` points to the previous one.

**Tech Stack:** Python 3.12, Flask 3.0, SQLAlchemy 2.0, Alembic, MySQL (prod), SQLite (dev/test), pytest.

## Global Constraints

- All migrations live in `migrations/versions/` (note: NOT `alembic/versions/`).
- `alembic.ini` sets `script_location = migrations`.
- Current Alembic HEAD: `140a64b0185c` (file: `140a64b0185c_drop_authorized_emails_table.py`).
- New migrations must chain: `014` → `015` → `016`, each setting `down_revision` to the previous revision ID.
- Tests use in-memory SQLite via `conftest.py`; use the `patch_db` fixture to get a patched session.
- Return type for mutations: `(bool, str)`. Queries return typed values.
- Run the full suite with `pytest` from project root. Run a single file with `pytest tests/test_X.py`.
- Never commit — leave that to the user.

---

### Task 1: Fix model annotation and remove dead config (C-1, M-7)

**Files:**
- Modify: `app/models.py:16`
- Modify: `config.py:53-57`

**Interfaces:**
- Produces: `DBUser.rullenummer` correctly typed as `Mapped[str | None]`; `SQLALCHEMY_ENGINE_OPTIONS` removed from `AppConfig`

- [ ] **Step 1: Fix `rullenummer` type annotation in `app/models.py`**

  Line 16 currently reads:
  ```python
  rullenummer: Mapped[int] = mapped_column(String(10), nullable=True)
  ```
  Change to:
  ```python
  rullenummer: Mapped[str | None] = mapped_column(String(10), nullable=True)
  ```
  No column type change — this is annotation only. All call sites already pass strings (verified by grep: `str(rullenummer)` at every write site).

- [ ] **Step 2: Remove dead `SQLALCHEMY_ENGINE_OPTIONS` from `config.py`**

  Lines 53–57 currently read:
  ```python
  SQLALCHEMY_ENGINE_OPTIONS = (
      {"pool_pre_ping": True}
      if DB_TYPE == "sqlite"
      else {"pool_recycle": 300, "pool_pre_ping": True}
  )
  ```
  Delete those five lines entirely. The actual engine is created in `app/database.py` with explicit kwargs; this dict is never consumed (there is no Flask-SQLAlchemy).

- [ ] **Step 3: Run the test suite to confirm nothing broke**

  ```bash
  pytest
  ```
  Expected: all tests pass. No functional change was made.

- [ ] **Step 4: Commit**
  ```bash
  git add app/models.py config.py
  git commit -m "fix: correct rullenummer type annotation; remove dead SQLALCHEMY_ENGINE_OPTIONS"
  ```

---

### Task 2: Fix MySQL connection charset and session data type (L-1, H-5)

**Files:**
- Modify: `config.py:40` — add `?charset=utf8mb4` to MySQL URI
- Modify: `app/models.py:125` — `LargeBinary` → `LargeBinary(16_777_215)`
- Create: `migrations/versions/014_mysql_session_blob.py`

**Interfaces:**
- Consumes: Alembic HEAD `140a64b0185c` from Task 0 (pre-existing)
- Produces: revision `014_mysql_session_blob`; `flask_sessions.data` becomes MEDIUMBLOB on MySQL

- [ ] **Step 1: Add `charset=utf8mb4` to MySQL URI in `config.py`**

  Line 40 currently reads:
  ```python
  return f"mysql+pymysql://{user}:{password}@{host}/{database}"
  ```
  Change to:
  ```python
  return f"mysql+pymysql://{user}:{password}@{host}/{database}?charset=utf8mb4"
  ```

- [ ] **Step 2: Update `FlaskSessionModel.data` in `app/models.py`**

  Line 125 currently reads:
  ```python
  data = Column(LargeBinary, nullable=False)
  ```
  Change to:
  ```python
  data = Column(LargeBinary(16_777_215), nullable=False)
  ```
  `LargeBinary(16_777_215)` maps to `MEDIUMBLOB` (16 MB) on MySQL. On SQLite, the size argument is ignored.

- [ ] **Step 3: Create migration `014_mysql_session_blob.py`**

  Create file `migrations/versions/014_mysql_session_blob.py`:
  ```python
  """mysql: session data BLOB → MEDIUMBLOB

  Revision ID: 014_mysql_session_blob
  Revises: 140a64b0185c
  Create Date: 2026-06-25
  """
  from typing import Sequence, Union

  import sqlalchemy as sa
  from alembic import op

  revision: str = "014_mysql_session_blob"
  down_revision: Union[str, None] = "140a64b0185c"
  branch_labels: Union[str, Sequence[str], None] = None
  depends_on: Union[str, Sequence[str], None] = None


  def upgrade() -> None:
      bind = op.get_bind()
      if bind.dialect.name == "mysql":
          op.alter_column(
              "flask_sessions",
              "data",
              existing_type=sa.LargeBinary(),
              type_=sa.LargeBinary(16_777_215),
              existing_nullable=False,
          )


  def downgrade() -> None:
      bind = op.get_bind()
      if bind.dialect.name == "mysql":
          op.alter_column(
              "flask_sessions",
              "data",
              existing_type=sa.LargeBinary(16_777_215),
              type_=sa.LargeBinary(),
              existing_nullable=False,
          )
  ```

- [ ] **Step 4: Verify migration is in the chain**

  ```bash
  alembic heads
  ```
  Expected output: `014_mysql_session_blob (head)` — exactly one head.

- [ ] **Step 5: Run session tests to confirm nothing broke**

  ```bash
  pytest tests/test_sa_session_interface.py -v
  ```
  Expected: all pass.

- [ ] **Step 6: Commit**
  ```bash
  git add config.py app/models.py migrations/versions/014_mysql_session_blob.py
  git commit -m "fix: add utf8mb4 charset to MySQL URI; upgrade session data column to MEDIUMBLOB"
  ```

---

### Task 3: Add missing indexes and fix ilike username lookup (M-1, M-2, M-5)

**Files:**
- Create: `migrations/versions/015_add_indexes.py`
- Modify: `app/services/user_service.py:44-45`

**Interfaces:**
- Consumes: revision `014_mysql_session_blob` from Task 2
- Produces: revision `015_add_indexes`; `users.email`, `users.rullenummer`, `users.is_stub`, `user_activity.user_id` indexed; `get_user_data` uses exact match on username

- [ ] **Step 1: Create migration `015_add_indexes.py`**

  Create file `migrations/versions/015_add_indexes.py`:
  ```python
  """add indexes on users.email, rullenummer, is_stub and user_activity.user_id

  Revision ID: 015_add_indexes
  Revises: 014_mysql_session_blob
  Create Date: 2026-06-25
  """
  from typing import Sequence, Union

  from alembic import op

  revision: str = "015_add_indexes"
  down_revision: Union[str, None] = "014_mysql_session_blob"
  branch_labels: Union[str, Sequence[str], None] = None
  depends_on: Union[str, Sequence[str], None] = None


  def upgrade() -> None:
      op.create_index("ix_users_email", "users", ["email"])
      op.create_index("ix_users_rullenummer", "users", ["rullenummer"])
      op.create_index("ix_users_is_stub", "users", ["is_stub"])
      op.create_index("ix_user_activity_user_id", "user_activity", ["user_id"])


  def downgrade() -> None:
      op.drop_index("ix_users_email", table_name="users")
      op.drop_index("ix_users_rullenummer", table_name="users")
      op.drop_index("ix_users_is_stub", table_name="users")
      op.drop_index("ix_user_activity_user_id", table_name="user_activity")
  ```

- [ ] **Step 2: Verify migration chain**

  ```bash
  alembic heads
  ```
  Expected: `015_add_indexes (head)` — one head.

- [ ] **Step 3: Write failing test for `get_user_data` exact-match behavior**

  Add to `tests/test_user_service.py`:
  ```python
  class TestGetUserDataExactMatch:
      def test_exact_username_lookup(self, patch_db):
          user_service.create_user("exactuser", "pw")
          data = user_service.get_user_data("exactuser")
          assert data is not None
          assert data["username"] == "exactuser"

      def test_returns_none_for_nonexistent(self, patch_db):
          assert user_service.get_user_data("doesnotexist") is None
  ```

  Run to confirm these pass already (they test existing behavior):
  ```bash
  pytest tests/test_user_service.py::TestGetUserDataExactMatch -v
  ```
  Expected: PASS (tests existing behavior that must be preserved).

- [ ] **Step 4: Fix `ilike` → `filter_by` in `app/services/user_service.py`**

  Lines 43–46 currently read:
  ```python
  result = (
      db_session.query(DBUser)
      .filter(DBUser.username.ilike(username_or_email))
      .first()
  )
  ```
  Change to:
  ```python
  result = (
      db_session.query(DBUser)
      .filter_by(username=username_or_email)
      .first()
  )
  ```
  On production MySQL with `utf8mb4_unicode_ci` collation, `=` is already case-insensitive and uses the `username` unique index. The old `ilike` compiled to `LIKE` which disabled the index.

- [ ] **Step 5: Run tests to confirm fix**

  ```bash
  pytest tests/test_user_service.py::TestGetUserDataExactMatch -v
  ```
  Expected: PASS.

- [ ] **Step 6: Run full suite**

  ```bash
  pytest
  ```
  Expected: all pass.

- [ ] **Step 7: Commit**
  ```bash
  git add migrations/versions/015_add_indexes.py app/services/user_service.py
  git commit -m "perf: add missing DB indexes; replace ilike with exact match in username lookup"
  ```

---

### Task 4: Add FK constraints and fix orphan cleanup (H-2, L-8)

**Files:**
- Modify: `app/models.py:66-94` — add `ForeignKey` to `Favorites`, `Shifts`, `SoknadsskjemaChoice`
- Modify: `app/services/user_service.py:354-366` — clean up `SoknadsskjemaChoice` in `delete_user`
- Modify: `app/services/turnus_service.py:177-193` — clean up `SoknadsskjemaChoice` in `delete_turnus_set`
- Create: `migrations/versions/016_add_fk_constraints.py`

**Interfaces:**
- Consumes: revision `015_add_indexes` from Task 3
- Produces: revision `016_add_fk_constraints`; FK constraints enforced on MySQL; `delete_user` and `delete_turnus_set` clean up `SoknadsskjemaChoice` rows

**Pre-migration check (run on production MySQL before deploying):**
```sql
SELECT COUNT(*) FROM favorites WHERE user_id NOT IN (SELECT id FROM users);
SELECT COUNT(*) FROM favorites WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
SELECT COUNT(*) FROM shifts WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
SELECT COUNT(*) FROM soknadsskjema_choices WHERE user_id NOT IN (SELECT id FROM users);
SELECT COUNT(*) FROM soknadsskjema_choices WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
```
All must return 0 before running `alembic upgrade head`. If any return > 0, delete the orphans first.

- [ ] **Step 1: Write failing test for `delete_user` orphan cleanup**

  Add to `tests/test_user_service.py`:
  ```python
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
  ```

  Run to confirm it currently fails:
  ```bash
  pytest tests/test_user_service.py::TestDeleteUserCleansUpSoknadsskjema -v
  ```
  Expected: FAIL (orphans are not cleaned up yet).

- [ ] **Step 2: Fix `delete_user` in `app/services/user_service.py`**

  The function currently at lines 351–367:
  ```python
  def delete_user(user_id):
      """Delete a user and all associated data"""
      db_session = get_db_session()
      try:
          user = db_session.query(DBUser).filter_by(id=user_id).first()
          if not user:
              return False, "Bruker ikke funnet"

          db_session.query(Favorites).filter_by(user_id=user_id).delete()
          db_session.delete(user)
          db_session.commit()
          return True, "Bruker slettet"
      except Exception as e:
          db_session.rollback()
          return False, f"Error deleting user: {e}"
      finally:
          db_session.close()
  ```

  Add the import at the top of the function and the cleanup line. The function should become:
  ```python
  def delete_user(user_id):
      """Delete a user and all associated data"""
      from app.models import SoknadsskjemaChoice
      db_session = get_db_session()
      try:
          user = db_session.query(DBUser).filter_by(id=user_id).first()
          if not user:
              return False, "Bruker ikke funnet"

          db_session.query(Favorites).filter_by(user_id=user_id).delete()
          db_session.query(SoknadsskjemaChoice).filter_by(user_id=user_id).delete()
          db_session.delete(user)
          db_session.commit()
          return True, "Bruker slettet"
      except Exception as e:
          db_session.rollback()
          return False, f"Error deleting user: {e}"
      finally:
          db_session.close()
  ```

  Note: `SoknadsskjemaChoice` is a deferred import inside the function body to match the project's pattern for avoiding circular imports.

- [ ] **Step 3: Run test to confirm it now passes**

  ```bash
  pytest tests/test_user_service.py::TestDeleteUserCleansUpSoknadsskjema -v
  ```
  Expected: PASS.

- [ ] **Step 4: Write failing test for `delete_turnus_set` orphan cleanup**

  Add to `tests/test_turnus_service.py`:
  ```python
  class TestDeleteTurnusSetCleansUpSoknadsskjema:
      def test_delete_turnus_set_removes_soknadsskjema_choices(self, patch_db, db_session):
          from app.models import DBUser, SoknadsskjemaChoice, TurnusSet, Shifts
          from app.services.user_service import hash_password
          from app.services import turnus_service

          ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
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

          success, _ = turnus_service.delete_turnus_set(ts.id)
          assert success is True

          orphans = (
              db_session.query(SoknadsskjemaChoice)
              .filter_by(turnus_set_id=ts.id)
              .count()
          )
          assert orphans == 0
  ```

  Run to confirm it currently fails:
  ```bash
  pytest tests/test_turnus_service.py::TestDeleteTurnusSetCleansUpSoknadsskjema -v
  ```
  Expected: FAIL.

- [ ] **Step 5: Fix `delete_turnus_set` in `app/services/turnus_service.py`**

  The function currently at lines 177–194 (relevant section):
  ```python
  def delete_turnus_set(turnus_set_id):
      """Delete a turnus set and all its associated data"""
      db_session = get_db_session()
      try:
          turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
          if not turnus_set:
              return False, "Turnussett ikke funnet"

          db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id).delete()
          db_session.query(Favorites).filter_by(turnus_set_id=turnus_set_id).delete()
          db_session.delete(turnus_set)
          db_session.commit()
          return True, f"Turnussett {turnus_set.year_identifier} slettet"
      ...
  ```

  Add `SoknadsskjemaChoice` cleanup. Change the try block to:
  ```python
      try:
          from app.models import SoknadsskjemaChoice
          turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
          if not turnus_set:
              return False, "Turnussett ikke funnet"

          db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id).delete()
          db_session.query(Favorites).filter_by(turnus_set_id=turnus_set_id).delete()
          db_session.query(SoknadsskjemaChoice).filter_by(turnus_set_id=turnus_set_id).delete()
          db_session.delete(turnus_set)
          db_session.commit()
          return True, f"Turnussett {turnus_set.year_identifier} slettet"
  ```

- [ ] **Step 6: Run test to confirm it now passes**

  ```bash
  pytest tests/test_turnus_service.py::TestDeleteTurnusSetCleansUpSoknadsskjema -v
  ```
  Expected: PASS.

- [ ] **Step 7: Add FK definitions to `app/models.py`**

  The three models currently use bare `Integer` for `user_id`/`turnus_set_id`. Update them to use `ForeignKey`. Show the complete new `__tablename__` + columns section for each:

  **`Favorites` (lines 63–70):**
  ```python
  class Favorites(Base):
      __tablename__ = 'favorites'
      id = Column(Integer, primary_key=True, autoincrement=True)
      user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
      shift_title = Column(String(255), nullable=False)
      turnus_set_id = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
      order_index: Mapped[int] = mapped_column(Integer, default=0)
      __table_args__ = (UniqueConstraint('user_id', 'shift_title', 'turnus_set_id'),)
  ```

  **`Shifts` (lines 73–78):**
  ```python
  class Shifts(Base):
      __tablename__ = 'shifts'
      id = Column(Integer, primary_key=True, autoincrement=True)
      title = Column(String(255), nullable=False)
      turnus_set_id = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
      __table_args__ = (UniqueConstraint('title', 'turnus_set_id'),)
  ```

  **`SoknadsskjemaChoice` (lines 81–94):**
  ```python
  class SoknadsskjemaChoice(Base):
      __tablename__ = "soknadsskjema_choices"
      id              = Column(Integer, primary_key=True, autoincrement=True)
      user_id         = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
      turnus_set_id   = Column(Integer, ForeignKey('turnus_sets.id', ondelete='CASCADE'), nullable=False)
      shift_title     = Column(String(255), nullable=False)
      linje_135       = Column(Integer, default=0)
      linje_246       = Column(Integer, default=0)
      linjeprioritering = Column(String(255), nullable=True)
      h_dag           = Column(Integer, default=0)
      __table_args__ = (
          UniqueConstraint("user_id", "turnus_set_id", "shift_title",
                           name="uq_soknadsskjema_choices"),
      )
  ```

  The `ForeignKey` symbol is already imported at the top of `models.py` (line 4).

- [ ] **Step 8: Create migration `016_add_fk_constraints.py`**

  Create file `migrations/versions/016_add_fk_constraints.py`:
  ```python
  """add FK constraints on favorites, shifts, soknadsskjema_choices (MySQL only)

  Revision ID: 016_add_fk_constraints
  Revises: 015_add_indexes
  Create Date: 2026-06-25

  IMPORTANT: Before running this on production, verify there are no orphan rows:
      SELECT COUNT(*) FROM favorites WHERE user_id NOT IN (SELECT id FROM users);
      SELECT COUNT(*) FROM favorites WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
      SELECT COUNT(*) FROM shifts WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
      SELECT COUNT(*) FROM soknadsskjema_choices WHERE user_id NOT IN (SELECT id FROM users);
      SELECT COUNT(*) FROM soknadsskjema_choices WHERE turnus_set_id NOT IN (SELECT id FROM turnus_sets);
  All must return 0.
  """
  from typing import Sequence, Union

  from alembic import op

  revision: str = "016_add_fk_constraints"
  down_revision: Union[str, None] = "015_add_indexes"
  branch_labels: Union[str, Sequence[str], None] = None
  depends_on: Union[str, Sequence[str], None] = None


  def upgrade() -> None:
      bind = op.get_bind()
      if bind.dialect.name != "mysql":
          return

      op.create_foreign_key(
          "fk_favorites_user_id", "favorites", "users", ["user_id"], ["id"],
          ondelete="CASCADE",
      )
      op.create_foreign_key(
          "fk_favorites_turnus_set_id", "favorites", "turnus_sets", ["turnus_set_id"], ["id"],
          ondelete="CASCADE",
      )
      op.create_foreign_key(
          "fk_shifts_turnus_set_id", "shifts", "turnus_sets", ["turnus_set_id"], ["id"],
          ondelete="CASCADE",
      )
      op.create_foreign_key(
          "fk_soknadsskjema_user_id", "soknadsskjema_choices", "users", ["user_id"], ["id"],
          ondelete="CASCADE",
      )
      op.create_foreign_key(
          "fk_soknadsskjema_turnus_set_id", "soknadsskjema_choices", "turnus_sets", ["turnus_set_id"], ["id"],
          ondelete="CASCADE",
      )


  def downgrade() -> None:
      bind = op.get_bind()
      if bind.dialect.name != "mysql":
          return

      op.drop_constraint("fk_favorites_user_id", "favorites", type_="foreignkey")
      op.drop_constraint("fk_favorites_turnus_set_id", "favorites", type_="foreignkey")
      op.drop_constraint("fk_shifts_turnus_set_id", "shifts", type_="foreignkey")
      op.drop_constraint("fk_soknadsskjema_user_id", "soknadsskjema_choices", type_="foreignkey")
      op.drop_constraint("fk_soknadsskjema_turnus_set_id", "soknadsskjema_choices", type_="foreignkey")
  ```

- [ ] **Step 9: Verify migration chain**

  ```bash
  alembic heads
  ```
  Expected: `016_add_fk_constraints (head)` — one head.

- [ ] **Step 10: Run full test suite**

  ```bash
  pytest
  ```
  Expected: all pass. Model FK definitions don't affect SQLite tests (FK enforcement is off by default in SQLite).

- [ ] **Step 11: Commit**
  ```bash
  git add app/models.py app/services/user_service.py app/services/turnus_service.py \
      migrations/versions/016_add_fk_constraints.py
  git commit -m "fix: add FK constraints; delete_user and delete_turnus_set now clean up SoknadsskjemaChoice orphans"
  ```

---

### Task 5: Standardize datetimes in auth_service.py (H-1)

**Files:**
- Modify: `app/services/auth_service.py` — replace 6 uses of `datetime.now()` with `datetime.utcnow()`

**Interfaces:**
- Produces: all token timestamps use `datetime.utcnow()` (naive UTC), consistent with the `sa_session_interface.py` pattern

**Why `utcnow()` not `now()`:** The mixed state (some naive, some offset-aware) is the risk. `now()` uses the process's local timezone. On a UTC server this is the same as `utcnow()`, but it creates a latent bug if timezones ever diverge. `utcnow()` is explicit. `sa_session_interface.py` already uses `datetime.now(timezone.utc).replace(tzinfo=None)` which is naive UTC — `utcnow()` is equivalent and simpler.

- [ ] **Step 1: Write failing test for token expiry**

  Add to `tests/test_auth_service.py`:
  ```python
  from datetime import datetime, timedelta

  class TestTokenExpiry:
      def test_expired_token_is_rejected(self, patch_db, db_session):
          from app.models import DBUser, EmailVerificationToken
          from app.services.user_service import hash_password
          from app.services import auth_service

          user = DBUser(username="expiry_user", password=hash_password("pw"), is_auth=0)
          db_session.add(user)
          db_session.commit()

          # Create a token that expired 1 second ago
          expired_token = EmailVerificationToken(
              user_id=user.id,
              token="expired-tok-123",
              expires_at=datetime.utcnow() - timedelta(seconds=1),
              used=0,
          )
          db_session.add(expired_token)
          db_session.commit()

          result = auth_service.verify_token("expired-tok-123")
          assert result["success"] is False
          assert "utløpt" in result["message"]

      def test_valid_token_is_accepted(self, patch_db, db_session):
          from app.models import DBUser, EmailVerificationToken
          from app.services.user_service import hash_password
          from app.services import auth_service

          user = DBUser(
              username="valid_tok_user",
              email="valid@example.com",
              password=hash_password("pw"),
              is_auth=0,
          )
          db_session.add(user)
          db_session.commit()

          valid_token = EmailVerificationToken(
              user_id=user.id,
              token="valid-tok-456",
              expires_at=datetime.utcnow() + timedelta(hours=48),
              used=0,
          )
          db_session.add(valid_token)
          db_session.commit()

          result = auth_service.verify_token("valid-tok-456")
          assert result["success"] is True
  ```

  Run to confirm the tests pass already (they test the existing comparison logic):
  ```bash
  pytest tests/test_auth_service.py::TestTokenExpiry -v
  ```
  Expected: PASS (the logic works; we're changing the datetime source, not the comparison).

- [ ] **Step 2: Replace `datetime.now()` with `datetime.utcnow()` in `app/services/auth_service.py`**

  There are 6 call sites. Apply each replacement:

  **Line 16** (`create_verification_token`):
  ```python
  # Before
  expires_at = datetime.now() + timedelta(hours=expiry_hours)
  # After
  expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
  ```

  **Line 51** (`verify_token`):
  ```python
  # Before
  if token_record.expires_at < datetime.now():
  # After
  if token_record.expires_at < datetime.utcnow():
  ```

  **Line 83** (`can_send_verification_email`):
  ```python
  # Before
  time_since_last = datetime.now() - user.verification_sent_at
  # After
  time_since_last = datetime.utcnow() - user.verification_sent_at
  ```

  **Line 89** (`can_send_verification_email`):
  ```python
  # Before
  EmailVerificationToken.created_at >= datetime.now() - timedelta(days=1)
  # After
  EmailVerificationToken.created_at >= datetime.utcnow() - timedelta(days=1)
  ```

  **Line 103** (`update_verification_sent_time`):
  ```python
  # Before
  user.verification_sent_at = datetime.now()
  # After
  user.verification_sent_at = datetime.utcnow()
  ```

  **Line 116** (`create_password_reset_token`):
  ```python
  # Before
  expires_at = datetime.now() + timedelta(hours=1)
  # After
  expires_at = datetime.utcnow() + timedelta(hours=1)
  ```

  **Line 154** (`verify_password_reset_token`):
  ```python
  # Before
  if token_record.expires_at < datetime.now():
  # After
  if token_record.expires_at < datetime.utcnow():
  ```

- [ ] **Step 3: Run tests**

  ```bash
  pytest tests/test_auth_service.py -v
  ```
  Expected: all pass.

- [ ] **Step 4: Run full suite**

  ```bash
  pytest
  ```
  Expected: all pass.

- [ ] **Step 5: Commit**
  ```bash
  git add app/services/auth_service.py
  git commit -m "fix: use datetime.utcnow() consistently in auth_service for naive UTC timestamps"
  ```

---

### Task 6: Query optimizations (H-3, H-6, M-10, M-11)

**Files:**
- Modify: `app/services/turnus_service.py:119-165` — cache `get_active_turnus_set`, fix N+1 in `add_shifts_to_turnus_set`
- Modify: `app/services/user_service.py:1204-1253` — column-only query in `get_all_stub_users`
- Modify: `app/services/user_service.py:1256-1326` — batch deletes in `delete_missing_stubs` and `delete_stub_users`
- Modify: `tests/conftest.py` — add `cache.clear()` to `patch_db` fixture to prevent cache bleed between tests

**Interfaces:**
- Produces: `get_active_turnus_set` cached 60 s and invalidated on set change; `add_shifts_to_turnus_set` uses a single prefetch; `get_all_stub_users` avoids loading password/tour columns; stub delete functions use `.in_()` bulk deletes

- [ ] **Step 1: Add `cache.clear()` to `patch_db` fixture in `tests/conftest.py`**

  The `patch_db` fixture currently starts by grabbing the connection. Add a cache clear at the top so cached values from one test don't leak into the next:

  ```python
  @pytest.fixture()
  def patch_db(db_session, monkeypatch):
      from app.extensions import cache
      cache.clear()

      connection = db_session.get_bind()
      TestSession = sessionmaker(bind=connection)
      # ... rest unchanged
  ```

  Run the full suite to confirm this doesn't break anything:
  ```bash
  pytest
  ```
  Expected: all pass.

- [ ] **Step 2: Write failing test for N+1 fix in `add_shifts_to_turnus_set`**

  Add to `tests/test_turnus_service.py`:
  ```python
  class TestAddShiftsNoNPlusOne:
      def test_second_import_does_not_create_duplicates(self, patch_db, db_session, tmp_path):
          import json
          from app.models import TurnusSet, Shifts
          from app.services import turnus_service

          ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
          db_session.add(ts)
          db_session.commit()

          shifts_data = [{"D1": {"some": "data"}, "N2": {"other": "data"}}]
          f = tmp_path / "turnus.json"
          f.write_text(json.dumps(shifts_data))

          turnus_service.add_shifts_to_turnus_set(str(f), ts.id)
          turnus_service.add_shifts_to_turnus_set(str(f), ts.id)  # second run

          count = db_session.query(Shifts).filter_by(turnus_set_id=ts.id).count()
          assert count == 2  # D1 and N2, no duplicates
  ```

  Run — this likely already passes due to the existing SELECT-then-insert guard, but confirm:
  ```bash
  pytest tests/test_turnus_service.py::TestAddShiftsNoNPlusOne -v
  ```

- [ ] **Step 3: Fix N+1 in `add_shifts_to_turnus_set` in `app/services/turnus_service.py`**

  Replace the inner loop at lines 146–154:
  ```python
  # Before
  for x in turnus_data:
      for name in x.keys():
          existing = db_session.query(Shifts).filter_by(
              title=name,
              turnus_set_id=turnus_set_id
          ).first()
          if not existing:
              new_shift = Shifts(title=name, turnus_set_id=turnus_set_id)
              db_session.add(new_shift)
  ```
  Replace with:
  ```python
  # After — one SELECT for all existing titles, then batch insert new ones
  existing_titles = {
      r.title
      for r in db_session.query(Shifts.title).filter_by(turnus_set_id=turnus_set_id).all()
  }
  for x in turnus_data:
      for name in x.keys():
          if name not in existing_titles:
              db_session.add(Shifts(title=name, turnus_set_id=turnus_set_id))
              existing_titles.add(name)
  ```

- [ ] **Step 4: Run test to confirm N+1 fix**

  ```bash
  pytest tests/test_turnus_service.py::TestAddShiftsNoNPlusOne -v
  ```
  Expected: PASS.

- [ ] **Step 5: Cache `get_active_turnus_set` in `app/services/turnus_service.py`**

  Add import at the top of the file (after `from app.models import TurnusSet, Shifts, Favorites`):
  ```python
  from app.extensions import cache
  ```

  Add `@cache.memoize(timeout=60)` decorator to `get_active_turnus_set`:
  ```python
  @cache.memoize(timeout=60)
  def get_active_turnus_set():
      """Get the currently active turnus set"""
      db_session = get_db_session()
      try:
          active_set = db_session.query(TurnusSet).filter_by(is_active=1).first()
          if active_set:
              return {
                  'id': active_set.id,
                  'name': active_set.name,
                  'year_identifier': active_set.year_identifier,
                  'is_active': active_set.is_active,
                  'created_at': active_set.created_at,
                  'turnus_file_path': active_set.turnus_file_path,
                  'df_file_path': active_set.df_file_path
              }
          return None
      finally:
          db_session.close()
  ```

  Add cache invalidation in `set_active_turnus_set` (after `db_session.commit()`):
  ```python
  def set_active_turnus_set(turnus_set_id):
      """Switch which turnus set is currently active"""
      db_session = get_db_session()
      try:
          db_session.query(TurnusSet).update({'is_active': 0})

          turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
          if not turnus_set:
              return False, "Turnussett ikke funnet"

          turnus_set.is_active = 1
          db_session.commit()
          cache.delete_memoized(get_active_turnus_set)  # invalidate after commit
          return True, f"Turnussett {turnus_set.year_identifier} er nå aktivt"
      except Exception as e:
          db_session.rollback()
          return False, f"Error setting active turnus set: {e}"
      finally:
          db_session.close()
  ```

- [ ] **Step 6: Fix `get_all_stub_users` to select only needed columns in `app/services/user_service.py`**

  Lines 1211–1213 currently read:
  ```python
  users = (
      db_session.query(DBUser)
      .order_by(
          func.coalesce(DBUser.seniority_nr, 999999).asc(),
          DBUser.id.asc(),
      )
      .all()
  )
  ```
  Replace with a column-only query (avoids loading `password`, `has_seen_*`, `email_verified`, etc.):
  ```python
  users = (
      db_session.query(
          DBUser.id,
          DBUser.rullenummer,
          DBUser.medlemsnummer,
          DBUser.name,
          DBUser.stasjoneringssted,
          DBUser.ans_dato,
          DBUser.fodt_dato,
          DBUser.seniority_nr,
          DBUser.is_stub,
          DBUser.is_auth,
          DBUser.email,
          DBUser.username,
          DBUser.not_on_nlf_list,
      )
      .order_by(
          func.coalesce(DBUser.seniority_nr, 999999).asc(),
          DBUser.id.asc(),
      )
      .all()
  )
  ```
  The rest of the function body uses only these attributes via `.attr` access on the SQLAlchemy `Row` named-tuple, so no other changes are needed.

- [ ] **Step 7: Fix batch deletes in `delete_missing_stubs` and `delete_stub_users`**

  **`delete_missing_stubs`** — replace the per-user loop (lines 1282–1284):
  ```python
  # Before
  count = len(targets)
  for user in targets:
      db_session.query(FavModel).filter_by(user_id=user.id).delete()
      db_session.delete(user)
  db_session.commit()
  ```
  Replace with:
  ```python
  # After
  count = len(targets)
  if count:
      ids = [u.id for u in targets]
      db_session.query(FavModel).filter(FavModel.user_id.in_(ids)).delete(synchronize_session=False)
      db_session.query(DBUser).filter(DBUser.id.in_(ids)).delete(synchronize_session=False)
  db_session.commit()
  ```

  **`delete_stub_users`** — replace the per-user loop (lines 1315–1317):
  ```python
  # Before
  count = len(targets)
  for user in targets:
      db_session.query(FavModel).filter_by(user_id=user.id).delete()
      db_session.delete(user)
  db_session.commit()
  ```
  Replace with:
  ```python
  # After
  count = len(targets)
  if count:
      ids = [u.id for u in targets]
      db_session.query(FavModel).filter(FavModel.user_id.in_(ids)).delete(synchronize_session=False)
      db_session.query(DBUser).filter(DBUser.id.in_(ids)).delete(synchronize_session=False)
  db_session.commit()
  ```

- [ ] **Step 8: Run full test suite**

  ```bash
  pytest
  ```
  Expected: all pass.

- [ ] **Step 9: Commit**
  ```bash
  git add app/services/turnus_service.py app/services/user_service.py tests/conftest.py
  git commit -m "perf: cache get_active_turnus_set; fix N+1 in shift import; batch stub deletes; column-only query in get_all_stub_users"
  ```

---

## Production deployment order

After all tasks are committed and merged:

1. Deploy the code.
2. On the server: `alembic upgrade head`
   - This runs migrations 014, 015, 016 in order.
   - **Before 016 runs**, the migration itself prints the orphan check SQL — verify those return 0 before proceeding (or comment out the FK migration if orphans exist and clean them first).
3. Restart gunicorn.

No downtime required for any migration (all are `ADD INDEX` / `MODIFY COLUMN` with no table locks beyond the column alter on `flask_sessions.data` which is typically fast on a small sessions table).
