"""Simulated students against a running Hermes (how to run: scripts/loadtest/run_matrix.sh).

Each student, for --duration seconds (start staggered over --stagger):
  opens /coach (the daily plan, a new session), clicks the plan's «review my last game» card (review_game_id), opens
  a database game of 80 plies in its own tab, asks «Разбери эту партию» about the tab, looks at its 40th move and asks
  about that position, then plays the coach: a move every 5–10 s, the coach's comment when the site would ask for
  one, a question about the position every 3rd move, a voice check every 4th; a finished game is reviewed
  («Где я ошибся?») and a new one started.

Measured on the live path (client side unless noted):
  chat_*        to_model  (server: request arrival → the model is called; launcher.py), answer_first / total
                (server stages), and the whole request as the client sees it;
  move          POST …/game/{id}/move (the verdict of the student's move and the engine's reply);
  voice_check   POST /api/coach/voice/check (the site drops it after COACH_VOICE_CHECK_BUDGET_MS);
  plan, board, game_start, comment.
Every 2 s: /health (stockfish.pool, stockfish.precompute) and /bench/proc (CPU seconds, RSS).

Deterministic: the games and every random choice come from --seed and the student's number.
  python loadgen.py --n 10 --duration 240 --out results/branch-n10.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import uuid

import chess
import httpx

QUESTIONS_POS = ["Какой здесь лучший план?", "Что здесь лучше сыграть?", "Как оценить эту позицию?"]
QUESTIONS_GAME = ["Что мне здесь лучше сыграть?", "Какая угроза у соперника?", "Как мне продолжать?"]
VOICE_LINES = ["Здесь хорош ход {san}, он усиливает позицию.", "Сильнее всего {san}: это развивает фигуру."]


def make_game(seed: int, plies: int = 80, engine_path: str = "stockfish") -> tuple[str, list]:
    """A game of *plies* half-moves played by a weak player on both sides (the host's Stockfish at depth 5, a
    random one of its 3 best moves, now and then any legal move: a club game with mistakes in it), not over before
    the end. Deterministic for a seed."""
    import chess.engine

    s = seed
    eng = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        eng.configure({"Threads": 1, "Hash": 16})
        while True:
            rng = random.Random(s)
            b, sans, fens = chess.Board(), [], []
            while len(sans) < plies and not b.is_game_over():
                moves = list(b.legal_moves)
                if rng.random() < 0.08:
                    m = rng.choice(moves)
                else:
                    info = eng.analyse(b, chess.engine.Limit(depth=5), multipv=3)
                    cand = [x["pv"][0] for x in info if x.get("pv")]
                    m = cand[min(len(cand) - 1, int(rng.random() ** 2 * len(cand)))] if cand else rng.choice(moves)
                sans.append(b.san(m))
                b.push(m)
                fens.append(b.fen())
            if len(sans) == plies and not b.is_game_over():
                body = " ".join((f"{i // 2 + 1}. " if i % 2 == 0 else "") + x for i, x in enumerate(sans))
                return body + " *", fens
            s += 100_003
    finally:
        eng.quit()


class Mover:
    """The student's moves in a game with the coach: the host's Stockfish at depth 3, one of its 3 best, sometimes
    any legal move (a 1200 player). One process for every student, one search at a time (milliseconds each)."""

    def __init__(self, path: str = "stockfish"):
        self.path, self.eng, self.lock = path, None, asyncio.Lock()

    async def move(self, board: chess.Board, rng: random.Random) -> chess.Move:
        import chess.engine

        moves = list(board.legal_moves)
        if rng.random() < 0.12:
            return rng.choice(moves)
        async with self.lock:
            if self.eng is None:
                _, self.eng = await chess.engine.popen_uci(self.path)
            info = await self.eng.analyse(board, chess.engine.Limit(depth=3), multipv=3)
        cand = [x["pv"][0] for x in info if x.get("pv")]
        return rng.choice(cand) if cand else rng.choice(moves)

    async def close(self):
        if self.eng is not None:
            await self.eng.quit()


class Rec:
    def __init__(self):
        self.rows: list = []

    def add(self, kind: str, **kw):
        self.rows.append({"kind": kind, "t": time.time(), **kw})


async def chat(cl: httpx.AsyncClient, rec: Rec, user: str, sid: str, kind: str, message: str, **extra) -> None:
    body = {"message": message, "session_id": sid, "locale": "ru", **{k: v for k, v in extra.items() if v is not None}}
    h = {"X-User-Id": user, "X-Bench-Sid": sid}
    t0 = time.monotonic()
    usage, err, first = None, None, None
    try:
        async with cl.stream("POST", "/api/coach/chat", json=body, headers=h, timeout=120) as r:
            if r.status_code != 200:
                err = f"http {r.status_code}"
                await r.aread()
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        obj = json.loads(line[6:])
                    except ValueError:
                        continue
                    if "delta" in obj and first is None:
                        first = time.monotonic() - t0
                    if "usage" in obj:
                        usage = obj["usage"]
                    if "error" in obj:
                        err = str(obj["error"])[:200]
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"[:200]
    total = time.monotonic() - t0
    to_model = None
    try:
        to_model = (await cl.get("/bench/model", params={"sid": sid}, timeout=10)).json().get("ms")
    except Exception:  # noqa: BLE001
        pass
    st = (usage or {}).get("stages_ms") or {}
    rv = (usage or {}).get("review") or {}
    mv = (usage or {}).get("move_verify") or {}
    rec.add(kind, user=user, ms=int(total * 1000), first_ms=int(first * 1000) if first else None, err=err,
            to_model=to_model, answer_first=st.get("answer_first"), answer_shown=st.get("answer_shown"),
            stages=st, iterations=(usage or {}).get("iterations"), review_used=rv.get("used"),
            review_ms=rv.get("ms"), review_moments=(len(rv["moments"]) if isinstance(rv.get("moments"), list)
                                                    else rv.get("moments")),
            from_board=rv.get("from_board"), tools_dropped=rv.get("tools_dropped"),
            review_late=rv.get("late"), board_skipped=rv.get("board_skipped"), board_estimate=rv.get("board_estimate"),
            verify_ms=mv.get("ms"), engine_ms=((usage or {}).get("engine_note") or {}).get("ms"),
            live_ms=((usage or {}).get("live_look") or {}).get("ms"))


async def timed(rec: Rec, kind: str, user: str, coro):
    t0 = time.monotonic()
    try:
        r = await coro
        ok = r.status_code < 400
        out = r.json() if ok else None
        err = None if ok else f"http {r.status_code} {r.text[:120]}"
    except Exception as exc:  # noqa: BLE001
        out, err = None, f"{type(exc).__name__}: {exc}"[:200]
    rec.add(kind, user=user, ms=int((time.monotonic() - t0) * 1000), err=err)
    return out


async def drain(cl, rec, user, kind, path, body, h):
    t0 = time.monotonic()
    err = None
    try:
        async with cl.stream("POST", path, json=body, headers=h, timeout=60) as r:
            async for _ in r.aiter_lines():
                pass
            if r.status_code >= 400:
                err = f"http {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"[:200]
    rec.add(kind, user=user, ms=int((time.monotonic() - t0) * 1000), err=err)


async def student(i: int, args, cl: httpx.AsyncClient, rec: Rec, end_at: float):
    rng = random.Random(args.seed * 1000 + i)
    user = f"bench-u{i}"
    h = {"X-User-Id": user}
    await asyncio.sleep(rng.uniform(0, args.stagger))
    # /coach: the plan card and a new session
    if not args.only_game:
        await timed(rec, "plan", user, cl.get("/api/coach/daily-plan", headers=h, timeout=30))
    s = await timed(rec, "session", user, cl.post("/api/coach/sessions", json={}, headers=h, timeout=30))
    if not s:
        return
    sid = s["id"]
    if args.only_game:
        tab_id = None
    else:
        tab_id = await reviews(i, args, cl, rec, end_at, rng, user, h, sid)
    if tab_id is False:
        return
    await games(i, args, cl, rec, end_at, rng, user, h, sid)


async def reviews(i, args, cl, rec, end_at, rng, user, h, sid):
    """/coach's plan card, a database game in its tab, its review and a position question about it."""
    # the plan card «review my last game» (on the coach's own board)
    await asyncio.sleep(rng.uniform(4, 10))
    game_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "bench/" + user))
    await chat(cl, rec, user, sid, "chat_plan_review", "Разбери мою последнюю партию", review_game_id=game_id)
    if time.monotonic() > end_at:
        return False
    # a database game in its own tab
    tab_pgn, tab_fens = GAMES["tab"][user]
    await asyncio.sleep(rng.uniform(1, 3))
    b = await timed(rec, "board", user, cl.post(f"/api/coach/sessions/{sid}/boards", headers=h, timeout=30,
                                                json={"kind": "master_game", "title": f"Tab {i}", "pgn": tab_pgn,
                                                      "source": {"kind": "bench"}}))
    tab_id = (b or {}).get("id")
    # «Разбери эту партию» about the tab
    await asyncio.sleep(rng.uniform(3, 8))
    if tab_id:
        await chat(cl, rec, user, sid, "chat_tab_review", "Разбери эту партию", board_id=tab_id, fen=tab_fens[-1])
        await asyncio.sleep(rng.uniform(3, 6))
        fen40 = tab_fens[39]
        await timed(rec, "board_nav", user, cl.patch(f"/api/coach/sessions/{sid}/boards/{tab_id}", headers=h,
                                                     timeout=30, json={"position": fen40, "ply": 40}))
        await asyncio.sleep(rng.uniform(3, 6))
        await chat(cl, rec, user, sid, "chat_tab_position", rng.choice(QUESTIONS_POS), board_id=tab_id, fen=fen40)
    return tab_id


