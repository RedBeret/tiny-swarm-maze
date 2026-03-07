import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { motion } from "framer-motion";
import { Play, Pause, RotateCcw, Send, Eye, Volume2, Flag, Bot } from "lucide-react";

const TILE = 24;
const GRID_W = 26;
const GRID_H = 16;
const TICK_MS = 260;
const COLORS = {
  blue: { body: "#4f8cff", accent: "#d9ecff", badge: "bg-blue-500/20 text-blue-200 border-blue-400/30" },
  red: { body: "#ff6b6b", accent: "#ffe1e1", badge: "bg-red-500/20 text-red-200 border-red-400/30" },
  yellow: { body: "#ffd166", accent: "#fff1bf", badge: "bg-yellow-500/20 text-yellow-200 border-yellow-400/30" },
  green: { body: "#5dd39e", accent: "#daf7eb", badge: "bg-emerald-500/20 text-emerald-200 border-emerald-400/30" },
  purple: { body: "#b197fc", accent: "#efe7ff", badge: "bg-violet-500/20 text-violet-200 border-violet-400/30" },
  cyan: { body: "#66d9ef", accent: "#dff9ff", badge: "bg-cyan-500/20 text-cyan-200 border-cyan-400/30" },
};

const ROLE_STYLES = {
  Scout: "bg-sky-500/20 text-sky-200 border-sky-400/30",
  Runner: "bg-orange-500/20 text-orange-200 border-orange-400/30",
  Mapper: "bg-fuchsia-500/20 text-fuchsia-200 border-fuchsia-400/30",
  Anchor: "bg-lime-500/20 text-lime-200 border-lime-400/30",
  Rescuer: "bg-rose-500/20 text-rose-200 border-rose-400/30",
  Caller: "bg-teal-500/20 text-teal-200 border-teal-400/30",
};

function makeRng(seed = 1337) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function keyOf(x, y) {
  return `${x},${y}`;
}

function manhattan(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function neighbors(x, y) {
  return [
    { x: x + 1, y },
    { x: x - 1, y },
    { x, y: y + 1 },
    { x, y: y - 1 },
  ];
}

function carveMaze(width, height, seed = 1337) {
  const rng = makeRng(seed);
  const grid = Array.from({ length: height }, () => Array.from({ length: width }, () => 1));

  const start = { x: 1, y: 1 };
  grid[start.y][start.x] = 0;
  const stack = [start];

  while (stack.length) {
    const current = stack[stack.length - 1];
    const dirs = [
      { x: 2, y: 0 },
      { x: -2, y: 0 },
      { x: 0, y: 2 },
      { x: 0, y: -2 },
    ].sort(() => rng() - 0.5);

    const next = dirs
      .map((d) => ({ x: current.x + d.x, y: current.y + d.y, midX: current.x + d.x / 2, midY: current.y + d.y / 2 }))
      .find((p) => p.x > 0 && p.x < width - 1 && p.y > 0 && p.y < height - 1 && grid[p.y][p.x] === 1);

    if (!next) {
      stack.pop();
      continue;
    }

    grid[next.midY][next.midX] = 0;
    grid[next.y][next.x] = 0;
    stack.push({ x: next.x, y: next.y });
  }

  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      if (grid[y][x] === 1 && rng() < 0.08) grid[y][x] = 0;
    }
  }

  return grid;
}

function findFloorCells(grid) {
  const cells = [];
  for (let y = 1; y < grid.length - 1; y++) {
    for (let x = 1; x < grid[0].length - 1; x++) {
      if (grid[y][x] === 0) cells.push({ x, y });
    }
  }
  return cells;
}

function pickFarCell(cells, from) {
  let best = cells[0];
  let bestDist = -1;
  for (const cell of cells) {
    const d = manhattan(cell, from);
    if (d > bestDist) {
      bestDist = d;
      best = cell;
    }
  }
  return best;
}

