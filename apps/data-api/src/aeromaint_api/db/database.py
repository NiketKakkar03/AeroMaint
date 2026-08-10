from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import dict_row


class Database:
    """Creates short-lived async connections; safe for API and worker process lifecycles."""

    def __init__(self, url: str) -> None:
        self.url = url.replace("postgresql+psycopg://", "postgresql://", 1)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        connection = await AsyncConnection.connect(self.url, row_factory=dict_row)
        try:
            yield connection
        finally:
            await connection.close()

    async def check(self) -> None:
        async with self.connection() as connection:
            await connection.execute("SELECT 1")
