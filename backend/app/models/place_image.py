from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.place import Place


class PlaceImage(Base):
    __tablename__ = "place_images"

    __table_args__ = (
        UniqueConstraint(
            "place_id",
            "source",
            "source_image_id",
            name="uq_place_images_place_source_image",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    place_id: Mapped[int] = mapped_column(
        ForeignKey(
            "places.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    source_image_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    image_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    thumbnail_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_page_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    attribution: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    license: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    license_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    place: Mapped[Place] = relationship()