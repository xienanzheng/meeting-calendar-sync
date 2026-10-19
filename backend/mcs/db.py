from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from mcs import models  # noqa: F401  (registers tables on SQLModel.metadata)
from mcs.config import Settings


def make_engine(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    _upgrade(engine)
    return engine


def _upgrade(engine: Engine) -> None:
    """Bring older local databases up to date (create_all never alters existing tables)."""
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(meeting)")}
        if "source_json" not in columns:
            conn.exec_driver_sql("ALTER TABLE meeting ADD COLUMN source_json VARCHAR NOT NULL DEFAULT ''")
        if "timezone" not in columns:
            conn.exec_driver_sql("ALTER TABLE meeting ADD COLUMN timezone VARCHAR")
