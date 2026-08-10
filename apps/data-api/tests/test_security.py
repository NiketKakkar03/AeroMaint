import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from aeromaint_api.main import create_app
from aeromaint_api.security.dependencies import require
from aeromaint_api.security.models import Permission

SECRET = b"development-only-change-me"


def token(*roles: str, **overrides: Any) -> str:
    header = overrides.pop("header", {"alg": "HS256", "typ": "JWT"})
    payload = {
        "sub": "test-user",
        "roles": list(roles),
        "iss": "aeromaint-local",
        "aud": "aeromaint-api",
        "exp": int(time.time()) + 60,
        **overrides,
    }

    def encode(value: object) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    signing_input = f"{encode(header)}.{encode(payload)}"
    signature = (
        base64.urlsafe_b64encode(hmac.new(SECRET, signing_input.encode(), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    return f"{signing_input}.{signature}"


def bearer(*roles: str, **overrides: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(*roles, **overrides)}"}


@pytest.mark.parametrize(
    ("role", "status"),
    [("viewer", 403), ("analyst", 403), ("engineer", 200), ("admin", 200)],
)
def test_explicit_approval_permission_and_audit(role: str, status: int) -> None:
    app = create_app()

    @app.get("/approval", dependencies=[Depends(require(Permission.RECOMMENDATION_APPROVE))])
    async def approval() -> dict[str, bool]:
        return {"allowed": True}

    with TestClient(app) as client:
        response = client.get("/approval", headers=bearer(role))

    assert response.status_code == status
    if status == 403:
        assert response.json()["code"] == "permission_denied"
        assert response.headers["content-type"] == "application/problem+json"
    events = asyncio.run(app.state.audit_sink.snapshot())
    assert events[-1].action == "recommendation:approve"
    assert events[-1].outcome == ("allowed" if status == 200 else "denied")


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic abc",
        "Bearer nonsense",
        "Bearer e30.e30.invalid",
        "Bearer " + token("viewer", exp=0),
        "Bearer " + token("owner"),
        "Bearer " + token("viewer", header={"alg": "none"}),
    ],
)
def test_malformed_or_untrusted_tokens_have_stable_failures(
    authorization: str | None,
) -> None:
    app = create_app()
    headers = {} if authorization is None else {"Authorization": authorization}

    response = TestClient(app).get("/v1/sessions/fixture-session/manifest", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] in {"authentication_required", "invalid_token"}
    assert response.json()["status"] == 401
    assert response.headers["content-type"] == "application/problem+json"


def test_idempotency_replays_response_and_rejects_changed_request() -> None:
    app = create_app()
    calls = 0

    @app.post("/mutate")
    async def mutate(payload: dict[str, int]) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"call": calls, "value": payload["value"]}

    headers = {**bearer("engineer"), "Idempotency-Key": "stable-key"}
    with TestClient(app) as client:
        first = client.post("/mutate", headers=headers, json={"value": 1})
        replay = client.post("/mutate", headers=headers, json={"value": 1})
        conflict = client.post("/mutate", headers=headers, json={"value": 2})

    assert first.json() == replay.json() == {"call": 1, "value": 1}
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_reused"
    assert calls == 1


def test_mutation_requires_idempotency_key() -> None:
    app = create_app()

    @app.post("/mutate")
    async def mutate() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).post("/mutate", headers=bearer("engineer"))

    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_required"


def test_mutation_requires_authentication() -> None:
    app = create_app()

    @app.post("/mutate")
    async def mutate() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).post("/mutate", headers={"Idempotency-Key": "unauthenticated"})

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_security_headers_are_applied_to_public_endpoints() -> None:
    response = TestClient(create_app()).get("/health/live")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
