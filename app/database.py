"""
app/database.py
SQLAlchemy engine + session, same pattern as BookIQ's Postgres setup but
defaults to SQLite for zero-config local dev. Swap DATABASE_URL for Postgres
in production exactly like we did for BookIQ on Render.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
