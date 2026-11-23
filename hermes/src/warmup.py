"""The warm-up is a set of exactly N puzzles: each has its place, and after the last one it ends (18.11).

Tester's report of 17.11: the daily plan's card promised five puzzles — «solved five, then a sixth came, then a
seventh; nowhere is it shown which puzzle of the set this is, and there is no summary at the end». The set of 17.11
was only a queue (src/sessions.Session.puzzle_queue): once it ran dry, the puzzle panel's «Дальше» — it sends the
plain «Дай мне тактическую задачу» — was the programme's next task again, and the place of a puzzle in the set was
left to the model's counting.

The session now keeps the warm-up itself (``Session.warmup``, not serialized — as the queue it frames):

* its puzzles in their order — the place of a puzzle («Задача 2 из 5») is its index, read here and written by the
  server at the head of the answer (``place_line``), whoever put the puzzle up;
* which of them the board showed solved — the final position of the puzzle's solution reached on a board of the
  session (the page reports the board after every move; a move of the puzzle is checked by the page before it
  counts) — and which the system showed the solution of at the student's request (src/solution_guard.reveal);
* its end: the next request for a puzzle after the last one of the set — «дальше», the panel's button — sets no
  puzzle; the answer is the ending (``over_result``), with the count of solved ones when every puzzle of the set is
  accounted for (solved on the board, or its solution shown). A puzzle answered only in words, or skipped, leaves
  the count unknown: the server did not see the answer, so the coach says only that the warm-up of N is over. The
  ending also sets the board's own position again (``_close_actions``): the page leaves its puzzle mode, so the
  ending is seen and the puzzle panel's «Дальше» is not left to bring a sixth puzzle (the Android app, 18.11).

A request that names a theme, «любую», a new warm-up or anything else that lines up other puzzles drops the frame
(``Session.set_puzzle_queue``); so does a warm-up the student has left — its last puzzle no longer on the board and
put up more than ``END_TURNS`` of their messages ago. Outside a warm-up nothing changes.
"""

from __future__ import annotations

import time
from typing import Optional

# The ending is said for a request that comes while the warm-up is still what the student is doing: its last puzzle
# is on the board (anywhere along its solution), or went up at most this many of their messages ago.
END_TURNS = 6
# A set of one puzzle is a puzzle, not a set: no place, no ending.
MIN_SET = 2
# The model's own get_puzzle call for words the system has just answered — the turn's puzzle step, the voice page's
# call (SYSTEM_CALLERS) — is the same request: the same words, within the same message of the student and this many
# seconds. It gets the same answer, not the next puzzle of the set and never a puzzle after the ending. Two calls of
# the system are two requests (the panel's «Дальше» pressed twice), whatever their words.
REPEAT_S = 30.0
SYSTEM_CALLERS = ("turn", "site")

_PLACE = {
    "ru": "Задача {n} из {of}.",
    "en": "Puzzle {n} of {of}.",
    "kk": "{n}-есеп, барлығы {of}.",
}
_OVER_COUNTED = {
    "ru": "Разминка окончена: решено {solved} из {of}.",
    "en": "The warm-up is over: {solved} of {of} solved.",
    "kk": "Жаттығу аяқталды: {of} есептің ішінен {solved} есеп шешілді.",
}
_PAUSED = {
    "ru": "Разминка прервана на задаче {n} из {of}.",
    "en": "The warm-up is paused at puzzle {n} of {of}.",
    "kk": "Жаттығу {of} есептің {n}-есебінде тоқтатылды.",
}
_OVER = {
    "ru": "Разминка из {of} задач окончена.",
    "en": "The warm-up of {of} puzzles is over.",
    "kk": "{of} есептен тұратын жаттығу аяқталды.",
}


def _lang(language: Optional[str]) -> str:
    code = (language or "ru").lower()[:2]
    return "kk" if code in ("kk", "kz") else code if code in _PLACE else "ru"


def _key(fen: Optional[str]) -> str:
    """Pieces and side to move: what tells a position of a puzzle's line (clocks and en passant differ by source)."""
    from src.boards import line_key

    return line_key(fen)


def line_keys(fen: str, solution: list) -> list:
    """The positions of a puzzle from its start to the end of its solution (SAN or UCI moves), as keys; the keys up
    to the first move that does not fit."""
    from src.boards import puzzle_line_keys

    return puzzle_line_keys(fen, solution)


