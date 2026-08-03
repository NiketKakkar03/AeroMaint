from fastapi.testclient import TestClient

from aeromaint_api.main import app


def test_readiness_endpoint() -> None:
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "data-api",
        "environment": "development",
    }
