"""strekliste_dagsverk and strekliste_aktivitet — the streker PDF as data

Revision ID: 018_strekliste_tables
Revises: 017_unique_rullenummer
Create Date: 2026-09-23

Until now the strekliste PDF was only cut into PNGs. These tables hold what
the PDF draws: one row per duty (number, weekdays, start, end) and one row
per segment of its bar (times, stations, type, train numbers), as read by
app/utils/pdf/strekliste_parser.py. Plan data for a rutetermin — a re-parse
replaces a turnus set's rows wholesale, so nothing here needs a status.

The duty key includes kjoredager: 1310 exists on days 2+5 and on days 3+4
as two different duties with the same number.

Hand-written with named constraints. The JSON columns are nullable and carry
no server_default: MySQL refuses a literal default on JSON.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_strekliste_tables"
down_revision: Union[str, None] = "017_unique_rullenummer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strekliste_dagsverk",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("turnus_set_id", sa.Integer(), nullable=False),
        sa.Column("stasjoneringssted", sa.String(length=10), nullable=True),
        sa.Column("nr", sa.String(length=20), nullable=False),
        sa.Column("nr_base", sa.String(length=10), nullable=False),
        sa.Column("kjoredager", sa.String(length=7), nullable=False, server_default=""),
        sa.Column("materiell", sa.String(length=120), nullable=True),
        sa.Column("start", sa.String(length=5), nullable=True),
        sa.Column("slutt", sa.String(length=5), nullable=True),
        sa.Column("slutt_neste_dag", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("side", sa.Integer(), nullable=True),
        sa.Column("beregninger", sa.JSON(), nullable=True),
        sa.Column("kommentar", sa.String(length=300), nullable=True),
        sa.Column("advarsler", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_strekliste_dagsverk"),
        sa.ForeignKeyConstraint(
            ["turnus_set_id"], ["turnus_sets.id"],
            name="fk_strekliste_dagsverk_turnus_set", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("turnus_set_id", "stasjoneringssted", "nr", "kjoredager",
                            name="uq_strekliste_dagsverk_nokkel"),
    )
    op.create_index("ix_strekliste_dagsverk_base", "strekliste_dagsverk",
                    ["turnus_set_id", "nr_base"])

    op.create_table(
        "strekliste_aktivitet",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dagsverk_id", sa.Integer(), nullable=False),
        sa.Column("radnr", sa.Integer(), nullable=False),
        sa.Column("fra_tid", sa.String(length=5), nullable=True),
        sa.Column("til_tid", sa.String(length=5), nullable=True),
        sa.Column("fra_neste_dag", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("til_neste_dag", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fra_stasjon", sa.String(length=10), nullable=True),
        sa.Column("til_stasjon", sa.String(length=10), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("monster", sa.String(length=30), nullable=True),
        sa.Column("tognumre", sa.String(length=120), nullable=True),
        sa.Column("tekst", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_strekliste_aktivitet"),
        sa.ForeignKeyConstraint(
            ["dagsverk_id"], ["strekliste_dagsverk.id"],
            name="fk_strekliste_aktivitet_dagsverk", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("dagsverk_id", "radnr", name="uq_strekliste_aktivitet_rad"),
    )
    op.create_index("ix_strekliste_aktivitet_dagsverk", "strekliste_aktivitet",
                    ["dagsverk_id", "radnr"])


def downgrade() -> None:
    op.drop_index("ix_strekliste_aktivitet_dagsverk", table_name="strekliste_aktivitet")
    op.drop_table("strekliste_aktivitet")
    op.drop_index("ix_strekliste_dagsverk_base", table_name="strekliste_dagsverk")
    op.drop_table("strekliste_dagsverk")
