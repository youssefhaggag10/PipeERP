from pathlib import Path

from app.database.connection import Database
from app.database.schema import initialize_database
from app.models.user import User
from app.repositories.admin_repository import (
    MASTER_DATA_TABLES,
    OPERATIONAL_DATA_TABLES,
)
from app.repositories.base_material_scrap_cost_repository import (
    BaseMaterialScrapCostRepository,
)
from app.repositories.crm_repository import CRMRepository
from app.repositories.detailed_return_refund_repository import (
    DetailedReturnRefundRepository,
)
from app.repositories.quotation_repository import QuotationRepository
from app.repositories.system_admin_repository import SystemAdminRepository
from app.security.passwords import hash_password

ADMIN_PASSWORD = "reset-test-password"


def _seed_database(tmp_path: Path) -> tuple[Database, User, dict[str, int]]:
    database = Database(tmp_path / "operational-reset.sqlite3")
    initialize_database(database)

    with database.session(immediate=True) as connection:
        admin_id = int(
            connection.execute(
                """
                INSERT INTO users(username, password_hash, full_name, role)
                VALUES ('admin', ?, 'مدير الاختبار', 'admin')
                """,
                (hash_password(ADMIN_PASSWORD),),
            ).lastrowid
        )
    admin = User(id=admin_id, username="admin", full_name="مدير الاختبار", role="admin")

    # Initialize every lazily-created table used by the application.
    CRMRepository(database, admin)
    BaseMaterialScrapCostRepository(database)
    DetailedReturnRefundRepository(database)
    QuotationRepository(database)
    SystemAdminRepository(database, admin)

    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN'"
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO settings(key, value) VALUES ('reset_test_setting', 'keep-me')"
        )
        connection.execute(
            """
            INSERT INTO user_permissions(user_id, permission_code, allowed)
            VALUES (?, 'sales', 1)
            """,
            (admin_id,),
        )
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(partner_type, code, name, opening_balance)
                VALUES ('customer', 'C-RESET', 'عميل ثابت', 125)
                """
            ).lastrowid
        )
        supplier_id = int(
            connection.execute(
                """
                INSERT INTO partners(partner_type, code, name, opening_balance)
                VALUES ('supplier', 'S-RESET', 'مورد ثابت', 250)
                """
            ).lastrowid
        )
        raw_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-RESET', 'خامة ثابتة', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        pipe_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit, standard_weight_kg)
                VALUES ('PIPE-RESET', 'ماسورة ثابتة', 'finished_good', 'قطعة', 2.5)
                """
            ).lastrowid
        )
        recipe_id = int(
            connection.execute(
                """
                INSERT INTO manufacturing_recipes(
                    code, name, estimated_scrap_unit_cost, is_active
                ) VALUES ('MIX-RESET', 'خلطة ثابتة', 37.5, 1)
                """
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO manufacturing_recipe_outputs(recipe_id, product_id)
            VALUES (?, ?)
            """,
            (recipe_id, pipe_id),
        )
        connection.execute(
            """
            INSERT INTO manufacturing_recipe_components(
                recipe_id, product_id, component_kind, quantity_per_batch, display_order
            ) VALUES (?, ?, 'material', 325, 1)
            """,
            (recipe_id, raw_id),
        )

        account_1 = int(
            connection.execute(
                "SELECT id FROM financial_accounts WHERE code = 'CASH-MAIN'"
            ).fetchone()[0]
        )
        account_2 = int(
            connection.execute(
                """
                INSERT INTO financial_accounts(
                    code, name, account_type, opening_balance, is_active
                ) VALUES ('BANK-RESET', 'حساب بنكي ثابت', 'bank', 500, 1)
                """
            ).lastrowid
        )

        lot_id = int(
            connection.execute(
                """
                INSERT INTO lots(product_id, lot_number, unit_cost)
                VALUES (?, 'LOT-RESET', 30)
                """,
                (raw_id,),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO inventory_moves(
                product_id, warehouse_id, lot_id, quantity_in, unit_cost,
                reference_type, partner_id
            ) VALUES (?, ?, ?, 1000, 30, 'purchase', ?)
            """,
            (raw_id, warehouse_id, lot_id, supplier_id),
        )

        purchase_order_id = int(
            connection.execute(
                """
                INSERT INTO purchase_orders(
                    order_number, supplier_id, warehouse_id, status
                ) VALUES ('PO-RESET', ?, ?, 'received')
                """,
                (supplier_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO purchase_order_lines(
                purchase_order_id, product_id, lot_number, quantity,
                unit, unit_price, line_total
            ) VALUES (?, ?, 'LOT-RESET', 1000, 'كجم', 30, 30000)
            """,
            (purchase_order_id, raw_id),
        )
        connection.execute(
            """
            INSERT INTO purchase_invoices(
                invoice_number, purchase_order_id, supplier_id, status, total
            ) VALUES ('PI-RESET', ?, ?, 'posted', 30000)
            """,
            (purchase_order_id, supplier_id),
        )

        sales_order_id = int(
            connection.execute(
                """
                INSERT INTO sales_orders(order_number, customer_id, warehouse_id, status)
                VALUES ('SO-RESET', ?, ?, 'delivered')
                """,
                (customer_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sales_order_lines(
                sales_order_id, product_id, quantity, unit, unit_price, line_total
            ) VALUES (?, ?, 10, 'قطعة', 100, 1000)
            """,
            (sales_order_id, pipe_id),
        )
        sales_invoice_id = int(
            connection.execute(
                """
                INSERT INTO sales_invoices(
                    invoice_number, sales_order_id, customer_id, status, total, net_total
                ) VALUES ('SI-RESET', ?, ?, 'posted', 1000, 1000)
                """,
                (sales_order_id, customer_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO payment_transactions(
                transaction_number, transaction_type, partner_id, amount,
                financial_account_id, sales_invoice_id
            ) VALUES ('CR-RESET', 'customer_receipt', ?, 500, ?, ?)
            """,
            (customer_id, account_1, sales_invoice_id),
        )
        connection.execute(
            """
            INSERT INTO financial_account_transfers(
                transfer_number, from_account_id, to_account_id, amount
            ) VALUES ('FT-RESET', ?, ?, 50)
            """,
            (account_1, account_2),
        )

        manufacturing_order_id = int(
            connection.execute(
                """
                INSERT INTO manufacturing_orders(
                    order_number, recipe_id, warehouse_id, status, planned_batches
                ) VALUES ('MO-RESET', ?, ?, 'in_progress', 9)
                """,
                (recipe_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO manufacturing_order_outputs(
                manufacturing_order_id, product_id, planned_quantity, standard_weight_kg
            ) VALUES (?, ?, 100, 2.5)
            """,
            (manufacturing_order_id, pipe_id),
        )

        lead_id = int(
            connection.execute(
                """
                INSERT INTO crm_leads(
                    lead_number, name, phone, source_code, stage_code, created_by
                ) VALUES ('LEAD-RESET', 'عميل محتمل', '01000000000',
                          'facebook', 'new', ?)
                """,
                (admin_id,),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO crm_activities(lead_id, activity_type, subject, created_by)
            VALUES (?, 'call', 'متابعة', ?)
            """,
            (lead_id, admin_id),
        )

        quotation_id = int(
            connection.execute(
                """
                INSERT INTO sales_quotations(quotation_number, customer_id, total)
                VALUES ('Q-RESET', ?, 1000)
                """,
                (customer_id,),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sales_quotation_lines(
                quotation_id, product_id, item_name, quantity, unit,
                unit_price, line_total
            ) VALUES (?, ?, 'ماسورة ثابتة', 10, 'قطعة', 100, 1000)
            """,
            (quotation_id, pipe_id),
        )

    return database, admin, {
        "customer": customer_id,
        "supplier": supplier_id,
        "raw": raw_id,
        "pipe": pipe_id,
        "recipe": recipe_id,
        "bank": account_2,
    }


def test_reset_clears_movements_and_preserves_master_data(tmp_path: Path) -> None:
    database, admin, ids = _seed_database(tmp_path)

    SystemAdminRepository(database, admin).reset_system(ADMIN_PASSWORD)

    with database.session() as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        assert MASTER_DATA_TABLES.isdisjoint(OPERATIONAL_DATA_TABLES)
        assert set(tables) - (MASTER_DATA_TABLES | OPERATIONAL_DATA_TABLES) == set()
        assert OPERATIONAL_DATA_TABLES <= set(tables)
        for table in OPERATIONAL_DATA_TABLES:
            count = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            assert count == 0, f"operational table was not cleared: {table}"

        customer = connection.execute(
            "SELECT name, opening_balance FROM partners WHERE id = ?", (ids["customer"],)
        ).fetchone()
        supplier = connection.execute(
            "SELECT name, opening_balance FROM partners WHERE id = ?", (ids["supplier"],)
        ).fetchone()
        assert tuple(customer) == ("عميل ثابت", 125.0)
        assert tuple(supplier) == ("مورد ثابت", 250.0)
        assert int(
            connection.execute(
                "SELECT COUNT(*) FROM products WHERE id IN (?, ?)",
                (ids["raw"], ids["pipe"]),
            ).fetchone()[0]
        ) == 2
        recipe = connection.execute(
            "SELECT name, estimated_scrap_unit_cost FROM manufacturing_recipes WHERE id = ?",
            (ids["recipe"],),
        ).fetchone()
        assert tuple(recipe) == ("خلطة ثابتة", 0.0)
        assert int(
            connection.execute(
                "SELECT COUNT(*) FROM manufacturing_recipe_outputs WHERE recipe_id = ?",
                (ids["recipe"],),
            ).fetchone()[0]
        ) == 1
        assert int(
            connection.execute(
                "SELECT COUNT(*) FROM manufacturing_recipe_components WHERE recipe_id = ?",
                (ids["recipe"],),
            ).fetchone()[0]
        ) == 1
        account = connection.execute(
            "SELECT name, opening_balance FROM financial_accounts WHERE id = ?",
            (ids["bank"],),
        ).fetchone()
        assert tuple(account) == ("حساب بنكي ثابت", 500.0)
        assert connection.execute(
            "SELECT value FROM settings WHERE key = 'reset_test_setting'"
        ).fetchone()[0] == "keep-me"
        assert int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]) == 1
        assert int(connection.execute("SELECT COUNT(*) FROM user_permissions").fetchone()[0]) == 1
        assert int(connection.execute("SELECT COUNT(*) FROM crm_sources").fetchone()[0]) > 0
        assert int(connection.execute("SELECT COUNT(*) FROM crm_stages").fetchone()[0]) > 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_reset_rejects_wrong_password_without_deleting_anything(tmp_path: Path) -> None:
    database, admin, _ = _seed_database(tmp_path)

    try:
        SystemAdminRepository(database, admin).reset_system("wrong-password")
    except ValueError as error:
        assert str(error) == "كلمة مرور الأدمن غير صحيحة"
    else:
        raise AssertionError("reset accepted the wrong administrator password")

    assert database.fetch_one("SELECT COUNT(*) AS count FROM sales_orders")["count"] == 1
    assert database.fetch_one("SELECT COUNT(*) AS count FROM partners")["count"] == 2
