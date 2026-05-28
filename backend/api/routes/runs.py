"""Run management endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette import status

from api.deps import AuthenticatedUser, get_current_user
from api.execution import execute_pipeline_background
from api.limits import check_quota, check_rate_limit, tier_limits
from api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    ExportNotImplementedResponse,
    ExportRequest,
    RunEventsResponse,
    RunListResponse,
    RunResponse,
    ir_to_json_dict,
)
from core.ir import ProblemIR
from core.parser import ParseFailure, ParseSuccess, parse
from core.templates import get_template
from infra.gemini import is_gemini_circuit_open
from infra.supabase import get_user_client

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: CreateRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> CreateRunResponse:
    """Create a queued run from template, code, or IR."""

    _raise_if_gemini_circuit_open()
    await check_quota(current_user)
    await check_rate_limit(current_user)
    problem_ir = _resolve_ir(payload)
    client = _client_for_request(request)
    response = (
        client.table("runs")
        .insert(
            {
                "user_id": str(current_user.id),
                "template": payload.template_name,
                "input_source": payload.input_source,
                "problem_ir": ir_to_json_dict(problem_ir),
            }
        )
        .execute()
    )
    row = _single_row(response.data)
    background_tasks.add_task(
        execute_pipeline_background,
        UUID(str(row["id"])),
        current_user.id,
        problem_ir,
        tier_limits(current_user.tier)["max_qubits"],
    )
    return CreateRunResponse(run_id=UUID(str(row["id"])), status="queued")


@router.get("", response_model=RunListResponse)
def list_runs(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> RunListResponse:
    """List current user's runs ordered by newest first."""

    del current_user
    query = (
        _client_for_request(request)
        .table("runs")
        .select("*")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status_filter is not None:
        query = query.eq("status", status_filter)
    if cursor is not None:
        query = query.lt("created_at", cursor)
    response = query.execute()
    items = [_run_response(row) for row in response.data]
    next_cursor = items[-1].created_at if len(items) == limit else None
    return RunListResponse(items=items, next_cursor=next_cursor)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> RunResponse:
    """Return full run state for an owned run."""

    del current_user
    row = _fetch_owned_run(request, run_id)
    return _run_response(row)


@router.get("/{run_id}/events", response_model=RunEventsResponse)
def get_run_events(
    run_id: UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    after_event_id: Annotated[int | None, Query(ge=0)] = None,
) -> RunEventsResponse:
    """Return ordered events for a run."""

    del current_user
    _fetch_owned_run(request, run_id)
    query = (
        _client_for_request(request)
        .table("run_events")
        .select("*")
        .eq("run_id", str(run_id))
        .order("created_at")
    )
    if after_event_id is not None:
        query = query.gt("id", after_event_id)
    response = query.execute()
    return RunEventsResponse(items=response.data)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(
    run_id: UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Response:
    """Soft-delete an owned run."""

    del current_user
    _fetch_owned_run(request, run_id)
    response = (
        _client_for_request(request)
        .table("runs")
        .update({"deleted_at": datetime.now(tz=UTC).isoformat()})
        .eq("id", str(run_id))
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_run(
    run_id: UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Request cancellation for an in-flight run.

    Sets ``cancel_requested=true`` on the run row. The background executor
    polls this flag between major pipeline nodes and finalises the run with
    ``status='cancelled'`` when it sees the flag.
    """

    del current_user
    row = _fetch_owned_run(request, run_id)
    if row.get("status") in {"done", "failed", "timeout", "cancelled"}:
        return {"run_id": str(run_id), "status": row.get("status"), "cancel_requested": False}
    response = (
        _client_for_request(request)
        .table("runs")
        .update({"cancel_requested": True})
        .eq("id", str(run_id))
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"run_id": str(run_id), "status": row.get("status"), "cancel_requested": True}


@router.post(
    "/{run_id}/export",
    response_model=ExportNotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def export_run(
    run_id: UUID,
    payload: ExportRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ExportNotImplementedResponse:
    """Placeholder export endpoint."""

    del payload, current_user
    _fetch_owned_run(request, run_id)
    return ExportNotImplementedResponse(detail="Export available in Day 4.")


def _client_for_request(request: Request) -> Any:
    bearer_jwt = getattr(request.state, "bearer_jwt", None)
    if not isinstance(bearer_jwt, str) or not bearer_jwt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return get_user_client(bearer_jwt)


def _resolve_ir(payload: CreateRunRequest) -> ProblemIR:
    if payload.input_source == "template":
        try:
            return get_template(str(payload.template_name))
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown template: {payload.template_name}",
            ) from exc
    if payload.input_source == "code":
        result = parse(str(payload.source_code))
        if isinstance(result, ParseFailure):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[error.message for error in result.errors],
            )
        if isinstance(result, ParseSuccess):
            return result.ir
    if payload.problem_ir is not None:
        try:
            return ProblemIR.from_dict(payload.problem_ir)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid run input"
    )


def _fetch_owned_run(request: Request, run_id: UUID) -> dict[str, Any]:
    try:
        response = (
            _client_for_request(request)
            .table("runs")
            .select("*")
            .eq("id", str(run_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    row = _single_row(response.data, not_found_detail="Run not found")
    return row


def _single_row(data: list[dict[str, Any]], not_found_detail: str = "Not found") -> dict[str, Any]:
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    return data[0]


def _run_response(row: dict[str, Any]) -> RunResponse:
    return RunResponse.model_validate(row)


def _raise_if_gemini_circuit_open() -> None:
    open_, remaining = is_gemini_circuit_open()
    if open_:
        retry_after = max(1, int(remaining))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_busy",
                "message": "System busy, please retry in 30s",
            },
            headers={"Retry-After": str(retry_after)},
        )
