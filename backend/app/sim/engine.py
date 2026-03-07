from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import (
    Difficulty,
    EventPublic,
    GameStateMessage,
    KeyPublicState,
    MetricsPublic,
    ObjectivePublic,
    ParsedCommand,
    PointModel,
    ProfileName,
    TrapPublicState,
    UnitPublicState,
)
from .maze import carve_maze, farthest_reachable_cell, floor_cells, in_bounds, manhattan, neighbors
from .types import CommandState, EventEntry, KeyItem, Point, Rumor, TrapItem, UnitState

RECENT_EVENT_LIMIT = 60


def point_key(x: int, y: int) -> str:
    return f"{x},{y}"


@dataclass(slots=True)
class DifficultyConfig:
    width: int
    height: int
    key_count: int
    trap_count: int
    loop_chance: float
    rumor_ttl: int
    explore_spread: int
    non_scout_vision_penalty: int


DIFFICULTY_PRESETS: dict[Difficulty, DifficultyConfig] = {
    "starter": DifficultyConfig(
        width=29,
        height=19,
        key_count=3,
        trap_count=3,
        loop_chance=0.1,
        rumor_ttl=16,
        explore_spread=2,
        non_scout_vision_penalty=0,
    ),
    "standard": DifficultyConfig(
        width=35,
        height=23,
        key_count=5,
        trap_count=6,
        loop_chance=0.08,
        rumor_ttl=12,
        explore_spread=4,
        non_scout_vision_penalty=1,
    ),
    "dense": DifficultyConfig(
        width=43,
        height=29,
        key_count=7,
        trap_count=10,
        loop_chance=0.06,
        rumor_ttl=9,
        explore_spread=6,
        non_scout_vision_penalty=1,
    ),
}


@dataclass(slots=True)
class EngineState:
    session_id: str
    seed: int
    difficulty: Difficulty
    config: DifficultyConfig
    grid: list[list[int]]
    spawn: Point
    exit_point: Point
    keys: list[KeyItem]
    traps: list[TrapItem]
    units: list[UnitState]
    tick: int = 0
    won: bool = False
    stun_count: int = 0
    reroute_count: int = 0
    commands_applied_count: int = 0
    recent_events: deque[EventEntry] = field(default_factory=lambda: deque(maxlen=RECENT_EVENT_LIMIT))
    applied_command_ids: set[str] = field(default_factory=set)


class GameEngine:
    def __init__(self, session_id: str, seed: int, difficulty: Difficulty = "standard") -> None:
        self._rng = random.Random(seed)
        self._difficulty = difficulty
        cfg = DIFFICULTY_PRESETS[difficulty]
        grid = carve_maze(cfg.width, cfg.height, seed, loop_chance=cfg.loop_chance)
        spawn = Point(1, 1)
        exit_point = farthest_reachable_cell(grid, spawn)
        keys = self._make_keys(grid, seed, spawn, exit_point, cfg.key_count)
        traps = self._make_traps(grid, seed, spawn, exit_point, keys, cfg.trap_count)
        units = self._make_units(spawn, cfg.non_scout_vision_penalty)
        self.state = EngineState(
            session_id=session_id,
            seed=seed,
            difficulty=difficulty,
            config=cfg,
            grid=grid,
            spawn=spawn,
            exit_point=exit_point,
            keys=keys,
            traps=traps,
            units=units,
        )
        self._append_event("system", f"Session {session_id} ready. Seed {seed}. Difficulty {difficulty}.")

    @property
    def width(self) -> int:
        return len(self.state.grid[0])

    @property
    def height(self) -> int:
        return len(self.state.grid)

    def _make_keys(self, grid: list[list[int]], seed: int, spawn: Point, exit_point: Point, count: int) -> list[KeyItem]:
        rng = random.Random(seed + 7)
        width = len(grid[0])
        candidates = [
            cell
            for cell in floor_cells(grid)
            if manhattan(cell, spawn) > max(8, width // 5) and manhattan(cell, exit_point) > max(6, width // 7)
        ]
        rng.shuffle(candidates)

        keys: list[KeyItem] = []
        for cell in candidates:
            if any(manhattan(cell, Point(existing.x, existing.y)) < max(4, width // 9) for existing in keys):
                continue
            keys.append(KeyItem(id=f"key-{len(keys) + 1}", x=cell.x, y=cell.y))
            if len(keys) >= count:
                break

        if len(keys) < count:
            for cell in candidates:
                if len(keys) >= count:
                    break
                if any(existing.x == cell.x and existing.y == cell.y for existing in keys):
                    continue
                keys.append(KeyItem(id=f"key-{len(keys) + 1}", x=cell.x, y=cell.y))

        return keys

    def _make_traps(
        self,
        grid: list[list[int]],
        seed: int,
        spawn: Point,
        exit_point: Point,
        keys: list[KeyItem],
        count: int,
    ) -> list[TrapItem]:
        rng = random.Random(seed + 31)
        key_positions = {(key.x, key.y) for key in keys}
        candidates: list[Point] = []
        for cell in floor_cells(grid):
            if (cell.x, cell.y) in key_positions:
                continue
            if manhattan(cell, spawn) <= 5:
                continue
            if manhattan(cell, exit_point) <= 2:
                continue
            open_neighbors = [n for n in neighbors(cell) if in_bounds(grid, n) and grid[n.y][n.x] == 0]
            if len(open_neighbors) >= 2:
                candidates.append(cell)

        rng.shuffle(candidates)
        traps: list[TrapItem] = []
        for cell in candidates:
            if any(manhattan(cell, Point(t.x, t.y)) <= 2 for t in traps):
                continue
            traps.append(TrapItem(id=f"trap-{len(traps) + 1}", x=cell.x, y=cell.y, stun_ticks=6))
            if len(traps) >= count:
                break
        return traps

    def _make_units(self, spawn: Point, non_scout_vision_penalty: int) -> list[UnitState]:
        specs = [
            ("blue-1", "blue", "Scout", 5, 5, "curious"),
            ("red-2", "red", "Runner", 4, 5, "busy"),
            ("yellow-3", "yellow", "Mapper", 4, 5, "methodical"),
            ("green-4", "green", "Anchor", 4, 4, "steady"),
            ("purple-5", "purple", "Rescuer", 4, 5, "helpful"),
            ("cyan-6", "cyan", "Caller", 4, 7, "loud"),
        ]
        units: list[UnitState] = []
        for idx, (unit_id, color, role, vision, hearing, mood) in enumerate(specs):
            if role != "Scout":
                vision = max(2, vision - non_scout_vision_penalty)
            units.append(
                UnitState(
                    id=unit_id,
                    color=color,
                    role=role,
                    x=spawn.x + (idx % 2),
                    y=spawn.y + (idx // 2),
                    vision=vision,
                    hearing=hearing,
                    mood=mood,
                )
            )
        return units

    def apply_command(self, command: ParsedCommand, client_command_id: str) -> bool:
        if client_command_id in self.state.applied_command_ids:
            return False
        self.state.applied_command_ids.add(client_command_id)
        expires_at = self.state.tick + command.ttl_ticks

        for unit in self.state.units:
            if unit.id not in command.target_ids:
                continue
            follow_unit_id = None
            if command.intent == "follow":
                candidate = command.arguments.get("follow_unit_id")
                if isinstance(candidate, str) and candidate != unit.id and self._unit_by_id(candidate):
                    follow_unit_id = candidate
            unit.active_command = CommandState(
                intent=command.intent,
                expires_at_tick=expires_at,
                direction=command.direction,
                follow_unit_id=follow_unit_id,
            )
            unit.target = self._target_for_command(unit, command)
            self._issue_bubble(unit, self._bubble_for_intent(command.intent, command.direction))

        self.state.commands_applied_count += 1
        target_label = ", ".join(command.target_ids)
        self._append_event("command", f"{command.intent} -> {target_label}")
        return True

    def _bubble_for_intent(self, intent: str, direction: Optional[str]) -> str:
        if intent == "halt":
            return "Holding!"
        if intent == "regroup":
            return "Regrouping!"
        if intent == "find_key":
            return "Searching!"
        if intent == "to_exit":
            return "Exit route!"
        if intent == "sweep":
            return f"Sweep {direction or 'out'}!"
        if intent == "avoid":
            return "Rerouting!"
        if intent == "resume":
            return "Resuming!"
        if intent == "guard":
            return "Guarding!"
        if intent == "follow":
            return "On your six!"
        return "Exploring!"

    def _target_for_command(self, unit: UnitState, command: ParsedCommand) -> Optional[Point]:
        if command.intent == "halt":
            return Point(unit.x, unit.y)
        if command.intent == "regroup":
            return Point(self.state.spawn.x, self.state.spawn.y)
        if command.intent == "to_exit":
            return Point(self.state.exit_point.x, self.state.exit_point.y)
        if command.intent == "guard":
            return Point(unit.x, unit.y)
        if command.intent == "follow":
            follow_unit_id = command.arguments.get("follow_unit_id")
            if isinstance(follow_unit_id, str):
                leader = self._unit_by_id(follow_unit_id)
                if leader:
                    return Point(leader.x, leader.y)
            return unit.target
        if command.intent == "find_key":
            key = self._nearest_open_key(unit)
            if key is not None:
                return Point(key.x, key.y)
            return self._choose_explore_target(unit)
        if command.intent == "sweep":
            direction = command.direction
            if direction is None:
                arg_direction = command.arguments.get("direction")
                direction = arg_direction if isinstance(arg_direction, str) else "east"
            offsets = {"east": (6, 0), "west": (-6, 0), "north": (0, -6), "south": (0, 6)}
            dx, dy = offsets.get(direction, (0, 0))
            return self._clamp_floor(Point(unit.x + dx, unit.y + dy))
        if command.intent in {"avoid", "resume", "explore"}:
            return self._choose_explore_target(unit)
        return None

    def _clamp_floor(self, point: Point) -> Point:
        x = max(1, min(self.width - 2, point.x))
        y = max(1, min(self.height - 2, point.y))
        if self.state.grid[y][x] == 0:
            return Point(x, y)
        return self._nearest_floor(Point(x, y))

    def _nearest_floor(self, start: Point) -> Point:
        queue = deque([start])
        seen = {(start.x, start.y)}
        while queue:
            cur = queue.popleft()
            if in_bounds(self.state.grid, cur) and self.state.grid[cur.y][cur.x] == 0:
                return cur
            for nxt in neighbors(cur):
                if not in_bounds(self.state.grid, nxt):
                    continue
                key = (nxt.x, nxt.y)
                if key in seen:
                    continue
                seen.add(key)
                queue.append(nxt)
        return Point(self.state.spawn.x, self.state.spawn.y)

    def step(self) -> None:
        state = self.state
        if state.won:
            return
        state.tick += 1

        occupied = {point_key(unit.x, unit.y) for unit in state.units}

        for unit in state.units:
            self._discover(unit)
            if unit.bubble and state.tick >= unit.bubble_expires_at_tick:
                unit.bubble = None
            if unit.active_command and state.tick >= unit.active_command.expires_at_tick:
                unit.active_command = None

            if unit.active_command and unit.active_command.intent == "resume":
                unit.active_command = None

            if unit.stunned_until_tick > state.tick:
                if state.tick % 2 == 0:
                    self._issue_bubble(unit, "Stunned!", ttl_ticks=2)
                continue

            visible_key = self._visible_key(unit)
            if visible_key and not visible_key.found:
                visible_key.found = True
                self._issue_bubble(unit, "Key here!")
                self._broadcast_rumor(unit, "key", Point(visible_key.x, visible_key.y))
                self._append_event("speech", f"{unit.id}: Key here!")

            self._reveal_visible_traps(unit)

            if manhattan(Point(unit.x, unit.y), state.exit_point) <= unit.vision and unit.role == "Caller":
                self._issue_bubble(unit, "Exit spotted!")

        for unit in state.units:
            unit.heard_rumors = [r for r in unit.heard_rumors if r.expires_at_tick > state.tick]

        for unit in state.units:
            if unit.stunned_until_tick > state.tick:
                continue
            if unit.active_command and unit.active_command.intent == "halt":
                continue

            if unit.active_command and unit.active_command.intent == "follow" and unit.active_command.follow_unit_id:
                leader = self._unit_by_id(unit.active_command.follow_unit_id)
                if leader:
                    unit.target = Point(leader.x, leader.y)

            if unit.target is None or (unit.x == unit.target.x and unit.y == unit.target.y):
                unit.target = self._default_target(unit)

            occupied.remove(point_key(unit.x, unit.y))
            nxt = self._next_step(unit, unit.target, occupied)
            if nxt is None:
                unit.stuck_ticks += 1
                if unit.stuck_ticks >= 4:
                    unit.target = self._choose_explore_target(unit)
                    self._issue_bubble(unit, "Stuck...")
                    state.reroute_count += 1
                    unit.stuck_ticks = 0
                occupied.add(point_key(unit.x, unit.y))
                continue

            unit.stuck_ticks = 0
            unit.x = nxt.x
            unit.y = nxt.y
            occupied.add(point_key(unit.x, unit.y))

            trap = self._active_trap_at(unit.x, unit.y)
            if trap is not None:
                trap.revealed = True
                trap.active = False
                unit.stunned_until_tick = state.tick + trap.stun_ticks
                unit.target = None
                state.stun_count += 1
                self._issue_bubble(unit, "Trap!")
                self._append_event("warning", f"{unit.id} triggered {trap.id} and is stunned.")
                self._broadcast_rumor(unit, "trap", Point(trap.x, trap.y))

            key = self._key_at(unit.x, unit.y)
            if key and not key.delivered and key.carried_by is None:
                key.carried_by = unit.id
                key.found = True
                unit.carrying_key_id = key.id
                unit.target = Point(state.exit_point.x, state.exit_point.y)
                self._issue_bubble(unit, "Got it!")
                self._append_event("info", f"{unit.id} picked up {key.id}.")

            if unit.carrying_key_id and unit.x == state.exit_point.x and unit.y == state.exit_point.y:
                carried = self._key_by_id(unit.carrying_key_id)
                if carried:
                    carried.delivered = True
                    carried.carried_by = None
                self._append_event("success", f"{unit.id} delivered {unit.carrying_key_id}.")
                unit.carrying_key_id = None
                self._issue_bubble(unit, "Delivered!")
                unit.target = None

        for key in state.keys:
            if key.carried_by:
                carrier = self._unit_by_id(key.carried_by)
                if carrier:
                    key.x = carrier.x
                    key.y = carrier.y

        if all(key.delivered for key in state.keys):
            state.won = True
            self._append_event("success", "All keys delivered. Maze clear.")
            for unit in state.units:
                self._issue_bubble(unit, "Maze clear!")

    def _discover(self, unit: UnitState) -> None:
        for dy in range(-unit.vision, unit.vision + 1):
            for dx in range(-unit.vision, unit.vision + 1):
                x = unit.x + dx
                y = unit.y + dy
                if not (0 <= x < self.width and 0 <= y < self.height):
                    continue
                if abs(dx) + abs(dy) <= unit.vision:
                    unit.discovered.add(point_key(x, y))

    def _visible_key(self, unit: UnitState) -> Optional[KeyItem]:
        for key in self.state.keys:
            if key.delivered:
                continue
            if manhattan(Point(unit.x, unit.y), Point(key.x, key.y)) <= unit.vision:
                return key
        return None

    def _reveal_visible_traps(self, unit: UnitState) -> None:
        for trap in self.state.traps:
            if trap.revealed:
                continue
            if manhattan(Point(unit.x, unit.y), Point(trap.x, trap.y)) <= unit.vision:
                trap.revealed = True
                self._append_event("info", f"{unit.id} spotted {trap.id}.")
                if unit.role in {"Caller", "Mapper"}:
                    self._broadcast_rumor(unit, "trap", Point(trap.x, trap.y))

    def _broadcast_rumor(self, source: UnitState, kind: str, point: Point) -> None:
        rumor = Rumor(
            id=f"{self.state.tick}-{source.id}-{kind}",
            kind=kind,
            x=point.x,
            y=point.y,
            source_unit_id=source.id,
            expires_at_tick=self.state.tick + self.state.config.rumor_ttl,
        )
        for unit in self.state.units:
            distance = manhattan(Point(source.x, source.y), Point(unit.x, unit.y))
            if distance <= unit.hearing:
                unit.heard_rumors = [r for r in unit.heard_rumors if r.id != rumor.id]
                unit.heard_rumors.append(rumor)

    def _default_target(self, unit: UnitState) -> Optional[Point]:
        if unit.carrying_key_id:
            return Point(self.state.exit_point.x, self.state.exit_point.y)

        if unit.active_command:
            target = self._target_for_command(
                unit,
                ParsedCommand(
                    target_ids=[unit.id],
                    intent=unit.active_command.intent,  # type: ignore[arg-type]
                    direction=unit.active_command.direction,  # type: ignore[arg-type]
                    arguments={
                        "follow_unit_id": unit.active_command.follow_unit_id,
                        "direction": unit.active_command.direction,
                    },
                    ttl_ticks=max(1, unit.active_command.expires_at_tick - self.state.tick),
                    confidence=0.9,
                ),
            )
            if target is not None:
                return target

        if unit.role == "Rescuer":
            ally = self._nearest_stunned_ally(unit)
            if ally:
                return Point(ally.x, ally.y)

        rumor = self._best_rumor_for(unit)
        if rumor and unit.role != "Anchor":
            if rumor.kind == "trap" and unit.role in {"Mapper", "Caller"}:
                return self._safe_adjacent(Point(rumor.x, rumor.y))
            return Point(rumor.x, rumor.y)

        if unit.role == "Anchor":
            return self._anchor_target()

        if unit.role == "Runner":
            key = self._nearest_open_key(unit, require_found=True)
            if key:
                return Point(key.x, key.y)

        return self._choose_explore_target(unit)

    def _nearest_stunned_ally(self, unit: UnitState) -> Optional[UnitState]:
        stunned = [
            ally
            for ally in self.state.units
            if ally.id != unit.id and ally.stunned_until_tick > self.state.tick
        ]
        if not stunned:
            return None
        return min(stunned, key=lambda ally: manhattan(Point(unit.x, unit.y), Point(ally.x, ally.y)))

    def _anchor_target(self) -> Point:
        target = Point(self.state.spawn.x + 2, self.state.spawn.y + 2)
        return self._clamp_floor(target)

    def _safe_adjacent(self, point: Point) -> Point:
        for nxt in neighbors(point):
            if not in_bounds(self.state.grid, nxt):
                continue
            if self.state.grid[nxt.y][nxt.x] == 1:
                continue
            if self._active_trap_at(nxt.x, nxt.y) is not None:
                continue
            return nxt
        return point

    def _choose_explore_target(self, unit: UnitState) -> Point:
        frontier: list[Point] = []
        discovered = self._global_discovered()

        for y in range(1, self.height - 1):
            for x in range(1, self.width - 1):
                if self.state.grid[y][x] == 1:
                    continue
                if point_key(x, y) not in discovered:
                    continue
                has_unknown_neighbor = False
                for nxt in neighbors(Point(x, y)):
                    if not in_bounds(self.state.grid, nxt):
                        continue
                    if self.state.grid[nxt.y][nxt.x] == 1:
                        continue
                    if point_key(nxt.x, nxt.y) not in discovered:
                        has_unknown_neighbor = True
                        break
                if has_unknown_neighbor:
                    frontier.append(Point(x, y))

        if frontier:
            frontier.sort(key=lambda p: manhattan(Point(unit.x, unit.y), p))
            if unit.role == "Scout":
                return frontier[0]
            spread = min(len(frontier), max(1, self.state.config.explore_spread))
            return frontier[self._rng.randint(0, spread - 1)]

        floors = [cell for cell in floor_cells(self.state.grid) if point_key(cell.x, cell.y) in discovered]
        if floors:
            floors.sort(key=lambda p: manhattan(Point(unit.x, unit.y), p))
            idx = min(len(floors) - 1, self._rng.randint(0, min(6, len(floors) - 1)))
            return floors[idx]
        return Point(self.state.spawn.x, self.state.spawn.y)

    def _best_rumor_for(self, unit: UnitState) -> Optional[Rumor]:
        if not unit.heard_rumors:
            return None
        weighted = sorted(
            unit.heard_rumors,
            key=lambda r: (
                0 if r.kind == "key" and unit.role == "Runner" else 1,
                manhattan(Point(unit.x, unit.y), Point(r.x, r.y)),
            ),
        )
        return weighted[0]

    def _nearest_open_key(self, unit: UnitState, require_found: bool = False) -> Optional[KeyItem]:
        keys = [
            key
            for key in self.state.keys
            if not key.delivered and key.carried_by is None and (key.found or not require_found)
        ]
        if not keys:
            return None
        return min(keys, key=lambda item: manhattan(Point(unit.x, unit.y), Point(item.x, item.y)))

    def _next_step(self, unit: UnitState, target: Optional[Point], blocked: set[str]) -> Optional[Point]:
        if target is None:
            return None
        if unit.x == target.x and unit.y == target.y:
            return None

        start = Point(unit.x, unit.y)
        queue = deque([start])
        prev: dict[tuple[int, int], Point] = {}
        seen = {(start.x, start.y)}
        found = False

        while queue:
            cur = queue.popleft()
            if cur.x == target.x and cur.y == target.y:
                found = True
                break
            for nxt in neighbors(cur):
                if not in_bounds(self.state.grid, nxt):
                    continue
                if self.state.grid[nxt.y][nxt.x] == 1:
                    continue
                key = point_key(nxt.x, nxt.y)
                if key in blocked and not (nxt.x == target.x and nxt.y == target.y):
                    continue
                if self._active_trap_at(nxt.x, nxt.y) is not None and unit.role == "Runner":
                    continue
                if (nxt.x, nxt.y) in seen:
                    continue
                seen.add((nxt.x, nxt.y))
                prev[(nxt.x, nxt.y)] = cur
                queue.append(nxt)

        if not found:
            return None

        cur = target
        parent = prev.get((cur.x, cur.y))
        while parent and not (parent.x == start.x and parent.y == start.y):
            cur = parent
            parent = prev.get((cur.x, cur.y))
        return cur

    def _global_discovered(self) -> set[str]:
        discovered: set[str] = set()
        for unit in self.state.units:
            discovered.update(unit.discovered)
        return discovered

    def _append_event(self, tone: str, text: str) -> None:
        event = EventEntry(
            id=f"{self.state.tick}-{len(self.state.recent_events)}-{abs(hash(text)) % 10000}",
            tick=self.state.tick,
            tone=tone,
            text=text,
        )
        self.state.recent_events.appendleft(event)

    def _issue_bubble(self, unit: UnitState, text: str, ttl_ticks: int = 8) -> None:
        unit.bubble = text
        unit.bubble_expires_at_tick = self.state.tick + ttl_ticks

    def _unit_by_id(self, unit_id: str) -> Optional[UnitState]:
        return next((unit for unit in self.state.units if unit.id == unit_id), None)

    def _key_at(self, x: int, y: int) -> Optional[KeyItem]:
        return next(
            (
                key
                for key in self.state.keys
                if key.x == x and key.y == y and not key.delivered and key.carried_by is None
            ),
            None,
        )

    def _active_trap_at(self, x: int, y: int) -> Optional[TrapItem]:
        return next((trap for trap in self.state.traps if trap.x == x and trap.y == y and trap.active), None)

    def _key_by_id(self, key_id: str) -> Optional[KeyItem]:
        return next((key for key in self.state.keys if key.id == key_id), None)

    def snapshot(
        self,
        *,
        selected_unit_id: Optional[str] = None,
        profile: ProfileName = "rules",
        paused: bool = False,
        queue_depth: int = 0,
        commands_queued: int = 0,
        parser_latency_last_ms: int = 0,
        parser_latency_avg_ms: int = 0,
        planner_latency_last_ms: int = 0,
        planner_latency_avg_ms: int = 0,
        timeout_count: int = 0,
        model_error_count: int = 0,
    ) -> GameStateMessage:
        discovered = sorted(self._global_discovered())
        events = [
            EventPublic(id=e.id, tick=e.tick, tone=e.tone, text=e.text)
            for e in list(self.state.recent_events)
        ]
        keys = [
            KeyPublicState(
                id=key.id,
                x=key.x,
                y=key.y,
                found=key.found,
                delivered=key.delivered,
                carried_by=key.carried_by,
            )
            for key in self.state.keys
        ]
        traps = [
            TrapPublicState(id=trap.id, x=trap.x, y=trap.y, revealed=trap.revealed, active=trap.active)
            for trap in self.state.traps
        ]
        units = [
            UnitPublicState(
                id=unit.id,
                color=unit.color,
                role=unit.role,
                x=unit.x,
                y=unit.y,
                vision=unit.vision,
                hearing=unit.hearing,
                mood=unit.mood,
                target=PointModel(x=unit.target.x, y=unit.target.y) if unit.target else None,
                bubble=unit.bubble,
                carrying_key_id=unit.carrying_key_id,
                active_command=unit.active_command.intent if unit.active_command else None,
                stunned_until_tick=unit.stunned_until_tick,
            )
            for unit in self.state.units
        ]
        objectives = ObjectivePublic(
            delivered_keys=sum(1 for key in self.state.keys if key.delivered),
            total_keys=len(self.state.keys),
            maze_clear=self.state.won,
        )
        fog_percent = int(round((len(discovered) / max(1, self.width * self.height)) * 100))
        metrics = MetricsPublic(
            fog_percent=fog_percent,
            stuns=self.state.stun_count,
            reroutes=self.state.reroute_count,
            commands_queued=commands_queued,
            commands_applied=self.state.commands_applied_count,
            parser_latency_last_ms=parser_latency_last_ms,
            parser_latency_avg_ms=parser_latency_avg_ms,
            planner_latency_last_ms=planner_latency_last_ms,
            planner_latency_avg_ms=planner_latency_avg_ms,
            timeout_count=timeout_count,
            model_error_count=model_error_count,
        )
        return GameStateMessage(
            session_id=self.state.session_id,
            seed=self.state.seed,
            tick=self.state.tick,
            width=self.width,
            height=self.height,
            difficulty=self.state.difficulty,
            profile=profile,
            paused=paused,
            queue_depth=queue_depth,
            grid=self.state.grid,
            discovered_tiles=discovered,
            exit=PointModel(x=self.state.exit_point.x, y=self.state.exit_point.y),
            units=units,
            keys=keys,
            traps=traps,
            objectives=objectives,
            metrics=metrics,
            events=events,
            selected_unit_id=selected_unit_id,
        )
