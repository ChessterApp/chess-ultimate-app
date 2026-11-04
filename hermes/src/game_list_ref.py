"""«Загрузи третью из списка», «а следующую?»: a game of the list the coach showed, resolved on the server.

The live run of 04.11 (f2, f1): after a search listed eight games, «загрузи третью из списка» loaded the fifth — the
model searched again by two names it picked itself — and «а следующую?» loaded «the fourth» after the fifth. The
next turn's history holds only the text of the list, never the games' ids, and nothing checked the number.

Now the session keeps the games of the last search that found some, in the order the tool returned them, and the
id of the game loaded last (``Session.note_db_list`` / ``note_db_loaded``). A message that points into that list —
by its number («третью», «3-ю», «№3», "the third", «үшінші»), «последнюю из списка», «следующую» / «предыдущую» —
gets a note with the list numbered as the coach's own answer showed it (its items matched to the games by the
players' names, in any script), the game meant, and its id to load with get_game_pgn — no new search.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional

import chess

_B = r"(?<![\w-])"
_E = r"(?![\w-])"

_ORDINAL_WORDS = [
    (1, r"перв\w*|first|бірінші"), (2, r"втор\w*|second|екінші"), (3, r"треть\w*|трет\w+|third|үшінші"),
    (4, r"четв[её]рт\w*|fourth|төртінші"), (5, r"пят\w+|fifth|бесінші"), (6, r"шест\w+|sixth|алтыншы"),
    (7, r"седьм\w*|seventh|жетінші"), (8, r"восьм\w*|eighth|сегізінші"), (9, r"девят\w+|ninth|тоғызыншы"),
    (10, r"десят\w+|tenth|оныншы"),
]
_ORDINAL = re.compile(_B + r"(?:" + "|".join(f"(?P<n{n}>{rx})" for n, rx in _ORDINAL_WORDS) + r")" + _E,
                      re.IGNORECASE)
# «3-ю», «3-ю партию», «№3», «номер 3», «#3», "number 3", "3rd"
_NUMBERED = re.compile(r"(?:№|#|номер\s*|number\s*|no\.\s*)(?P<a>\d{1,2})(?!\d)|(?<!\d)(?P<b>\d{1,2})\s*-?\s*(?:ю|я|й|ую|"
                       r"ая|ой|ый|ое|е|th|st|nd|rd)" + _E, re.IGNORECASE)
_LAST = re.compile(_B + r"(?:последн\w*|last|соңғы)" + _E, re.IGNORECASE)
_NEXT = re.compile(_B + r"(?:следующ\w*|next|келесі\w*|дальше\s+по\s+списку)" + _E, re.IGNORECASE)
_PREV = re.compile(_B + r"(?:предыдущ\w*|previous|алдыңғы\w*)" + _E, re.IGNORECASE)
_LIST_WORD = re.compile(_B + r"(?:спис\w*|перечн\w*|list\w*|тізім\w*)" + _E, re.IGNORECASE)
_GAME_WORD = re.compile(_B + r"(?:парти\w*|игр\w*|game\w*|её|ее|ее|it|загрузи\w*|покажи\w*|открой|поставь|"
                        r"load|show|open|put|жүкте\w*|көрсет\w*|ашып?)" + _E, re.IGNORECASE)
# «Следующий ход», «первый ход», «в пятой позиции»: a move, a position, a puzzle — not a game of the list.
_OTHER_THING = re.compile(_B + r"(?:ход\w*|move\w*|позици\w*|position\w*|задач\w*|пазл\w*|puzzle\w*|урок\w*|"
                          r"lesson\w*|тем\w*|вариант\w*|линию|line|стрелк\w*|жүріс\w*)" + _E, re.IGNORECASE)


def list_reference(message: str) -> Optional[tuple]:
    """("n", k) / ("last",) / ("next",) / ("prev",) when *message* points into a list of games, else None."""
    text = (message or "").strip()
    if not text or _OTHER_THING.search(text):
        return None
    listed = bool(_LIST_WORD.search(text))
    short = len(text.split()) <= 6
    about_game = listed or bool(_GAME_WORD.search(text))
    m = _ORDINAL.search(text)
    if m and (about_game or short):
        n = next(int(k[1:]) for k, v in m.groupdict().items() if v)
        return ("n", n)
    m = _NUMBERED.search(text)
    if m and (about_game or short):
        return ("n", int(m["a"] or m["b"]))
    if _LAST.search(text) and listed:
        return ("last",)  # «последняя партия Накамуры» is his latest game, not the list's last one
    if _NEXT.search(text) and (about_game or short):
        return ("next",)
    if _PREV.search(text) and (about_game or short):
        return ("prev",)
    return None


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def _close(token: str, side: str) -> bool:
    """*token* («Фируджа», «Альтамира» — the model's own spelling) is close to the surname of *side* («Firouzja,
    Alireza», «Martínez Alcántara,José Eduardo»): its Latin spellings against the surname's words."""
    from src.player_names import name_patterns

    words = [w for w in re.split(r"[\s,]+", _plain(side).split(",")[0]) if len(w) >= 4]
    spellings = [p.strip("%").replace("_", "").lower() for p in name_patterns(token)] or [_plain(token)]
    return any(difflib.SequenceMatcher(None, s, w).ratio() >= 0.65 for s in spellings for w in words)


