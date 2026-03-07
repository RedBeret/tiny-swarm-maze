from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ...schemas import ParsedCommand


@dataclass(slots=True)
class ParseOverrides:
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    backoff_ms: Optional[int] = None
    artificial_delay_ms: int = 0


class CommandParser(Protocol):
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
        ...
