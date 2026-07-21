COMPLETION_SUMMARY_SQL = """
CREATE TABLE IF NOT EXISTS manufacturing_completion_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturing_order_id INTEGER NOT NULL UNIQUE
        REFERENCES manufacturing_orders(id) ON DELETE CASCADE,
    planned_batches INTEGER NOT NULL DEFAULT 0,
    actual_batches INTEGER NOT NULL DEFAULT 0,
    full_batches INTEGER NOT NULL DEFAULT 0,
    modified_batches INTEGER NOT NULL DEFAULT 0,
    good_output_quantity REAL NOT NULL DEFAULT 0,
    defective_output_quantity REAL NOT NULL DEFAULT 0,
    actual_output_weight REAL NOT NULL DEFAULT 0,
    scrap_weight REAL NOT NULL DEFAULT 0,
    full_mix_cost REAL NOT NULL DEFAULT 0,
    modified_mix_cost REAL NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS manufacturing_completion_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturing_order_id INTEGER NOT NULL
        REFERENCES manufacturing_orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    good_quantity REAL NOT NULL DEFAULT 0,
    defective_quantity REAL NOT NULL DEFAULT 0,
    actual_weight_kg REAL NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0,
    UNIQUE(manufacturing_order_id, product_id)
);

CREATE TABLE IF NOT EXISTS manufacturing_mix_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturing_order_id INTEGER NOT NULL
        REFERENCES manufacturing_orders(id) ON DELETE CASCADE,
    excluded_product_id INTEGER NOT NULL REFERENCES products(id),
    excluded_batches INTEGER NOT NULL CHECK(excluded_batches > 0),
    reason TEXT NOT NULL,
    actual_materials_json TEXT NOT NULL DEFAULT '{}',
    cost_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_completion_summary_order
ON manufacturing_completion_summaries(manufacturing_order_id);

CREATE INDEX IF NOT EXISTS idx_completion_outputs_order
ON manufacturing_completion_outputs(manufacturing_order_id, product_id);

CREATE INDEX IF NOT EXISTS idx_mix_adjustments_order
ON manufacturing_mix_adjustments(manufacturing_order_id, id);
"""


def ensure_completion_summary_schema(connection) -> None:
    connection.executescript(COMPLETION_SUMMARY_SQL)


__all__ = ["ensure_completion_summary_schema"]
