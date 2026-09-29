"""Model calls that reuse one connection and survive a stalled provider (2026-09-30).

Two gaps in how the coach reached OpenRouter, both measured:

* A new HTTPS connection per call. hermes-agent builds a fresh client for every
  request and closes it afterwards, and the reaction did the same, so every
  step of a turn paid a TCP+TLS handshake (~0.17 s to openrouter.ai from
  Almaty). The calls now share one pooled client per API key that stays open.
* Silence while a provider stalls. On the bench of 2026-09-29, 3 of 36 turns
  waited 6.5-7.6 s for DeepSeek's first token (it normally starts in ~0.5 s),
  and the reaction, on the same provider, timed out as well: the student saw
  nothing for seven seconds. Now, when a call has produced nothing after a
  short delay, the same request also goes to the fallback model and the
  student gets whichever starts first; the other stream is closed.

Settings: COACH_HEDGE_MS (answer, default 2000), COACH_QUICK_HEDGE_MS
(reaction, default 1000) — 0 turns the hedge off; COACH_SHARED_HTTP=0 brings
back the framework's connection per call.
"""

from __future__ import annotations

import copy
import logging
import os
import queue
import socket
import threading
import time
from typing import Any, Callable, Iterable, Iterator, Optional

import httpx

logger = logging.getLogger(__name__)

HEDGE_MS = int(os.environ.get("COACH_HEDGE_MS", "2000"))
QUICK_HEDGE_MS = int(os.environ.get("COACH_QUICK_HEDGE_MS", "1000"))
SHARED_HTTP = os.environ.get("COACH_SHARED_HTTP", "1").strip().lower() not in ("0", "false", "no", "off")

# Idle connections stay open this long: a student's next question usually comes
# within a minute (httpx closes them after 5 s by default).
KEEPALIVE_S = 90.0


def reasoning_for(model: str) -> Optional[dict]:
    """The thinking level for a Gemini 3 model, or None for any other model.

    Gemini 3 rejects ``enabled: false``, so "none"/"off" becomes "minimal".
    """
    from src import config

    name = (model or "").lower()
    if not name.startswith("google/gemini-") or name.startswith("google/gemini-2"):
        return None
    effort = config.COACH_GEMINI_REASONING_EFFORT.lower()
    if not effort:
        return None
    return {"effort": "minimal" if effort in ("none", "off") else effort}


def hedge_model_for(model: str) -> Optional[str]:
    """The model a stalled call of *model* is raced against, or None.

    The fallback tier (Gemini) backs up the DeepSeek tiers; a Gemini turn (the
    game review) is not raced — the fast model would win it and answer a
    review worse.
    """
    from src.config import get_model_config

    tiers = get_model_config().get("tiers", {}) or {}
    backup = tiers.get("fallback")
    if not backup or backup == model or (model or "").startswith("google/"):
        return None
    return backup


# ── one pooled connection per API key ─────────────────────────────────────

_lock = threading.Lock()
_http: Optional[httpx.Client] = None
_openai_clients: dict = {}


class _DrainAfterDone(httpx.SyncByteStream):
    """A streamed body that keeps its connection when closed right after [DONE].

    The OpenAI SDK stops reading at the SSE "[DONE]" and closes the response,
    a few bytes before the end of the HTTP body — and a response closed before
    its end takes the connection with it, so the pool never kept one. After a
    "[DONE]" the rest is read in the background; the connection then goes back
    to the pool. A stream closed mid-answer (aborted) is closed at once.
    """

    def __init__(self, inner):
        self._inner = inner
        self._items = None
        self._tail = b""

    def __iter__(self):
        self._items = iter(self._inner)
        for chunk in self._items:
            self._tail = (self._tail + chunk)[-48:]
            yield chunk

    def close(self) -> None:
        items, self._items = self._items, None
        if items is None or b"[DONE]" not in self._tail:
            self._inner.close()
            return

        def drain():
            try:
                for _ in items:
                    pass
            except Exception:  # noqa: BLE001 — the connection is simply not reused
                pass
            finally:
                self._inner.close()

        threading.Thread(target=drain, daemon=True, name="llm-drain").start()


class _ReusingTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        if "text/event-stream" in response.headers.get("content-type", ""):
            response.stream = _DrainAfterDone(response.stream)
        return response

    def close(self) -> None:
        self._inner.close()


