from html import escape

from app.utils.datetime_utils import format_egypt_datetime


def _text(value: object) -> str:
    return escape(str(value or ""))


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


def _company_name_html(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
