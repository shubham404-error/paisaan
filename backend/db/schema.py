"""Local additive schema bootstrap. Production deploys use versioned migrations."""
from sqlalchemy import inspect, text

from backend.db.database import Base, engine
import backend.db.models  # registers metadata


def ensure_local_schema() -> None:
    """Create new tables and add missing nullable columns in local SQLite only."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or column.primary_key:
                    continue
                sql_type = column.type.compile(dialect=engine.dialect)
                default = " DEFAULT 0" if column.name in {"new_52w_high", "new_52w_low", "golden_cross_20d", "death_cross_20d"} else ""
                nullable = "" if column.nullable else " NOT NULL"
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {sql_type}{nullable}{default}'))
