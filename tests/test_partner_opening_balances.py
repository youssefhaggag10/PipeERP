from datetime import date
from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.migrations import run_migrations
from app.database.sales_finance_v10_schema import ensure_sales_finance_v10_schema
from app.database.schema import initialize_database
from app.repositories.customer_statement_accounting_repository import (
    CustomerStatementAccountingRepository,
)
from app.repositories.detailed_return_refund_repository import (
    DetailedReturnRefundRepository,
)


def _create_user(
    database: Database,
    *,
    username: str,
    role: str,
    accounts_permission: bool = False,
) -> int:
    with database.session(immediate=True) as connection:
        user_id = int(
            connection.execute(
                """
                INSERT INTO users(username, password_hash, full_name, role)
                VALUES (?, 'test-password-hash', ?, ?)
                """,
                (username, f"مستخدم {username}", role),
            ).lastrowid
        )
        if accounts_permission:
            connection.execute(
                """
                INSERT INTO user_permissions(user_id, permission_code, allowed)
                VALUES (?, 'accounts', 1)
                """,
                (user_id,),
            )
        return user_id


def _create_partner(
    database: Database,
    *,
    partner_type: str,
    code: str,
    name: str,
    opening_balance: float = 0,
) -> int:
    with database.session(immediate=True) as connection:
        return int(
            connection.execute(
                """
                INSERT INTO partners(
                    partner_type, code, name, opening_balance
                ) VALUES (?, ?, ?, ?)
                """,
                (partner_type, code, name, float(opening_balance)),
            ).lastrowid
        )


def test_all_opening_balance_natures_update_accounts_without_touching_treasury(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "opening-balances.sqlite3")
    initialize_database(database)
    admin_id = _create_user(database, username="admin", role="admin")
    customer_debit = _create_partner(
        database,
        partner_type="customer",
        code="C-DB",
        name="عميل مدين",
    )
    customer_credit = _create_partner(
        database,
        partner_type="customer",
        code="C-CR",
        name="عميل دائن",
    )
    supplier_credit = _create_partner(
        database,
        partner_type="supplier",
        code="S-CR",
        name="مورد دائن",
    )
    supplier_debit = _create_partner(
        database,
        partner_type="supplier",
        code="S-DB",
        name="مورد مدين",
    )
    repository = DetailedReturnRefundRepository(database)
    treasury_before = {
        int(row["id"]): float(row["current_balance"])
        for row in repository.list_financial_accounts()
    }

    entries = (
        ("customer", customer_debit, "debit", 1000),
        ("customer", customer_credit, "credit", 200),
        ("supplier", supplier_credit, "credit", 500),
        ("supplier", supplier_debit, "debit", 150),
    )
    for partner_type, partner_id, nature, amount in entries:
        repository.record_partner_opening_balance(
            partner_type=partner_type,
            partner_id=partner_id,
            nature=nature,
            amount=amount,
            entry_date=date(2026, 1, 1),
            notes="رصيد معتمد",
            created_by_user_id=admin_id,
        )

    customer_balances = {
        int(row["id"]): row for row in repository.list_partner_balances("customer")
    }
    supplier_balances = {
        int(row["id"]): row for row in repository.list_partner_balances("supplier")
    }
    assert customer_balances[customer_debit]["opening_balance"] == pytest.approx(1000)
    assert customer_balances[customer_credit]["opening_balance"] == pytest.approx(-200)
    assert supplier_balances[supplier_credit]["opening_balance"] == pytest.approx(500)
    assert supplier_balances[supplier_debit]["opening_balance"] == pytest.approx(-150)

    summary = repository.dashboard_summary()
    assert summary["receivables"] == pytest.approx(800)
    assert summary["payables"] == pytest.approx(350)
    assert summary["customer_advances"] == pytest.approx(200)
    assert summary["supplier_advances"] == pytest.approx(150)
    assert any(
        row[4] == "رصيد افتتاحي"
        for row in repository.summary_card_details("customer_advances")["rows"]
    )
    assert any(
        row[4] == "رصيد افتتاحي"
        for row in repository.summary_card_details("supplier_advances")["rows"]
    )
    treasury_after = {
        int(row["id"]): float(row["current_balance"])
        for row in repository.list_financial_accounts()
    }
    assert treasury_after == treasury_before