def start(session, puzzles: list) -> Optional[dict]:
    """A warm-up of *puzzles* begins: the first is the one going on the board, the rest are lined up. Returns the
    place of the first, or None when the set is too small to be one (the puzzles are lined up all the same)."""
    puzzles = [p for p in (puzzles or []) if isinstance(p, dict) and p.get("fen") and p.get("puzzle_id")]
    session.set_puzzle_queue(puzzles[1:], theme="")
    if len(puzzles) < MIN_SET:
        return None
    ids = [str(p["puzzle_id"]) for p in puzzles]
    session.set_warmup({
        "ids": ids,
        "lines": {str(p["puzzle_id"]): line_keys(p["fen"], p.get("solution") or []) for p in puzzles},
        "at": 0,
        "up_turn": session.user_turns(),
        "solved": set(),
        "shown": set(),
        "over": False,
        "last": None,
    })
    return {"n": 1, "of": len(ids)}


def place_of(session, puzzle_id) -> Optional[dict]:
    """{"n", "of"} of *puzzle_id* in the session's warm-up, or None (no warm-up, not one of its puzzles)."""
    state = getattr(session, "warmup", None)
    if not state or str(puzzle_id) not in state["ids"]:
        return None
    return {"n": state["ids"].index(str(puzzle_id)) + 1, "of": len(state["ids"])}


def put_up(session, puzzle_id=None, fen: Optional[str] = None) -> None:
    """A puzzle went on the board (by its id, else by its position): when it is one of the warm-up's, the warm-up is
    at it now, and it and the ones before it leave the queue — the server's step, the model's own board_control
    set_puzzle and the voice tools alike."""
    state = getattr(session, "warmup", None)
    if not state:
        return
    pid = str(puzzle_id) if puzzle_id not in (None, "") else None
    if pid not in state["ids"]:
        pid = next((i for i in state["ids"] if fen and (state["lines"].get(i) or [None])[0] == _key(fen)), None)
    if pid is None:
        return
    at = state["ids"].index(pid)
    state["paused_said"] = False  # back at the warm-up: a later break is said again
    if at != state["at"]:
        state["at"] = at
        state["up_turn"] = session.user_turns()
    gone = set(state["ids"][:at + 1])
    session.trim_puzzle_queue(gone)


def note_board(session, board) -> None:
    """*board* was saved: when it shows the final position of a puzzle of the warm-up, that puzzle was solved on the
    board — unless the system had shown its solution."""
    state = getattr(session, "warmup", None)
    if not state or state.get("over") or board is None:
        return
    key = _key(getattr(board, "fen", None))
    for pid, keys in state["lines"].items():
        if len(keys) > 1 and keys[-1] == key and pid not in state["shown"]:
            state["solved"].add(pid)


def note_shown(session, puzzle_id) -> None:
    """The system showed the solution of *puzzle_id* at the student's request: not one they solved."""
    state = getattr(session, "warmup", None)
    if state and str(puzzle_id) in state["ids"] and str(puzzle_id) not in state["solved"]:
        state["shown"].add(str(puzzle_id))


def _on_the_board(session, state) -> bool:
    board = session.active_board() if getattr(session, "boards", None) else None
    keys = state["lines"].get(state["ids"][state["at"]]) or []
    return board is not None and _key(board.fen) in keys


def _alive(session, state) -> bool:
    return session.user_turns() - state["up_turn"] <= END_TURNS or _on_the_board(session, state)


def ending_due(session) -> bool:
    """The session's warm-up has shown its last puzzle and waits for its ending: the next «дальше» is about it. A
    warm-up the student has left is dropped here."""
    state = getattr(session, "warmup", None)
    if not state or state.get("over") or session.puzzle_queue:
        return False
    if not _alive(session, state):
        session.set_warmup(None)
        return False
    return True


def _request(session, words: Optional[str]) -> tuple:
    return " ".join((words or "").lower().split()), session.user_turns()


