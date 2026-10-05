#!/usr/bin/env python3
"""Multi-turn flows the single-turn bench cannot run — the live coach on the stand.

Starts Hermes with the production routing (scripts/model_bench.start_server("prod")),
then drives: a language asked for earlier in the session holding for a later
English question; a game against the coach with an «а если…» question and a move
comment after a Russian chat; a language the coach does not speak; «вернись на
русский». Writes eval/bench/<out>/flows.json and prints what the student saw,
with the answer-check events (sentences withheld or rewritten) of each turn.

    python scripts/live_flows_check.py --out eval/bench/2026-10-04-live-flows [--port 8661]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from model_bench import start_server, wait_health  # noqa: E402

T_PRE = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/2Q2P1P/1PP2PK1/4R3 w - - 0 1"
USER = "live-flows-2026-10-04"


async def chat(c: httpx.AsyncClient, base: str, sid: str, message: str, locale: str, fen: str = None) -> dict:
    body = {"message": message, "session_id": sid, "locale": locale}
    if fen:
        body["fen"] = fen
    t0 = time.monotonic()
    first = None
    text, actions, errors, tools = [], [], [], []
    async with c.stream("POST", f"{base}/api/coach/chat", json=body, headers={"X-User-Id": USER}, timeout=240) as r:
        async for line in r.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                f = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if "delta" in f:
                if first is None:
                    first = time.monotonic() - t0
                text.append(f["delta"])
            elif "board_actions" in f:
                actions += [a.get("type") for a in f["board_actions"]]
            elif "error" in f:
                errors.append(f["error"])
            elif "tool_call" in f:
                tc = f["tool_call"]
                tools.append((tc.get("name") or str(tc)[:40]) if isinstance(tc, dict) else str(tc)[:40])
    return {"message": message, "locale": locale, "fen": fen, "text": "".join(text), "first_s": first,
            "total_s": time.monotonic() - t0, "board_actions": actions, "errors": errors, "tools": tools}


def lang(text: str) -> str:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "none"
    cyr = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    return "ru" if cyr / len(letters) >= 0.5 else "en"


async def main(out: Path, port: int):
    out.mkdir(parents=True, exist_ok=True)
    proc = start_server("prod", port, out / "hermes.log")
    base = f"http://127.0.0.1:{port}"
    flows = {}
    try:
        if not await wait_health(base, 90):
            raise SystemExit("Hermes did not come up; see hermes.log")
        async with httpx.AsyncClient() as c:
            async def new_session():
                r = await c.post(f"{base}/api/coach/sessions", json={}, headers={"X-User-Id": USER})
                j = r.json()
                return j.get("id") or j.get("session_id") or j.get("session", {}).get("id")

            # F1: a language asked for earlier holds for a later English question
            sid = await new_session()
            f1 = [await chat(c, base, sid, "говори по-русски, пожалуйста", "en"),
                  await chat(c, base, sid, "So if instead of b3 I played Rg1 and the knight takes on a4, am I just down a pawn?", "en", T_PRE)]
            flows["F1_sticky_language"] = {"session": sid, "turns": f1, "expect": "both answers in Russian"}

            # F2: a game; a what-if question in Russian; the comment after a move must be Russian despite locale=en
            sid = await new_session()
            g = (await c.post(f"{base}/api/coach/sessions/{sid}/game", json={"color": "white", "elo": 1500, "comment_mode": "every"},
                              headers={"X-User-Id": USER})).json()
            bid = g["board_id"]
            moves = []
            for mv in ("e4", "Nf3"):
                m = (await c.post(f"{base}/api/coach/sessions/{sid}/game/{bid}/move", json={"move": mv}, headers={"X-User-Id": USER})).json()
                moves.append({"student": mv, "verdict": (m.get("student") or {}).get("verdict"), "engine": (m.get("engine") or {}).get("san"), "fen": m.get("fen")})
            q = await chat(c, base, sid, "а если я сейчас сыграю Bc4, слон не повиснет? и что вообще тут делать?", "ru")
            m = (await c.post(f"{base}/api/coach/sessions/{sid}/game/{bid}/move", json={"move": "Bc4"}, headers={"X-User-Id": USER})).json()
            moves.append({"student": "Bc4", "verdict": (m.get("student") or {}).get("verdict"), "engine": (m.get("engine") or {}).get("san"), "fen": m.get("fen")})
            # the comment: locale en, but the student has been writing Russian
            text = []
            async with c.stream("POST", f"{base}/api/coach/sessions/{sid}/game/{bid}/comment", json={"locale": "en", "event": "move"},
                                headers={"X-User-Id": USER}, timeout=60) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        f = json.loads(line[6:])
                        if "delta" in f:
                            text.append(f["delta"])
            flows["F2_game"] = {"session": sid, "moves": moves, "question": q, "comment_locale_en": "".join(text),
                                "expect": "hint, no illegal claims; the comment in Russian"}

            # F3: a language the coach does not speak
            sid = await new_session()
            f3 = [await chat(c, base, sid, "Говори по-немецки, пожалуйста. Что такое вилка?", "ru")]
            flows["F3_german"] = {"session": sid, "turns": f3, "expect": "says it speaks ru/kk/en, answers in Russian"}

            # F4: English asked for, then «вернись на русский»
            sid = await new_session()
            f4 = [await chat(c, base, sid, "Отвечай по-английски: что такое связка?", "ru"),
                  await chat(c, base, sid, "вернись на русский. а что такое вилка?", "ru"),
                  await chat(c, base, sid, "ok and a skewer?", "ru")]
            flows["F4_back_to_russian"] = {"session": sid, "turns": f4, "expect": "en, then ru, then ru (the request holds)"}
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    # the answer-check events of these sessions
    sessions = {v["session"] for v in flows.values()}
    checks = []
    for p in sorted((ROOT / "metrics").glob("coach-events-*.jsonl")):
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "answer_check" and e.get("session_id") in sessions:
                checks.append({"session_id": e.get("session_id"), "payload": e.get("payload")})
    flows["_answer_check_events"] = checks
    (out / "flows.json").write_text(json.dumps(flows, ensure_ascii=False, indent=1), encoding="utf-8")
    # summary
    for name, v in flows.items():
        if name.startswith("_"):
            continue
        print(f"\n## {name} — expect: {v['expect']}")
        for t in v.get("turns", []) + ([v["question"]] if "question" in v else []):
            print(f"- [{t['locale']}] {t['message'][:70]}\n  → ({lang(t['text'])}, first {t['first_s'] and round(t['first_s'],1)} s, total {round(t['total_s'],1)} s, tools {t['tools']}, errors {t['errors']})\n  {t['text'][:600].strip()}")
        if "comment_locale_en" in v:
            print(f"- moves: {v['moves']}\n- comment (locale en) → ({lang(v['comment_locale_en'])}) {v['comment_locale_en'][:300]}")
    print(f"\n## answer_check events: {len(checks)}")
    for ch in checks:
        print("-", json.dumps(ch["payload"], ensure_ascii=False)[:500])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8661)
    a = ap.parse_args()
    asyncio.run(main(Path(a.out), a.port))
