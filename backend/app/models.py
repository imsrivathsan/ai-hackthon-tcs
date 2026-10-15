from datetime import datetime, timezone
import uuid
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    headquarters: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    market_cap_tier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[List["Item"]] = relationship(
        "Item", back_populates="competitor", cascade="all, delete-orphan", order_by="desc(Item.date)"
    )
    battlecard: Mapped[Optional["Battlecard"]] = relationship(
        "Battlecard", back_populates="competitor", uselist=False, cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    competitor_id: Mapped[str] = mapped_column(String(64), ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    tag: Mapped[str] = mapped_column(String(32), nullable=False)  # M&A, Leadership, Product, Pricing
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO format YYYY-MM-DD
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    impact_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 - 5
    is_sample: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    competitor: Mapped["Competitor"] = relationship("Competitor", back_populates="items")


class Battlecard(Base):
    __tablename__ = "battlecards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    competitor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("competitors.id", ondelete="CASCADE"), unique=True, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # High, Medium, Low
    threat_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 - 100
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    subtext: Mapped[str] = mapped_column(Text, nullable=False)
    wins: Mapped[list] = mapped_column(JSON, nullable=False)  # Exactly 3 wins
    moves: Mapped[list] = mapped_column(JSON, nullable=False)  # Exactly 3 moves
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)  # ma_deals_12m, activity_trend, evidence_confidence
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    competitor: Mapped["Competitor"] = relationship("Competitor", back_populates="battlecard")
