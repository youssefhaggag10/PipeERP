import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.master_data.models import DocumentSequence
from app.modules.master_data.service import allocate_document_number


def test_document_sequence_allocates_monotonic_unique_numbers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            DocumentSequence(
                document_type="sales_order",
                prefix="SO-",
                next_value=1,
                padding=6,
                version=1,
            )
        )
        db.commit()

        assert allocate_document_number(db, "sales_order") == "SO-000001"
        assert allocate_document_number(db, "sales_order") == "SO-000002"
        db.commit()

        sequence = db.get(DocumentSequence, "sales_order")
        assert sequence is not None
        assert sequence.next_value == 3
        assert sequence.version == 3


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL row-lock test",
)
def test_five_concurrent_postgres_allocations_never_collide() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, pool_size=5)
    document_type = f"concurrency_{uuid4().hex}"
    with Session(engine) as db, db.begin():
        db.add(
            DocumentSequence(
                document_type=document_type,
                prefix="CC-",
                next_value=1,
                padding=6,
                version=1,
            )
        )

    barrier = Barrier(5)

    def allocate() -> str:
        with Session(engine) as db, db.begin():
            barrier.wait()
            return allocate_document_number(db, document_type)

    with ThreadPoolExecutor(max_workers=5) as executor:
        numbers = list(executor.map(lambda _: allocate(), range(5)))

    assert len(set(numbers)) == 5
    assert sorted(numbers) == [f"CC-{value:06d}" for value in range(1, 6)]

    with Session(engine) as db, db.begin():
        sequence = db.get(DocumentSequence, document_type)
        assert sequence is not None
        assert sequence.next_value == 6
        db.delete(sequence)
