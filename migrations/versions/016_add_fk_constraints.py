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

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_fk_constraints"
down_revision: Union[str, None] = "015_add_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_exists(bind, name):
    result = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name "
            "AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
        ),
        {"name": name},
    )
    return result.scalar() > 0


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    if not _fk_exists(bind, "fk_favorites_user_id"):
        op.create_foreign_key(
            "fk_favorites_user_id", "favorites", "users", ["user_id"], ["id"],
            ondelete="CASCADE",
        )
    if not _fk_exists(bind, "fk_favorites_turnus_set_id"):
        op.create_foreign_key(
            "fk_favorites_turnus_set_id", "favorites", "turnus_sets", ["turnus_set_id"], ["id"],
            ondelete="CASCADE",
        )
    if not _fk_exists(bind, "fk_shifts_turnus_set_id"):
        op.create_foreign_key(
            "fk_shifts_turnus_set_id", "shifts", "turnus_sets", ["turnus_set_id"], ["id"],
            ondelete="CASCADE",
        )
    if not _fk_exists(bind, "fk_soknadsskjema_user_id"):
        op.create_foreign_key(
            "fk_soknadsskjema_user_id", "soknadsskjema_choices", "users", ["user_id"], ["id"],
            ondelete="CASCADE",
        )
    if not _fk_exists(bind, "fk_soknadsskjema_turnus_set_id"):
        op.create_foreign_key(
            "fk_soknadsskjema_turnus_set_id", "soknadsskjema_choices", "turnus_sets", ["turnus_set_id"], ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    if _fk_exists(bind, "fk_favorites_user_id"):
        op.drop_constraint("fk_favorites_user_id", "favorites", type_="foreignkey")
    if _fk_exists(bind, "fk_favorites_turnus_set_id"):
        op.drop_constraint("fk_favorites_turnus_set_id", "favorites", type_="foreignkey")
    if _fk_exists(bind, "fk_shifts_turnus_set_id"):
        op.drop_constraint("fk_shifts_turnus_set_id", "shifts", type_="foreignkey")
    if _fk_exists(bind, "fk_soknadsskjema_user_id"):
        op.drop_constraint("fk_soknadsskjema_user_id", "soknadsskjema_choices", type_="foreignkey")
    if _fk_exists(bind, "fk_soknadsskjema_turnus_set_id"):
        op.drop_constraint("fk_soknadsskjema_turnus_set_id", "soknadsskjema_choices", type_="foreignkey")
