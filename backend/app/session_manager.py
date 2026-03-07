from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

from .config import Settings
from .schemas import (
    AckMessage,
    CommandAppliedMessage,
    CommandQueuedMessage,
    Difficulty,
    GameStateMessage,
    ParsedCommand,
    ProfileName,
)
from .services.llm.base import ParseOverrides
from .services.llm.ollama_adapter import OllamaCommandParser
from .services.llm.rule_adapter import RuleCommandParser
from .sim.engine import GameEngine
from .telemetry import TelemetryStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProfilePreset:
    use_ollama: bool
    timeout_ms: int
    max_retries: int
    backoff_ms: int
    artificial_delay_ms: int
    model: Optional[str] = None


PROFILE_PRESETS: dict[ProfileName, ProfilePreset] = {
    "rules": ProfilePreset(
        use_ollama=False,
        timeout_ms=0,
        max_retries=0,
        backoff_ms=0,
        artificial_delay_ms=0,
        model=None,
    ),
    "ollama_fast": ProfilePreset(
        use_ollama=True,
        timeout_ms=2500,
        max_retries=1,
        backoff_ms=120,
        artificial_delay_ms=0,
        model=None,
    ),
    "ollama_slow": ProfilePreset(
        use_ollama=True,
        timeout_ms=7000,
        max_retries=2,
        backoff_ms=300,
        artificial_delay_ms=900,
        model=None,
    ),
    "ollama_cloud_kimi": ProfilePreset(
        use_ollama=True,
        timeout_ms=9000,
        max_retries=2,
        backoff_ms=400,
        artificial_delay_ms=1300,
        model="kimi-k2.5:cloud",
    ),
}


@dataclass(slots=True)
class ProviderConfig:
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    backoff_ms: Optional[int] = None
    artificial_delay_ms: Optional[int] = None


@dataclass(slots=True)
class QueuedCommand:
    command_id: str
    raw_text: str
    selected_unit_id: Optional[str]
    issued_at_ms: int
    queued_at_ms: int
    generation: int


