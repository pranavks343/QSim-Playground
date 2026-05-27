"""Manual N-user concurrency stress script.

Spawns N parallel clients (default 4), each creates a temporary Supabase
account, fires three back-to-back ``POST /api/runs`` requests, polls each
to completion, and prints a summary. Useful for local stress testing and
the Day 5 production smoke test (see ``docs/OPERATIONS.md`` →
"Concurrency Verification").

Usage::

    python scripts/manual_concurrency_test.py --clients 4 --runs-per-client 3 \
        --base-url http://localhost:8000

Requires Supabase credentials in the environment (the standard ``.env``
loaded by ``infra.settings``). The backend must already be running and
reachable at ``--base-url``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infra.settings import get_settings  # noqa: E402
from infra.supabase import get_anon_client, get_service_client  # noqa: E402

DEFAULT_CLIENTS = 4
DEFAULT_RUNS_PER_CLIENT = 3
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TEMPLATE = "portfolio"
POLL_INTERVAL_SECONDS = 0.75
POLL_TIMEOUT_SECONDS = 240.0
TERMINAL_STATUSES = {"done", "failed", "timeout", "cancelled"}


@dataclass
class ClientReport:
    """Per-client outcome captured for the final summary."""

    label: str
    user_id: str
    email: str
    run_ids: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    winners: list[str | None] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return self.finished_at - self.started_at


async def main() -> int:
    args = _parse_args()
    get_settings()
    service = get_service_client()
    anon = get_anon_client()
    marker = uuid4().hex
    secret = f"QsimManual-{uuid4().hex}-77"

    print(
        f"manual_concurrency_test: spawning {args.clients} clients, "
        f"{args.runs_per_client} runs each, base_url={args.base_url}"
    )
    created_user_ids: list[str] = []
    try:
        async with httpx.AsyncClient(
            base_url=args.base_url,
            timeout=httpx.Timeout(60.0, read=300.0),
        ) as http_client:
            credentials = await asyncio.gather(
                *[
                    _provision_user(service, anon, secret, marker, index)
                    for index in range(args.clients)
                ]
            )
            for cred in credentials:
                created_user_ids.append(cred["user_id"])

            overall_started = time.perf_counter()
            reports = await asyncio.gather(
                *[
                    _run_client(
                        http_client=http_client,
                        label=f"client-{index}",
                        credential=credentials[index],
                        runs_per_client=args.runs_per_client,
                        template=args.template,
                    )
                    for index in range(args.clients)
                ]
            )
            overall_elapsed = time.perf_counter() - overall_started
    finally:
        for user_id in created_user_ids:
            try:
                service.auth.admin.delete_user(user_id)
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup_failed user_id={user_id} error={exc}")

    return _print_summary(reports, overall_elapsed)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=DEFAULT_CLIENTS)
    parser.add_argument("--runs-per-client", type=int, default=DEFAULT_RUNS_PER_CLIENT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    return parser.parse_args()


async def _provision_user(
    service: Any,
    anon: Any,
    secret: str,
    marker: str,
    index: int,
) -> dict[str, str]:
    email = f"qsim-manual-{marker}-{index}@example.com"
    creation = await asyncio.to_thread(
        service.auth.admin.create_user,
        {
            "email": email,
            "password": secret,
            "email_confirm": True,
            "user_metadata": {"display_name": f"Manual Client {index}"},
        },
    )
    user_id = str(creation.user.id)
    session = await asyncio.to_thread(
        anon.auth.sign_in_with_password,
        {"email": email, "password": secret},
    )
    if session.session is None:
        raise RuntimeError(f"sign-in failed for {email}")
    return {
        "user_id": user_id,
        "email": email,
        "access_token": session.session.access_token,
    }


async def _run_client(
    http_client: httpx.AsyncClient,
    label: str,
    credential: dict[str, str],
    runs_per_client: int,
    template: str,
) -> ClientReport:
    report = ClientReport(
        label=label,
        user_id=credential["user_id"],
        email=credential["email"],
    )
    headers = {"Authorization": f"Bearer {credential['access_token']}"}
    report.started_at = time.perf_counter()
    for run_index in range(runs_per_client):
        try:
            response = await http_client.post(
                "/api/runs",
                json={"input_source": "template", "template_name": template},
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"create#{run_index}: {exc}")
            continue
        if response.status_code != 201:
            report.errors.append(
                f"create#{run_index}: status={response.status_code} body={response.text}"
            )
            continue
        run_id = response.json()["run_id"]
        report.run_ids.append(run_id)
        final = await _poll_until_terminal(http_client, run_id, headers)
        report.statuses.append(final.get("status", "unknown"))
        report.winners.append(final.get("winner_agent"))
        if final.get("status") != "done":
            report.errors.append(
                f"run#{run_index}: terminal_status={final.get('status')} error={final.get('error')}"
            )
    report.finished_at = time.perf_counter()
    print(
        f"{label}: user_id={credential['user_id']} "
        f"runs={len(report.run_ids)} statuses={report.statuses} "
        f"winners={report.winners} elapsed_s={report.elapsed_seconds:.2f} "
        f"errors={len(report.errors)}"
    )
    for error in report.errors:
        print(f"  {label} error: {error}")
    return report


async def _poll_until_terminal(
    http_client: httpx.AsyncClient,
    run_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        response = await http_client.get(f"/api/runs/{run_id}", headers=headers)
        if response.status_code == 200:
            payload: dict[str, Any] = response.json()
            if payload["status"] in TERMINAL_STATUSES:
                return payload
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return {"status": "timeout-waiting", "error": "client poll timed out"}


def _print_summary(reports: list[ClientReport], overall_elapsed: float) -> int:
    total_runs = sum(len(report.run_ids) for report in reports)
    successes = sum(1 for report in reports for status in report.statuses if status == "done")
    failures = total_runs - successes
    error_count = sum(len(report.errors) for report in reports)

    print("")
    print("=" * 64)
    print(
        f"Total clients: {len(reports)} | total runs: {total_runs} | "
        f"successes: {successes} | failures: {failures} | "
        f"errors: {error_count}"
    )
    print(f"Wall-clock elapsed: {overall_elapsed:.2f}s")
    print("=" * 64)

    if failures or error_count or successes != total_runs:
        return 1
    if overall_elapsed > 90.0:
        print(
            f"warning: total elapsed {overall_elapsed:.2f}s exceeds the 90s "
            "Block G acceptance threshold"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
