from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings


def build_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine = build_engine(get_settings().database_url)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_database_session() -> Generator[Session, None, None]:
    with SessionFactory() as session:
        yield session
