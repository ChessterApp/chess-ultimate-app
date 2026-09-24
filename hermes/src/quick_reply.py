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
fallback and tool loop are exactly the latency this stage exists to hide.
"""

from __future__ import annotations

import json
import logging
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
    "reaction: one short sentence, at most 20 words, in {language}.\n"
    "Acknowledge what the student asked and say what you are about to check or "
    "look at — the line, the opening, the game, the database, or the position "
    "(mention the position ONLY if the message says one is on the board).\n"
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


def wants_reaction(message: str, has_position: bool) -> bool:
    """Whether a turn deserves a first-stage reaction at all.

    A greeting or a two-word aside ("Привет!", "спасибо", "ok") is answered in
    a few seconds without tools, and a reaction there reads as a false promise
    ("let me look at the position…"). A question about a position on the board
    always gets one, however short it is.
    """
    words = (message or "").split()
    if has_position:
        return bool(words)
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


def build_quick_messages(message: str, locale: Optional[str], board_fen: Optional[str]) -> list[dict]:
    """The two-message prompt for the reaction call.

    The student's message is passed as-is (already cleaned by the server); the
    board FEN is mentioned only as a hint that a position is on the board so the
    coach can say "looking at the position" — the model is not asked to read it.
    """
    language = _LANGUAGE.get((locale or "").lower(), "the student's language")
    system = QUICK_SYSTEM_PROMPT.format(language=language)
    user = message.strip()
    if board_fen:
        user = f"[A position is set up on the student's board.]\n{user}"
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
) -> QuickReply:
    """One tool-free, no-reasoning streamed completion (the reaction, a game
    comment): plain httpx against OpenRouter, never raises — see QuickReply.error."""
    reply = QuickReply(model=model)
    started = time.monotonic()
    if not api_key:
        reply.error = "no_api_key"
        return reply

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        # These calls must not think first — the wait is what they exist to avoid.
        "reasoning": {"enabled": False},
        "usage": {"include": True},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://chesster.io",
        "X-Title": "Chesster coach (quick reaction)",
    }
    parts: list[str] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, read=timeout_s)) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = resp.read()[:300].decode("utf-8", "replace")
                    reply.error = f"http_{resp.status_code}: {body}"
                    return reply
                for line in resp.iter_lines():
                    if should_abort and should_abort():
                        reply.error = "aborted"
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
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
    except httpx.TimeoutException:
        reply.error = "timeout"
    except Exception as exc:  # noqa: BLE001 — the first stage is best-effort
        reply.error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        reply.latency_ms = int((time.monotonic() - started) * 1000)
    # Exactly what the student saw (the chunks were streamed as they came), so
    # the stored message and the screen agree; only surrounding whitespace goes.
    reply.text = "".join(parts).strip()
    if reply.error and reply.error != "aborted":
        logger.info("quick reaction failed (%s) on %s after %d ms", reply.error, model, reply.latency_ms)
    return reply
