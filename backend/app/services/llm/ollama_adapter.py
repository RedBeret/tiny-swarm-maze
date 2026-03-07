from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ...config import Settings
from ...schemas import ParsedCommand
from ...telemetry import TelemetryStore
from .base import CommandParser, ParseOverrides
from .rule_adapter import RuleCommandParser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _EffectiveConfig:
    base_url: str
    model: str
    api_key: str | None
    timeout_ms: int
    max_retries: int
    backoff_ms: int
    artificial_delay_ms: int


class OllamaCommandParser(CommandParser):
    def __init__(self, settings: Settings, telemetry: TelemetryStore) -> None:
        self._settings = settings
        self._telemetry = telemetry
        self._fallback = RuleCommandParser()

    async def parse_command(
        self,
        *,
        text: str,
        selected_unit_id: str | None,
        available_unit_ids: list[str],
        available_colors: list[str],
        session_id: str,
        overrides: ParseOverrides | None = None,
    ) -> ParsedCommand:
        if not self._settings.llm_enabled or self._settings.llm_provider != "ollama":
            return await self._fallback.parse_command(
                text=text,
                selected_unit_id=selected_unit_id,
                available_unit_ids=available_unit_ids,
                available_colors=available_colors,
                session_id=session_id,
                overrides=overrides,
            )

        cfg = self._effective_config(overrides)
        prompt = self._build_prompt(
            text=text,
            selected_unit_id=selected_unit_id,
            available_unit_ids=available_unit_ids,
            available_colors=available_colors,
        )

        if cfg.artificial_delay_ms > 0:
            await asyncio.sleep(cfg.artificial_delay_ms / 1000)

        last_error: str | None = None
        started = time.perf_counter()

        for attempt in range(cfg.max_retries + 1):
            try:
                result = await self._call_ollama(prompt, cfg)
                parsed = self._coerce_parsed_command(result, available_unit_ids)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._telemetry.record_llm_call(
                    session_id=session_id,
                    provider="ollama",
                    model=cfg.model,
                    duration_ms=duration_ms,
                    success=True,
                )
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("ollama parse attempt %s failed: %s", attempt + 1, exc)
                if attempt < cfg.max_retries:
                    await asyncio.sleep((cfg.backoff_ms * (2**attempt)) / 1000)

        duration_ms = int((time.perf_counter() - started) * 1000)
        self._telemetry.record_llm_call(
            session_id=session_id,
            provider="ollama",
            model=cfg.model,
            duration_ms=duration_ms,
            success=False,
            error_text=last_error,
        )
        return await self._fallback.parse_command(
            text=text,
            selected_unit_id=selected_unit_id,
            available_unit_ids=available_unit_ids,
            available_colors=available_colors,
            session_id=session_id,
            overrides=overrides,
        )

    def _effective_config(self, overrides: ParseOverrides | None) -> _EffectiveConfig:
        override = overrides or ParseOverrides()
        return _EffectiveConfig(
            base_url=(override.base_url or self._settings.ollama_host).rstrip("/"),
            model=override.model or self._settings.ollama_model,
            api_key=override.api_key if override.api_key is not None else self._settings.ollama_api_key,
            timeout_ms=override.timeout_ms or self._settings.ollama_timeout_ms,
            max_retries=override.max_retries if override.max_retries is not None else self._settings.ollama_max_retries,
            backoff_ms=override.backoff_ms if override.backoff_ms is not None else self._settings.ollama_backoff_ms,
            artificial_delay_ms=override.artificial_delay_ms,
        )

    async def _call_ollama(self, prompt: str, cfg: _EffectiveConfig) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        payload = {
            "model": cfg.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Convert a maze-game player instruction into strict JSON only. "
                        "Valid intents: halt, regroup, find_key, sweep, avoid, resume, explore, to_exit, guard, follow. "
                        "Only include target ids that exist in the provided list. "
                        "Output schema: "
                        '{"target_ids":["blue-1"],"intent":"halt","arguments":{},"priority":"normal","ttl_ticks":12,"confidence":0.95,"rationale":"short"}'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self._settings.ollama_temperature,
            "response_format": {"type": "json_object"},
        }

        timeout_seconds = max(0.25, cfg.timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(self._chat_completions_url(cfg.base_url), headers=headers, json=payload)
            if response.status_code == 404:
                # Fallback for older Ollama installs still using /api/chat.
                legacy_payload = {
                    "model": cfg.model,
                    "messages": payload["messages"],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self._settings.ollama_temperature},
                }
                response = await client.post(f"{cfg.base_url}/api/chat", headers=headers, json=legacy_payload)

            response.raise_for_status()
            data = response.json()

        content = self._extract_content(data)
        if not content:
            raise ValueError("empty response content from ollama")
        return self._extract_json(content)

    def _chat_completions_url(self, base_url: str) -> str:
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        if "/v1/" in base_url:
            return f"{base_url.rstrip('/')}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
        message = payload.get("message", {})
        content = message.get("content")
        return content if isinstance(content, str) else ""

    def _build_prompt(
        self,
        *,
        text: str,
        selected_unit_id: str | None,
        available_unit_ids: list[str],
        available_colors: list[str],
    ) -> str:
        return (
            "Game units:\n"
            f"- ids: {', '.join(available_unit_ids)}\n"
            f"- colors: {', '.join(available_colors)}\n"
            f"- selected_unit_id: {selected_unit_id or 'none'}\n\n"
            "Rules:\n"
            "- If player addresses a color, target all units with that color prefix.\n"
            "- If player says all, target all units.\n"
            "- If ambiguous, use selected_unit_id.\n"
            "- Use arguments.direction only for sweep intent.\n"
            "- Keep ttl_ticks between 8 and 24 unless halt uses 12.\n"
            "- If unknown, choose explore and confidence <= 0.6.\n\n"
            f"Player text: {text}\n"
        )

    def _extract_json(self, content: str) -> dict[str, Any]:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("ollama response did not contain valid JSON") from None
            return json.loads(content[start : end + 1])

    def _coerce_parsed_command(self, payload: dict[str, Any], available_unit_ids: list[str]) -> ParsedCommand:
        target_ids = payload.get("target_ids")
        if isinstance(target_ids, str):
            target_ids = [target_ids]
        if not isinstance(target_ids, list) or not target_ids:
            raise ValueError("invalid target_ids from ollama")

        cleaned_ids = [target for target in target_ids if target in available_unit_ids]
        if not cleaned_ids:
            cleaned_ids = [available_unit_ids[0]]

        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        direction = payload.get("direction")
        if isinstance(arguments.get("direction"), str) and direction is None:
            direction = arguments["direction"]

        ttl_ticks = payload.get("ttl_ticks", payload.get("duration_ticks", 18))
        confidence = payload.get("confidence", 0.8)
        try:
            confidence = float(confidence)
        except Exception:  # noqa: BLE001
            confidence = 0.8

        parsed = ParsedCommand.model_validate(
            {
                "target_ids": cleaned_ids,
                "intent": payload.get("intent"),
                "arguments": arguments,
                "priority": payload.get("priority", "normal"),
                "ttl_ticks": ttl_ticks,
                "source": "player",
                "confidence": max(0.0, min(1.0, confidence)),
                "rationale": payload.get("rationale"),
                "direction": direction,
            }
        )
        return parsed