def shared_http() -> httpx.Client:
    """The process-wide pooled HTTP client (thread-safe, never closed)."""
    global _http
    with _lock:
        if _http is None:
            limits = httpx.Limits(max_connections=64, max_keepalive_connections=16,
                                  keepalive_expiry=KEEPALIVE_S)
            _http = httpx.Client(
                transport=_ReusingTransport(httpx.HTTPTransport(limits=limits)),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return _http


def shared_openai_client(client_kwargs: dict):
    """An OpenAI client on the shared pool with the agent's key, URL and headers."""
    from openai import OpenAI

    headers = client_kwargs.get("default_headers") or {}
    key = (client_kwargs.get("base_url"), client_kwargs.get("api_key"),
           tuple(sorted((str(k), str(v)) for k, v in headers.items())))
    with _lock:
        client = _openai_clients.get(key)
    if client is None:
        kwargs = {k: v for k, v in client_kwargs.items() if k not in ("http_client",)}
        client = OpenAI(**kwargs, http_client=shared_http())
        with _lock:
            client = _openai_clients.setdefault(key, client)
    return client


def abort_stream(stream: Any) -> None:
    """Stop a stream now, from any thread.

    Closing the response alone leaves a thread blocked in a read waiting for the
    provider; shutting the socket down wakes it. A finished response is left
    alone — its connection is back in the pool, serving someone else.
    """
    if stream is None:
        return
    response = getattr(stream, "response", None)
    if response is not None and getattr(response, "is_closed", False):
        return
    try:
        network = (getattr(response, "extensions", None) or {}).get("network_stream")
        sock = network.get_extra_info("socket") if network is not None else None
        if sock is not None:
            sock.shutdown(socket.SHUT_RDWR)
    except Exception:  # noqa: BLE001 — best effort, the close below still runs
        pass
    try:
        stream.close()
    except Exception:  # noqa: BLE001
        pass


# ── the race ──────────────────────────────────────────────────────────────

def race(
    primary: Iterable,
    open_backup: Optional[Callable[[], Iterable]],
    delay_s: float,
    meaningful: Callable[[Any], bool],
    on_hedge: Optional[Callable[[], None]] = None,
    on_winner: Optional[Callable[[str], None]] = None,
) -> Iterator:
    """Yield the items of whichever stream says something first.

    *primary* is an open stream (iterable, with ``close``). *open_backup* opens
    the backup; it is called only when *delay_s* passes without a meaningful
    primary item. Items before the first meaningful one are held and yielded
    with it. A stream that fails while the other still runs is dropped; the
    loser is closed. ``on_winner`` gets "primary" or "backup".
    """
    events: queue.Queue = queue.Queue()
    streams: dict = {}
    stopped: set = set()
    ended: set = set()

    def pump(name: str, stream: Iterable) -> None:
        try:
            for item in stream:
                if name in stopped:
                    return
                events.put((name, "item", item))
            events.put((name, "end", None))
        except BaseException as exc:  # noqa: BLE001 — handed to the consumer
            events.put((name, "error", exc))

    def start(name: str, stream: Iterable) -> None:
        streams[name] = stream
        threading.Thread(target=pump, args=(name, stream), daemon=True,
                         name=f"llm-race-{name}").start()

    def stop(name: str) -> None:
        if name in stopped or name in ended:
            return
        stopped.add(name)
        abort_stream(streams.get(name))

    start("primary", primary)
    held: dict = {"primary": []}
    running = {"primary"}
    winner: Optional[str] = None
    hedged = open_backup is None or delay_s <= 0
    deadline = time.monotonic() + max(0.0, delay_s)
    try:
        while True:
            wait = None if (winner is not None or hedged) else max(0.0, deadline - time.monotonic())
            try:
                name, kind, value = events.get(timeout=wait)
            except queue.Empty:
                hedged = True
                try:
                    backup = open_backup()
                except Exception as exc:  # noqa: BLE001 — the primary goes on alone
                    logger.info("hedge request failed: %s", exc)
                    continue
                if on_hedge:
                    on_hedge()
                held["backup"] = []
                running.add("backup")
                start("backup", backup)
                continue
            if name in stopped:
                continue
            if kind == "end":
                ended.add(name)
            if winner is None:
                if kind == "error":
                    running.discard(name)
                    stopped.add(name)
                    if running:
                        continue  # the other stream may still answer
                    raise value
                if kind == "item":
                    held[name].append(value)
                    if not meaningful(value):
                        continue
                # The first meaningful item, or a stream that finished: it wins.
                winner = name
                for other in running - {name}:
                    stop(other)
                if on_winner:
                    on_winner(name)
                yield from held.pop(name)
                if kind == "end":
                    return
                continue
            if name != winner:
                continue
            if kind == "item":
                yield value
            elif kind == "end":
                return
            else:
                raise value
    finally:
        for name in list(streams):
            stop(name)


def chunk_says_something(chunk: Any) -> bool:
    """Whether an OpenAI stream chunk shows the model has started (not a bare role)."""
    if getattr(chunk, "usage", None):
        return True
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return False
    choice = choices[0]
    if getattr(choice, "finish_reason", None):
        return True
    delta = getattr(choice, "delta", None)
    if delta is None:
        return False
    return bool(
        getattr(delta, "content", None)
        or getattr(delta, "tool_calls", None)
        or getattr(delta, "reasoning", None)
        or getattr(delta, "reasoning_content", None)
    )


class RacedStream:
    """What the framework iterates: the primary stream, raced against a backup."""

    def __init__(self, primary, open_backup, delay_s, on_hedge=None, on_winner=None):
        self.response = getattr(primary, "response", None)
        self._items = race(primary, open_backup, delay_s, chunk_says_something,
                           on_hedge=on_hedge, on_winner=on_winner)

    def __iter__(self):
        return self._items

    def __next__(self):
        return next(self._items)

    def close(self) -> None:
        self._items.close()


# ── the agent's calls ─────────────────────────────────────────────────────

def _backup_kwargs(kwargs: dict, backup: str) -> dict:
    out = dict(kwargs)
    out["model"] = backup
    extra = copy.deepcopy(kwargs.get("extra_body") or {})
    reasoning = reasoning_for(backup)
    if reasoning is not None:
        extra["reasoning"] = reasoning
    else:
        extra.pop("reasoning", None)
    if extra:
        out["extra_body"] = extra
    return out


def _first_call_of_turn(kwargs: dict) -> bool:
    """Only a call answering the student's message is raced.

    Later steps carry the turn's tool calls, and Gemini 3 refuses a history
    of function calls without its own thought signatures.
    """
    messages = kwargs.get("messages") or []
    return bool(messages) and (messages[-1] or {}).get("role") == "user"


def install(agent, *, hedge_ms: Optional[int] = None) -> None:
    """Route *agent*'s model calls through the shared pool, racing a stalled first call.

    The framework asks ``_create_request_openai_client`` for a client per call
    and closes it afterwards — also to kill a stale stream. The client it gets
    keeps its shape, but ``chat.completions.create`` goes through the shared
    pool, and closing the client stops the streams it opened.
    Records ``agent._coach_hedge`` = {"fired", "winner", "model"} for the turn.
    """
    make = getattr(agent, "_create_request_openai_client", None)
    if make is None or not SHARED_HTTP:
        return
    delay_s = (HEDGE_MS if hedge_ms is None else hedge_ms) / 1000.0
    agent._coach_hedge = {"fired": False, "winner": None, "model": None}

    def _create_request_openai_client(*, reason: str):
        client = make(reason=reason)
        completions = getattr(getattr(client, "chat", None), "completions", None)
        if completions is None or not hasattr(client, "close"):
            return client
        from unittest.mock import Mock

        if isinstance(client, Mock):
            return client
        opened: list = []
        close = client.close

        def create(**kwargs):
            shared = shared_openai_client(getattr(agent, "_client_kwargs", {}) or {})
            primary = shared.chat.completions.create(**kwargs)
            if not kwargs.get("stream"):
                return primary
            opened.append(primary)
            backup = hedge_model_for(kwargs.get("model") or getattr(agent, "model", ""))
            if backup is None or delay_s <= 0 or not _first_call_of_turn(kwargs):
                return primary
            state = agent._coach_hedge

            def open_backup():
                stream = shared.chat.completions.create(**_backup_kwargs(kwargs, backup))
                opened.append(stream)
                return stream

            def on_hedge():
                state["fired"] = True
                logger.info("hedge: %s silent for %d ms, racing %s",
                            kwargs.get("model"), int(delay_s * 1000), backup)

            def on_winner(name):
                state["winner"] = name
                state["model"] = backup if name == "backup" else kwargs.get("model")

            raced = RacedStream(primary, open_backup, delay_s, on_hedge, on_winner)
            opened.append(raced)
            return raced

        def close_all():
            for stream in opened:
                abort_stream(stream)
            close()

        completions.create = create
        client.close = close_all
        return client

    agent._create_request_openai_client = _create_request_openai_client