function shortestStep(grid, from, target, blocked = new Set()) {
  if (!target) return null;
  if (from.x === target.x && from.y === target.y) return null;
  const q = [from];
  const prev = new Map();
  const seen = new Set([keyOf(from.x, from.y)]);
  let found = false;

  while (q.length) {
    const cur = q.shift();
    if (cur.x === target.x && cur.y === target.y) {
      found = true;
      break;
    }
    for (const n of neighbors(cur.x, cur.y)) {
      const k = keyOf(n.x, n.y);
      if (n.x < 0 || n.x >= grid[0].length || n.y < 0 || n.y >= grid.length) continue;
      if (grid[n.y][n.x] === 1) continue;
      if (blocked.has(k) && !(n.x === target.x && n.y === target.y)) continue;
      if (seen.has(k)) continue;
      seen.add(k);
      prev.set(k, cur);
      q.push(n);
    }
  }

  if (!found) return null;
  let cur = target;
  let parent = prev.get(keyOf(cur.x, cur.y));
  while (parent && !(parent.x === from.x && parent.y === from.y)) {
    cur = parent;
    parent = prev.get(keyOf(cur.x, cur.y));
  }
  return cur;
}

function buildGame(seed = 1337) {
  const grid = carveMaze(GRID_W, GRID_H, seed);
  const floors = findFloorCells(grid);
  const spawn = { x: 1, y: 1 };
  const exit = pickFarCell(floors, spawn);
  const keyCandidates = floors.filter((c) => manhattan(c, spawn) > 8 && manhattan(c, exit) > 5);
  const keys = [keyCandidates[3], keyCandidates[Math.floor(keyCandidates.length / 2)], keyCandidates[keyCandidates.length - 5]]
    .filter(Boolean)
    .map((c, idx) => ({ id: `key-${idx + 1}`, x: c.x, y: c.y, found: false, carriedBy: null, delivered: false }));

  const roles = ["Scout", "Runner", "Mapper", "Anchor", "Rescuer", "Caller"];
  const palette = ["blue", "red", "yellow", "green", "purple", "cyan"];
  const units = palette.map((color, idx) => ({
    id: `${color}-${idx + 1}`,
    color,
    role: roles[idx],
    x: spawn.x + (idx % 2),
    y: spawn.y + Math.floor(idx / 2),
    vision: roles[idx] === "Scout" ? 5 : 4,
    hearing: roles[idx] === "Caller" ? 7 : 5,
    target: null,
    bubble: null,
    bubbleTicks: 0,
    command: null,
    commandTicks: 0,
    carryingKeyId: null,
    lastHeard: null,
    stuckTicks: 0,
    mood: roles[idx] === "Scout" ? "curious" : roles[idx] === "Anchor" ? "steady" : "busy",
  }));

  return {
    seed,
    grid,
    spawn,
    exit,
    keys,
    units,
    discovered: new Set([keyOf(spawn.x, spawn.y)]),
    heardRumors: [],
    tick: 0,
    won: false,
  };
}

function discoverAround(game, unit) {
  for (let dy = -unit.vision; dy <= unit.vision; dy++) {
    for (let dx = -unit.vision; dx <= unit.vision; dx++) {
      const x = unit.x + dx;
      const y = unit.y + dy;
      if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) continue;
      if (Math.abs(dx) + Math.abs(dy) <= unit.vision) game.discovered.add(keyOf(x, y));
    }
  }
}

function addEvent(events, text, tone = "system") {
  events.unshift({ id: `${Date.now()}-${Math.random()}`, text, tone });
  return events.slice(0, 40);
}

function issueBubble(unit, text) {
  unit.bubble = text;
  unit.bubbleTicks = 8;
}

