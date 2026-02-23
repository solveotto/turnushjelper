"""create initial schema (all 6 tables)

Revision ID: 000_initial_schema
Revises: —
Create Date: 2026-02-19

Baseline migration that creates the full schema as it existed before
Alembic was introduced.  The ``has_seen_turnusliste_tour`` column on
``users`` is intentionally omitted — it is added by the next migration
(001_add_tour_tracking).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "000_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rullenummer", sa.String(10), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("password", sa.String(255), nullable=False),
        sa.Column("is_auth", sa.Integer(), server_default="0"),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("verification_sent_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "authorized_emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("rullenummer", sa.String(50), nullable=True),
        sa.Column(
            "added_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("added_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("notes", sa.String(500)),
        sa.UniqueConstraint("email", "rullenummer", name="unique_email_rullenummer"),
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(255), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Integer(), server_default="0"),
        sa.Column("token_type", sa.String(50), server_default="'verification'"),
    )

    op.create_table(
        "turnus_sets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("year_identifier", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("turnus_file_path", sa.String(500), nullable=True),
        sa.Column("df_file_path", sa.String(500), nullable=True),
        sa.UniqueConstraint("year_identifier"),
    )

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("shift_title", sa.String(255), nullable=False),
        sa.Column("turnus_set_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0"),
        sa.UniqueConstraint("user_id", "shift_title", "turnus_set_id"),
    )

    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("turnus_set_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("title", "turnus_set_id"),
    )


def downgrade() -> None:
    op.drop_table("shifts")
    op.drop_table("favorites")
    op.drop_table("turnus_sets")
    op.drop_table("email_verification_tokens")
    op.drop_table("authorized_emails")
    op.drop_table("users")
