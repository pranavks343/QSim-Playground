"""Public, unauthenticated read-only share endpoint.

The endpoint deliberately bypasses RLS via the service-role client and
applies a strict ``shared = true AND status = 'done' AND deleted_at IS NULL``
filter so a run is only readable here once its owner has opted in. The
response is sanitised to drop ``user_id``, ``error``, and any other
field that could leak across users.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from starlette import status

from api.schemas import SharedRunResponse
from infra.supabase import get_service_client

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/{run_id}", response_model=SharedRunResponse)
def get_shared_run(run_id: UUID) -> SharedRunResponse:
    """Return the sanitized read-only view of a shared, completed run."""

    client = get_service_client()
    response = (
        client.table("runs")
        .select("*")
        .eq("id", str(run_id))
        .eq("shared", True)
        .eq("status", "done")
        .is_("deleted_at", "null")
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return SharedRunResponse.model_validate(_sanitized(rows[0]))


def _sanitized(row: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "id",
        "status",
        "template",
        "input_source",
        "problem_ir",
        "qubos",
        "scorecards",
        "winner_agent",
        "critic_verdict",
        "refined_qubo",
        "circuit_data",
        "sim_result",
        "classical_result",
        "total_runtime_ms",
        "created_at",
        "completed_at",
    }
    return {key: row.get(key) for key in keep}
