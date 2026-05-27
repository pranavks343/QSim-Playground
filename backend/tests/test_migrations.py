from __future__ import annotations

from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "infra" / "migrations" / "001_initial_schema.sql"


def test_initial_schema_migration_contains_required_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for table_name in [
        "users_profile",
        "runs",
        "run_events",
        "exports",
        "rate_limit_log",
    ]:
        assert f"create table if not exists public.{table_name}" in sql
        assert f"alter table public.{table_name} enable row level security" in sql


def test_initial_schema_migration_contains_realtime_triggers_and_cron() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "alter publication supabase_realtime add table public.run_events" in sql
    assert "create trigger auth_users_create_profile" in sql
    assert "create trigger users_profile_set_updated_at" in sql
    assert "create trigger runs_increment_monthly_runs_used" in sql
    assert "qsim-reset-monthly-quotas" in sql
    assert "qsim-delete-stale-rate-limit-log" in sql
    assert "qsim-free-tier-retention" in sql


def test_initial_schema_migration_keeps_service_only_tables_client_unwritable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "grant select on table public.run_events to authenticated" in sql
    assert "grant select on table public.exports to authenticated" in sql
    assert "grant insert" not in _section_for_table(sql, "public.run_events")
    assert "grant insert" not in _section_for_table(sql, "public.exports")
    assert "grant" not in _section_for_table(sql, "public.rate_limit_log")


def _section_for_table(sql: str, table_name: str) -> str:
    lines = [
        line for line in sql.splitlines() if table_name in line and line.strip().startswith("grant")
    ]
    return "\n".join(lines)
