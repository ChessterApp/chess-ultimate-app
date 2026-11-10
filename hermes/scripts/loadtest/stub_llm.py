"""A stand-in for OpenRouter's chat completions, for the load test (how to run: scripts/loadtest/run_matrix.sh).

No model is called and nothing is paid: every chat call gets a fixed reply after a fixed delay (FIRST_TOKEN_S, then
CHUNKS chunks CHUNK_S apart), streamed or not, as the request asks. What it answers:

* a review question («разбери партию», «где я ошибся») with no critical-moments block in the message and no tool
  result yet: a tool call first — find_critical_moments when the game's record is in the message, else
  analyze_position on the board's position (what the live model did on main for a game on the board: two calls);
* a turn with a board position: a sentence that recommends a legal move there («Здесь я бы сыграл Nf3»), so the
  server's recommended-move check runs, as it does on most real answers;
* anything else: a neutral sentence.

Run on the host (not inside the measured container):  python stub_llm.py --port 9999
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time

import chess
from aiohttp import web

FIRST_TOKEN_S = 0.6
CHUNK_S = 0.12
CHUNKS = 6

FEN_RE = re.compile(r"((?:[rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+ [wb] (?:[KQkq]+|-) (?:[a-h][36]|-) \d+ \d+)")
REVIEW_RE = re.compile(r"разбер\w*\s+(?:эту\s+|мою\s+)?парти|где\s+я\s+ошиб|review\s+(?:my|this)\s+game", re.I)
MOVETEXT_RE = re.compile(r"(?<![\w.])(1\.\s*[a-hNBRQKO][a-h1-8x+#=NBRQKO-]*(?:\s+(?:\d+\.\s*)?[a-hNBRQKO][a-h1-8x+#=NBRQKO-]*){9,}(?:\s+\*)?)")

STATS = {"calls": 0, "tool_calls": 0, "stream": 0}


def _text(messages: list) -> str:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            out += [p.get("text", "") for p in c if isinstance(p, dict)]
    return "\n".join(out)


def _last_user(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _text([m])
    return ""


def _move_for(fen: str) -> str | None:
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    moves = sorted(board.legal_moves, key=lambda m: m.uci())
    if not moves:
        return None
    h = int(hashlib.md5(fen.encode()).hexdigest(), 16)
    return board.san(moves[h % len(moves)])


def _reply(body: dict) -> tuple[str | None, dict | None]:
    messages = body.get("messages") or []
    user = _last_user(messages)
    # The student's own words: before the turn's context the server appends (which quotes earlier turns too).
    question = user.split("[Turn context", 1)[0]
    tools = {((t.get("function") or {}).get("name")) for t in body.get("tools") or []}
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    all_text = _text(messages)
    if REVIEW_RE.search(question) and not has_tool_result and "Critical moments of the student's game" not in all_text:
        # No moments from the server: the model spends a call first — the scan when it has the game's record,
        # else the engine on the position it sees (main 10.11: two calls, then a review of the final position).
        found = MOVETEXT_RE.findall(user)
        if found and "find_critical_moments" in tools:
            return None, {"name": "find_critical_moments", "arguments": json.dumps({"pgn": max(found, key=len)})}
        fens = FEN_RE.findall(user)
        if fens and "analyze_position" in tools:
            return None, {"name": "analyze_position", "arguments": json.dumps({"fen": fens[0]})}
    if REVIEW_RE.search(question):
        return ("Давай разберём партию. Главный перелом случился в середине игры: там была упущена тактика, "
                "и после этого оценка ушла в пользу соперника."), None
    fens = FEN_RE.findall(user) or FEN_RE.findall(all_text)
    if fens:
        san = _move_for(fens[-1])
        if san:
            return f"Здесь я бы сыграл {san}: этот ход усиливает позицию и готовит следующий план.", None
    return "Хороший вопрос. Давай посмотрим на позицию спокойно и найдём план.", None


def _chunk(model: str, delta: dict, finish=None, usage=None) -> bytes:
    obj = {"id": "stub", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
           "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        obj["usage"] = usage
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n"


async def completions(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    STATS["calls"] += 1
    if os.environ.get("STUB_DUMP"):
        with open(os.environ["STUB_DUMP"], "a") as fh:
            fh.write(json.dumps(body, ensure_ascii=False) + "\n")
    model = body.get("model") or "stub"
    text, tool = _reply(body)
    usage = {"prompt_tokens": 1000, "completion_tokens": 40, "total_tokens": 1040}
    await asyncio.sleep(FIRST_TOKEN_S)
    if tool:
        STATS["tool_calls"] += 1
    if not body.get("stream"):
        msg = {"role": "assistant", "content": text}
        if tool:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_stub", "type": "function", "function": tool}]}
        return web.json_response({"id": "stub", "object": "chat.completion", "created": int(time.time()),
                                  "model": model, "usage": usage,
                                  "choices": [{"index": 0, "message": msg,
                                               "finish_reason": "tool_calls" if tool else "stop"}]})
    STATS["stream"] += 1
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await resp.prepare(request)
    if tool:
        await resp.write(_chunk(model, {"role": "assistant", "tool_calls": [
            {"index": 0, "id": "call_stub", "type": "function", "function": tool}]}))
        await resp.write(_chunk(model, {}, "tool_calls", usage))
    else:
        words = text.split(" ")
        step = max(1, len(words) // CHUNKS)
        parts = [" ".join(words[i:i + step]) + " " for i in range(0, len(words), step)]
        await resp.write(_chunk(model, {"role": "assistant", "content": parts[0]}))
        for p in parts[1:]:
            await asyncio.sleep(CHUNK_S)
            await resp.write(_chunk(model, {"content": p}))
        await resp.write(_chunk(model, {}, "stop", usage))
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


async def stats(_request):
    return web.json_response(STATS)


async def other(request):
    return web.json_response({"error": "stub: not served"}, status=404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9999)
    args = ap.parse_args()
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_post("/v1/chat/completions", completions)
    app.router.add_post("/api/v1/chat/completions", completions)
    app.router.add_get("/stats", stats)
    app.router.add_route("*", "/{tail:.*}", other)
    web.run_app(app, host="0.0.0.0", port=args.port, print=None)


if __name__ == "__main__":
    main()
