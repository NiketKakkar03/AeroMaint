from dataclasses import dataclass
from importlib.resources import files

from aeromaint_api.db.database import Database


@dataclass(frozen=True)
class Migration:
    version: int
    up: str
    down: str


class MigrationRunner:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _migration() -> Migration:
        root = files("aeromaint_api.db.migrations")
        return Migration(
            version=1,
            up=root.joinpath("0001_initial.up.sql").read_text(),
            down=root.joinpath("0001_initial.down.sql").read_text(),
        )

    async def upgrade(self) -> None:
        migration = self._migration()
        async with self.database.connection() as connection, connection.transaction():
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cursor = await connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (migration.version,)
            )
            if await cursor.fetchone() is None:
                await connection.execute(migration.up)
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s)", (migration.version,)
                )

    async def downgrade(self) -> None:
        migration = self._migration()
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute("SELECT to_regclass('schema_migrations') AS name")
            row = await cursor.fetchone()
            if row is None or row["name"] is None:
                return
            cursor = await connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (migration.version,)
            )
            if await cursor.fetchone() is not None:
                await connection.execute(migration.down)
