import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class Database:
    """Small SQLite wrapper used by services and repositories."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def session(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            if immediate:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.session() as connection:
            return connection.execute(query, tuple(params))

    def fetch_one(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.session() as connection:
            return connection.execute(query, tuple(params)).fetchone()

    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(connection.execute(query, tuple(params)).fetchall())
