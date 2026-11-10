"""Hermes for the load test (how to run: scripts/loadtest/run_matrix.sh): the real server, three things changed.

* Every OpenRouter URL points at BENCH_STUB_URL (scripts/loadtest/stub_llm.py): no model is called, nothing is paid.
* The daily plan and the plan card's game read a fake «last game» per student (BENCH_GAMES_JSON: user id → PGN)
  instead of Supabase.
* Timing of the turn up to the model: a request to /api/coach/chat with the header X-Bench-Sid is timed from its
  arrival to the first AIAgent.run_conversation of that session (the moment the model is called, after every engine
  wait of the turn); GET /bench/model?sid=… returns and clears it. GET /bench/proc gives this process's CPU and RSS.

Run from the hermes/ directory:  python scripts/loadtest/launcher.py   (port 8642)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.getcwd())

STUB = os.environ.get("BENCH_STUB_URL", "http://127.0.0.1:9999/v1").rstrip("/")
REAL = "https://openrouter.ai/api/v1"

import uvicorn  # noqa: E402

from src import server  # noqa: E402  (imports config, tools, the pool)


def _redirect_urls() -> int:
    """Every module global and function default in src.* that names OpenRouter now names the stub."""
    import importlib

    for extra in ("src.quick_reply", "src.memory_writer", "src.bestofn", "src.playbook", "src.voice_tts",
                  "src.llm_transport", "src.claim_judge"):
        try:
            importlib.import_module(extra)
        except Exception:  # noqa: BLE001 — a module this version does not have
            pass
    n = 0
    for name, mod in list(sys.modules.items()):
        if not (name == "src" or name.startswith("src.")) or mod is None:
            continue
        for attr, val in list(vars(mod).items()):
            if isinstance(val, str) and val.startswith(REAL):
                setattr(mod, attr, STUB + val[len(REAL):])
                n += 1
            fn = getattr(val, "__func__", val)
            if callable(fn) and getattr(fn, "__module__", None) == name:
                d = getattr(fn, "__defaults__", None)
                if d and any(isinstance(x, str) and x.startswith(REAL) for x in d):
                    fn.__defaults__ = tuple(STUB + x[len(REAL):] if isinstance(x, str) and x.startswith(REAL) else x
                                            for x in d)
                    n += 1
                kd = getattr(fn, "__kwdefaults__", None)
                if kd and any(isinstance(x, str) and x.startswith(REAL) for x in kd.values()):
                    fn.__kwdefaults__ = {k: (STUB + x[len(REAL):] if isinstance(x, str) and x.startswith(REAL) else x)
                                         for k, x in kd.items()}
                    n += 1
    return n


# ── the students' saved games ──
GAMES: dict = {}
if os.environ.get("BENCH_GAMES_JSON"):
    with open(os.environ["BENCH_GAMES_JSON"]) as fh:
        GAMES = json.load(fh)
    GAMES = GAMES.get("plan", GAMES)  # loadgen --write-games: {"plan": user → PGN, "tab": …}


def _game_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "bench/" + user_id))


def _fake_sources(user_id: str) -> dict:
    pgn = GAMES.get(user_id)
    games = [{"id": _game_id(user_id), "pgn": pgn, "white": user_id, "black": "Opponent", "eco": None}] if pgn else []
    return {"games": lambda: games, "insights": lambda: [], "focus": lambda: []}


def _fake_game_pgn(user_id: str, game_id: str):
    pgn = GAMES.get(user_id)
    return pgn if pgn and game_id == _game_id(user_id) else None


def _install_fakes() -> None:
    from src import daily_plan
    from src.tools import user_data

    daily_plan._sources = _fake_sources
    user_data.get_user_game_pgn = _fake_game_pgn


# ── time to the model ──
_lock = threading.Lock()
_started: dict = {}
_model: dict = {}


def _wrap_agent() -> None:
    from run_agent import AIAgent

    orig = AIAgent.run_conversation

    def run_conversation(self, *a, **k):
        sid = getattr(self, "session_id", None)
        now = time.monotonic()
        with _lock:
            t0 = _started.pop(sid, None)
            if t0 is not None:
                _model[sid] = int((now - t0) * 1000)
        return orig(self, *a, **k)

    AIAgent.run_conversation = run_conversation


class _Timing:
    """ASGI middleware: the arrival of a chat request carrying X-Bench-Sid, and the /bench endpoints."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/api/coach/chat":
                for k, v in scope.get("headers") or []:
                    if k == b"x-bench-sid":
                        with _lock:
                            _started[v.decode()] = time.monotonic()
                            _model.pop(v.decode(), None)
            elif path.startswith("/bench/"):
                return await self._bench(scope, send)
        return await self.app(scope, receive, send)

    async def _bench(self, scope, send):
        from urllib.parse import parse_qs

        q = parse_qs((scope.get("query_string") or b"").decode())
        if scope["path"] == "/bench/model":
            sid = (q.get("sid") or [""])[0]
            with _lock:
                body = {"ms": _model.pop(sid, None)}
        else:
            body = _proc()
        data = json.dumps(body).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": data})


def _proc() -> dict:
    """This process and its children (the Stockfish processes): CPU seconds and RSS."""
    import psutil

    me = psutil.Process()
    procs = [me] + me.children(recursive=True)
    cpu = rss = 0.0
    sf_rss = sf_cpu = 0.0
    for p in procs:
        try:
            t = p.cpu_times()
            cpu += t.user + t.system
            r = p.memory_info().rss
            rss += r
            if "stockfish" in (p.name() or ""):
                sf_rss += r
                sf_cpu += t.user + t.system
        except psutil.Error:
            pass
    t = me.cpu_times()
    # The whole machine (the VM in the load test): CPU seconds busy and in total, so another tenant shows.
    host = psutil.cpu_times()
    host_busy = sum(getattr(host, k, 0.0) for k in ("user", "system", "nice", "irq", "softirq", "steal"))
    return {"t": time.time(), "cpu_s": cpu, "py_cpu_s": t.user + t.system, "stockfish_cpu_s": sf_cpu,
            "host_busy_s": host_busy, "host_total_s": host_busy + host.idle + getattr(host, "iowait", 0.0),
            "rss_mb": rss / 2 ** 20, "py_rss_mb": me.memory_info().rss / 2 ** 20,
            "stockfish_rss_mb": sf_rss / 2 ** 20, "threads": me.num_threads(), "children": len(procs) - 1}


def main() -> None:
    n = _redirect_urls()
    _install_fakes()
    _wrap_agent()
    print(f"loadtest launcher: {n} OpenRouter references → {STUB}; {len(GAMES)} students' games", flush=True)
    app = _Timing(server.app)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8642")), log_level="warning", workers=1)


if __name__ == "__main__":
    main()
