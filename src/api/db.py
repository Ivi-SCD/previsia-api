"""Database engine + session helper (Supabase Postgres)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
