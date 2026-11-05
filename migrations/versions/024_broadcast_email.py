"""Email from admins to all users: the opt-out setting and the send's state

Revision ID: 024_broadcast_email
Revises: 023_h_dag_jobb_valgfri
Create Date: 2026-11-04

Adds one column to users and two new tables. Touches nothing else.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_broadcast_email"
down_revision: Union[str, None] = "023_h_dag_jobb_valgfri"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("announcements_opt_out", sa.Integer(), nullable=False, server_default="0")
        )

    op.create_table(
        "broadcast_emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("stop_requested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_reason", sa.String(255), nullable=True),
        sa.Column("test_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "broadcast_recipients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "broadcast_id", sa.Integer(),
            sa.ForeignKey("broadcast_emails.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipient"),
    )
    op.create_index("ix_broadcast_recipient_state", "broadcast_recipients", ["broadcast_id", "state"])


def downgrade() -> None:
    op.drop_table("broadcast_recipients")
    op.drop_table("broadcast_emails")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("announcements_opt_out")
