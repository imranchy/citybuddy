from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geography

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)


from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Place(Base):
    __tablename__ = "places"

    __table_args__ = (
        CheckConstraint(
            "price_level BETWEEN 1 AND 4",
            name="ck_places_price_level",
        ),
        CheckConstraint(
            "rating BETWEEN 0 AND 5",
            name="ck_places_rating",
        ),
        UniqueConstraint(
            "source",
            "source_id",
            name="uq_places_source_source_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    source_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )

    location: Mapped[object] = mapped_column(
        Geography(
            geometry_type="POINT",
            srid=4326,
            spatial_index=True,
        ),
        nullable=False,
    )

    price_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    rating: Mapped[Decimal | None] = mapped_column(
        Numeric(2, 1),
        nullable=True,
    )

    dietary_options: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    opening_hours: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    website: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    operator: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
