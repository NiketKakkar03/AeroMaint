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


def test_metrics_and_trace_correlation() -> None:
    client = TestClient(app)
    response = client.get("/health/live", headers={"X-Trace-ID": "release-drill-28"})

    assert response.headers["X-Trace-ID"] == "release-drill-28"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "aeromaint_http_requests_total" in metrics.text
    assert 'aeromaint_build_info{service="data-api",version="0.1.0"} 1' in metrics.text