def remember(session, words: Optional[str], result: dict, caller: Optional[str] = None) -> dict:
    """*result* is what the warm-up answered the request *words* of *caller* with (a puzzle of the set with its
    place, or the ending): the model's call for the same request gets it again (``same_request``). Returns *result*."""
    state = getattr(session, "warmup", None)
    if state:
        state["last"] = {"request": _request(session, words), "at": time.monotonic(), "result": result,
                         "system": caller in SYSTEM_CALLERS}
    return result


def same_request(session, words: Optional[str], caller: Optional[str] = None) -> Optional[dict]:
    """What the warm-up has already answered this very request with, when *caller* is the model asking again for
    words the system answered — or anyone asking again right after the ending; None otherwise."""
    last = (getattr(session, "warmup", None) or {}).get("last")
    if not last or last["request"] != _request(session, words) or time.monotonic() - last["at"] > REPEAT_S:
        return None
    if last["result"].get("warmup_over") and not (caller in SYSTEM_CALLERS and last["system"]):
        return last["result"]   # the ending moves nothing: said again, it is still the ending
    return last["result"] if last["system"] and caller not in SYSTEM_CALLERS else None


def over_result(session, words: Optional[str], caller: Optional[str] = None) -> Optional[dict]:
    """The ending of the session's warm-up for a plain request for the next puzzle — a get_puzzle-shaped result with
    no puzzle — or None: no warm-up, puzzles of it still lined up, or one the student has left. Once the ending is
    said the next request goes on as any other (``same_request`` answers the same one arriving again)."""
    state = getattr(session, "warmup", None)
    if not state:
        return None
    if state.get("over"):
        session.set_warmup(None)
        return None
    if not ending_due(session):
        return None
    board = session.active_board() if getattr(session, "boards", None) else None
    note_board(session, board)
    result = _result(state, _close_actions(state, board))
    state["over"] = True
    return remember(session, words, result, caller)


def _close_actions(state: dict, board) -> list:
    """The puzzle mode ends with the warm-up (tester, 18.11): the board's own position set again (``set_fen``) —
    the site and the app leave their puzzle panel on it, so the ending is what the student sees, and the panel's
    «Дальше», still on the solved fifth puzzle, is not there to bring a sixth one.

    The Android app hid the ending behind that panel: at its smallest the sheet shows the panel instead of the coach's
    last line, the ending changed nothing on the board, and «Дальше» pressed once more — the warm-up over by then —
    was the programme's next task: «после пятой нажал "Дальше" и пришла шестая», «итога разминки нет».

    Only while the board shows a position of one of the warm-up's puzzles: a board the student has put something
    else on (a game in its tab) is left alone."""
    if board is None or getattr(board, "kind", None) == "game":
        return []
    key = _key(getattr(board, "fen", None))
    if not any(key in keys for keys in state["lines"].values()):
        return []
    return [{"type": "set_fen", "fen": board.fen}]


def _result(state: dict, actions: Optional[list] = None) -> dict:
    total = len(state["ids"])
    shown = len(state["shown"])
    solved = len(state["solved"] - state["shown"])
    known = solved + shown == total
    if known:
        facts = (f"{solved} of {total} solved"
                 + (f"; the solution of the other {shown} was shown at the student's request" if shown else "")
                 + " — these exact numbers, counted by the system on the board")
    else:
        facts = (f"the warm-up of {total} puzzles is finished. The system did not see every answer (a puzzle "
                 "answered in words or skipped leaves no trace on the board): do NOT say how many were solved, "
                 "and do not guess")
    return {
        "warmup_over": True,
        "source": "warmup",
        "count": total,
        "solved": solved if known else None,
        "solution_shown": shown if known else None,
        "solved_on_board": solved,
        "puzzles": [],
        # No puzzle: at most the board's own position set again, which closes the puzzle panel (_close_actions).
        "board_actions": list(actions or []),
        "note": (
            f"The WARM-UP is OVER: the student asked for the next puzzle after the last one of the set of {total}. "
            "NO new puzzle was put on the board (the system closed the puzzle mode; the last position stays) — do "
            "not call get_puzzle or board_control now and set none yourself. Tell the student the warm-up is over: "
            f"{facts}. Then offer, in one or two short sentences, what they can do next — only what exists: go on "
            "with the puzzles of their own programme (the words «дай задачу» now give the programme's next task), "
            "another warm-up («ещё разминку»), a game against you, or a review of one of their games. No list, no "
            "new buttons."
        ),
    }


