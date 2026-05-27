from __future__ import annotations

import pytest
from pydantic import ValidationError

from infra.settings import Settings
from infra.supabase import get_anon_client, get_service_client


def _real_supabase_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        pytest.skip(f"Supabase credentials are not configured: {exc}")


def test_anon_client_can_read_local_auth_session() -> None:
    _real_supabase_settings()

    client = get_anon_client()

    client.auth.get_session()


def test_service_client_can_call_admin_api() -> None:
    _real_supabase_settings()

    client = get_service_client()

    client.auth.admin.list_users()
