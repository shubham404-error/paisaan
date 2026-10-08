from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(24), nullable=True)
    company_name: Mapped[str] = mapped_column(String(256))
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class IndexMembership(Base):
    __tablename__ = "index_memberships"
    __table_args__ = (UniqueConstraint("index_code", "instrument_id", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(24), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64))


class DailyBar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (UniqueConstraint("instrument_id", "trading_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)


class TechnicalSnapshot(Base):
    __tablename__ = "technical_snapshots"
    __table_args__ = (UniqueConstraint("instrument_id", "trading_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    sma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma100: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema50: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema100: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema200: Mapped[float | None] = mapped_column(Float, nullable=True)
    d20: Mapped[float | None] = mapped_column(Float, nullable=True)
    d50: Mapped[float | None] = mapped_column(Float, nullable=True)
    d100: Mapped[float | None] = mapped_column(Float, nullable=True)
    d200: Mapped[float | None] = mapped_column(Float, nullable=True)
    above_ma_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rsi14: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr14_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol1y: Mapped[float | None] = mapped_column(Float, nullable=True)
    maxdd1y: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta_equal_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    rel_strength_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1w: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_volume_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_turnover_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_spikes_20d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1y: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_3y_cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_high_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_low_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_52w_high: Mapped[bool] = mapped_column(Boolean, default=False)
    new_52w_low: Mapped[bool] = mapped_column(Boolean, default=False)
    golden_cross_20d: Mapped[bool] = mapped_column(Boolean, default=False)
    death_cross_20d: Mapped[bool] = mapped_column(Boolean, default=False)


class SectorDailyMetric(Base):
    __tablename__ = "sector_daily_metrics"
    __table_args__ = (UniqueConstraint("index_code", "industry", "trading_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(24), index=True)
    industry: Mapped[str] = mapped_column(String(128), index=True)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    members: Mapped[int] = mapped_column(Integer)
    advancers: Mapped[int] = mapped_column(Integer)
    decliners: Mapped[int] = mapped_column(Integer)
    average_change_pct: Mapped[float] = mapped_column(Float)
    turnover: Mapped[float] = mapped_column(Float)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
