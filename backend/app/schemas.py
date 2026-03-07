from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


Direction = Literal["north", "south", "east", "west"]
CommandIntent = Literal[
    "halt",
    "regroup",
    "find_key",
    "sweep",
    "avoid",
    "resume",
    "explore",
    "to_exit",
    "guard",
    "follow",
]
Difficulty = Literal["starter", "standard", "dense"]
ProfileName = Literal["rules", "ollama_fast", "ollama_slow", "ollama_cloud_kimi"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str


class SessionCreateRequest(BaseModel):
    seed: Optional[int] = Field(default=None, ge=1, le=2_147_483_647)
    difficulty: Difficulty = "standard"


class SessionCreateResponse(BaseModel):
    session_id: str
    seed: int
    tick_rate_hz: int
    ws_path: str
    difficulty: Difficulty


class PointModel(BaseModel):
    x: int
    y: int


class UnitPublicState(BaseModel):
    id: str
    color: str
    role: str
    x: int
    y: int
    vision: int
    hearing: int
    mood: str
    target: Optional[PointModel] = None
    bubble: Optional[str] = None
    carrying_key_id: Optional[str] = None
    active_command: Optional[str] = None
    stunned_until_tick: int = 0


class KeyPublicState(BaseModel):
    id: str
    x: int
    y: int
    found: bool
    delivered: bool
    carried_by: Optional[str] = None


class TrapPublicState(BaseModel):
    id: str
    x: int
    y: int
    revealed: bool
    active: bool


class EventPublic(BaseModel):
    id: str
    tick: int
    tone: Literal["system", "command", "speech", "success", "warning", "info"]
    text: str


class ObjectivePublic(BaseModel):
    delivered_keys: int
    total_keys: int
    maze_clear: bool


class MetricsPublic(BaseModel):
    fog_percent: int
    stuns: int
    reroutes: int
    commands_queued: int
    commands_applied: int
    parser_latency_last_ms: int
    parser_latency_avg_ms: int
    planner_latency_last_ms: int
    planner_latency_avg_ms: int
    timeout_count: int
    model_error_count: int


class GameStateMessage(BaseModel):
    type: Literal["state"] = "state"
    session_id: str
    seed: int
    tick: int
    width: int
    height: int
    difficulty: Difficulty
    profile: ProfileName
    paused: bool
    queue_depth: int
    grid: list[list[int]]
    discovered_tiles: list[str]
    exit: PointModel
    units: list[UnitPublicState]
    keys: list[KeyPublicState]
    traps: list[TrapPublicState]
    objectives: ObjectivePublic
    metrics: MetricsPublic
    events: list[EventPublic]
    selected_unit_id: Optional[str] = None


class AckMessage(BaseModel):
    type: Literal["ack"] = "ack"
    ok: bool
    client_command_id: Optional[str] = None
    reason: Optional[str] = None


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class WarningMessage(BaseModel):
    type: Literal["warning"] = "warning"
    code: str
    message: str


class CommandQueuedMessage(BaseModel):
    type: Literal["command_queued"] = "command_queued"
    command_id: str
    raw_text: str
    profile: ProfileName
    eta_ms: int
    queued_at_ms: int


class CommandAppliedMessage(BaseModel):
    type: Literal["command_applied"] = "command_applied"
    command_id: str
    profile: ProfileName
    latency_ms: int
    parse_latency_ms: int
    parsed: "ParsedCommand"


class CommandInputMessage(BaseModel):
    type: Literal["command_input"] = "command_input"
    text: str = Field(min_length=1, max_length=240)
    selected_unit_id: Optional[str] = None
    client_command_id: str = Field(min_length=8, max_length=128)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


class SubmitCommandMessage(BaseModel):
    type: Literal["submit_command"] = "submit_command"
    raw_text: str = Field(min_length=1, max_length=240)
    selected_unit_id: Optional[str] = None
    issued_at_ms: Optional[int] = None
    client_command_id: Optional[str] = Field(default=None, min_length=8, max_length=128)

    @field_validator("raw_text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


class SetProfileMessage(BaseModel):
    type: Literal["set_profile"] = "set_profile"
    profile: ProfileName


class SetProviderConfigMessage(BaseModel):
    type: Literal["set_provider_config"] = "set_provider_config"
    base_url: Optional[str] = Field(default=None, max_length=512)
    model: Optional[str] = Field(default=None, max_length=128)
    api_key: Optional[str] = Field(default=None, max_length=512)
    timeout_ms: Optional[int] = Field(default=None, ge=250, le=120_000)
    max_retries: Optional[int] = Field(default=None, ge=0, le=6)
    backoff_ms: Optional[int] = Field(default=None, ge=50, le=10_000)
    artificial_delay_ms: Optional[int] = Field(default=None, ge=0, le=15_000)


class PauseMessage(BaseModel):
    type: Literal["pause"] = "pause"


class ResumeMessage(BaseModel):
    type: Literal["resume"] = "resume"


class ResetMessage(BaseModel):
    type: Literal["reset"] = "reset"
    seed: Optional[int] = Field(default=None, ge=1, le=2_147_483_647)
    difficulty: Optional[Difficulty] = None


class ParsedCommand(BaseModel):
    target_ids: list[str] = Field(min_length=1)
    intent: CommandIntent
    arguments: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high"] = "normal"
    ttl_ticks: int = Field(default=18, ge=1, le=300)
    source: Literal["player", "planner"] = "player"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    rationale: Optional[str] = Field(default=None, max_length=240)
    direction: Optional[Direction] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)

        if "duration_ticks" in payload and "ttl_ticks" not in payload:
            payload["ttl_ticks"] = payload.pop("duration_ticks")

        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        if "direction" in payload and payload["direction"] is not None and "direction" not in arguments:
            arguments["direction"] = payload["direction"]

        if "direction" not in payload and isinstance(arguments.get("direction"), str):
            payload["direction"] = arguments.get("direction")

        payload["arguments"] = arguments
        return payload

    @field_validator("target_ids")
    @classmethod
    def unique_target_ids(cls, value: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item not in seen:
                ordered.append(item)
                seen.add(item)
        if not ordered:
            raise ValueError("target_ids cannot be empty")
        return ordered

