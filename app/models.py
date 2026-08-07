"""
app/models.py
ORM models. Every trade the bot makes (paper or live) gets a row here -
this is what makes the backtest/performance reporting possible later,
and it's what you'd show a recruiter: "here's the DB-backed trade history,
not just console logs."
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from datetime import datetime

from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String, index=True)
    side = Column(String)          # "BUY" or "SELL"
    qty = Column(Integer)
    price = Column(Float)
    value = Column(Float)
    cash_after = Column(Float)
    is_live = Column(Boolean, default=False)
    strategy_name = Column(String, default="ema_rsi")


class PriceTick(Base):
    """Every price the bot observes gets logged here - this is what powers the
    candlestick chart on the frontend. Cleared out periodically in real use,
    but fine to just grow for now."""
    __tablename__ = "price_ticks"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String, index=True)
    price = Column(Float)


class BotSession(Base):
    """One row per bot run, so we can compare strategy performance across runs."""
    __tablename__ = "bot_sessions"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    symbol = Column(String)
    strategy_name = Column(String)
    starting_capital = Column(Float)
    final_value = Column(Float, nullable=True)
    is_live = Column(Boolean, default=False)
    status = Column(String, default="running")  # running / stopped / crashed

class User(Base):
    """Real user accounts, Phase 1 of moving from single-shared-bot to
    per-user portfolios. Phase 2 will add user_id foreign keys to Trade
    and BotSession once this is tested and stable."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)