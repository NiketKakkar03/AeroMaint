from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from aeromaint_api.main import create_app


def test_health_load_has_no_failures() -> None:
    client = TestClient(create_app())

    def request(_: int) -> int:
        return client.get("/health/live").status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(request, range(250)))

    assert statuses == [200] * 250