def test_opening_balance_is_immutable_and_corrected_by_linked_reversal(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "opening-reversal.sqlite3")
    initialize_database(database)
    admin_id = _create_user(database, username="admin", role="admin")
    customer_id = _create_partner(
        database,
        partner_type="customer",
        code="C-REV",
        name="عميل العكس",
    )
    repository = DetailedReturnRefundRepository(database)

    entry_id = repository.record_partner_opening_balance(
        partner_type="customer",
        partner_id=customer_id,
        nature="debit",
        amount=1000,
        entry_date=date.today(),
        created_by_user_id=admin_id,
    )
    with pytest.raises(ValueError, match="يوجد رصيد افتتاحي"):
        repository.record_partner_opening_balance(
            partner_type="customer",
            partner_id=customer_id,
            nature="debit",
            amount=900,
            entry_date=date.today(),
            created_by_user_id=admin_id,
        )

    reversal_id = repository.reverse_partner_opening_balance(
        entry_id,
        reason="تصحيح مستند المراجعة",
        created_by_user_id=admin_id,
    )
    assert reversal_id != entry_id
    with pytest.raises(ValueError, match="بالفعل"):
        repository.reverse_partner_opening_balance(
            entry_id,
            reason="محاولة ثانية",
            created_by_user_id=admin_id,
        )

    repository.record_partner_opening_balance(
        partner_type="customer",
        partner_id=customer_id,
        nature="debit",
        amount=900,
        entry_date=date.today(),
        created_by_user_id=admin_id,
    )
    customer = repository.list_partner_balances("customer")[0]
    assert customer["opening_balance"] == pytest.approx(900)
    statuses = [
        row["status"] for row in repository.list_partner_opening_balance_entries()
    ]
    assert statuses.count("posted") == 1
    assert statuses.count("reversed") == 1
    assert statuses.count("reversal") == 1


def test_opening_balance_requires_admin_or_accounts_permission(tmp_path: Path) -> None:
    database = Database(tmp_path / "opening-permission.sqlite3")
    initialize_database(database)
    employee_id = _create_user(
        database,
        username="employee",
        role="employee",
    )
    accountant_id = _create_user(
        database,
        username="accountant",
        role="employee",
        accounts_permission=True,
    )
    customer_1 = _create_partner(
        database,
        partner_type="customer",
        code="C-P1",
        name="عميل بدون صلاحية",
    )
    customer_2 = _create_partner(
        database,
        partner_type="customer",
        code="C-P2",
        name="عميل المحاسب",
    )
    repository = DetailedReturnRefundRepository(database)

    with pytest.raises(PermissionError, match="مستخدم الحسابات"):
        repository.record_partner_opening_balance(
            partner_type="customer",
            partner_id=customer_1,
            nature="debit",
            amount=100,
            entry_date=date.today(),
            created_by_user_id=employee_id,
        )
    repository.record_partner_opening_balance(
        partner_type="customer",
        partner_id=customer_2,
        nature="debit",
        amount=100,
        entry_date=date.today(),
        created_by_user_id=accountant_id,
    )


def test_opening_balance_appears_in_customer_statement(tmp_path: Path) -> None:
    database = Database(tmp_path / "opening-statement.sqlite3")
    initialize_database(database)
    admin_id = _create_user(database, username="admin", role="admin")
    customer_id = _create_partner(
        database,
        partner_type="customer",
        code="C-ST",
        name="عميل كشف الرصيد",
    )
    repository = CustomerStatementAccountingRepository(database)
    repository.record_partner_opening_balance(
        partner_type="customer",
        partner_id=customer_id,
        nature="credit",
        amount=250,
        entry_date=date(2026, 1, 5),
        notes="دفعة مقدمة مرحلة",
        created_by_user_id=admin_id,
    )

    statement = repository.get_customer_statement(
        customer_id=customer_id,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    movement = statement["movements"][0]
    assert movement["document_type"] == "رصيد افتتاحي دائن"
    assert movement["debit"] == pytest.approx(0)
    assert movement["credit"] == pytest.approx(250)
    assert movement["running_balance"] == pytest.approx(-250)
    assert statement["summary"]["closing_balance"] == pytest.approx(-250)


def test_v10_partner_values_migrate_to_auditable_entries(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy-v10.sqlite3")
    with database.session(immediate=True) as connection:
        run_migrations(connection)
        ensure_sales_finance_v10_schema(connection)
        connection.execute(
            """
            INSERT INTO partners(partner_type, code, name, opening_balance)
            VALUES ('customer', 'C-OLD', 'عميل قديم', 125)
            """
        )
        connection.execute(
            """
            INSERT INTO partners(partner_type, code, name, opening_balance)
            VALUES ('supplier', 'S-OLD', 'مورد قديم', -40)
            """
        )
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 10

    initialize_database(database)

    assert int(database.fetch_one("PRAGMA user_version")[0]) == 11
    legacy_values = database.fetch_all(
        """
        SELECT p.code, p.opening_balance, entry.nature, entry.amount, entry.source
        FROM partners p
        JOIN partner_opening_balance_entries entry ON entry.partner_id = p.id
        ORDER BY p.code
        """
    )
    assert [float(row["opening_balance"]) for row in legacy_values] == [0.0, 0.0]
    assert [
        (row["code"], row["nature"], float(row["amount"]), row["source"])
        for row in legacy_values
    ] == [
        ("C-OLD", "debit", 125.0, "legacy"),
        ("S-OLD", "debit", 40.0, "legacy"),
    ]

    repository = DetailedReturnRefundRepository(database)
    assert repository.list_partner_balances("customer")[0]["opening_balance"] == pytest.approx(
        125
    )
    assert repository.list_partner_balances("supplier")[0]["opening_balance"] == pytest.approx(
        -40
    )

    initialize_database(database)
    assert (
        int(
            database.fetch_one(
                "SELECT COUNT(*) AS count FROM partner_opening_balance_entries"
            )["count"]
        )
        == 2
    )
