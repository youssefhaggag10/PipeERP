"""Create normalized master-data and document-sequence tables."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0004"
down_revision: str | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "units_of_measure",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("normalized_code", sa.String(length=24), nullable=False),
        sa.Column("name_ar", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decimal_places BETWEEN 0 AND 6", name=op.f("ck_units_of_measure_decimal_places_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units_of_measure")),
        sa.UniqueConstraint("normalized_code", name=op.f("uq_units_of_measure_normalized_code")),
    )
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("normalized_code", sa.String(length=40), nullable=False),
        sa.Column("name_ar", sa.String(length=160), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["product_categories.id"],
            name=op.f("fk_product_categories_parent_id_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_categories")),
        sa.UniqueConstraint("normalized_code", name=op.f("uq_product_categories_normalized_code")),
    )
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("normalized_code", sa.String(length=40), nullable=False),
        sa.Column("name_ar", sa.String(length=160), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouses")),
        sa.UniqueConstraint("normalized_code", name=op.f("uq_warehouses_normalized_code")),
    )
    op.create_table(
        "partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("normalized_code", sa.String(length=80), nullable=False),
        sa.Column("name_ar", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("tax_number", sa.String(length=80), nullable=False),
        sa.Column("is_customer", sa.Boolean(), nullable=False),
        sa.Column("is_supplier", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "is_customer OR is_supplier", name=op.f("ck_partners_partner_type_required")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
        sa.UniqueConstraint("normalized_code", name=op.f("uq_partners_normalized_code")),
    )
    op.create_index(
        "ix_partners_customer_active", "partners", ["is_customer", "is_active"], unique=False
    )
    op.create_index(
        "ix_partners_supplier_active", "partners", ["is_supplier", "is_active"], unique=False
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("normalized_code", sa.String(length=80), nullable=False),
        sa.Column("name_ar", sa.String(length=200), nullable=False),
        sa.Column("product_type", sa.String(length=32), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid()),
        sa.Column("min_stock", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("track_lots", sa.Boolean(), nullable=False),
        sa.Column("standard_weight_kg", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("weight_tolerance_percent", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("min_stock >= 0", name=op.f("ck_products_min_stock_nonnegative")),
        sa.CheckConstraint(
            "product_type IN ('raw_material', 'finished_good', 'waste', 'service', 'spare_part')",
            name=op.f("ck_products_product_type_valid"),
        ),
        sa.CheckConstraint(
            "standard_weight_kg >= 0", name=op.f("ck_products_standard_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_tolerance_percent BETWEEN 0 AND 100",
            name=op.f("ck_products_weight_tolerance_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_products_category_id_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["units_of_measure.id"],
            name=op.f("fk_products_unit_id_units_of_measure"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("normalized_code", name=op.f("uq_products_normalized_code")),
    )
    op.create_index(
        "ix_products_type_active", "products", ["product_type", "is_active"], unique=False
    )
    op.create_table(
        "company_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_name_ar", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("tax_number", sa.String(length=80), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("currency_decimal_places", sa.Integer(), nullable=False),
        sa.Column("tax_enabled", sa.Boolean(), nullable=False),
        sa.Column("default_tax_rate", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("default_warehouse_id", sa.Uuid()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "currency_decimal_places BETWEEN 0 AND 4",
            name=op.f("ck_company_settings_currency_scale_valid"),
        ),
        sa.CheckConstraint(
            "default_tax_rate BETWEEN 0 AND 100", name=op.f("ck_company_settings_tax_rate_valid")
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_company_settings_singleton")),
        sa.ForeignKeyConstraint(
            ["default_warehouse_id"],
            ["warehouses.id"],
            name=op.f("fk_company_settings_default_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_settings")),
    )
    op.create_table(
        "document_sequences",
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("padding", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "next_value > 0", name=op.f("ck_document_sequences_next_value_positive")
        ),
        sa.CheckConstraint(
            "padding BETWEEN 1 AND 12", name=op.f("ck_document_sequences_padding_valid")
        ),
        sa.PrimaryKeyConstraint("document_type", name=op.f("pk_document_sequences")),
    )

    unit_table = sa.table(
        "units_of_measure",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("normalized_code", sa.String()),
        sa.column("name_ar", sa.String()),
        sa.column("symbol", sa.String()),
        sa.column("decimal_places", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    warehouse_table = sa.table(
        "warehouses",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("normalized_code", sa.String()),
        sa.column("name_ar", sa.String()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    settings_table = sa.table(
        "company_settings",
        sa.column("id", sa.Integer()),
        sa.column("company_name_ar", sa.String()),
        sa.column("phone", sa.String()),
        sa.column("address", sa.Text()),
        sa.column("tax_number", sa.String()),
        sa.column("currency_code", sa.String()),
        sa.column("currency_decimal_places", sa.Integer()),
        sa.column("tax_enabled", sa.Boolean()),
        sa.column("default_tax_rate", sa.Numeric()),
        sa.column("default_warehouse_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    sequence_table = sa.table(
        "document_sequences",
        sa.column("document_type", sa.String()),
        sa.column("prefix", sa.String()),
        sa.column("next_value", sa.Integer()),
        sa.column("padding", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    main_warehouse_id = uuid4()
    now = datetime.now(UTC)
    op.bulk_insert(
        unit_table,
        [
            {
                "id": uuid4(),
                "code": "KG",
                "normalized_code": "KG",
                "name_ar": "كيلوجرام",
                "symbol": "كجم",
                "decimal_places": 3,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid4(),
                "code": "PCS",
                "normalized_code": "PCS",
                "name_ar": "قطعة",
                "symbol": "قطعة",
                "decimal_places": 0,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    op.bulk_insert(
        warehouse_table,
        [
            {
                "id": main_warehouse_id,
                "code": "MAIN",
                "normalized_code": "MAIN",
                "name_ar": "المصنع",
                "is_default": True,
                "is_active": True,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "id": 1,
                "company_name_ar": "PipeERP",
                "phone": "",
                "address": "",
                "tax_number": "",
                "currency_code": "EGP",
                "currency_decimal_places": 2,
                "tax_enabled": False,
                "default_tax_rate": 0,
                "default_warehouse_id": main_warehouse_id,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        sequence_table,
        [
            {
                "document_type": document_type,
                "prefix": prefix,
                "next_value": 1,
                "padding": 6,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for document_type, prefix in (
                ("purchase_order", "PO-"),
                ("sales_order", "SO-"),
                ("manufacturing_order", "MO-"),
                ("sales_invoice", "SI-"),
                ("purchase_invoice", "PI-"),
                ("opening_balance", "OB-"),
                ("quotation", "QT-"),
                ("weight_card", "WC-"),
                ("return", "RT-"),
            )
        ],
    )


def downgrade() -> None:
    op.drop_table("document_sequences")
    op.drop_table("company_settings")
    op.drop_index("ix_products_type_active", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_partners_supplier_active", table_name="partners")
    op.drop_index("ix_partners_customer_active", table_name="partners")
    op.drop_table("partners")
    op.drop_table("warehouses")
    op.drop_table("product_categories")
    op.drop_table("units_of_measure")
