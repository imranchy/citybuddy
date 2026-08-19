"""add official evidence metadata

Revision ID: 8b4e8d2a7c31
Revises: f27b9d4d6c10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b4e8d2a7c31"
down_revision: Union[str, Sequence[str], None] = "f27b9d4d6c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("place_evidence", sa.Column("content_type", sa.String(length=60), nullable=True))
    op.add_column("place_evidence", sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_place_evidence_content_type", "place_evidence", ["content_type"])


def downgrade() -> None:
    op.drop_index("ix_place_evidence_content_type", table_name="place_evidence")
    op.drop_column("place_evidence", "source_fetched_at")
    op.drop_column("place_evidence", "content_type")