function parseCommand(raw, selectedUnitId, units) {
  const text = raw.trim().toLowerCase();
  const byColor = Object.keys(COLORS).find((c) => text.includes(c));
  const selected = units.find((u) => u.id === selectedUnitId);
  const targetIds = byColor
    ? units.filter((u) => u.color === byColor).map((u) => u.id)
    : text.includes("all")
      ? units.map((u) => u.id)
      : selected
        ? [selected.id]
        : [units[0].id];

  if (text.includes("stop") || text.includes("halt") || text.includes("wait") || text.includes("don't do that") || text.includes("dont do that")) {
    return { targetIds, intent: "halt", ttl: 12, debug: "parsed halt" };
  }
  if (text.includes("regroup") || text.includes("come back") || text.includes("return")) {
    return { targetIds, intent: "regroup", ttl: 18, debug: "parsed regroup" };
  }
  if (text.includes("exit") || text.includes("goal")) {
    return { targetIds, intent: "to_exit", ttl: 20, debug: "parsed exit path" };
  }
  if (text.includes("key") || text.includes("find")) {
    return { targetIds, intent: "find_key", ttl: 20, debug: "parsed key search" };
  }
  if (text.includes("east") || text.includes("right")) {
    return { targetIds, intent: "sweep", dir: "east", ttl: 18, debug: "parsed east sweep" };
  }
  if (text.includes("west") || text.includes("left")) {
    return { targetIds, intent: "sweep", dir: "west", ttl: 18, debug: "parsed west sweep" };
  }
  if (text.includes("north") || text.includes("up")) {
    return { targetIds, intent: "sweep", dir: "north", ttl: 18, debug: "parsed north sweep" };
  }
  if (text.includes("south") || text.includes("down")) {
    return { targetIds, intent: "sweep", dir: "south", ttl: 18, debug: "parsed south sweep" };
  }
  if (text.includes("not that way") || text.includes("no, not that way") || text.includes("avoid")) {
    return { targetIds, intent: "jitter", ttl: 8, debug: "parsed avoid/jitter" };
  }
  return { targetIds, intent: "explore", ttl: 18, debug: "default explore" };
}

function chooseExploreTarget(game, unit) {
  const discoveredUnknownEdges = [];
  for (let y = 1; y < GRID_H - 1; y++) {
    for (let x = 1; x < GRID_W - 1; x++) {
      if (game.grid[y][x] === 1) continue;
      const here = keyOf(x, y);
      if (!game.discovered.has(here)) continue;
      const hasUnknownNeighbor = neighbors(x, y).some((n) => n.x >= 0 && n.x < GRID_W && n.y >= 0 && n.y < GRID_H && !game.discovered.has(keyOf(n.x, n.y)) && game.grid[n.y][n.x] === 0);
      if (hasUnknownNeighbor) discoveredUnknownEdges.push({ x, y });
    }
  }
  if (discoveredUnknownEdges.length) {
    discoveredUnknownEdges.sort((a, b) => manhattan(unit, a) - manhattan(unit, b));
    return discoveredUnknownEdges[0];
  }

  const floors = findFloorCells(game.grid).filter((c) => game.discovered.has(keyOf(c.x, c.y)));
  floors.sort((a, b) => manhattan(unit, a) - manhattan(unit, b));
  return floors[Math.min(floors.length - 1, 4)] || game.spawn;
}

function applyIntent(game, unit, intent) {
  switch (intent.intent) {
    case "halt":
      unit.command = { kind: "halt" };
      unit.commandTicks = intent.ttl;
      unit.target = { x: unit.x, y: unit.y };
      issueBubble(unit, "Holding!");
      return;
    case "regroup":
      unit.command = { kind: "regroup" };
      unit.commandTicks = intent.ttl;
      unit.target = { ...game.spawn };
      issueBubble(unit, "Regrouping!");
      return;
    case "to_exit":
      unit.command = { kind: "to_exit" };
      unit.commandTicks = intent.ttl;
      unit.target = { ...game.exit };
      issueBubble(unit, "Exit route!");
      return;
    case "find_key": {
      unit.command = { kind: "find_key" };
      unit.commandTicks = intent.ttl;
      const unseenKey = game.keys.find((k) => !k.delivered && !k.carriedBy && (!k.found || manhattan(unit, k) < 10));
      unit.target = unseenKey ? { x: unseenKey.x, y: unseenKey.y } : chooseExploreTarget(game, unit);
      issueBubble(unit, "Searching!");
      return;
    }
    case "sweep": {
      unit.command = { kind: "sweep", dir: intent.dir };
      unit.commandTicks = intent.ttl;
      const dirOffsets = { east: [5, 0], west: [-5, 0], north: [0, -5], south: [0, 5] };
      const [dx, dy] = dirOffsets[intent.dir] || [0, 0];
      const tx = Math.max(1, Math.min(GRID_W - 2, unit.x + dx));
      const ty = Math.max(1, Math.min(GRID_H - 2, unit.y + dy));
      unit.target = { x: tx, y: ty };
      issueBubble(unit, `Sweep ${intent.dir}!`);
      return;
    }
    case "jitter":
      unit.command = { kind: "jitter" };
      unit.commandTicks = intent.ttl;
      unit.target = chooseExploreTarget(game, unit);
      issueBubble(unit, "Rerouting!");
      return;
    default:
      unit.command = { kind: "explore" };
      unit.commandTicks = intent.ttl;
      unit.target = chooseExploreTarget(game, unit);
      issueBubble(unit, "Exploring!");
  }
}

