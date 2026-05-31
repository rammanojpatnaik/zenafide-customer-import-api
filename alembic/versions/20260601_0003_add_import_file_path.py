"""Add durable import file path.

Revision ID: 20260601_0003
Revises: 20260601_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260601_0003"
down_revision: Union[str, None] = "20260601_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("stored_file_path", sa.String(length=1000), nullable=True),
    )
    op.execute("UPDATE import_jobs SET stored_file_path = '' WHERE stored_file_path IS NULL")
    op.alter_column("import_jobs", "stored_file_path", nullable=False)


def downgrade() -> None:
    op.drop_column("import_jobs", "stored_file_path")
