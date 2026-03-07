from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from time import time
from typing import Any, Optional


class TelemetryStore:
    def __init__(self, db_path: str, enabled: bool = True) -> None:
        self._enabled = enabled
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        if self._enabled:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    seed INTEGER NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    client_command_id TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    parsed_json TEXT,
                    created_at REAL NOT NULL,
                    UNIQUE(session_id, client_command_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    error_text TEXT,
                    created_at REAL NOT NULL
                )
                """
            )

    def record_session_started(self, session_id: str, seed: int) -> None:
        if not self._enabled:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id, seed, created_at) VALUES (?, ?, ?)",
                (session_id, seed, time()),
            )

    def record_command(
        self,
        session_id: str,
        client_command_id: str,
        raw_text: str,
        parsed_json: Optional[dict[str, Any]],
    ) -> None:
        if not self._enabled:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO commands(session_id, client_command_id, raw_text, parsed_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    client_command_id,
                    raw_text,
                    json.dumps(parsed_json) if parsed_json else None,
                    time(),
                ),
            )

    def record_llm_call(
        self,
        session_id: str,
        provider: str,
        model: str,
        duration_ms: int,
        success: bool,
        error_text: Optional[str] = None,
    ) -> None:
        if not self._enabled:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls(session_id, provider, model, duration_ms, success, error_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, provider, model, duration_ms, int(success), error_text, time()),
            )

    def summary(self) -> dict[str, Any]:
        if not self._enabled:
            return {
                "enabled": False,
                "sessions": 0,
                "commands": 0,
                "llm_calls": 0,
                "llm_success_rate": 0.0,
                "llm_latency_avg_ms": 0,
            }

        with self._lock, self._connect() as conn:
            sessions = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            commands = int(conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0])
            llm_calls = int(conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0])
            success_count = int(
                conn.execute("SELECT COALESCE(SUM(success), 0) FROM llm_calls").fetchone()[0]
            )
            avg_latency = int(
                conn.execute("SELECT COALESCE(AVG(duration_ms), 0) FROM llm_calls").fetchone()[0]
            )

        success_rate = (success_count / llm_calls) if llm_calls else 0.0
        return {
            "enabled": True,
            "sessions": sessions,
            "commands": commands,
            "llm_calls": llm_calls,
            "llm_success_rate": round(success_rate, 3),
            "llm_latency_avg_ms": avg_latency,
        }
