from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .schemas import Difficulty, ProfileName


class Settings(BaseModel):
    app_name: str = "tiny-swarm-maze"
    env: str = "dev"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"

    tick_rate_hz: int = Field(default=5, ge=1, le=30)
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    max_sessions: int = Field(default=32, ge=1, le=500)

    telemetry_db_path: str = "data/telemetry.sqlite3"

    default_difficulty: Difficulty = "standard"
    default_profile: ProfileName = "rules"

    llm_enabled: bool = True
    llm_provider: Literal["ollama", "rule"] = "ollama"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_api_key: Optional[str] = None
    ollama_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    ollama_timeout_ms: int = Field(default=5000, ge=250, le=120_000)
    ollama_max_retries: int = Field(default=2, ge=0, le=6)
    ollama_backoff_ms: int = Field(default=250, ge=50, le=10_000)

    feature_planner_enabled: bool = False
    feature_telemetry_enabled: bool = True


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, raw_value = stripped.split('=', 1)
        values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    import os

    dot_env = _load_dotenv(Path('.env'))
    payload: dict[str, object] = {}

    for field_name in Settings.model_fields:
        env_name = f"SWARM_{field_name.upper()}"
        raw = os.environ.get(env_name, dot_env.get(env_name))
        if raw is None:
            continue
        payload[field_name] = None if raw == '' else raw

    return Settings.model_validate(payload)
