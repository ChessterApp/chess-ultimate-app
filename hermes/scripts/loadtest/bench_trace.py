"""Load-test trace (launcher.py, BENCH_TRACE=<file>): every engine-pool search (its priority, wait, time, what the pool
was running when it came) and every game move (its evals and the reply's search) and voice check, as JSON lines.

10.11-2: this is how the small-load «regression» was taken apart — the move's time is the reply's search on the game's
own process, and it follows the position, not the version (launcher.py, BENCH_SEEDED_REPLIES)."""
import contextvars
import json
import os
import threading
import time

PATH = os.environ.get("BENCH_TRACE")
_lock = threading.Lock()
_fh = open(PATH, "a", buffering=1) if PATH else None
_tl = threading.local()
REQ = contextvars.ContextVar("bench_req", default=None)


def emit(**kw):
    if _fh is None:
        return
    kw["t"] = round(time.time(), 4)
    with _lock:
        _fh.write(json.dumps(kw) + "\n")


def _tag():
    return getattr(_tl, "tag", None) or REQ.get()


def install():
    if _fh is None:
        return
    from src import engine_pool, game_mode
    from src import server

    orig_search = engine_pool.EnginePool.search

    def search(self, fen, *, go, **kw):
        prio = engine_pool.current_priority() if kw.get("priority") is None else kw["priority"]
        with self._cv:
            busy = sorted(p for _, p, _ in self._busy.values())
            waiting = sorted(w.priority for w in self._waiters)
        t0 = time.monotonic()
        res = orig_search(self, fen, go=go, **kw)
        emit(ev="search", tag=_tag(), prio=prio, go=go, mpv=kw.get("multipv", 1),
             ms=round((time.monotonic() - t0) * 1000), wait=round(res.get("wait_ms") or 0) if isinstance(res, dict) else None,
             stopped=bool(isinstance(res, dict) and res.get("stopped")), err=(res.get("error") if isinstance(res, dict) else None),
             busy0=busy, wait0=waiting, th=threading.current_thread().name)
        return res
    engine_pool.EnginePool.search = search

    orig_play = game_mode.play_move

    def play_move(session, board, move):
        _tl.tag = "move"; _tl.ph = []
        t0 = time.monotonic()
        try:
            return orig_play(session, board, move)
        finally:
            emit(ev="move", ms=round((time.monotonic() - t0) * 1000), ph=_tl.ph)
            _tl.tag = None
    game_mode.play_move = play_move

    def timed(name, fn):
        def w(*a, **k):
            t0 = time.monotonic()
            try:
                return fn(*a, **k)
            finally:
                ph = getattr(_tl, "ph", None)
                if ph is not None and getattr(_tl, "tag", None) == "move":
                    ph.append([name, round((time.monotonic() - t0) * 1000)])
        return w
    game_mode._evaluate = timed("eval", game_mode._evaluate)
    game_mode._engine_move = timed("engine_move", game_mode._engine_move)

    # voice check / chat: tag by path (asyncio.to_thread copies the context)
    app = server.app

    @app.middleware("http")
    async def _bench_trace(request, call_next):
        p = request.url.path
        tag = "voice" if p.endswith("/voice/check") else ("chat" if p.endswith("/coach/chat") else None)
        tok = REQ.set(tag) if tag else None
        t0 = time.monotonic()
        try:
            return await call_next(request)
        finally:
            if tag == "voice":
                emit(ev="voice", ms=round((time.monotonic() - t0) * 1000))
            if tok is not None:
                REQ.reset(tok)
