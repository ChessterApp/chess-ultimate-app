"""A lesson of the site is always given as a link with a name — never as a raw address (17.11).

Tester's report of 16.11: the coach's answer ended with a bare «chesster.io/learn/chess-basics/…». The site
(ReactMarkdown) and the mobile app (its markdown parser) both show ``[text](url)`` as a link that opens the lesson
and print a bare address as plain text; the page's reader strips a markdown link to its words and would read a
scheme-less address aloud (frontend/src/lib/coach/voice-pipeline.ts ``speakable``).

Whether the model writes the link form is its choice — the prompt and the tools' hints ask for it —, so the server
rewrites what is left: every lesson address of the outgoing answer that is not already the destination of a
markdown link — with or without a scheme, chesster.io or a school's host (chess-empire.chesster.io) — becomes
``[title](https://…)``. The title is the lesson's own, from the data the turn's tools returned for that address;
with none, a neutral word in the answer's language. ``LessonLinks`` does it on a stream: an address that may still
be growing at the end of a delta is held until the text after it shows where it ends.
"""

import json
import re
from typing import Callable, Iterable, Optional

# What an address is made of here: the characters a lesson's path can hold. Brackets, quotes, asterisks and
# backticks are markdown's or the sentence's and end it.
_URL_CHARS = r"A-Za-z0-9._~:/?#@&+=%-"
_HOST = r"(?:www\.)?(?:[a-z0-9-]+\.)*chesster\.io"
# …/learn, …/learn/course, …/learn/course/lesson — not «…/learning».
_ADDRESS = rf"(?:https?://)?{_HOST}/learn(?:[/?#][{_URL_CHARS}]*|(?![\w-]))"
_FIND = re.compile(
    r"(?P<md>\[(?P<label>[^\]\n]*)\]\((?P<dest>[^)\s]*)(?:\s+\"[^\"\n]*\")?\))"   # [text](url): the destination is kept
    rf"|<(?P<auto>{_ADDRESS})>"                                                    # <https://…>
    rf"|(?P<tick>`+)\s*(?P<code>{_ADDRESS})\s*(?P=tick)"                           # `chesster.io/learn/…`
    rf"|(?<![\w@./-])(?P<bare>{_ADDRESS})",
    re.IGNORECASE)
_WHOLE = re.compile(_ADDRESS, re.IGNORECASE)
_TAIL = re.compile(rf"[`{_URL_CHARS}]+$")  # with the backticks of a code span around it
_LEARN_PATH = re.compile(r"/learn(?:/[^?#]*)?", re.IGNORECASE)

# The neutral words, by what the address is: a lesson (/learn/course/lesson), a course page, the programme.
_LABELS = {
    "ru": ("урок", "курс", "уроки"),
    "en": ("lesson", "course", "lessons"),
    "kz": ("сабақ", "курс", "сабақтар"),
}
_LABELS["kk"] = _LABELS["kz"]

_CONTEXT = 300   # emitted text kept to see a markdown link that began in it
_MAX_HOLD = 400  # a held tail longer than this is no address


def _path_key(url: str) -> str:
    """The address by its path — /learn/course/lesson, lower case, no trailing slash: the same lesson whatever
    the host (the tools give chesster.io, a school's student sees its own) or the scheme."""
    m = _LEARN_PATH.search(url or "")
    return m.group(0).rstrip("/").lower() if m else ""


def _link_text(title: str) -> str:
    """*title* as the text of a markdown link: one line, no square brackets."""
    return re.sub(r"\s+", " ", re.sub(r"[\[\]]", "", str(title or ""))).strip()


def lesson_md(title: str, url: str) -> str:
    """The lesson as the server itself writes it: [«title»](url)."""
    return f"[«{_link_text(title)}»]({url})"


def known_lessons(sources: Iterable) -> dict:
    """{path: title} of every lesson or course address in the tools' results of the turn (*sources*: JSON strings or
    parsed values) — any object with a /learn/ ``url`` and a ``title`` (get_lesson, get_learning_path, get_topic's
    example and site_lessons, training_recommender) or a ``lesson`` name (a task of a set, get_puzzle). An address
    two different titles share (a lesson without a slug falls back to its course's page) names neither."""
    found: dict = {}
    clash: set = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and "/learn" in url:
                title = node.get("title") if isinstance(node.get("title"), str) else node.get("lesson")
                key = _path_key(url)
                if key and isinstance(title, str) and _link_text(title):
                    if found.setdefault(key, _link_text(title)) != _link_text(title):
                        clash.add(key)
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    for raw in sources or []:
        try:
            walk(json.loads(raw) if isinstance(raw, str) else raw)
        except (TypeError, ValueError):
            continue
    return {k: v for k, v in found.items() if k not in clash}


def _label(address: str, lessons: dict, language: Optional[str]) -> str:
    key = _path_key(address)
    if key in lessons:
        return lessons[key]
    words = _LABELS.get((language or "ru").lower(), _LABELS["ru"])
    depth = len([p for p in key.split("/") if p]) - 1  # segments after /learn
    return words[0] if depth >= 2 else words[1] if depth == 1 else words[2]


