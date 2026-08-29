"""SQLAlchemy foundation for the platform-owned PostgreSQL database."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.config.database import PlatformDatabaseSettings


def create_platform_engine(settings: PlatformDatabaseSettings) -> Engine:
    """Create an engine without opening a database connection."""
    return create_engine(settings.dsn, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the platform session factory without creating tables or connecting."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield one transaction-scoped session and roll back failed work."""
    with factory.begin() as session:
        yield session
