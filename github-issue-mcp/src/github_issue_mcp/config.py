"""Configuration loaded from a project-local .env file."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigurationError(RuntimeError):
    """Raised when required local configuration is missing."""


@dataclass(frozen=True)
class Settings:
    github_token: str

    @classmethod
    def from_env_file(cls, env_file: Path | None = None) -> "Settings":
        """Load secrets from .env without copying them into process environment."""
        project_root = Path(__file__).resolve().parents[2]
        path = env_file if env_file is not None else project_root / ".env"
        values = dotenv_values(path)
        token = (values.get("GITHUB_TOKEN") or "").strip()
        if not token or token == "github_pat_replace_me":
            raise ConfigurationError(
                "GitHub authentication is not configured. Copy .env.example to .env "
                "and add a fine-grained token."
            )
        return cls(github_token=token)

