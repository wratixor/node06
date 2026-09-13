from sqlalchemy import Engine, create_engine, text


class Database:
    """Small synchronous boundary; request handlers do not own database engines."""

    def __init__(self, database_url: str | None) -> None:
        self._engine: Engine | None = (
            create_engine(database_url, pool_pre_ping=True) if database_url else None
        )

    def ready(self) -> tuple[bool, str | None]:
        if self._engine is None:
            return False, "DATABASE_NOT_CONFIGURED"
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False, "DATABASE_UNAVAILABLE"
        return True, None

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
