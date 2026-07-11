from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.database.connection import Database
from app.models.user import User


EGYPT_TIMEZONE = ZoneInfo("Africa/Cairo")


CRM_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crm_sources (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sequence INTEGER NOT NULL DEFAULT 100,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF