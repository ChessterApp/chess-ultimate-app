"""First stage of a two-stage coach answer: a one-sentence spoken-style reaction.

The full answer's first token arrives only after every tool call (engine,
databases, board), which is 15–23 s at the median. This module produces the
sentence the student hears meanwhile — "Смотрю на позицию, сейчас проверю
жертву на движке" — with a direct, tool-free, streamed model call that is
cheap enough to run on every turn and short enough to finish in ~1–2 s.

The reaction deliberately never contains a move, an evaluation, or a verdict:
those come from the second stage after the engine has spoken, and the two must
never contradict each other. The caller enforces a time budget and simply drops
the reaction when the budget runs out or the real answer arrives first, so a
slow reaction can never delay the answer.

Plain httpx is used instead of the agent framework: the framework's retry,
fallback and tool loop are exactly the latency this stage exists to hide. The
calls share the pooled connection of src/llm_transport.py and race the
fallback model when the provider is silent (2026-09-30).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

_LANGUAGE = {"ru": "Russian", "kz": "Kazakh", "kk": "Kazakh", "en": "English"}

QUICK_SYSTEM_PROMPT = (
    "You are Chesster, a friendly chess coach sitting next to the student. The "
    "student has just asked something; the precise, engine-checked answer is "
    "being prepared and will follow your line. Your job is ONLY the first spoken "
    "reaction: one short sentence, at most 20 words, in {language} — whatever "
    "language the student's message is in.\n"
    "Acknowledge what the student asked and say what you are about to check or "
    "look at — the line, the opening, the game, the database, the lessons, or the "
    "position. Mention the position ONLY when the question is about the position on "
    "the board — never for what to study next, a concept in general, an opening in "
    "general or the student's own games.\n"
    "Rules:\n"
    "- NEVER name a move, give an evaluation, a verdict, a plan or a hint.\n"
    "- NEVER ask the student a question.\n"
    "- No markdown, no lists, no emoji, no greeting, no quotes.\n"
    "- Speak naturally, like a coach thinking out loud, not like a system message.\n"
    "Write the sentence only."
)

# Reactions that would read as a non-answer are dropped by the caller; this is
# the floor below which a reaction is considered garbage (e.g. a lone "OK").
MIN_REACTION_CHARS = 8


# Openers of small talk: a greeting or thanks is answered in a couple of
# seconds without tools, so a reaction only adds a false "let me look at the
# position…" and a second greeting in the answer.
_SMALL_TALK = (
    "привет", "здравствуй", "здравствуйте", "добрый", "доброе", "салем", "сәлем", "салам",
    "спасибо", "рахмет", "пока", "ок", "окей", "как дела",
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye",
)


def is_small_talk(message: str) -> bool:
    """A greeting, thanks or goodbye and nothing else. «ok and a skewer?» is a
    question that happens to open with "ok" — it went down this path and came
    back in English past the language gate (live flows, 2026-10-04)."""
    text = re.sub(r"[^\w\s]", " ", (message or "").lower()).strip()
    words = text.split()
    if len(words) > 4:
        return False
    if text in _SMALL_TALK:
        return True  # «Как дела?» is a greeting, question mark and all
    if "?" in (message or ""):
        return False
    for w in _SMALL_TALK:
        if text.startswith(w + " ") and len(words) - len(w.split()) <= 2:
            return True  # «спасибо большое», "thanks a lot" — not «ok and a skewer»
    return False


def wants_reaction(message: str, has_position: bool) -> bool:
    """Whether a turn deserves a first-stage reaction at all.

    Small talk ("Привет!", "спасибо", "hi!") never gets one — /coach always
    has a position on the board, and the live site answered "Привет" with
    "Привет, сейчас посмотрю, что на доске… Привет! Рад…" (2026-09-26). A
    question about a position on the board always gets one, however short.
    """
    words = (message or "").split()
    if not words or is_small_talk(message):
        return False
    if has_position:
        return True
    return len(words) >= 3


@dataclass
class QuickReply:
    text: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    first_token_ms: Optional[int] = None
    latency_ms: int = 0
    error: Optional[str] = None
    chunks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and len(self.text.strip()) >= MIN_REACTION_CHARS


SMALL_TALK_PROMPT = (
    "You are Chesster, a friendly chess coach sitting next to the student. The student's "
    "message is small talk — a greeting, thanks, a goodbye or \"how are you\". Reply in one or "
    "two short, warm sentences in {language} — whatever language their message is in. "
    "After a greeting, offer what you can do together: look at "
    "the position on their board, a puzzle, an idea to learn, a game against you. After thanks, "
    "say you are glad and offer a next step that fits the conversation. No moves, no "
    "evaluations, no markdown, at most one emoji."
)
SMALL_TALK_HISTORY_TURNS = 4
SMALL_TALK_HISTORY_CHARS = 400


def build_small_talk_messages(
    message: str, locale: Optional[str], history: Optional[list[tuple[str, str]]] = None,
) -> list[dict]:
    """The whole answer to small talk: the persona line, the last few turns for
    context (so "спасибо" after a lesson can suggest a fitting puzzle), the message.

    *locale* is the language of the answer, already chosen by the server
    (prompt_builder.conversation_language: what the student asked for, else the
    language they write in, else the interface language)."""
    from src.prompt_builder import kazakh_terms_note

    language = _LANGUAGE.get((locale or "").lower(), "the student's language")
    terms = kazakh_terms_note(locale)
    out = [{"role": "system", "content": SMALL_TALK_PROMPT.format(language=language) + (f"\n{terms}" if terms else "")}]
    for role, content in (history or [])[-SMALL_TALK_HISTORY_TURNS:]:
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:SMALL_TALK_HISTORY_CHARS]})
    out.append({"role": "user", "content": message.strip()})
    return out


def build_quick_messages(message: str, locale: Optional[str], board_fen: Optional[str]) -> list[dict]:
    """The two-message prompt for the reaction call.

    The student's message is passed as-is (already cleaned by the server); the
    board FEN is mentioned only as a hint that a position is on the board so the
    coach can say "looking at the position" — the model is not asked to read it.
    *locale* is the language of the reaction, chosen by the server (see
    build_small_talk_messages) — the small model guessed it from the message and
    reacted in Russian to an English question (production, 2026-10-01).
    """
    from src.prompt_builder import kazakh_terms_note

    language = _LANGUAGE.get((locale or "").lower(), "the student's language")
    terms = kazakh_terms_note(locale)
    system = QUICK_SYSTEM_PROMPT.format(language=language) + (f"\n{terms}" if terms else "")
    user = message.strip()
    if board_fen:
        # The coach page sends its board with every message, so this is only a
        # hint: "what should I study next?" came back as "let me look at the
        # position" (production, 2026-09-28).
        user = (f"[The student's board shows a position; it matters only if the question "
                f"is about it.]\n{user}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def stream_quick_reply(
    *,
    model: str,
    api_key: str,
    message: str,
    locale: Optional[str] = None,
    board_fen: Optional[str] = None,
    on_delta: Optional[Callable[[str], None]] = None,
    timeout_s: float = 4.0,
    max_tokens: int = 60,
    should_abort: Optional[Callable[[], bool]] = None,
    url: str = OPENROUTER_CHAT_URL,
) -> QuickReply:
    """Stream the reaction from OpenRouter, calling ``on_delta`` per text chunk.

    Never raises: any failure (network, HTTP status, malformed stream) comes back
    in ``QuickReply.error`` and the caller silently skips the first stage.
    ``should_abort`` is polled between chunks so the caller can stop the
    reaction the moment the full answer starts arriving.
    """
    return stream_completion(
        model=model, api_key=api_key,
        messages=build_quick_messages(message, locale, board_fen),
        on_delta=on_delta, timeout_s=timeout_s, max_tokens=max_tokens,
        should_abort=should_abort, url=url, temperature=0.6,
    )


def _payload(model: str, messages: list[dict], max_tokens: int, temperature: float) -> dict:
    from src.config import COACH_PROVIDER_SORT
    from src.llm_transport import reasoning_for

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        # These calls must not think first — the wait is what they exist to avoid.
        # Gemini 3 cannot switch thinking off, only down to "minimal".
        "reasoning": reasoning_for(model) or {"enabled": False},
        "usage": {"include": True},
    }
    if COACH_PROVIDER_SORT:
        payload["provider"] = {"sort": COACH_PROVIDER_SORT}
    return payload


class _HttpError(Exception):
    pass


class _EventStream:
    """The parsed SSE events of one streamed completion, tagged with its model."""

    def __init__(self, response: httpx.Response, model: str):
        self.response = response
        self.model = model

    def __iter__(self):
        try:
            done = False
            for line in self.response.iter_lines():
                # Read on past [DONE] to the end of the body: a response closed
                # early takes its connection with it instead of back to the pool.
                if done or not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    continue
                try:
                    yield (self.model, json.loads(data))
                except json.JSONDecodeError:
                    continue
        finally:
            self.response.close()

    def close(self) -> None:
        self.response.close()


def _open(client: httpx.Client, url: str, payload: dict, headers: dict, timeout_s: float) -> _EventStream:
    request = client.build_request("POST", url, json=payload, headers=headers,
                                   timeout=httpx.Timeout(timeout_s, read=timeout_s))
    response = client.send(request, stream=True)
    if response.status_code != 200:
        body = response.read()[:300].decode("utf-8", "replace")
        response.close()
        raise _HttpError(f"http_{response.status_code}: {body}")
    return _EventStream(response, payload["model"])


def _says_something(item) -> bool:
    _, event = item
    if event.get("usage"):
        return True
    choices = event.get("choices") or []
    return bool(choices and ((choices[0].get("delta") or {}).get("content") or choices[0].get("finish_reason")))


def _http() -> httpx.Client:
    from src.llm_transport import shared_http

    return shared_http()


def stream_completion(
    *,
    model: str,
    api_key: str,
    messages: list[dict],
    on_delta: Optional[Callable[[str], None]] = None,
    timeout_s: float = 4.0,
    max_tokens: int = 60,
    should_abort: Optional[Callable[[], bool]] = None,
    url: str = OPENROUTER_CHAT_URL,
    temperature: float = 0.6,
    hedge_ms: Optional[int] = None,
) -> QuickReply:
    """One tool-free, no-reasoning streamed completion (the reaction, a game
    comment): plain httpx against OpenRouter, never raises — see QuickReply.error.

    It goes over the shared connection pool, and when *model* is silent for
    ``hedge_ms`` (COACH_QUICK_HEDGE_MS) the fallback model gets the same request;
    the first to answer is streamed and ``QuickReply.model`` names it.
    """
    from src import llm_transport

    reply = QuickReply(model=model)
    started = time.monotonic()
    if not api_key:
        reply.error = "no_api_key"
        return reply

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://chesster.io",
        "X-Title": "Chesster coach (quick reaction)",
    }
    delay_ms = llm_transport.QUICK_HEDGE_MS if hedge_ms is None else hedge_ms
    backup = llm_transport.hedge_model_for(model) if delay_ms > 0 else None
    parts: list[str] = []
    events = None
    try:
        client = _http()
        primary = _open(client, url, _payload(model, messages, max_tokens, temperature), headers, timeout_s)
        open_backup = None
        if backup:
            def open_backup():
                return _open(client, url, _payload(backup, messages, max_tokens, temperature), headers, timeout_s)
        events = llm_transport.race(primary, open_backup, delay_ms / 1000.0, _says_something)
        for served, event in events:
            if should_abort and should_abort():
                reply.error = "aborted"
                break
            reply.model = served
            usage = event.get("usage")
            if isinstance(usage, dict):
                reply.prompt_tokens = int(usage.get("prompt_tokens") or 0)
                reply.completion_tokens = int(usage.get("completion_tokens") or 0)
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {}).get("content")
            if not delta:
                continue
            if reply.first_token_ms is None:
                reply.first_token_ms = int((time.monotonic() - started) * 1000)
            parts.append(delta)
            reply.chunks.append(delta)
            if on_delta:
                on_delta(delta)
    except _HttpError as exc:
        reply.error = str(exc)
    except httpx.TimeoutException:
        reply.error = "timeout"
    except Exception as exc:  # noqa: BLE001 — the first stage is best-effort
        reply.error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if events is not None:
            events.close()
        reply.latency_ms = int((time.monotonic() - started) * 1000)
    # Exactly what the student saw (the chunks were streamed as they came), so
    # the stored message and the screen agree; only surrounding whitespace goes.
    reply.text = "".join(parts).strip()
    if reply.error and reply.error != "aborted":
        logger.info("quick reaction failed (%s) on %s after %d ms", reply.error, model, reply.latency_ms)
    return reply
