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
    method = str(payment_method or "").strip()
    return set(PAYMENT_METHOD_ACCOUNT_TYPES.get(method, set()))


def account_matches_payment_method(payment_method: str, account_type: str) -> bool:
    """Check that a selected cash/bank/wallet account matches the payment method."""
    allowed = allowed_account_types(payment_method)
    return bool(allowed) and str(account_type or "").strip() in allowed


def expected_account_label(payment_method: str) -> str:
    allowed = allowed_account_types(payment_method)
    if not allowed:
        return "حساب مالي مناسب"
    return " أو ".join(ACCOUNT_TYPE_LABELS.get(item, item) for item in sorted(allowed))


__all__ = [
    "PAYMENT_METHOD_ACCOUNT_TYPES",
    "ACCOUNT_TYPE_LABELS",
    "allowed_account_types",
    "account_matches_payment_method",
    "expected_account_label",
]