async def games(i, args, cl, rec, end_at, rng, user, h, sid):
    """Games against the coach until the end: moves, comments, questions, voice checks, a review of each game."""
    while time.monotonic() < end_at:
        g = await timed(rec, "game_start", user, cl.post(f"/api/coach/sessions/{sid}/game", headers=h, timeout=60,
                                                         json={"color": "white", "elo": 1500,
                                                               "comment_mode": "mistakes"}))
        if not g:
            await asyncio.sleep(5)
            continue
        board_id = g.get("board_id")
        fen = g.get("fen") or chess.STARTING_FEN
        nmove = 0
        finished = False
        while time.monotonic() < end_at:
            await asyncio.sleep(rng.uniform(5, 10))
            board = chess.Board(fen)
            moves = list(board.legal_moves)
            if not moves:
                finished = True
                break
            m = await MOVER.move(board, rng)
            r = await timed(rec, "move", user, cl.post(f"/api/coach/sessions/{sid}/game/{board_id}/move",
                                                       headers=h, timeout=60, json={"move": m.uci()}))
            if not r:
                break
            nmove += 1
            fen = r.get("fen") or fen
            if r.get("comment_wanted"):
                await drain(cl, rec, user, "comment", f"/api/coach/sessions/{sid}/game/{board_id}/comment",
                            {"event": "end" if r.get("status") != "playing" else "move", "locale": "ru"}, h)
            if r.get("status") != "playing":
                finished = True
                break
            if nmove % 3 == 0:
                await asyncio.sleep(rng.uniform(1, 3))
                await chat(cl, rec, user, sid, "chat_game_question", rng.choice(QUESTIONS_GAME),
                           board_id=board_id, fen=fen)
            if nmove % 4 == 0:
                bb = chess.Board(fen)
                lm = sorted(bb.legal_moves, key=lambda x: x.uci())
                if lm:
                    san = bb.san(lm[rng.randrange(len(lm))])
                    vt0 = time.monotonic()
                    vr = await timed(rec, "voice_check", user, cl.post(
                        "/api/coach/voice/check", headers=h, timeout=30,
                        json={"text": rng.choice(VOICE_LINES).format(san=san), "fen": fen, "session_id": sid,
                              "question": "Что мне здесь сыграть?", "engine": True}))
                    rec.rows[-1]["issues"] = len((vr or {}).get("issues") or [])
                    del vt0
        if finished and time.monotonic() < end_at:
            await asyncio.sleep(rng.uniform(2, 5))
            await chat(cl, rec, user, sid, "chat_game_review", "Где я ошибся?", board_id=board_id, fen=fen)


