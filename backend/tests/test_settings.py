from __future__ import annotations

import pytest
from pydantic import ValidationError

from infra.settings import Settings


def test_settings_parses_comma_separated_environment_values() -> None:
    settings = Settings.model_validate(
        {
            "GEMINI_API_KEYS": "key-1, key-2",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "SUPABASE_JWT_SECRET": "jwt",
            "SENTRY_DSN": "https://sentry.example/1",
            "ALLOWED_ORIGINS": "http://localhost:3000, https://qsim.example",
        }
    )

    assert settings.gemini_api_keys == ["key-1", "key-2"]
    assert settings.allowed_origins == ["http://localhost:3000", "https://qsim.example"]


def test_settings_rejects_missing_required_values() -> None:
    with pytest.raises(ValidationError, match="value must include at least one entry"):
        Settings()
