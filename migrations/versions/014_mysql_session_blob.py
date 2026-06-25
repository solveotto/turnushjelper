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
