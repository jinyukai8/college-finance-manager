from __future__ import annotations

import pytest

from college_finance_manager.infrastructure.database import apply_migrations, connect_database


@pytest.fixture
def database(tmp_path):
    connection = connect_database(tmp_path / "test.db")
    apply_migrations(connection)
    try:
        yield connection
    finally:
        connection.close()
