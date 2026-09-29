from pathlib import Path


def test_treasury_idempotency_migration_preserves_historical_rows() -> None:
    source = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260929_0018_treasury_idempotency.py"
    ).read_text()

    assert 'sa.Column("idempotency_key", sa.String(length=120), nullable=True)' in source
    assert 'sa.Column("request_hash", sa.String(length=64), nullable=True)' in source
    assert (
        'sa.Column("reversal_idempotency_key", sa.String(length=120), nullable=True)'
        in source
    )
    assert "UPDATE partner_opening_balance_entries" not in source
    assert "UPDATE customer_account_adjustments" not in source
    assert "DELETE FROM" not in source