function stepGame(prevGame) {
  const game = {
    ...prevGame,
    discovered: new Set(prevGame.discovered),
    keys: prevGame.keys.map((k) => ({ ...k })),
    units: prevGame.units.map((u) => ({ ...u, target: u.target ? { ...u.target } : null, command: u.command ? { ...u.command } : null })),
    heardRumors: [...prevGame.heardRumors],
    tick: prevGame.tick + 1,
  };

  if (game.won) return game;

  const occupied = new Set(game.units.map((u) => keyOf(u.x, u.y)));

  for (const unit of game.units) discoverAround(game, unit);

  for (const unit of game.units) {
    if (unit.bubbleTicks > 0) unit.bubbleTicks -= 1;
    else unit.bubble = null;

    if (unit.commandTicks > 0) unit.commandTicks -= 1;
    else unit.command = null;

    const visibleKey = game.keys.find((k) => !k.delivered && !k.carriedBy && manhattan(unit, k) <= unit.vision);
    if (visibleKey && !visibleKey.found) {
      visibleKey.found = true;
      issueBubble(unit, "Key here!");
      game.heardRumors.unshift({ id: `${game.tick}-${unit.id}`, source: unit.id, kind: "key", x: visibleKey.x, y: visibleKey.y, ttl: 10 });
    }

    const visibleExit = manhattan(unit, game.exit) <= unit.vision;
    if (visibleExit && unit.role === "Caller") issueBubble(unit, "Exit spotted!");
  }

  game.heardRumors = game.heardRumors
    .map((r) => ({ ...r, ttl: r.ttl - 1 }))
    .filter((r) => r.ttl > 0);

  for (const unit of game.units) {
    if (!unit.target || (unit.x === unit.target.x && unit.y === unit.target.y)) {
      if (unit.carryingKeyId) {
        unit.target = { ...game.exit };
      } else {
        const rumor = game.heardRumors.find((r) => manhattan(unit, r) <= unit.hearing + 2);
        if (rumor && unit.role !== "Anchor") {
          unit.target = { x: rumor.x, y: rumor.y };
          unit.lastHeard = rumor.id;
        } else if (unit.role === "Anchor") {
          unit.target = { x: 3, y: 3 };
        } else if (unit.role === "Runner") {
          const foundKey = game.keys.find((k) => k.found && !k.delivered && !k.carriedBy);
          unit.target = foundKey ? { x: foundKey.x, y: foundKey.y } : chooseExploreTarget(game, unit);
        } else {
          unit.target = chooseExploreTarget(game, unit);
        }
      }
    }
  }

  for (const unit of game.units) {
    if (unit.command?.kind === "halt") continue;

    occupied.delete(keyOf(unit.x, unit.y));
    const next = shortestStep(game.grid, unit, unit.target, occupied);

    if (!next) {
      unit.stuckTicks += 1;
      if (unit.stuckTicks >= 4) {
        unit.target = chooseExploreTarget(game, unit);
        issueBubble(unit, "Stuck...");
        unit.stuckTicks = 0;
      }
      occupied.add(keyOf(unit.x, unit.y));
      continue;
    }

    unit.stuckTicks = 0;
    unit.x = next.x;
    unit.y = next.y;
    occupied.add(keyOf(unit.x, unit.y));

    for (const key of game.keys) {
      if (!key.delivered && !key.carriedBy && key.x === unit.x && key.y === unit.y) {
        key.carriedBy = unit.id;
        key.found = true;
        unit.carryingKeyId = key.id;
        unit.target = { ...game.exit };
        issueBubble(unit, "Got it!");
      }
    }

    if (unit.carryingKeyId && unit.x === game.exit.x && unit.y === game.exit.y) {
      const held = game.keys.find((k) => k.id === unit.carryingKeyId);
      if (held) {
        held.delivered = true;
        held.carriedBy = null;
      }
      unit.carryingKeyId = null;
      issueBubble(unit, "Delivered!");
    }
  }

  for (const key of game.keys) {
    if (key.carriedBy) {
      const carrier = game.units.find((u) => u.id === key.carriedBy);
      if (carrier) {
        key.x = carrier.x;
        key.y = carrier.y;
      }
    }
  }

  game.won = game.keys.every((k) => k.delivered);
  if (game.won) {
    for (const unit of game.units) issueBubble(unit, "Maze clear!");
  }

  return game;
}

