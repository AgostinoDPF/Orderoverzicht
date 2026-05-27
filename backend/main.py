"""
DP Factory Planner — lokale backend
FastAPI + SQLite, bedoeld voor een klein team op hetzelfde netwerk.

Start:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
Toegang collega's: http://<jouw-ip>:8000
"""

from __future__ import annotations
import json
import os
import pathlib
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# ── Paden ────────────────────────────────────────────────────────────────────
BASE_DIR = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "planner.db"
HTML_PATH = BASE_DIR / "index.html"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="DP Factory Planner", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS state (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS last_modified (
            id  INTEGER PRIMARY KEY CHECK (id = 1),
            ts  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        INSERT OR IGNORE INTO last_modified (id) VALUES (1);
    """)
    conn.commit()
    conn.close()

_init_db()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_app() -> str:
    """Serve de frontend HTML."""
    return HTML_PATH.read_text(encoding="utf-8")

@app.get("/api/state")
def get_state() -> JSONResponse:
    """Haal alle opgeslagen staat op."""
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM state").fetchall()
    ts   = conn.execute("SELECT ts FROM last_modified WHERE id=1").fetchone()
    conn.close()
    state: dict = {r["key"]: json.loads(r["value"]) for r in rows}
    state["_ts"] = ts["ts"] if ts else ""
    return JSONResponse(state)

@app.post("/api/state")
async def save_state(request: Request) -> dict:
    """Sla alle staat op (volledige vervanging per sleutel)."""
    data: dict = await request.json()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    conn = _get_conn()
    for key, value in data.items():
        if key.startswith("_"):
            continue                         # meta-sleutels overslaan
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False, default=str), now),
        )
    conn.execute("UPDATE last_modified SET ts=? WHERE id=1", (now,))
    conn.commit()
    conn.close()
    return {"ok": True, "ts": now}

@app.get("/api/ping")
def ping() -> dict:
    """Geeft de laatste wijzigingstijd terug — voor change-detection polling."""
    conn = _get_conn()
    row = conn.execute("SELECT ts FROM last_modified WHERE id=1").fetchone()
    conn.close()
    return {"ts": row["ts"] if row else ""}
