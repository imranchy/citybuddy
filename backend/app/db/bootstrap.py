from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import BASE_DIR

if TYPE_CHECKING:
    from sqlalchemy import Engine


REQUIRED_EXTENSIONS = ("postgis", "vector")


def ensure_required_extensions(engine: "Engine | None" = None) -> None:
    """Enable database extensions required by CityBuddy before schema migrations."""

    if engine is None:
        from app.db.database import engine as configured_engine

        engine = configured_engine
    with engine.begin() as connection:
        for extension in REQUIRED_EXTENSIONS:
            connection.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))


def upgrade_schema(alembic_ini: Path | None = None) -> None:
    """Upgrade the application schema to the latest committed Alembic revision."""

    config_path = alembic_ini or (BASE_DIR / "alembic.ini")
    config = Config(str(config_path))
    command.upgrade(config, "head")


def bootstrap_database(
    *,
    engine: "Engine | None" = None,
    alembic_ini: Path | None = None,
) -> None:
    ensure_required_extensions(engine)
    upgrade_schema(alembic_ini)
