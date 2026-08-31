"""Typed SQLAlchemy session factory and transaction boundary helpers."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.tenant_context import TenantAwareSession
from app.bootstrap.settings import Settings


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=TenantAwareSession,
        expire_on_commit=False,
        autoflush=False,
    )


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Provide a commit/rollback/close transaction boundary."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """FastAPI-compatible session dependency for future HTTP adapters."""

    factory = create_session_factory(get_engine(settings))
    with session_scope(factory) as session:
        yield session