@dataclass
class GameSession:
    session_id: str
    seed: int
    difficulty: Difficulty
    engine: GameEngine
    rules_parser: RuleCommandParser
    ollama_parser: OllamaCommandParser
    telemetry: TelemetryStore
    tick_rate_hz: int
    profile: ProfileName
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    selected_unit_id: Optional[str] = None
    paused: bool = False
    provider_config: ProviderConfig = field(default_factory=ProviderConfig)
    _connections: set[WebSocket] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _tick_task: Optional[asyncio.Task] = None
    _command_task: Optional[asyncio.Task] = None
    _queue: asyncio.Queue[QueuedCommand] = field(default_factory=asyncio.Queue)
    _queue_generation: int = 0
    _queued_command_ids: set[str] = field(default_factory=set)
    _commands_queued_count: int = 0
    _parse_latencies_ms: deque[int] = field(default_factory=lambda: deque(maxlen=128))
    _planner_latencies_ms: deque[int] = field(default_factory=lambda: deque(maxlen=128))
    _timeout_count: int = 0
    _model_error_count: int = 0

    async def start(self) -> None:
        if self._tick_task and not self._tick_task.done():
            return
        self._tick_task = asyncio.create_task(self._tick_loop(), name=f"session:{self.session_id}:tick")
        self._command_task = asyncio.create_task(self._command_loop(), name=f"session:{self.session_id}:commands")

    async def stop(self) -> None:
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        if self._command_task:
            self._command_task.cancel()
            try:
                await self._command_task
            except asyncio.CancelledError:
                pass
        for websocket in list(self._connections):
            await websocket.close()
        self._connections.clear()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        self.last_active_at = time.time()
        await self._send_snapshot(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        self.last_active_at = time.time()

    async def set_profile(self, profile: ProfileName) -> None:
        async with self._lock:
            self.profile = profile
            self.last_active_at = time.time()
        await self.broadcast_snapshot()

    async def set_provider_config(
        self,
        *,
        base_url: Optional[str],
        model: Optional[str],
        api_key: Optional[str],
        timeout_ms: Optional[int],
        max_retries: Optional[int],
        backoff_ms: Optional[int],
        artificial_delay_ms: Optional[int],
    ) -> None:
        async with self._lock:
            self.last_active_at = time.time()
            if base_url is not None:
                self.provider_config.base_url = base_url.strip() or None
            if model is not None:
                self.provider_config.model = model.strip() or None
            if api_key is not None:
                self.provider_config.api_key = api_key.strip() or None
            if timeout_ms is not None:
                self.provider_config.timeout_ms = timeout_ms
            if max_retries is not None:
                self.provider_config.max_retries = max_retries
            if backoff_ms is not None:
                self.provider_config.backoff_ms = backoff_ms
            if artificial_delay_ms is not None:
                self.provider_config.artificial_delay_ms = artificial_delay_ms
        await self.broadcast_snapshot()

    async def pause(self) -> None:
        async with self._lock:
            self.paused = True
            self.last_active_at = time.time()
        await self.broadcast_snapshot()

    async def resume(self) -> None:
        async with self._lock:
            self.paused = False
            self.last_active_at = time.time()
        await self.broadcast_snapshot()

    async def reset(self, seed: Optional[int], difficulty: Optional[Difficulty]) -> None:
        async with self._lock:
            self.last_active_at = time.time()
            if seed is None:
                seed = int(time.time() * 1000) % 2_147_483_647
            self.seed = seed
            self.difficulty = difficulty or self.difficulty
            self.engine = GameEngine(session_id=self.session_id, seed=seed, difficulty=self.difficulty)
            self.selected_unit_id = None
            self._queue_generation += 1
            self._queued_command_ids.clear()
            self.paused = False
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break

        self.telemetry.record_session_started(self.session_id, seed)
        await self.broadcast_snapshot()

    async def enqueue_command(
        self,
        *,
        raw_text: str,
        selected_unit_id: Optional[str],
        client_command_id: Optional[str],
        issued_at_ms: Optional[int],
    ) -> AckMessage:
        command_id = client_command_id or uuid.uuid4().hex
        now_ms = int(time.time() * 1000)

        async with self._lock:
            self.last_active_at = time.time()
            self.selected_unit_id = selected_unit_id
            if command_id in self.engine.state.applied_command_ids or command_id in self._queued_command_ids:
                return AckMessage(ok=True, client_command_id=command_id, reason="duplicate command ignored")

            queued = QueuedCommand(
                command_id=command_id,
                raw_text=raw_text,
                selected_unit_id=selected_unit_id,
                issued_at_ms=issued_at_ms or now_ms,
                queued_at_ms=now_ms,
                generation=self._queue_generation,
            )
            self._queued_command_ids.add(command_id)
            self._commands_queued_count += 1
            self._queue.put_nowait(queued)
            profile = self.profile
            queue_depth = self._queue.qsize()
            eta_ms = self._estimate_eta_ms(profile)

        await self._broadcast_payload(
            CommandQueuedMessage(
                command_id=command_id,
                raw_text=raw_text,
                profile=profile,
                eta_ms=eta_ms,
                queued_at_ms=now_ms,
            ).model_dump()
        )

        if queue_depth <= 1:
            await self.broadcast_snapshot()

        return AckMessage(ok=True, client_command_id=command_id, reason="queued")

    async def broadcast_snapshot(self) -> None:
        if not self._connections:
            return
        message = await self._build_snapshot_payload()
        await self._broadcast_payload(message)

    async def _send_snapshot(self, websocket: WebSocket) -> None:
        snapshot = await self._build_snapshot_payload()
        await websocket.send_json(snapshot)

    async def _build_snapshot_payload(self) -> dict:
        async with self._lock:
            parser_last = self._parse_latencies_ms[-1] if self._parse_latencies_ms else 0
            parser_avg = int(sum(self._parse_latencies_ms) / len(self._parse_latencies_ms)) if self._parse_latencies_ms else 0
            planner_last = self._planner_latencies_ms[-1] if self._planner_latencies_ms else 0
            planner_avg = int(sum(self._planner_latencies_ms) / len(self._planner_latencies_ms)) if self._planner_latencies_ms else 0

            snapshot: GameStateMessage = self.engine.snapshot(
                selected_unit_id=self.selected_unit_id,
                profile=self.profile,
                paused=self.paused,
                queue_depth=self._queue.qsize(),
                commands_queued=self._commands_queued_count,
                parser_latency_last_ms=parser_last,
                parser_latency_avg_ms=parser_avg,
                planner_latency_last_ms=planner_last,
                planner_latency_avg_ms=planner_avg,
                timeout_count=self._timeout_count,
                model_error_count=self._model_error_count,
            )
            return snapshot.model_dump()

    async def _broadcast_payload(self, payload: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(websocket)
        for websocket in stale:
            self._connections.discard(websocket)

    async def _tick_loop(self) -> None:
        interval = 1.0 / self.tick_rate_hz
        try:
            while True:
                async with self._lock:
                    if not self.paused:
                        self.engine.step()
                await self.broadcast_snapshot()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("tick loop stopped for session %s", self.session_id)
            raise

    async def _command_loop(self) -> None:
        try:
            while True:
                queued = await self._queue.get()
                try:
                    await self._process_queued_command(queued)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("command loop stopped for session %s", self.session_id)
            raise

    async def _process_queued_command(self, queued: QueuedCommand) -> None:
        parse_started = time.perf_counter()

        async with self._lock:
            if queued.generation != self._queue_generation:
                self._queued_command_ids.discard(queued.command_id)
                return
            available_unit_ids = [unit.id for unit in self.engine.state.units]
            available_colors = sorted({unit.color for unit in self.engine.state.units})
            selected_unit_id = queued.selected_unit_id
            profile = self.profile
            overrides = self._build_parse_overrides(profile)

        parser = self.ollama_parser if PROFILE_PRESETS[profile].use_ollama else self.rules_parser

        try:
            parsed: ParsedCommand = await parser.parse_command(
                text=queued.raw_text,
                selected_unit_id=selected_unit_id,
                available_unit_ids=available_unit_ids,
                available_colors=available_colors,
                session_id=self.session_id,
                overrides=overrides,
            )
        except Exception as exc:  # noqa: BLE001
            self._model_error_count += 1
            if "timeout" in str(exc).lower():
                self._timeout_count += 1
            logger.warning("parser failed, falling back to rules: %s", exc)
            parsed = await self.rules_parser.parse_command(
                text=queued.raw_text,
                selected_unit_id=selected_unit_id,
                available_unit_ids=available_unit_ids,
                available_colors=available_colors,
                session_id=self.session_id,
            )

        parse_latency_ms = int((time.perf_counter() - parse_started) * 1000)
        self._parse_latencies_ms.append(parse_latency_ms)

        self.telemetry.record_command(
            session_id=self.session_id,
            client_command_id=queued.command_id,
            raw_text=queued.raw_text,
            parsed_json={
                **parsed.model_dump(),
                "profile": profile,
                "parse_latency_ms": parse_latency_ms,
                "queued_at_ms": queued.queued_at_ms,
            },
        )

        async with self._lock:
            if queued.generation != self._queue_generation:
                self._queued_command_ids.discard(queued.command_id)
                return

            applied = self.engine.apply_command(parsed, queued.command_id)
            self._queued_command_ids.discard(queued.command_id)

        if applied:
            total_latency_ms = int(time.time() * 1000) - queued.issued_at_ms
            await self._broadcast_payload(
                CommandAppliedMessage(
                    command_id=queued.command_id,
                    profile=profile,
                    latency_ms=max(0, total_latency_ms),
                    parse_latency_ms=parse_latency_ms,
                    parsed=parsed,
                ).model_dump()
            )

        await self.broadcast_snapshot()

    def _build_parse_overrides(self, profile: ProfileName) -> ParseOverrides:
        preset = PROFILE_PRESETS[profile]
        cfg = self.provider_config

        model = cfg.model or preset.model
        timeout_ms = cfg.timeout_ms if cfg.timeout_ms is not None else preset.timeout_ms
        max_retries = cfg.max_retries if cfg.max_retries is not None else preset.max_retries
        backoff_ms = cfg.backoff_ms if cfg.backoff_ms is not None else preset.backoff_ms
        artificial_delay_ms = (
            cfg.artificial_delay_ms if cfg.artificial_delay_ms is not None else preset.artificial_delay_ms
        )

        return ParseOverrides(
            base_url=cfg.base_url,
            model=model,
            api_key=cfg.api_key,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            backoff_ms=backoff_ms,
            artificial_delay_ms=artificial_delay_ms,
        )

    def _estimate_eta_ms(self, profile: ProfileName) -> int:
        preset = PROFILE_PRESETS[profile]
        if not preset.use_ollama:
            return 75
        base = max(250, preset.artificial_delay_ms + 250)
        return base + (self._queue.qsize() * 150)


class SessionManager:
    def __init__(self, settings: Settings, telemetry: TelemetryStore) -> None:
        self._settings = settings
        self._telemetry = telemetry
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, seed: Optional[int] = None, difficulty: Optional[Difficulty] = None) -> GameSession:
        async with self._lock:
            await self._evict_expired_locked()
            if len(self._sessions) >= self._settings.max_sessions:
                raise RuntimeError("maximum active sessions reached")

            session_id = uuid.uuid4().hex
            if seed is None:
                seed = int(time.time() * 1000) % 2_147_483_647
            difficulty = difficulty or self._settings.default_difficulty

            engine = GameEngine(session_id=session_id, seed=seed, difficulty=difficulty)
            session = GameSession(
                session_id=session_id,
                seed=seed,
                difficulty=difficulty,
                engine=engine,
                rules_parser=RuleCommandParser(),
                ollama_parser=OllamaCommandParser(self._settings, self._telemetry),
                telemetry=self._telemetry,
                tick_rate_hz=self._settings.tick_rate_hz,
                profile=self._settings.default_profile,
            )
            self._sessions[session_id] = session
            self._telemetry.record_session_started(session_id, seed)
            await session.start()
            return session

    async def get_session(self, session_id: str) -> Optional[GameSession]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_active_at = time.time()
            return session

    async def remove_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            await session.stop()

    async def _evict_expired_locked(self) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if (time.time() - session.last_active_at) > self._settings.session_ttl_seconds
        ]
        for session_id in expired_ids:
            session = self._sessions.pop(session_id, None)
            if session:
                await session.stop()
