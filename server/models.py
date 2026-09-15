"""Modelo ORM da tabela `audios` (campos conforme especificação do trabalho)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class GUID(TypeDecorator):
    """UUID portátil: nativo no PostgreSQL, CHAR(36) nos demais bancos (SQLite)."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: D102
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PGUUID

            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # noqa: D102
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):  # noqa: D102
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return uuid.UUID(str(value))


class Audio(Base):
    __tablename__ = "audios"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_ext: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_type: Mapped[str] = mapped_column(String(50), nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    path_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    path_processed: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "original_name": self.original_name,
            "original_ext": self.original_ext,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "duration_sec": self.duration_sec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bitrate": self.bitrate,
            "processing_type": self.processing_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "path_original": self.path_original,
            "path_processed": self.path_processed,
        }
