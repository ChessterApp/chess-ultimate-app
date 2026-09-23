#!/usr/bin/env python3
"""Talk to a local Hermes coach from the terminal — for trying models by hand.

Starts nothing: point it at a running Hermes (see scripts/coach_local.sh) and chat.
Shows the reply as it streams, then the tools it called, time to first token, total
time, tokens and cost (the server must run with COACH_EMIT_USAGE=1 for the last two).

    python scripts/coach_cli.py [--url http://127.0.0.1:8690] [--locale ru] [--fen "<FEN>"]
      > Что мне здесь играть?
      > /fen r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3
      > /new            (new session)      /quit
"""
import argparse
import json
import sys
import time

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8690")
ap.add_argument("--locale", default="ru")
ap.add_argument("--fen", default=None)
args = ap.parse_args()

session_id = None
fen = args.fen
print(f"Hermes at {args.url}, locale={args.locale}. /fen <FEN>, /new, /quit")
while True:
    try:
        msg = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not msg:
        continue
    if msg == "/quit":
        break
    if msg == "/new":
        session_id = None
        print("new session")
        continue
    if msg.startswith("/fen "):
        fen = msg[5:].strip()
        print(f"fen set: {fen}")
        continue
    body = {"message": msg, "locale": args.locale}
    if fen:
        body["fen"] = fen
    if session_id:
        body["session_id"] = session_id
    t0 = time.monotonic()
    ttft = None
    tools = []
    usage = None
    try:
        with httpx.stream("POST", f"{args.url}/api/coach/chat", json=body,
                          headers={"X-User-Id": "manual-test"}, timeout=300) as r:
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                d = json.loads(line[5:])
                if "delta" in d:
                    if ttft is None and d["delta"].strip():
                        ttft = time.monotonic() - t0
                    sys.stdout.write(d["delta"])
                    sys.stdout.flush()
                elif "tool_call" in d:
                    tools.append(d["tool_call"])
                    sys.stdout.write(f"  [{d['tool_call']}…]")
                    sys.stdout.flush()
                elif "usage" in d:
                    usage = d["usage"]
                elif "done" in d:
                    session_id = d.get("session_id", session_id)
                elif "error" in d:
                    print(f"\nERROR: {d['error']}")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        continue
    total = time.monotonic() - t0
    line = f"\n— tools: {tools or '—'} | first token {ttft:.1f}s | total {total:.1f}s" if ttft else f"\n— tools: {tools or '—'} | total {total:.1f}s"
    if usage:
        try:
            sys.path.insert(0, ".")
            from src.model_prices import estimate_cost_usd
            cost = estimate_cost_usd(usage["model"], usage["prompt_tokens"], usage["completion_tokens"], usage.get("cached_tokens", 0))
            line += f" | {usage['model']} | {usage['prompt_tokens']} in ({usage.get('cached_tokens', 0)} cached) / {usage['completion_tokens']} out | ${cost:.4f}"
        except Exception:
            line += f" | {usage['model']} | {usage['prompt_tokens']} in / {usage['completion_tokens']} out"
    print(line)
