from __future__ import annotations

from ...schemas import ParsedCommand
from .base import CommandParser, ParseOverrides


class RuleCommandParser(CommandParser):
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
        lowered = " ".join(text.lower().strip().split())

        target_ids = self._resolve_targets(
            lowered=lowered,
            selected_unit_id=selected_unit_id,
            available_unit_ids=available_unit_ids,
            available_colors=available_colors,
        )

        if any(token in lowered for token in ("stop", "halt", "wait", "don't do that", "dont do that")):
            return ParsedCommand(target_ids=target_ids, intent="halt", ttl_ticks=12, confidence=0.98, rationale="rule: halt")
        if any(token in lowered for token in ("regroup", "come back", "return")):
            return ParsedCommand(target_ids=target_ids, intent="regroup", ttl_ticks=18, confidence=0.92, rationale="rule: regroup")
        if "guard" in lowered:
            return ParsedCommand(target_ids=target_ids, intent="guard", ttl_ticks=16, confidence=0.86, rationale="rule: guard")
        if "follow" in lowered:
            follow_target = self._resolve_follow_target(lowered, available_unit_ids, selected_unit_id)
            args = {"follow_unit_id": follow_target} if follow_target else {}
            return ParsedCommand(target_ids=target_ids, intent="follow", arguments=args, ttl_ticks=16, confidence=0.85, rationale="rule: follow")
        if "exit" in lowered or "goal" in lowered:
            return ParsedCommand(target_ids=target_ids, intent="to_exit", ttl_ticks=20, confidence=0.91, rationale="rule: exit")
        if "key" in lowered or "find" in lowered:
            return ParsedCommand(target_ids=target_ids, intent="find_key", ttl_ticks=20, confidence=0.9, rationale="rule: key search")
        if "east" in lowered or "right" in lowered:
            return ParsedCommand(
                target_ids=target_ids,
                intent="sweep",
                direction="east",
                arguments={"direction": "east"},
                ttl_ticks=18,
                confidence=0.88,
                rationale="rule: east",
            )
        if "west" in lowered or "left" in lowered:
            return ParsedCommand(
                target_ids=target_ids,
                intent="sweep",
                direction="west",
                arguments={"direction": "west"},
                ttl_ticks=18,
                confidence=0.88,
                rationale="rule: west",
            )
        if "north" in lowered or "up" in lowered:
            return ParsedCommand(
                target_ids=target_ids,
                intent="sweep",
                direction="north",
                arguments={"direction": "north"},
                ttl_ticks=18,
                confidence=0.88,
                rationale="rule: north",
            )
        if "south" in lowered or "down" in lowered:
            return ParsedCommand(
                target_ids=target_ids,
                intent="sweep",
                direction="south",
                arguments={"direction": "south"},
                ttl_ticks=18,
                confidence=0.88,
                rationale="rule: south",
            )
        if "avoid" in lowered or "not that way" in lowered or "no not that way" in lowered:
            return ParsedCommand(target_ids=target_ids, intent="avoid", ttl_ticks=10, confidence=0.84, rationale="rule: avoid")
        if "resume" in lowered or "continue" in lowered:
            return ParsedCommand(target_ids=target_ids, intent="resume", ttl_ticks=8, confidence=0.95, rationale="rule: resume")
        return ParsedCommand(target_ids=target_ids, intent="explore", ttl_ticks=18, confidence=0.78, rationale="rule: explore")

    def _resolve_targets(
        self,
        *,
        lowered: str,
        selected_unit_id: str | None,
        available_unit_ids: list[str],
        available_colors: list[str],
    ) -> list[str]:
        if "all" in lowered:
            return available_unit_ids

        for color in available_colors:
            if color in lowered:
                matches = [unit_id for unit_id in available_unit_ids if unit_id.startswith(f"{color}-")]
                if matches:
                    return matches

        for unit_id in available_unit_ids:
            if unit_id in lowered:
                return [unit_id]

        if selected_unit_id and selected_unit_id in available_unit_ids:
            return [selected_unit_id]

        return [available_unit_ids[0]]

    def _resolve_follow_target(
        self,
        lowered: str,
        available_unit_ids: list[str],
        selected_unit_id: str | None,
    ) -> str | None:
        for unit_id in available_unit_ids:
            if unit_id in lowered:
                return unit_id
        return selected_unit_id