def _sides_in(item: str, game: dict) -> int:
    """How many of *game*'s players the list item names, in any spelling close enough."""
    from src.answer_check_db import _sides_named
    from src.player_names import _NAME_TOKEN

    white, black = game.get("white_name") or "", game.get("black_name") or ""
    named = _sides_named(item, {"White": white, "Black": black})
    tokens = [t for t in _NAME_TOKEN.findall(item) if len(t) >= 4 and t[0].isupper()]
    count = 0
    for color, side in ((chess.WHITE, white), (chess.BLACK, black)):
        if color in named or any(_close(t, side) for t in tokens):
            count += 1
    return count


def shown_order(answer: str, games: list) -> list:
    """The games' ids in the order the coach's answer listed them: each item line («1) Накамура — Карлсен…»,
    «- 18.10: Синдаров — Каруана…») matched to the one game both of whose players it names. Numbers written on the
    items are kept («3) …» is #3). [] when the answer holds no such list."""
    numbers: list = []
    seq: list = []
    for line in (answer or "").splitlines():
        item = re.match(r"\s*(?:(?P<n>\d{1,2})\s*[.)]|[-•*–—])\s+(?P<rest>.+)", line)
        if not item:
            continue
        scored = []
        for g in games:
            sides = _sides_in(item["rest"].split("(")[0], g)
            if sides:
                scored.append((sides, g.get("id")))
        best = max((s for s, _ in scored), default=0)
        top = {gid for s, gid in scored if s == best}
        if not best:
            continue  # not an item of the list («- Можно ещё посмотреть…»)
        seq.append(next(iter(top)) if len(top) == 1 else None)  # None: an item that names no one game
        numbers.append(int(item["n"]) if item["n"] else None)
    ids = [g.get("id") for g in games]
    missing = [gid for gid in ids if gid not in seq]
    if seq.count(None) == 1 and len(missing) == 1:
        seq[seq.index(None)] = missing[0]  # the one item not told apart is the one game left
    if len(seq) < 2 or None in seq or len(set(seq)) != len(seq):
        return []
    if all(n is not None for n in numbers) and len(set(numbers)) == len(numbers):
        return [gid for _, gid in sorted(zip(numbers, seq))]
    return seq


def _label(g: dict) -> str:
    return (f"id {g.get('id')} — {g.get('white_name') or '?'} – {g.get('black_name') or '?'}, "
            f"{g.get('event') or ''} {g.get('date') or ''}, {g.get('result') or ''}").strip()


def list_note(message: str, games: list, loaded_id=None, previous_answer: str = "") -> str:
    """The note for the model when *message* points into the session's last list of games; "" otherwise."""
    ref = list_reference(message)
    if not ref or not games:
        return ""
    by_id = {g.get("id"): g for g in games if isinstance(g, dict) and g.get("id") is not None}
    order = shown_order(previous_answer, list(by_id.values()))
    if not order and previous_answer and re.search(r"(?m)^\s*(?:\d{1,2}\s*[.)]|[-•*])\s+", previous_answer):
        # a list was shown, but its items could not all be told apart: the numbers are not ours to guess
        order, unsure = list(by_id), True
    else:
        order, unsure = order or list(by_id), False
    if len(order) < 2:
        return ""
    at = order.index(loaded_id) if loaded_id in order else None
    if ref[0] == "n":
        pick = ref[1] - 1
    elif ref[0] == "last":
        pick = len(order) - 1
    elif ref[0] == "next":
        pick = at + 1 if at is not None else None
    else:
        pick = at - 1 if at is not None else None
    if unsure:
        # the answer's list could not be matched item by item: no number of ours, the model counts in its own list
        lines = [f"- {_label(by_id[gid])}" for gid in order]
        return ("## The list of games the student refers to\nThe games your search found on an earlier turn (not in "
                "the order your answer listed them):\n" + "\n".join(lines) + "\nCount the student's number in the "
                "list YOUR previous answer showed, find that game here by its two players, and load it by its id "
                "with get_game_pgn(show=true) — no new search; name it by the players and its number in your list.")
    lines = [f"{i + 1}. {_label(by_id[gid])}" for i, gid in enumerate(order)]
    note = ("## The list of games the student refers to\nThe games your search found on an earlier turn, numbered as "
            "your answer listed them:\n" + "\n".join(lines))
    if at is not None:
        note += f"\nThe game loaded last is #{at + 1} (id {order[at]})."
    if pick is None or not 0 <= pick < len(order):
        return note + ("\nThe number the student gave is not in this list: say so and ask which game they mean — do "
                       "not search again or load another game.")
    g = by_id[order[pick]]
    return note + (f"\nThe student means #{pick + 1}: {_label(g)}. Load exactly this game: get_game_pgn(game_id="
                   f"{g.get('id')}, show=true) — no new search — and name it as #{pick + 1} of the list, by these "
                   "players.")
