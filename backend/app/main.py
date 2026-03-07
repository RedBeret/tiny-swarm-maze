from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .schemas import (
    AckMessage,
    CommandInputMessage,
    ErrorMessage,
    HealthResponse,
    PauseMessage,
    ResetMessage,
    ResumeMessage,
    SessionCreateRequest,
    SessionCreateResponse,
    SetProfileMessage,
    SetProviderConfigMessage,
    SubmitCommandMessage,
)
from .session_manager import PROFILE_PRESETS, SessionManager
from .telemetry import TelemetryStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    telemetry = TelemetryStore(settings.telemetry_db_path, enabled=settings.feature_telemetry_enabled)
    app.state.settings = settings
    app.state.telemetry = telemetry
    app.state.session_manager = SessionManager(settings, telemetry)
    yield


app = FastAPI(title="Tiny Swarm Maze API", version="0.2.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name)


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "default_difficulty": settings.default_difficulty,
        "default_profile": settings.default_profile,
        "tick_rate_hz": settings.tick_rate_hz,
        "profiles": {
            name: {
                "use_ollama": preset.use_ollama,
                "timeout_ms": preset.timeout_ms,
                "max_retries": preset.max_retries,
                "backoff_ms": preset.backoff_ms,
                "artificial_delay_ms": preset.artificial_delay_ms,
                "model": preset.model,
            }
            for name, preset in PROFILE_PRESETS.items()
        },
        "ollama": {
            "base_url": settings.ollama_host,
            "model": settings.ollama_model,
            "timeout_ms": settings.ollama_timeout_ms,
            "max_retries": settings.ollama_max_retries,
            "backoff_ms": settings.ollama_backoff_ms,
        },
    }


@app.get("/api/metrics")
async def get_metrics() -> dict[str, Any]:
    telemetry: TelemetryStore = app.state.telemetry
    return telemetry.summary()


@app.post("/api/session", response_model=SessionCreateResponse)
async def create_session(payload: SessionCreateRequest) -> SessionCreateResponse:
    manager: SessionManager = app.state.session_manager
    try:
        session = await manager.create_session(seed=payload.seed, difficulty=payload.difficulty)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return SessionCreateResponse(
        session_id=session.session_id,
        seed=session.seed,
        tick_rate_hz=session.tick_rate_hz,
        ws_path=f"/ws/{session.session_id}",
        difficulty=session.difficulty,
    )


@app.get("/api/session/{session_id}")
async def get_session_state(session_id: str) -> dict[str, Any]:
    manager: SessionManager = app.state.session_manager
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="unknown session")
    return await session._build_snapshot_payload()


@app.get("/api/session/{session_id}/replay")
async def get_session_replay(session_id: str) -> dict[str, Any]:
    manager: SessionManager = app.state.session_manager
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="unknown session")
    snapshot = await session._build_snapshot_payload()
    return {"session_id": session_id, "frames": [snapshot]}


@app.post("/api/session/{session_id}/reset")
async def reset_session(session_id: str, payload: ResetMessage) -> dict[str, Any]:
    manager: SessionManager = app.state.session_manager
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="unknown session")
    await session.reset(seed=payload.seed, difficulty=payload.difficulty)
    return {"ok": True, "seed": session.seed, "difficulty": session.difficulty}


@app.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str) -> None:
    manager: SessionManager = app.state.session_manager
    session = await manager.get_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json(ErrorMessage(message="unknown session").model_dump())
        await websocket.close(code=1008)
        return

    await session.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(AckMessage(ok=False, reason=f"invalid payload: {exc}").model_dump())
                continue

            try:
                ack = await _handle_ws_payload(session, payload)
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(AckMessage(ok=False, reason=f"invalid message: {exc}").model_dump())
                continue
            if ack is not None:
                await websocket.send_json(ack.model_dump())
    except WebSocketDisconnect:
        await session.disconnect(websocket)


async def _handle_ws_payload(session, payload: dict[str, Any]) -> AckMessage | None:
    message_type = payload.get("type")

    if message_type == "command_input":
        legacy = CommandInputMessage.model_validate(payload)
        return await session.enqueue_command(
            raw_text=legacy.text,
            selected_unit_id=legacy.selected_unit_id,
            client_command_id=legacy.client_command_id,
            issued_at_ms=None,
        )

    if message_type == "submit_command":
        message = SubmitCommandMessage.model_validate(payload)
        return await session.enqueue_command(
            raw_text=message.raw_text,
            selected_unit_id=message.selected_unit_id,
            client_command_id=message.client_command_id,
            issued_at_ms=message.issued_at_ms,
        )

    if message_type == "set_profile":
        message = SetProfileMessage.model_validate(payload)
        await session.set_profile(message.profile)
        return AckMessage(ok=True, reason=f"profile set to {message.profile}")

    if message_type == "set_provider_config":
        message = SetProviderConfigMessage.model_validate(payload)
        await session.set_provider_config(
            base_url=message.base_url,
            model=message.model,
            api_key=message.api_key,
            timeout_ms=message.timeout_ms,
            max_retries=message.max_retries,
            backoff_ms=message.backoff_ms,
            artificial_delay_ms=message.artificial_delay_ms,
        )
        return AckMessage(ok=True, reason="provider config updated")

    if message_type == "pause":
        PauseMessage.model_validate(payload)
        await session.pause()
        return AckMessage(ok=True, reason="paused")

    if message_type == "resume":
        ResumeMessage.model_validate(payload)
        await session.resume()
        return AckMessage(ok=True, reason="resumed")

    if message_type == "reset":
        message = ResetMessage.model_validate(payload)
        await session.reset(seed=message.seed, difficulty=message.difficulty)
        return AckMessage(ok=True, reason="reset")

    return AckMessage(ok=False, reason=f"unsupported message type: {message_type}")
