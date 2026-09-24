"""Database session factory; importing it never opens a database connection."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine() -> Engine:
    """Build the PostgreSQL engine used by web requests and worker processes."""

    return create_engine(get_settings().database_url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session]:
    """Yield a transactional session to a future endpoint or worker."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
