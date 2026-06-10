from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChunkParent(Base):
    __tablename__ = "chunk_parents"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(255))
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_start: Mapped[int]
    page_end: Mapped[int]
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    car_make: Mapped[str | None] = mapped_column(String(50), nullable=True)
    car_models: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())