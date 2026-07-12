from __future__ import annotations

from app.database.connection import Database
from app.models.user import User
from app.security.passwords import hash_password, verify_password


PERMISSIONS = (
    ("dashboard", "الرئيسية"),
    ("crm", "CRM متابعة العملاء"),
    ("products", "الأصناف"),
    ("suppliers", "الموردين"),
    ("customers", "العملاء"),
    ("warehouse", "إعداد المخ