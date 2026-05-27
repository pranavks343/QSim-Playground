"""Typed request and response schemas for the REST API."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from core.ir import ProblemIR
from core.templates import TemplateMetadata

RunStatus = Literal["queued", "running", "done", "failed", "timeout", "cancelled"]
InputSource = Literal["template", "code", "ir"]
ExportFormat = Literal["notebook", "pdf", "script"]


class CreateRunRequest(BaseModel):
    """Request body for creating a run from a template, code snippet, or IR."""

    model_config = ConfigDict(extra="forbid")

    input_source: InputSource
    template_name: str | None = None
    source_code: str | None = None
    problem_ir: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> CreateRunRequest:
        """Require exactly the payload field matching input_source."""

        provided = {
            "template": self.template_name is not None,
            "code": self.source_code is not None,
            "ir": self.problem_ir is not None,
        }
        if not provided[self.input_source]:
            raise ValueError(f"{self.input_source} input requires matching payload field")
        if sum(provided.values()) != 1:
            raise ValueError("provide exactly one of template_name, source_code, or problem_ir")
        return self


class CreateRunResponse(BaseModel):
    """Response after queueing a run."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: Literal["queued"]


class RunResponse(BaseModel):
    """Serializable run state returned by the API."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    status: RunStatus
    template: str | None = None
    input_source: InputSource
    problem_ir: dict[str, Any]
    qubos: dict[str, Any] | None = None
    scorecards: dict[str, Any] | None = None
    winner_agent: str | None = None
    critic_verdict: dict[str, Any] | None = None
    refined_qubo: dict[str, Any] | None = None
    circuit_data: dict[str, Any] | None = None
    sim_result: dict[str, Any] | None = None
    classical_result: dict[str, Any] | None = None
    error: str | None = None
    total_runtime_ms: int | None = None
    cancel_requested: bool = False
    created_at: str
    completed_at: str | None = None
    deleted_at: str | None = None


class RunListResponse(BaseModel):
    """Paginated run list."""

    model_config = ConfigDict(extra="forbid")

    items: list[RunResponse]
    next_cursor: str | None = None


class RunEventResponse(BaseModel):
    """Run event entry."""

    model_config = ConfigDict(extra="forbid")

    id: int
    run_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: str


class RunEventsResponse(BaseModel):
    """Ordered run events for catch-up reads."""

    model_config = ConfigDict(extra="forbid")

    items: list[RunEventResponse]


class ExportRequest(BaseModel):
    """Export request shell."""

    model_config = ConfigDict(extra="forbid")

    format: ExportFormat


class ExportNotImplementedResponse(BaseModel):
    """Export placeholder response."""

    model_config = ConfigDict(extra="forbid")

    detail: str


class ProfileResponse(BaseModel):
    """Current profile and quota information."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    tier: str
    monthly_runs_used: int
    monthly_runs_limit: int
    quota_remaining: int
    quota_resets_at: str | None = None


class TemplatesResponse(BaseModel):
    """Public template catalog."""

    model_config = ConfigDict(extra="forbid")

    items: list[TemplateMetadata]


def ir_to_json_dict(ir: ProblemIR) -> dict[str, Any]:
    """Return a JSON-safe IR dictionary."""

    return ir.to_dict()
