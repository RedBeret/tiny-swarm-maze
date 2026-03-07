from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class Point:
    x: int
    y: int


@dataclass(slots=True)
class CommandState:
    intent: str
    expires_at_tick: int
    direction: Optional[str] = None
    follow_unit_id: Optional[str] = None


@dataclass(slots=True)
class Rumor:
    id: str
    kind: str
    x: int
    y: int
    source_unit_id: str
    expires_at_tick: int


@dataclass(slots=True)
class KeyItem:
    id: str
    x: int
    y: int
    found: bool = False
    delivered: bool = False
    carried_by: Optional[str] = None


@dataclass(slots=True)
class TrapItem:
    id: str
    x: int
    y: int
    revealed: bool = False
    active: bool = True
    stun_ticks: int = 6


@dataclass(slots=True)
class UnitState:
    id: str
    color: str
    role: str
    x: int
    y: int
    vision: int
    hearing: int
    mood: str
    target: Optional[Point] = None
    bubble: Optional[str] = None
    bubble_expires_at_tick: int = 0
    carrying_key_id: Optional[str] = None
    active_command: Optional[CommandState] = None
    discovered: set[str] = field(default_factory=set)
    heard_rumors: list[Rumor] = field(default_factory=list)
    stuck_ticks: int = 0
    stunned_until_tick: int = 0


@dataclass(slots=True)
class EventEntry:
    id: str
    tick: int
    tone: str
    text: str