async def monitor(cl: httpx.AsyncClient, out: list, stop: asyncio.Event):
    while not stop.is_set():
        row = {"t": time.time()}
        try:
            hh = (await cl.get("/health", timeout=10)).json()
            sf = hh.get("stockfish") or {}
            row["pool"] = sf.get("pool")
            row["precompute"] = sf.get("precompute")
        except Exception as exc:  # noqa: BLE001
            row["health_err"] = str(exc)[:100]
        try:
            row["proc"] = (await cl.get("/bench/proc", timeout=10)).json()
        except Exception:  # noqa: BLE001
            pass
        out.append(row)
        try:
            await asyncio.wait_for(stop.wait(), 2.0)
        except asyncio.TimeoutError:
            pass


GAMES: dict = {}
MOVER = Mover()


async def main_async(args):
    global GAMES
    with open(args.games) as fh:
        GAMES = json.load(fh)
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
    async with httpx.AsyncClient(base_url=args.url, limits=limits, timeout=60) as cl:
        rec, mon, stop = Rec(), [], asyncio.Event()
        mtask = asyncio.create_task(monitor(cl, mon, stop))
        t0 = time.monotonic()
        end_at = t0 + args.duration
        await asyncio.gather(*(student(i, args, cl, rec, end_at) for i in range(args.n)))
        wall = time.monotonic() - t0
        # the background's tail after the students stop
        tail_t0 = time.monotonic()
        while time.monotonic() - tail_t0 < args.tail:
            await asyncio.sleep(2)
            pc = (mon[-1].get("precompute") or {}) if mon else {}
            if not pc.get("pending") and not pc.get("running"):
                break
        stop.set()
        await mtask
        await MOVER.close()
    res = {"args": vars(args), "wall_s": wall, "tail_s": time.monotonic() - tail_t0, "rows": rec.rows,
           "monitor": mon}
    with open(args.out, "w") as fh:
        json.dump(res, fh, ensure_ascii=False)
    print(f"done: {len(rec.rows)} requests in {wall:.0f} s → {args.out}")


