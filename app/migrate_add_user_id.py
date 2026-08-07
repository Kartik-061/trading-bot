"""
app/migrate_add_user_id.py
One-time migration: adds user_id to trades/bot_sessions (SQLite ALTER TABLE
ADD COLUMN, safe since it's nullable), creates a "system" placeholder user,
and backfills every existing row to that user so today's real trading
history isn't lost.

Run once: python -m app.migrate_add_user_id
Safe to re-run - checks before altering/backfilling.
"""
from sqlalchemy import text, inspect
from app.database import engine, SessionLocal, Base
from app.models import User

SYSTEM_EMAIL = "system@tradebot.internal"


def column_exists(table: str, column: str) -> bool:
    inspector = inspect(engine)
    return column in [c["name"] for c in inspector.get_columns(table)]


def run_migration():
    Base.metadata.create_all(bind=engine)  # ensure users table exists

    with engine.begin() as conn:
        if not column_exists("trades", "user_id"):
            conn.execute(text("ALTER TABLE trades ADD COLUMN user_id INTEGER"))
            print("Added user_id to trades")
        if not column_exists("bot_sessions", "user_id"):
            conn.execute(text("ALTER TABLE bot_sessions ADD COLUMN user_id INTEGER"))
            print("Added user_id to bot_sessions")

    db = SessionLocal()
    try:
        system_user = db.query(User).filter(User.email == SYSTEM_EMAIL).first()
        if not system_user:
            system_user = User(email=SYSTEM_EMAIL, hashed_password="!no-login!")
            db.add(system_user)
            db.commit()
            db.refresh(system_user)
            print(f"Created system user id={system_user.id}")

        with engine.begin() as conn:
            r1 = conn.execute(text("UPDATE trades SET user_id = :uid WHERE user_id IS NULL"), {"uid": system_user.id})
            r2 = conn.execute(text("UPDATE bot_sessions SET user_id = :uid WHERE user_id IS NULL"), {"uid": system_user.id})
            print(f"Backfilled {r1.rowcount} trades, {r2.rowcount} bot_sessions to system user")
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()