function PixelUnit({ unit, selected }) {
  const c = COLORS[unit.color];
  return (
    <motion.div
      animate={{ y: [0, -1, 0] }}
      transition={{ repeat: Infinity, duration: 0.6, ease: "easeInOut" }}
      className="absolute z-20"
      style={{ left: unit.x * TILE + 2, top: unit.y * TILE + 1, width: TILE - 4, height: TILE - 4 }}
    >
      {selected && <div className="absolute -inset-1 rounded-sm border-2 border-white/80 shadow-[0_0_0_2px_rgba(96,165,250,0.7)]" />}
      {unit.bubble && (
        <div className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-white/10 bg-slate-950/90 px-2 py-1 text-[10px] text-slate-100 shadow-lg">
          {unit.bubble}
        </div>
      )}
      <div className="relative h-full w-full rounded-[2px] border border-black/30" style={{ background: c.body, imageRendering: "pixelated" }}>
        <div className="absolute left-[5px] top-[4px] h-[4px] w-[4px] bg-slate-950" />
        <div className="absolute right-[5px] top-[4px] h-[4px] w-[4px] bg-slate-950" />
        <div className="absolute left-[5px] top-[5px] h-[1px] w-[1px]" style={{ background: c.accent }} />
        <div className="absolute right-[5px] top-[5px] h-[1px] w-[1px]" style={{ background: c.accent }} />
        <div className="absolute left-1/2 top-[10px] h-[2px] w-[8px] -translate-x-1/2 bg-slate-950/80" />
        <div className="absolute bottom-[2px] left-[3px] right-[3px] h-[4px] rounded-[1px] bg-black/25" />
      </div>
    </motion.div>
  );
}

function Tile({ kind, discovered }) {
  if (!discovered) {
    return <div className="h-6 w-6 border border-slate-900/70 bg-slate-950" />;
  }
  if (kind === "wall") {
    return (
      <div className="h-6 w-6 border border-slate-900/50 bg-[linear-gradient(135deg,#334155_25%,#1e293b_25%,#1e293b_50%,#334155_50%,#334155_75%,#1e293b_75%,#1e293b_100%)] bg-[length:8px_8px]" />
    );
  }
  return <div className="h-6 w-6 border border-slate-900/20 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.06),transparent_40%),linear-gradient(180deg,#1f2937,#111827)]" />;
}