def write_games(args):
    """The students' games: the plan card's «last game» (user → PGN, what launcher.py serves as the saved game) and
    the database game each opens in a tab (user → [PGN, the FEN after each ply])."""
    plan, tab = {}, {}
    for i in range(args.n):
        user = f"bench-u{i}"
        plan[user] = make_game(args.seed * 7919 + i * 13 + 1)[0]
        tab[user] = list(make_game(args.seed * 104729 + i * 31 + 7))
    with open(args.write_games, "w") as fh:
        json.dump({"plan": plan, "tab": tab}, fh)
    print(f"{len(plan)} students' games → {args.write_games}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8642")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--duration", type=float, default=240)
    ap.add_argument("--stagger", type=float, default=20)
    ap.add_argument("--tail", type=float, default=150, help="wait up to this long for the background to drain")
    ap.add_argument("--seed", type=int, default=1110)
    ap.add_argument("--only-game", action="store_true", help="students only play the coach (no plan, tab, reviews)")
    ap.add_argument("--out", default="loadtest.json")
    ap.add_argument("--games", default="games.json", help="the students' games (written by --write-games)")
    ap.add_argument("--write-games", help="only write the students' games to this file (needs a local stockfish)")
    args = ap.parse_args()
    if args.write_games:
        write_games(args)
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
