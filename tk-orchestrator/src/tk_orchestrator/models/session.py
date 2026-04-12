from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session

from ..config import Config
from .tables import Base

_engine = None


def init_db(config: Config) -> None:
    global _engine
    db_url = f"sqlite:///{config.db_path.resolve()}"
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})

    event.listen(
        _engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON")
    )

    Base.metadata.create_all(_engine)
    _run_migrations()


def _run_migrations() -> None:
    engine = get_engine()
    inspector = inspect(engine)

    if "comments" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("comments")}
        if "zh" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE comments ADD COLUMN zh TEXT"))

    if "jobs" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("jobs")}
        if "last_completed_step" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN last_completed_step TEXT")
                )


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
