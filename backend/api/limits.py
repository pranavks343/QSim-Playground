"""Server-side tier limits: quota, rate limit, and resource caps.

All enforcement is server-side; nothing here trusts client-supplied data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict
from uuid import UUID

import structlog
from fastapi import HTTPException
from starlette import status

from api.deps import AuthenticatedUser
from core.limits import QubitCapExceeded, enforce_qubit_cap
from infra.supabase import get_service_client

logger = structlog.get_logger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_RETRY_AFTER = "60"


class TierLimit(TypedDict):
    monthly_runs: int | None
    runs_per_minute: int
    max_qubits: int | None


TIER_LIMITS: dict[str, TierLimit] = {
    "free": {"monthly_runs": 50, "runs_per_minute": 5, "max_qubits": 20},
    "pro": {"monthly_runs": 1000, "runs_per_minute": 30, "max_qubits": 50},
    "enterprise": {"monthly_runs": None, "runs_per_minute": 100, "max_qubits": 100},
}


__all__ = [
    "RATE_LIMIT_WINDOW_SECONDS",
    "TIER_LIMITS",
    "QubitCapExceeded",
    "check_qubit_cap",
    "check_quota",
    "check_rate_limit",
    "tier_limits",
]


def tier_limits(tier: str) -> TierLimit:
    """Return tier limits, defaulting to free for unknown tiers."""

    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


async def check_quota(user: AuthenticatedUser) -> None:
    """Enforce monthly run quota for the user's tier.

    Enterprise tier is unlimited. Raises HTTP 429 with a ``Retry-After``
    header set to the seconds remaining until the next quota reset.
    """

    if user.tier == "enterprise":
        return
    limit = tier_limits(user.tier)["monthly_runs"]
    if limit is None:
        return
    if user.monthly_runs_used < limit:
        return
    resets_at = _next_month_start(datetime.now(tz=UTC))
    retry_after = max(1, int((resets_at - datetime.now(tz=UTC)).total_seconds()))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "quota_exceeded",
            "limit": limit,
            "resets_at": resets_at.isoformat(),
        },
        headers={"Retry-After": str(retry_after)},
    )


async def check_rate_limit(
    user: AuthenticatedUser,
    action: str = "create_run",
    *,
    client: Any | None = None,
    now: datetime | None = None,
) -> None:
    """Insert a usage marker and enforce per-tier requests-per-minute.

    Uses the service-role client because ``rate_limit_log`` is RLS-guarded
    against direct client writes.
    """

    client = client or get_service_client()
    current = now or datetime.now(tz=UTC)
    try:
        client.table("rate_limit_log").insert(
            {
                "user_id": str(user.id),
                "action": action,
                "created_at": current.isoformat(),
            }
        ).execute()
    except Exception as exc:
        logger.warning(
            "rate_limit_log_insert_failed",
            user_id=str(user.id),
            action=action,
            error=str(exc),
        )
        return

    try:
        response = (
            client.table("rate_limit_log")
            .select("created_at")
            .eq("user_id", str(user.id))
            .eq("action", action)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "rate_limit_log_query_failed",
            user_id=str(user.id),
            action=action,
            error=str(exc),
        )
        return

    cutoff = current - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    rows = response.data or []
    recent = sum(1 for row in rows if _parse_timestamp(row.get("created_at")) >= cutoff)
    limit = tier_limits(user.tier)["runs_per_minute"]
    if recent > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "limit": limit,
                "window_seconds": int(RATE_LIMIT_WINDOW_SECONDS),
            },
            headers={"Retry-After": RATE_LIMIT_RETRY_AFTER},
        )


def check_qubit_cap(
    qubit_count: int,
    user: AuthenticatedUser,
    source: str = "qubo",
) -> None:
    """Raise :class:`QubitCapExceeded` if ``qubit_count`` is over the tier cap."""

    enforce_qubit_cap(qubit_count, tier_limits(user.tier)["max_qubits"], source)


def _next_month_start(current: datetime) -> datetime:
    if current.month == 12:
        return current.replace(
            year=current.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return current.replace(
        month=current.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalised = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalised)
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def _user_id_or_none(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None