def place_line(place: Optional[dict], language: Optional[str]) -> str:
    """«Задача 2 из 5.» in the student's language — the server's own line at the head of the answer."""
    if not isinstance(place, dict) or not place.get("n") or not place.get("of"):
        return ""
    return _PLACE[_lang(language)].format(n=int(place["n"]), of=int(place["of"]))


def over_line(result: Optional[dict], language: Optional[str]) -> str:
    """«Разминка окончена: решено 4 из 5.» — or, when the count is not known, «Разминка из 5 задач окончена.»"""
    if not isinstance(result, dict) or not result.get("warmup_over"):
        return ""
    of = int(result.get("count") or 0)
    if result.get("solved") is None:
        return _OVER[_lang(language)].format(of=of)
    return _OVER_COUNTED[_lang(language)].format(solved=int(result["solved"]), of=of)


def lead_line(result: Optional[dict], language: Optional[str]) -> str:
    """The line the server writes at the head of the answer for a get_puzzle result of a warm-up: the place of the
    puzzle put up, or the ending. "" for any other result."""
    if not isinstance(result, dict):
        return ""
    return over_line(result, language) or place_line(result.get("place"), language)


def place_note(place: dict) -> str:
    """What the model is told about the place (English, for the tool result)."""
    n, of = int(place["n"]), int(place["of"])
    last = (" It is the LAST puzzle of the warm-up: when it is solved or given up, the next «дальше» ends the "
            "warm-up — the system says so and sets no further puzzle; do not promise another one." if n == of else "")
    return f"It is puzzle {n} of {of} of the warm-up — the system counts, never count the puzzles yourself.{last}"


def say_place(place: dict) -> str:
    """For a model that reads the tool result itself (a voice coach, its own get_puzzle call): the place is said
    first, in the student's language, with the server's numbers."""
    return ("Tell the student the place of this puzzle FIRST, in their language, with exactly these numbers: "
            f"«{place_line(place, 'ru')}» / \"{place_line(place, 'en')}\" / «{place_line(place, 'kk')}».")


def paused(session, game_in_message: bool = False) -> Optional[dict]:
    """The student turned to something else in the middle of a warm-up — a game pasted into the message or onto the
    board, another position, a game against the coach: {"n", "of"} of the puzzle it stopped at until the break is said
    (``note_paused_said``; a puzzle of the warm-up put up again clears the mark), else None. It ended without a word before (open since 20.11): the puzzle
    panel was gone, the next «дальше» could bring its next puzzle or, a few messages later, the programme's task.

    Not a break: a turn on the warm-up's own positions (anywhere along a puzzle's solution), a warm-up over."""
    state = getattr(session, "warmup", None)
    if not state or state.get("over") or state.get("paused_said"):
        return None
    board = session.active_board() if getattr(session, "boards", None) else None
    key = _key(getattr(board, "fen", None)) if board is not None else ""
    on_its_own = (board is not None and getattr(board, "kind", None) != "game"
                  and any(key in keys for keys in state["lines"].values()))
    if on_its_own and not game_in_message:
        return None
    return {"n": state["at"] + 1, "of": len(state["ids"])}


def note_paused_said(session) -> None:
    """The break was said (``paused``): not again until the student is back at the warm-up."""
    state = getattr(session, "warmup", None)
    if state:
        state["paused_said"] = True


def paused_line(place: Optional[dict], language: Optional[str]) -> str:
    """«Разминка прервана на задаче 3 из 5.» — the server's own line at the head of the answer."""
    if not isinstance(place, dict) or not place.get("n") or not place.get("of"):
        return ""
    return _PAUSED[_lang(language)].format(n=int(place["n"]), of=int(place["of"]))


def paused_note(place: dict) -> str:
    """What the model is told about the break (English, for the turn's block)."""
    n, of = int(place["n"]), int(place["of"])
    return (f"[Warm-up paused] The student left the warm-up at puzzle {n} of {of} for what they bring now. The system "
            f"has already written «{paused_line(place, 'ru')}» at the head of your answer — do not repeat it and do "
            "not count puzzles. Answer what they bring now. If it fits, end with one short sentence that «дальше» "
            "goes back to the warm-up's puzzles.")
