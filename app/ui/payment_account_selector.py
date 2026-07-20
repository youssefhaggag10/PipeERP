from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from app.services.payment_account_rules import allowed_account_types, expected_account_label

PAYMENT_METHODS = ["نقدي", "تحويل بنكي", "شيك", "محفظة إلكترونية"]


def choose_payment_method(parent: QWidget) -> str | None:
    method, accepted = QInputDialog.getItem(
        parent,
        "طريقة الدفع",
        "اختر طريقة الدفع:",
        PAYMENT_METHODS,
        0,
        False,
    )
    return str(method) if accepted else None


def choose_financial_account(parent: QWidget, repository, payment_method: str) -> int | None:
    allowed_types = allowed_account_types(payment_method)
    accounts = [
        account
        for account in repository.list_financial_accounts()
        if str(account.get("account_type", "")) in allowed_types
    ]
    if not accounts:
        QMessageBox.warning(
            parent,
            "لا يوجد حساب مناسب",
            f"لا يوجد {expected_account_label(payment_method)} نشط لطريقة الدفع «{payment_method}». "
            "أضف الحساب أولًا من تبويب الخزينة والبنوك.",
        )
        return None

    labels = [
        f"{account['name']} — رصيد {float(account.get('current_balance', 0)):,.2f}"
        for account in accounts
    ]
    selected_label, accepted = QInputDialog.getItem(
        parent,
        "حساب الدفع",
        f"اختر الحساب المستخدم في {payment_method}:",
        labels,
        0,
        False,
    )
    if not accepted:
        return None
    index = labels.index(str(selected_label))
    return int(accounts[index]["id"])


__all__ = ["PAYMENT_METHODS", "choose_payment_method", "choose_financial_account"]
