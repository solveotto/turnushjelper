"""authorized_emails: rullenummer-only authorization

Revision ID: 002_authorized_emails_rullenummer_only
Revises: 001_add_tour_tracking
Create Date: 2026-02-22

Changes:
- authorized_emails.email: nullable=False → nullable=True
- Drop unique constraint on (email, rullenummer)
- Add unique constraint on (rullenummer) only
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_authorized_emails_rullenummer_only"
down_revision: Union[str, None] = "001_add_tour_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("authorized_emails") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(255), nullable=True)
        # Note: pre-Alembic databases have an unnamed UNIQUE(email) constraint
        # that cannot be dropped by name.  SQLite allows multiple NULLs even
        # with a UNIQUE constraint, so leaving it is harmless for our use case.
        batch_op.create_unique_constraint("unique_rullenummer", ["rullenummer"])


def downgrade() -> None:
    with op.batch_alter_table("authorized_emails") as batch_op:
        batch_op.drop_constraint("unique_rullenummer", type_="unique")
        batch_op.alter_column("email", existing_type=sa.String(255), nullable=False)
