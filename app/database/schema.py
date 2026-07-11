import os

from app.database.connection import Database
from app.database.migrations import run_migrations
from app.security.passwords import hash_password


def initialize_database(database: Database) -> None:
    with database.session() as connection:
        run_migrations(connection)
        connection.execute(
            "INSERT OR IGNORE INTO warehouses(code, name) VALUES (?, ?)",
            ("MAIN", "المصنع"