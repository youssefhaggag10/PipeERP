PAYMENT_METHOD_ACCOUNT_TYPES = {
    "نقدي": {"cash"},
    "تحويل بنكي": {"bank"},
    "شيك": {"bank"},
    "محفظة إلكترونية": {"wallet"},
}

ACCOUNT_TYPE_LABELS = {
    "cash": "خزينة نقدية",
    "bank": "حساب بنكي",
    "wallet": "محفظة إلكترونية",
    "other": "حساب دفع آخر",
}


def allowed_account_types(payment_method: str) -> set[str]:
    """Return the financial-account types compatible with a payment method."""
    return set