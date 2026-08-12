"""Stateful copilot with hard budgets and evidence-linked typed output.

The synthesizer is deliberately non-numeric: every number in a factual claim is
copied from captured public-tool evidence. Retrieved text is untrusted data and
is never interpreted as workflow instructions.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunStatus(StrEnum):
    DRAFT = "draft"
    REFUSED = "refused"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    source_url: str
    title: str
    locator: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)
    citations: list[Citation] = Field(min_length=1)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=2000)
    claims: list[Claim]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def citations_required(self) -> Recommendation:
        if any(not claim.citations for claim in self.claims):
            raise ValueError("all factual claims require citations")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    tool: str
    source_url: str
    title: str
    locator: str
    payload: dict[str, Any]
    captured_at: datetime
    trusted_numeric: bool = False


@dataclass(frozen=True, slots=True)
class AgentBudgets:
    max_tool_calls: int = 4
    max_input_tokens: int = 2_000
    max_output_tokens: int = 700
    timeout_seconds: float = 8.0


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: str
    session_id: str
    question: str
    classification: str
    status: RunStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    evidence: tuple[Evidence, ...] = ()
    recommendation: Recommendation | None = None
    refusal_reason: str | None = None
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    version: int = 1
    reviewed_by: str | None = None
    review_comment: str | None = None


class PublicTool(Protocol):
    name: str
    trusted_numeric: bool

    async def call(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class FunctionTool:
    def __init__(
        self,
        name: str,
        function: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        *,
        trusted_numeric: bool = False,
    ) -> None:
        self.name = name
        self.function = function
        self.trusted_numeric = trusted_numeric

    async def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.function(arguments)


class InMemoryAgentRepository:
    """Process-persistent adapter; replaceable by a durable repository."""

    def __init__(self) -> None:
        self._items: dict[str, AgentRun] = {}

    async def save(self, run: AgentRun) -> AgentRun:
        self._items[run.id] = run
        return run

    async def get(self, run_id: str) -> AgentRun | None:
        return self._items.get(run_id)

    async def list(self, session_id: str | None = None) -> tuple[AgentRun, ...]:
        values = self._items.values()
        return tuple(
            sorted(
                (item for item in values if session_id is None or item.session_id == session_id),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )


_INJECTION = re.compile(
    r"(?:ignore|override|reveal|disregard).{0,40}(?:instruction|prompt|policy|system)|"
    r"(?:system|assistant)\s*:",
    re.IGNORECASE,
)
_HEALTH = re.compile(r"\b(?:health|rul|remaining useful life|anomaly|engine)\b", re.I)
_DOCS = re.compile(r"\b(?:manual|procedure|inspection|approved data|guidance|document)\b", re.I)


class CopilotWorkflow:
    def __init__(
        self,
        repository: InMemoryAgentRepository,
        tools: dict[str, PublicTool],
        budgets: AgentBudgets | None = None,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.budgets = budgets or AgentBudgets()

    @staticmethod
    def _tokens(text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    def _classification(self, question: str) -> str:
        health, docs = bool(_HEALTH.search(question)), bool(_DOCS.search(question))
        return "health_and_guidance" if health and docs else "health" if health else "guidance"

    async def run(self, session_id: str, question: str, actor: str) -> AgentRun:
        started = time.monotonic()
        now = datetime.now(UTC)
        classification = self._classification(question)
        base = AgentRun(
            str(uuid4()), session_id, question, classification, RunStatus.REFUSED, actor, now, now
        )
        input_tokens = self._tokens(question)
        if input_tokens > self.budgets.max_input_tokens:
            return await self.repository.save(
                replace(
                    base, input_tokens=input_tokens, refusal_reason="input_token_budget_exceeded"
                )
            )
        if _INJECTION.search(question):
            return await self.repository.save(
                replace(base, input_tokens=input_tokens, refusal_reason="prompt_injection_detected")
            )

        plan: list[tuple[str, dict[str, Any]]] = []
        if classification in {"health", "health_and_guidance"}:
            plan.append(("predictions.get", {"session_id": session_id}))
        if classification in {"guidance", "health_and_guidance"}:
            plan.append(("documents.search", {"query": question, "limit": 3}))
        if len(plan) > self.budgets.max_tool_calls:
            return await self.repository.save(
                replace(base, input_tokens=input_tokens, refusal_reason="tool_call_budget_exceeded")
            )

        evidence: list[Evidence] = []
        try:
            async with asyncio.timeout(self.budgets.timeout_seconds):
                for name, arguments in plan:
                    tool = self.tools.get(name)
                    if tool is None:
                        return await self.repository.save(
                            replace(
                                base,
                                input_tokens=input_tokens,
                                tool_calls=len(evidence),
                                refusal_reason=f"required_tool_unavailable:{name}",
                            )
                        )
                    result = await tool.call(arguments)
                    evidence.extend(self._capture(name, result, tool.trusted_numeric))
        except TimeoutError:
            return await self.repository.save(
                replace(
                    base,
                    input_tokens=input_tokens,
                    tool_calls=len(evidence),
                    evidence=tuple(evidence),
                    refusal_reason="time_budget_exceeded",
                )
            )

        sufficient, reason = self._sufficient(classification, evidence)
        if not sufficient:
            return await self.repository.save(
                replace(
                    base,
                    input_tokens=input_tokens,
                    tool_calls=len(plan),
                    evidence=tuple(evidence),
                    refusal_reason=reason,
                )
            )
        recommendation = self._synthesize(classification, evidence)
        output_tokens = self._tokens(recommendation.model_dump_json())
        if (
            output_tokens > self.budgets.max_output_tokens
            or time.monotonic() - started > self.budgets.timeout_seconds
        ):
            return await self.repository.save(
                replace(
                    base,
                    input_tokens=input_tokens,
                    tool_calls=len(plan),
                    evidence=tuple(evidence),
                    output_tokens=output_tokens,
                    refusal_reason="output_or_time_budget_exceeded",
                )
            )
        return await self.repository.save(
            replace(
                base,
                status=RunStatus.DRAFT,
                input_tokens=input_tokens,
                tool_calls=len(plan),
                evidence=tuple(evidence),
                recommendation=recommendation,
                output_tokens=output_tokens,
                refusal_reason=None,
            )
        )

    def _capture(self, tool: str, result: dict[str, Any], trusted_numeric: bool) -> list[Evidence]:
        now = datetime.now(UTC)
        if tool == "documents.search":
            captured = []
            for item in result.get("results", []):
                if not isinstance(item, dict):
                    continue
                citation = item.get("citation", item)
                if not isinstance(citation, dict) or "source_url" not in citation:
                    continue
                captured.append(
                    Evidence(
                        id=str(uuid4()),
                        tool=tool,
                        source_url=str(citation["source_url"]),
                        title=str(citation.get("title", "Engineering source")),
                        locator=(
                            f"page {citation.get('page', 'n/a')} · "
                            f"{citation.get('section', 'section')}"
                        ),
                        payload={
                            "text": str(item.get("text", "")),
                            "version": citation.get("version"),
                        },
                        captured_at=now,
                    )
                )
            return captured
        return [
            Evidence(
                id=str(uuid4()),
                tool=tool,
                source_url=str(
                    result.get(
                        "source_url",
                        f"/v1/health/sessions/{result.get('session_id', 'unknown')}/model-track",
                    )
                ),
                title="Deterministic model health track",
                locator=str(result.get("artifact_id", "latest")),
                payload=result,
                captured_at=now,
                trusted_numeric=trusted_numeric,
            )
        ]

    def _sufficient(self, classification: str, evidence: list[Evidence]) -> tuple[bool, str]:
        if classification in {"health", "health_and_guidance"}:
            health = [
                item for item in evidence if item.tool == "predictions.get" and item.trusted_numeric
            ]
            if not health:
                return False, "deterministic_health_evidence_unavailable"
            payload = health[0].payload
            if (
                payload.get("status") in {"ood", "insufficient_history", "abstain"}
                or payload.get("rul") is None
            ):
                return False, "deterministic_model_abstained"
        if classification in {"guidance", "health_and_guidance"} and not any(
            item.tool == "documents.search" for item in evidence
        ):
            return False, "approved_guidance_evidence_unavailable"
        return True, ""

    def _synthesize(self, classification: str, evidence: list[Evidence]) -> Recommendation:
        claims: list[Claim] = []
        health = next((item for item in evidence if item.tool == "predictions.get"), None)
        if health:
            value, unit = health.payload["rul"], health.payload.get("rul_unit", "cycles")
            claims.append(
                Claim(
                    text=(
                        "The deterministic public health tool reports remaining useful "
                        f"life of {value} {unit}."
                    ),
                    citations=[self._citation(health)],
                )
            )
        document = next((item for item in evidence if item.tool == "documents.search"), None)
        if document:
            claims.append(
                Claim(
                    text=(
                        "Inspection disposition and return-to-service decisions require "
                        "appropriately authorized personnel and approved data."
                    ),
                    citations=[self._citation(document)],
                )
            )
        return Recommendation(
            summary=(
                "Draft only: review the cited evidence and schedule an authorized "
                "engineering inspection; this recommendation cannot approve maintenance "
                "or return to service."
            ),
            claims=claims,
            limitations=[
                "The copilot does not calculate numerical health.",
                "Approval requires an authorized engineer.",
            ],
        )

    @staticmethod
    def _citation(item: Evidence) -> Citation:
        return Citation(
            evidence_id=item.id, source_url=item.source_url, title=item.title, locator=item.locator
        )

    async def review(
        self,
        run_id: str,
        action: str,
        actor: str,
        comment: str | None = None,
        revised_summary: str | None = None,
        expected_version: int | None = None,
    ) -> AgentRun | None:
        current = await self.repository.get(run_id)
        if current is None:
            return None
        if current.status not in {RunStatus.DRAFT, RunStatus.REVISED}:
            raise ValueError("only draft or revised recommendations can be reviewed")
        if expected_version is not None and expected_version != current.version:
            raise RuntimeError("version_conflict")
        status = RunStatus(action)
        recommendation = current.recommendation
        if status == RunStatus.REVISED:
            if not revised_summary or recommendation is None:
                raise ValueError("revised_summary is required")
            recommendation = recommendation.model_copy(update={"summary": revised_summary})
        updated = replace(
            current,
            status=status,
            recommendation=recommendation,
            reviewed_by=actor,
            review_comment=comment,
            updated_at=datetime.now(UTC),
            version=current.version + 1,
        )
        return await self.repository.save(updated)