export default function TinySwarmMazeGUI() {
  const [game, setGame] = useState(() => buildGame(1337));
  const [running, setRunning] = useState(true);
  const [selectedUnitId, setSelectedUnitId] = useState("blue-1");
  const [command, setCommand] = useState("blue stop");
  const [events, setEvents] = useState(() => [
    { id: "e1", text: "Swarm online. Type commands like 'blue stop', 'all regroup', 'find key', 'go east'.", tone: "system" },
    { id: "e2", text: "Prototype uses local browser sim. Swap parser for Ollama later.", tone: "info" },
  ]);
  const tickRef = useRef(null);

  useEffect(() => {
    if (!running) return;
    tickRef.current = setInterval(() => {
      setGame((prev) => {
        const next = stepGame(prev);
        if (next.won && !prev.won) {
          setEvents((cur) => addEvent(cur, "All keys delivered. Maze complete.", "success"));
        }
        return next;
      });
    }, TICK_MS);
    return () => clearInterval(tickRef.current);
  }, [running]);

  const selectedUnit = useMemo(() => game.units.find((u) => u.id === selectedUnitId) || game.units[0], [game.units, selectedUnitId]);
  const deliveredCount = game.keys.filter((k) => k.delivered).length;
  const discoveredCount = game.discovered.size;
  const mapCount = GRID_W * GRID_H;

  const sendCommand = () => {
    const parsed = parseCommand(command, selectedUnitId, game.units);
    setGame((prev) => {
      const next = {
        ...prev,
        units: prev.units.map((u) => ({ ...u, target: u.target ? { ...u.target } : null, command: u.command ? { ...u.command } : null })),
      };
      next.units.forEach((u) => {
        if (parsed.targetIds.includes(u.id)) applyIntent(next, u, parsed);
      });
      return next;
    });

    setEvents((cur) => addEvent(cur, `Command: ${command} -> ${parsed.debug} on ${parsed.targetIds.join(", ")}`, "command"));
    setCommand("");
  };

  const reset = () => {
    setGame(buildGame(1337 + Math.floor(Math.random() * 1000)));
    setEvents((cur) => addEvent(cur, "Simulation reset with a new maze seed.", "system"));
    setRunning(true);
  };

  return (
    <div className="min-h-screen w-full bg-[radial-gradient(circle_at_top,#0f172a,#020617_70%)] p-4 text-slate-100">
      <div className="mx-auto grid max-w-7xl gap-4 lg:grid-cols-[1.65fr_0.95fr]">
        <Card className="overflow-hidden border-white/10 bg-slate-900/70 shadow-2xl backdrop-blur">
          <CardHeader className="border-b border-white/10 bg-slate-950/50 pb-3">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-2xl text-slate-50">
                  <Bot className="h-6 w-6 text-cyan-300" /> Tiny Swarm Maze
                </CardTitle>
                <div className="mt-1 text-sm text-slate-400">Retro swarm puzzle GUI prototype. Phaser-style layout built as a React handoff screen.</div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-cyan-400/30 bg-cyan-500/10 text-cyan-200">Tick {game.tick}</Badge>
                <Badge variant="outline" className="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">Keys {deliveredCount}/3</Badge>
                <Badge variant="outline" className="border-violet-400/30 bg-violet-500/10 text-violet-200">Fog {Math.round((discoveredCount / mapCount) * 100)}%</Badge>
                {game.won && <Badge className="bg-amber-400 text-slate-950">Maze Clear</Badge>}
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
              <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-3 shadow-inner">
                <div className="relative mx-auto overflow-hidden rounded-2xl border border-white/10 bg-slate-950 p-2" style={{ width: GRID_W * TILE + 18 }}>
                  <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),transparent)] pointer-events-none" />
                  <div
                    className="relative grid"
                    style={{ gridTemplateColumns: `repeat(${GRID_W}, ${TILE}px)`, width: GRID_W * TILE, height: GRID_H * TILE }}
                  >
                    {Array.from({ length: GRID_H }).map((_, y) =>
                      Array.from({ length: GRID_W }).map((__, x) => {
                        const discovered = game.discovered.has(keyOf(x, y));
                        const kind = game.grid[y][x] === 1 ? "wall" : "floor";
                        const isExit = game.exit.x === x && game.exit.y === y;
                        const key = game.keys.find((k) => !k.delivered && !k.carriedBy && k.x === x && k.y === y);
                        return (
                          <div key={`${x}-${y}`} className="relative">
                            <Tile kind={kind} discovered={discovered} />
                            {discovered && isExit && (
                              <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-emerald-300">
                                <Flag className="h-4 w-4" />
                              </div>
                            )}
                            {discovered && key && (
                              <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-amber-300">
                                <div className="h-3 w-3 rounded-sm bg-amber-300 shadow-[0_0_10px_rgba(252,211,77,0.5)]" />
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}

                    {game.units.map((unit) => (
                      <div key={unit.id} onClick={() => setSelectedUnitId(unit.id)} className="absolute cursor-pointer">
                        <PixelUnit unit={unit} selected={selectedUnitId === unit.id} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid gap-4">
                <Card className="border-white/10 bg-slate-950/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Selected Unit</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-xl border border-white/10" style={{ background: COLORS[selectedUnit.color].body }} />
                      <div>
                        <div className="font-medium text-slate-100">{selectedUnit.id}</div>
                        <div className="text-slate-400">Mood: {selectedUnit.mood}</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline" className={COLORS[selectedUnit.color].badge}>{selectedUnit.color}</Badge>
                      <Badge variant="outline" className={ROLE_STYLES[selectedUnit.role]}>{selectedUnit.role}</Badge>
                      {selectedUnit.carryingKeyId && <Badge className="bg-amber-400 text-slate-950">Carrying key</Badge>}
                    </div>
                    <Separator className="bg-white/10" />
                    <div className="grid grid-cols-2 gap-2 text-slate-300">
                      <div>Pos</div>
                      <div className="text-right">{selectedUnit.x}, {selectedUnit.y}</div>
                      <div className="flex items-center gap-1"><Eye className="h-3.5 w-3.5" /> Vision</div>
                      <div className="text-right">{selectedUnit.vision}</div>
                      <div className="flex items-center gap-1"><Volume2 className="h-3.5 w-3.5" /> Hearing</div>
                      <div className="text-right">{selectedUnit.hearing}</div>
                      <div>Goal</div>
                      <div className="text-right">{selectedUnit.target ? `${selectedUnit.target.x},${selectedUnit.target.y}` : "idle"}</div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-white/10 bg-slate-950/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Quick Controls</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-2">
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={() => setRunning((v) => !v)}>
                      {running ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                      {running ? "Pause" : "Resume"}
                    </Button>
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={reset}>
                      <RotateCcw className="mr-2 h-4 w-4" /> Reset
                    </Button>
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={() => setCommand("all regroup")}>
                      All regroup
                    </Button>
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={() => setCommand("find key") }>
                      Find key
                    </Button>
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={() => setCommand("go east") }>
                      Sweep east
                    </Button>
                    <Button variant="secondary" className="justify-start bg-slate-800 hover:bg-slate-700" onClick={() => setCommand(`${selectedUnit.color} stop`) }>
                      Stop selected color
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card className="border-white/10 bg-slate-900/70 shadow-2xl backdrop-blur">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Command Console</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-3 text-sm text-cyan-100">
                Try: <span className="font-semibold">blue stop</span>, <span className="font-semibold">all regroup</span>, <span className="font-semibold">find key</span>, <span className="font-semibold">go east</span>, <span className="font-semibold">blue not that way</span>
              </div>
              <div className="flex gap-2">
                <Input
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendCommand()}
                  className="border-white/10 bg-slate-950/70 text-slate-100"
                  placeholder="Type a command to guide the swarm"
                />
                <Button onClick={sendCommand} className="bg-cyan-500 text-slate-950 hover:bg-cyan-400">
                  <Send className="mr-2 h-4 w-4" /> Send
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {game.units.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => setSelectedUnitId(u.id)}
                    className={`rounded-2xl border px-3 py-2 text-left transition ${selectedUnitId === u.id ? "border-cyan-400/60 bg-cyan-500/10" : "border-white/10 bg-slate-950/40 hover:bg-slate-900"}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-100">{u.id}</span>
                      <Badge variant="outline" className={ROLE_STYLES[u.role]}>{u.role}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">goal {u.target ? `${u.target.x},${u.target.y}` : "idle"}</div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-slate-900/70 shadow-2xl backdrop-blur">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Event Log</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[280px] rounded-2xl border border-white/10 bg-slate-950/60 p-3">
                <div className="space-y-2 text-sm">
                  {events.map((event) => (
                    <motion.div
                      key={event.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`rounded-xl border px-3 py-2 ${
                        event.tone === "command"
                          ? "border-cyan-400/20 bg-cyan-500/5 text-cyan-100"
                          : event.tone === "success"
                            ? "border-emerald-400/20 bg-emerald-500/5 text-emerald-100"
                            : event.tone === "info"
                              ? "border-violet-400/20 bg-violet-500/5 text-violet-100"
                              : "border-white/10 bg-slate-900 text-slate-200"
                      }`}
                    >
                      {event.text}
                    </motion.div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-slate-900/70 shadow-2xl backdrop-blur">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Handoff Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-slate-300">
              <div>Frontend prototype only. Replace local parser with an Ollama-backed adapter.</div>
              <div>Recommended runtime split: Phaser renderer + FastAPI sim + Ollama parser/planner.</div>
              <div>Current demo proves selection, command routing, fog-of-war, rumor bubbles and key delivery loop.</div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
