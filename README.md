# Tiny Swarm Maze

Tiny Swarm Maze is a retro-style swarm command game where you guide a noisy, semi-autonomous squad through a randomized maze using short natural-language commands.

Instead of faking AI behavior, this project runs a deterministic simulation core and plugs real model parsing on top through an Ollama adapter. That means you can switch between rules-only, local model, and cloud model profiles while keeping gameplay responsive.

## What This Project Demonstrates

- Real-time swarm coordination with imperfect local knowledge
- Deterministic simulation with role-based autonomy (not per-frame LLM control)
- Model-backed command parsing with strict validation and safe fallback
- Visible latency effects via queued command UX
- Side-by-side profile testing (`rules`, fast/slow local, cloud)

## Core Gameplay

1. Generate a maze from a seed
2. Spawn a 6-unit squad with distinct roles
3. Explore under fog-of-war with local vision/hearing constraints
4. Discover keys, avoid traps, and deliver to exit
5. Issue short commands (`blue stop`, `all regroup`, `find key`)
6. Watch commands queue, parse, and apply in real time

## Why It Feels Like Real Swarm Control

- Units use local policies and rumor propagation
- Information is partial and decays over time
- Commands are parsed into validated command objects before state changes
- Model calls are asynchronous and never block the sim tick loop

## Features

- Difficulty presets: `starter`, `standard`, `dense`
- Seeded deterministic maze generation
- Trap hazards with stun/reveal behavior
- Right-rail UI (selected unit, command console, queue, metrics, settings, logs)
- Scroll-safe board container (no panel overlap)
- Live metrics: parser latency, queue depth, stuns, reroutes, timeouts, model errors
- WebSocket authoritative state stream
- SQLite telemetry store
- Browser-stored provider settings + API key (persists until local site data/cache is cleared)

## Stack

- Frontend: TypeScript, Vite, Phaser
- Backend: Python, FastAPI, WebSocket
- Telemetry: SQLite
- Model adapter: Ollama via OpenAI-compatible endpoint (plus legacy `/api/chat` fallback)

## Profiles

- `rules`: fully offline deterministic parser
- `ollama_fast`: low-latency local model profile
- `ollama_slow`: intentionally slower profile for queued-command behavior testing
- `ollama_cloud_kimi`: cloud profile (default model `kimi-k2.5:cloud`, configurable)

## Quick Start

### 1) Backend

```bash
cd backend
python -m venv .venv
# PowerShell:
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

## Commands to Try

- `blue stop`
- `all regroup`
- `find key`
- `runner go east`
- `yellow guard here`
- `blue follow red-2`
- `resume`

## API Surface

### REST

- `POST /api/session`
- `GET /api/session/{id}`
- `POST /api/session/{id}/reset`
- `GET /api/session/{id}/replay`
- `GET /api/config`
- `GET /api/metrics`
- `GET /api/health`

### WebSocket

Endpoint: `/ws/{session_id}`

Client messages:
- `submit_command`
- `set_profile`
- `set_provider_config`
- `pause`
- `resume`
- `reset`

Server messages:
- `state`
- `command_queued`
- `command_applied`
- `ack`
- `warning`

## Testing

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Roadmap Ideas

- Optional planner calls + planner traces
- Replay timeline scrubber
- Benchmark mode for profile comparison by fixed seeds
- Sprite/art pass and richer animation polish
