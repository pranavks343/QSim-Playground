"""Application settings loaded once from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for trusted backend processes."""

    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        validate_default=True,
    )

    gemini_api_keys: list[str] = Field(default_factory=list, alias="GEMINI_API_KEYS")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    allowed_origins: list[str] = Field(default_factory=list, alias="ALLOWED_ORIGINS")

    @field_validator("gemini_api_keys", "allowed_origins", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> list[str]:
        """Parse comma-separated env vars into non-empty string lists."""

        if isinstance(value, str):
            values = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            values = [str(item).strip() for item in value]
        else:
            raise ValueError("value must be a comma-separated string or list")

        parsed = [item for item in values if item]
        if not parsed:
            raise ValueError("value must include at least one entry")
        return parsed

    @field_validator(
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "supabase_jwt_secret",
        "sentry_dsn",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        """Reject missing required scalar settings."""

        if not value.strip():
            raise ValueError("value must be set")
        return value

    @field_validator(
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "supabase_jwt_secret",
    )
    @classmethod
    def reject_placeholder_supabase_values(cls, value: str) -> str:
        """Reject common copied placeholders so misconfigured deploys fail loudly."""

        normalized = value.strip().lower()
        placeholder_fragments = (
            "...",
            "xxxxx",
            "placeholder",
            "changeme",
            "change-me",
            "your-",
            "<",
            ">",
        )
        if any(fragment in normalized for fragment in placeholder_fragments):
            raise ValueError("Supabase setting appears to be a placeholder")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""

    return Settings()
