"""Background pipeline executor for run rows.

POST /api/runs schedules ``execute_pipeline_background`` via
``BackgroundTasks.add_task``. Cloud Run keeps the container alive while a
request handler — including its background tasks — is still running. The
handler returns immediately with the run id; the executor below runs the
LangGraph pipeline inline within the worker process, persists progress as
``run_events`` rows, and finalises the run row when finished.

A module-level :data:`PIPELINE_SEMAPHORE` caps concurrent pipelines per
Cloud Run instance. Above the cap, runs stay in ``queued`` status until a
slot frees up (an event is emitted while waiting). See ADR-002 in
``docs/DECISIONS.md`` for the design trade-offs and scaling envelope.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sentry_sdk
import structlog

from core.ir import ProblemIR
from core.orchestrator import PipelineEvent, PipelineState, run_pipeline
from infra.supabase import get_service_client

logger = structlog.get_logger(__name__)

PIPELINE_TIMEOUT_SECONDS = 180.0
MAX_CONCURRENT_PIPELINES = 10
PIPELINE_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)


async def execute_pipeline_background(
    run_id: UUID,
    user_id: UUID,
    ir: ProblemIR,
    max_qubits: int | None = None,
) -> None:
    """Run the QUBO pipeline for ``run_id`` and persist results.

    Always emits a final ``pipeline_done``, ``pipeline_failed``, or
    ``pipeline_cancelled`` event row, even on hard failure paths. The
    ``max_qubits`` cap is enforced inside the evaluator and circuit
    builder; tripping it surfaces as a ``QubitCapExceeded`` event.
    """

    client = get_service_client()
    started = time.perf_counter()

    if PIPELINE_SEMAPHORE.locked():
        _emit_event_sync(
            client,
            run_id,
            "pipeline_failed",
            {"reason": "waiting for free pipeline slot", "stage": "queued"},
        )

    async with PIPELINE_SEMAPHORE:
        try:
            _update_run(client, run_id, {"status": "running"})
        except Exception as exc:
            logger.error(
                "execution_initial_update_failed",
                run_id=str(run_id),
                error=str(exc),
            )

        async def event_callback(event: PipelineEvent) -> None:
            _emit_event_sync(
                client,
                run_id,
                event.event_type,
                event.payload,
            )

        async def cancel_check() -> bool:
            return _is_cancel_requested(client, run_id)

        try:
            state: PipelineState = await asyncio.wait_for(
                run_pipeline(
                    ir,
                    run_id=str(run_id),
                    event_callback=event_callback,
                    cancel_check=cancel_check,
                    max_qubits=max_qubits,
                ),
                timeout=PIPELINE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            runtime_ms = int((time.perf_counter() - started) * 1000.0)
            logger.warning(
                "execution_pipeline_timeout",
                run_id=str(run_id),
                user_id=str(user_id),
                runtime_ms=runtime_ms,
            )
            _update_run(
                client,
                run_id,
                {
                    "status": "timeout",
                    "error": f"pipeline exceeded {PIPELINE_TIMEOUT_SECONDS}s cap",
                    "total_runtime_ms": runtime_ms,
                    "completed_at": _now_iso(),
                },
            )
            _emit_event_sync(
                client,
                run_id,
                "pipeline_failed",
                {"reason": "pipeline timed out", "timeout_seconds": PIPELINE_TIMEOUT_SECONDS},
            )
            return
        except Exception as exc:
            runtime_ms = int((time.perf_counter() - started) * 1000.0)
            logger.error(
                "execution_pipeline_unhandled_exception",
                run_id=str(run_id),
                user_id=str(user_id),
                error_type=type(exc).__name__,
                error=str(exc),
                traceback="".join(traceback.format_exception(exc)),
            )
            sentry_sdk.capture_exception(exc)
            _update_run(
                client,
                run_id,
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "total_runtime_ms": runtime_ms,
                    "completed_at": _now_iso(),
                },
            )
            _emit_event_sync(
                client,
                run_id,
                "pipeline_failed",
                {"reason": "unhandled exception", "error_type": type(exc).__name__},
            )
            return

        runtime_ms = int((time.perf_counter() - started) * 1000.0)

        if state.get("cancelled"):
            _update_run(
                client,
                run_id,
                {
                    "status": "cancelled",
                    "total_runtime_ms": runtime_ms,
                    "completed_at": _now_iso(),
                },
            )
            logger.info(
                "execution_pipeline_cancelled",
                run_id=str(run_id),
                user_id=str(user_id),
                runtime_ms=runtime_ms,
            )
            return

        if state.get("pipeline_failed"):
            errors = state.get("errors") or []
            error_text = errors[-1].message if errors else "pipeline failed"
            _update_run(
                client,
                run_id,
                {
                    "status": "failed",
                    "error": error_text,
                    "total_runtime_ms": runtime_ms,
                    "completed_at": _now_iso(),
                },
            )
            _emit_event_sync(
                client,
                run_id,
                "pipeline_failed",
                {"reason": error_text},
            )
            logger.warning(
                "execution_pipeline_failed",
                run_id=str(run_id),
                user_id=str(user_id),
                runtime_ms=runtime_ms,
                error=error_text,
            )
            return

        _update_run(
            client,
            run_id,
            _success_update(state, runtime_ms),
        )
        logger.info(
            "execution_pipeline_done",
            run_id=str(run_id),
            user_id=str(user_id),
            runtime_ms=runtime_ms,
            winner=state["critic_verdict"].winner_agent,
        )


def _success_update(state: PipelineState, runtime_ms: int) -> dict[str, Any]:
    return {
        "status": "done",
        "qubos": {name: output.model_dump(mode="json") for name, output in state["qubos"].items()},
        "scorecards": {
            name: scorecard.model_dump(mode="json")
            for name, scorecard in state["scorecards"].items()
        },
        "winner_agent": state["critic_verdict"].winner_agent,
        "critic_verdict": state["critic_verdict"].model_dump(mode="json"),
        "refined_qubo": state["refined_qubo"].model_dump(mode="json"),
        "circuit_data": state["circuit_data"].model_dump(mode="json"),
        "sim_result": state["sim_result"].model_dump(mode="json"),
        "classical_result": state["classical_result"].model_dump(mode="json"),
        "total_runtime_ms": runtime_ms,
        "completed_at": _now_iso(),
    }


def _update_run(client: Any, run_id: UUID, payload: dict[str, Any]) -> None:
    try:
        client.table("runs").update(payload).eq("id", str(run_id)).execute()
    except Exception as exc:
        logger.error(
            "execution_run_update_failed",
            run_id=str(run_id),
            error=str(exc),
            payload_keys=sorted(payload),
        )
        raise


def _emit_event_sync(
    client: Any,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        client.table("run_events").insert(
            {
                "run_id": str(run_id),
                "event_type": event_type,
                "payload": payload,
            }
        ).execute()
    except Exception as exc:
        logger.error(
            "execution_event_insert_failed",
            run_id=str(run_id),
            event_type=event_type,
            error=str(exc),
        )


def _is_cancel_requested(client: Any, run_id: UUID) -> bool:
    try:
        response = (
            client.table("runs").select("cancel_requested").eq("id", str(run_id)).single().execute()
        )
    except Exception as exc:
        logger.warning(
            "execution_cancel_check_failed",
            run_id=str(run_id),
            error=str(exc),
        )
        return False
    data = getattr(response, "data", None) or {}
    return bool(data.get("cancel_requested", False))


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
