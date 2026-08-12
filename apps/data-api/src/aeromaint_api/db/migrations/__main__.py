import asyncio
import sys

from aeromaint_api.config import get_settings
from aeromaint_api.db.database import Database
from aeromaint_api.db.migrations.runner import MigrationRunner


async def run() -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("AEROMAINT_DATABASE_URL is required")
    runner = MigrationRunner(Database(settings.database_url))
    command = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if command == "upgrade":
        await runner.upgrade()
    elif command == "downgrade":
        await runner.downgrade()
    else:
        raise SystemExit(f"unknown migration command: {command}")


asyncio.run(run())
