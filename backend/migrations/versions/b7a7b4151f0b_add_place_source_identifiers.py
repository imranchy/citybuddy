"""add place source identifiers

Revision ID: b7a7b4151f0b
Revises: c4052ecb1bee
Create Date: 2026-08-03
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# Revision identifiers used by Alembic.
revision: str = "b7a7b4151f0b"
down_revision: str | Sequence[str] | None = "c4052ecb1bee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add identifiers for externally imported places."""

    op.add_column(
        "places",
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
        ),
    )

    op.add_column(
        "places",
        sa.Column(
            "source_id",
            sa.String(length=100),
            nullable=False,
        ),
    )

    op.create_unique_constraint(
        "uq_places_source_source_id",
        "places",
        ["source", "source_id"],
    )


def downgrade() -> None:
    """Remove external-source identifiers."""

    op.drop_constraint(
        "uq_places_source_source_id",
        "places",
        type_="unique",
    )

    op.drop_column("places", "source_id")
    op.drop_column("places", "source")