"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
          extra="ignore"
          )

    anthropic_api_key: str = ""
    github_token: str = ""
    github_webhook_secret: str = ""

    # Model is configurable so the eval section of the report can compare
    # e.g. claude-opus-4-8 vs claude-haiku-4-5 on the same PRs.
    copilot_model: str = "claude-opus-4-8"
    copilot_db_path: str = "copilot.db"

    # How many merged PRs to sample when learning conventions.
    convention_pr_sample: int = 15
    # Max characters of diff per review call (huge PRs get truncated per file).
    max_file_diff_chars: int = 60_000
    # Max characters of surrounding file context sent per file.
    max_context_chars: int = 30_000
    # Concurrent per-file Claude calls (after the cache-warming first file).
    max_concurrent_reviews: int = 4
    # Second-pass false-positive filter before posting.
    verify_findings: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
