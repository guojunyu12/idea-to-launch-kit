from sqlalchemy import create_engine, text

from app.db import create_session_factory


def test_sqlite_uses_waiting_and_wal_for_concurrent_requests(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    factory = create_session_factory(database_url)
    with factory().connection() as connection:
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() >= 30000
        assert connection.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"


def test_existing_sqlite_tasks_table_gets_new_tracking_columns(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    legacy_engine = create_engine(database_url)
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, owner_id VARCHAR(120), template_id VARCHAR(120), upload_id VARCHAR(36), status VARCHAR(30), provider VARCHAR(40), error_code VARCHAR(80), created_at DATETIME, updated_at DATETIME)")

    create_session_factory(database_url)
    with legacy_engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
    assert {"elapsed_ms", "cost_cents", "attempts", "aspect_ratio", "output_width", "output_height"}.issubset(columns)
