"""Evidence-first copilot and human review queue API."""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from services.agent.workflow import CopilotWorkflow, FunctionTool, InMemoryAgentRepository

from aeromaint_api.api.v1.documents import _INDEX
from aeromaint_api.errors import ApiProblem
from aeromaint_api.security.dependencies import require
from aeromaint_api.security.models import Permission, Principal
from aeromaint_api.services.health import demo_track, engine_summary

router = APIRouter(prefix="/copilot", tags=["copilot"])


class AskBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=2, max_length=8_000)


class ReviewBody(BaseModel):
    action: Literal["approved", "rejected", "revised"]
    expected_version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=2_000)
    revised_summary: str | None = Field(default=None, max_length=2_000)


async def _prediction(arguments: dict[str, Any]) -> dict[str, Any]:
    session_id = str(arguments["session_id"])
    track = demo_track("ENG-101", session_id)
    return {
        **engine_summary(track),
        "session_id": session_id,
        "artifact_id": track["artifact_id"],
        "source_url": f"/v1/health/sessions/{session_id}/model-track",
    }


async def _documents(arguments: dict[str, Any]) -> dict[str, Any]:
    result = _INDEX.search(str(arguments["query"]), limit=int(arguments.get("limit", 3)))
    return {"status": result.status, "results": list(result.results), "reason": result.reason}


def workflow(request: Request) -> CopilotWorkflow:
    return cast(CopilotWorkflow, request.app.state.copilot_workflow)


def response(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "question": run.question,
        "classification": run.classification,
        "status": run.status.value,
        "created_by": run.created_by,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "evidence": [item.model_dump(mode="json") for item in run.evidence],
        "recommendation": run.recommendation.model_dump(mode="json")
        if run.recommendation
        else None,
        "refusal_reason": run.refusal_reason,
        "budgets": {
            "tool_calls": run.tool_calls,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
        },
        "version": run.version,
        "reviewed_by": run.reviewed_by,
        "review_comment": run.review_comment,
    }


@router.post("/runs", status_code=201)
async def create_run(
    request: Request,
    body: AskBody,
    principal: Annotated[Principal, Depends(require(Permission.ANALYSIS_RUN))],
) -> dict[str, Any]:
    return response(await workflow(request).run(body.session_id, body.question, principal.subject))


@router.get("/runs", dependencies=[Depends(require(Permission.SESSION_READ))])
async def list_runs(request: Request, session_id: str | None = None) -> dict[str, Any]:
    return {
        "items": [response(item) for item in await workflow(request).repository.list(session_id)]
    }


@router.get("/runs/{run_id}", dependencies=[Depends(require(Permission.SESSION_READ))])
async def get_run(request: Request, run_id: str) -> dict[str, Any]:
    item = await workflow(request).repository.get(run_id)
    if item is None:
        raise ApiProblem(
            404, "COPILOT_RUN_NOT_FOUND", "Copilot run not found", "The run does not exist."
        )
    return response(item)


@router.post("/runs/{run_id}/review")
async def review_run(
    request: Request,
    run_id: str,
    body: ReviewBody,
    principal: Annotated[Principal, Depends(require(Permission.RECOMMENDATION_APPROVE))],
) -> dict[str, Any]:
    try:
        item = await workflow(request).review(
            run_id,
            body.action,
            principal.subject,
            body.comment,
            body.revised_summary,
            body.expected_version,
        )
    except RuntimeError as exc:
        raise ApiProblem(
            409, "COPILOT_VERSION_CONFLICT", "Recommendation changed", "Reload before reviewing."
        ) from exc
    except ValueError as exc:
        raise ApiProblem(422, "INVALID_REVIEW", "Invalid review", str(exc)) from exc
    if item is None:
        raise ApiProblem(
            404, "COPILOT_RUN_NOT_FOUND", "Copilot run not found", "The run does not exist."
        )
    return response(item)


def create_workflow() -> CopilotWorkflow:
    return CopilotWorkflow(
        InMemoryAgentRepository(),
        {
            "predictions.get": FunctionTool("predictions.get", _prediction, trusted_numeric=True),
            "documents.search": FunctionTool("documents.search", _documents),
        },
    )