def _split_end(address: str) -> tuple[str, str]:
    """(the address, the sentence's punctuation that came with it): «…/learn/a/b.» ends a sentence."""
    core = address.rstrip(".:?")
    return core, address[len(core):]


def _absolute(address: str) -> str:
    return address if re.match(r"https?://", address, re.IGNORECASE) else "https://" + address


def _rewrite(text: str, lessons: dict, language: Optional[str], start: int = 0) -> str:
    """*text* from *start* on with its lesson addresses as named links; what stands before *start* is context only
    (text already sent: a markdown link that began there is left as it is)."""
    out, pos = [], start
    for m in _FIND.finditer(text):
        if m.end() <= start:
            continue
        if m.start() < start:
            # A link that began in the text already sent: its rest goes out untouched.
            out.append(text[pos:m.end()])
            pos = m.end()
            continue
        out.append(text[pos:m.start()])
        pos = m.end()
        if m.group("md") is not None:
            label, dest = m.group("label"), m.group("dest")
            bare = re.sub(r"[*_`\s]", "", label)
            if _WHOLE.fullmatch(_split_end(bare)[0] or " ") and _path_key(dest):
                # «[chesster.io/learn/a/b](https://chesster.io/learn/a/b)»: a link, but its text is the raw address.
                out.append(f"[{_label(dest, lessons, language)}]({dest})")
            else:
                out.append(m.group(0))
            continue
        address, end = _split_end(m.group("auto") or m.group("code") or m.group("bare"))
        out.append(f"[{_label(address, lessons, language)}]({_absolute(address)}){end}")
    out.append(text[pos:])
    return "".join(out)


def link_lessons(text: str, sources: Iterable = (), language: Optional[str] = "ru") -> str:
    """*text* (a whole answer) with every bare lesson address as a named markdown link."""
    if not text or "/learn" not in text.lower():
        return text
    return _rewrite(text, known_lessons(sources), language)


def _may_grow(tail: str) -> bool:
    """*tail* — the address characters the text ends with — may be a lesson address still being written: one that
    reaches the end of the text, or the start of one — a scheme («ht», «https://chess-emp»), a host («chess-empire»
    before its «.chesster.io»), «chesster.io/le». A host cannot be told from a word until its dot and slash come,
    so a run of host characters waits too — for the next delta only: the space after a word lets it go."""
    t = tail.lower()
    for scheme in ("https://", "http://"):
        if t.startswith(scheme):
            t = t[len(scheme):]
            break
        if scheme.startswith(t):
            return True
    if "/" not in t:
        return bool(re.fullmatch(r"(?:[a-z0-9][a-z0-9.-]*)?", t))  # a sentence's lone «.» or «—» is no host
    host, path = t.split("/", 1)
    if not re.fullmatch(_HOST, host):
        return False
    return "learn".startswith(path) or (path.startswith("learn") and path[5] in "/?#")


# «[text]» or «[text](destination so far» at the end of the text: a markdown link that may still be closing.
_OPEN_LINK = re.compile(rf"\[[^\[\]\n]{{1,200}}\](?:\([^()\s]{{0,{_MAX_HOLD}}})?$")


class LessonLinks:
    """The rewrite on a stream: ``feed`` the answer's text as it goes out, ``flush`` at its end.

    *sources* is asked at every rewrite — the turn's tool results grow while the answer is written."""

    def __init__(self, sources: Optional[Callable[[], Iterable]] = None, language: Optional[str] = "ru") -> None:
        self._sources = sources
        self._language = language
        # The end of the text that may be an unfinished address (with the link opened before it): checked text
        # that goes out next — part of what the student is shown.
        self.held = ""
        self._context = ""  # the last text sent, as it was written

    def _lessons(self) -> dict:
        try:
            return known_lessons(self._sources() if self._sources else ())
        except Exception:  # noqa: BLE001 — without the titles the neutral word still names the link
            return {}

    def _send(self, text: str) -> str:
        if not text:
            return ""
        if "/learn" in (self._context + text).lower():
            out = _rewrite(self._context + text, self._lessons(), self._language, start=len(self._context))
        else:
            out = text
        self._context = (self._context + text)[-_CONTEXT:]
        return out

    def feed(self, text: str) -> str:
        buf = self.held + (text or "")
        cut = len(buf)
        m = _TAIL.search(buf)
        if m and len(m.group(0)) <= _MAX_HOLD and _may_grow(m.group(0).replace("`", "")):
            cut = m.start()
        # The markdown the address stands in waits with it: «[chess», «<https», «`chess» — and a link that may still
        # be closing, «[урок](https://chess», «[chesster.io/learn/a]»: judged whole, its destination is never
        # rewritten and its text is, when the text is the raw address.
        while cut > 0 and buf[cut - 1] in "[<":
            cut -= 1
        opened = _OPEN_LINK.search(buf)
        if opened:
            cut = min(cut, opened.start())
        self.held = buf[cut:]
        return self._send(buf[:cut])

    def flush(self) -> str:
        held, self.held = self.held, ""
        return self._send(held)
