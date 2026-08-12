"""
app/routes_user_bot.py
Per-user, JWT-authenticated bot control - Phase 2. Each logged-in user gets
their own isolated BotRunner (own portfolio, own trades, own history) via
UserBotManager. Kept as a separate router from the old API-key-protected
routes.py so nothing about the existing public research/backtest endpoints
changes.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Trade, BotSession, User
from app.auth_user import get_current_user
from app.bot_runner import user_bot_manager
from app.models import Trade, BotSession, User, PortfolioSnapshot

user_bot_router = APIRouter()


@user_bot_router.post("/me/bot/start")
def start_my_bot(symbols: Optional[str] = None, strategy: str = "mean_reversion",
                  tick_seconds: float = Query(60, gt=0, le=300),
                  starting_capital: Optional[float] = Query(None, gt=0),
                  current_user: User = Depends(get_current_user)):
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    return user_bot_manager.start(current_user.id, symbols=symbol_list,
                                    strategy_name=strategy, tick_seconds=tick_seconds,
                                    starting_capital=starting_capital)


@user_bot_router.post("/me/bot/stop")
def stop_my_bot(current_user: User = Depends(get_current_user)):
    return user_bot_manager.stop(current_user.id)


@user_bot_router.get("/me/bot/status")
def my_bot_status(current_user: User = Depends(get_current_user)):
    return user_bot_manager.status(current_user.id)


@user_bot_router.get("/me/watchlist/screener")
def my_screener(current_user: User = Depends(get_current_user)):
    return user_bot_manager.screener(current_user.id)


@user_bot_router.get("/me/trades")
def my_trades(limit: int = Query(50, gt=0, le=500), db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    trades = (db.query(Trade).filter(Trade.user_id == current_user.id)
              .order_by(desc(Trade.timestamp)).limit(limit).all())
    return [
        {"id": t.id, "timestamp": t.timestamp.isoformat(), "symbol": t.symbol,
         "side": t.side, "qty": t.qty, "price": t.price, "value": t.value,
         "cash_after": t.cash_after, "is_live": t.is_live, "strategy": t.strategy_name}
        for t in trades
    ]


@user_bot_router.get("/me/sessions")
def my_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = (db.query(BotSession).filter(BotSession.user_id == current_user.id)
                .order_by(desc(BotSession.started_at)).all())
    return [
        {"id": s.id, "started_at": s.started_at.isoformat(),
         "ended_at": s.ended_at.isoformat() if s.ended_at else None,
         "symbol": s.symbol, "strategy": s.strategy_name,
         "starting_capital": s.starting_capital, "final_value": s.final_value,
         "status": s.status}
        for s in sessions
    ]

@user_bot_router.get("/me/portfolio/history")
def my_portfolio_history(limit: int = Query(500, gt=0, le=5000),
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Powers the Dashboard equity curve - one point per bot tick."""
    snapshots = (db.query(PortfolioSnapshot)
                 .filter(PortfolioSnapshot.user_id == current_user.id)
                 .order_by(desc(PortfolioSnapshot.timestamp))
                 .limit(limit).all())
    snapshots.reverse()  # oldest-to-newest for the chart, but we fetched newest-first
    return [
        {"time": s.timestamp.isoformat(), "value": s.portfolio_value}
        for s in snapshots
    ]