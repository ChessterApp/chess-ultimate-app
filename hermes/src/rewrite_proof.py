"""The rewrite after a wrong sentence says only what the check proved (fix1102 K6, VERDICT §6.4).

The rewrite (src/server.py ``_run_fix``, src/answer_check.fix_messages) is a model call that writes the rest of an
answer after a sentence the check cut. On the live run of 02.11 it wrote new false facts the check could not judge —
trap-blackburne «Конь вынужден уйти на f7 с шахом» in place of a true mating line, st1#9 «прикрыта только пешкой d7»,
d2-solution «свои же пешки и слон его запирают» — and it was handed broken issue texts («defended (by )», «exf4 is
impossible after exf4»). A sentence the check finds nothing wrong with is not therefore true: most board words are
judged by no detector at all. So the rewrite is held to a stricter rule than the draft:

  issues    ``fix_issues``: only well-formed issue texts reach the rewrite. An issue that lists nothing where it names a
            list («defended (by )»), or names the same move or square on both sides of a relation that needs two
            («exf4 is impossible after exf4», «e6xe6: a pawn on e6 cannot capture on e6») is the trace of a detector
            that lost its way; it is no proof, and a sentence with no other issue is left unjudged
            (``well_formed``). «no any queen» is worded «no queen of either side».
  proof     ``prove``: every board word of a rewritten sentence — a square, a move, a piece, check or mate, material,
            an evaluation, a motif, a relation verb, a quantifier («только», «все», «вынужден») — must lie inside what
            the check proved true: a relation claim the judge found TRUE on its boards (src/claim_judge), or the
            engine's own line from the board on the screen (the moves, in order, from its first; the squares they
            go from and to, the pieces they move and take, «шах»/«мат» when they give it). A sentence with no board
            word proves nothing and claims nothing: 'neutral'. Anything else is 'unproven' and is not shown.

What a rewrite needs to be shown (src/server.py): its first sentence that carries a board word must be proven — then the
rewrite stands in for the rest of the draft as before, its neutral sentences go out with it, an unproven or wrong one
later is left out; a rewrite whose first such sentence is wrong or unproven (or that brings none) is abandoned, and the
draft goes on after the cut sentence, every sentence of it checked as usual — the cut sentence is simply left out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import chess

# ── issue texts ────────────────────────────────────────────────────────────────────────────────────────────────
# A list slot with nothing in it: «(by )», «()», «by ,».
_EMPTY_SLOT = re.compile(r"\(\s*(?:by|of|from|with|on|at)?\s*\)|\b(?:by|of|from)\s*[,;)]", re.IGNORECASE)
# The same move on both sides: «exf4 is impossible after exf4».
_SAME_MOVE = re.compile(r"(?<![\w.])(?P<a>[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?\s+is\s+"
                        r"(?:impossible|illegal|not\s+possible)\s+after\s+(?:\d+\.(?:\.\.)?\s*)?(?P=a)[+#]?(?![\w])")
# A capture from a square onto itself: «e6xe6», «a pawn on e6 cannot capture on e6».
_SAME_SQUARE = re.compile(r"(?<![a-z0-9])(?P<s>[a-h][1-8])x(?P=s)(?![0-9])|\bon\s+(?P<t>[a-h][1-8])\s+(?:cannot|can't|does\s+not|"
                          r"doesn't)\s+(?:capture|move|go)\s+(?:on|to)\s+(?P=t)\b", re.IGNORECASE)
_NO_ANY = re.compile(r"\bno\s+any\s+(king|queen|rook|bishop|knight|pawn|piece)\b", re.IGNORECASE)


def malformed(issue: str) -> Optional[str]:
    """Why *issue* is not a statement a reader could check, or None: an empty list where it names one, the same move
    or square on both sides of a relation that needs two, an empty text."""
    text = " ".join(str(issue or "").split())
    if not text:
        return "empty"
    if _EMPTY_SLOT.search(text):
        return "empty list"
    if _SAME_MOVE.search(text):
        return "a move impossible after itself"
    if _SAME_SQUARE.search(text):
        return "a square onto itself"
    return None


def clean_issue(issue: str) -> str:
    """*issue* worded for the reader: «no any queen» → «no queen of either side»."""
    return _NO_ANY.sub(lambda m: f"no {m.group(1)} of either side", str(issue or ""))


def well_formed(issues: Iterable[str]) -> list:
    """The issues of one sentence a reader can check, worded for the reader; the malformed ones are left out (a
    sentence with no other issue is unjudged). Markers such as PROMISE_ISSUE pass as they are."""
    out = []
    for issue in issues or ():
        if not isinstance(issue, str):
            continue
        if malformed(issue):
            continue
        cleaned = clean_issue(issue)
        if cleaned not in out:
            out.append(cleaned)
    return out


fix_issues = well_formed  # what the rewrite is given


def ends_the_draft(issues: Iterable[str]) -> bool:
    """The cut sentence's issues condemn the rest of the draft, not the sentence alone: an answer in the wrong language
    («…; the whole answer must be in Russian») goes on in it — its short fragments («Play e4.») are too short for the
    language check to judge one by one. An abandoned rewrite then ends the answer instead of resuming the draft."""
    return any(isinstance(i, str) and "the whole answer must be in" in i for i in issues or ())

# ── board words of a sentence ───────────────────────────────────────────────────────────────────────────────────
_CYR_FILES = {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}


def normalized(sentence: str) -> str:
    """The sentence as the check reads it (src/answer_check._check_sentence, the same steps): no emphasis, «ё» as «е»,
    one gap between words, Cyrillic files as Latin — the text the relation checker's claim spans are in."""
    from src.answer_check import _EMPHASIS, _WS_RUN

    text = _EMPHASIS.sub("", sentence or "").replace("ё", "е")
    text = _WS_RUN.sub(lambda m: "\n" if "\n" in m.group(0) else " ", text)
    return re.sub(r"(?<![а-яА-Яa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))",
                  lambda m: _CYR_FILES[m.group(1).lower()], text)


_F = "[a-hасебдфгх]"  # a file, Latin or its Cyrillic lookalike («Кс7+»)
_MOVE_TOKEN = re.compile(
    r"(?<![\w.])(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?|\.\.\.|…)?"
    rf"(?:(?:Кр|[KQRBNКФЛС♔♕♖♗♘♙♚♛♜♝♞♟]){_F}?[1-8]?[x:×]?{_F}[1-8](?:=[QRBNФЛСК])?"
    rf"|{_F}[x:×]{_F}[1-8](?:=[QRBNФЛСК])?"
    r"|(?<=[.…]|\s)[a-h][1-8](?:=[QRBNФЛСК])?(?=[+#]|\s|[,.;:!?)»—–-]|$)"
    r"|O-O-O|O-O|0-0-0|0-0)[+#]?(?![\w])")
_NUMBERED = re.compile(r"^(?:\d{1,3}\s?(?:\.\.\.|…|\.)|\.\.\.|…)")
_SQUARE = re.compile(r"(?<![A-Za-z0-9])([a-h][1-8])(?![0-9])")

_WORDS = {
    # the pieces, by name (Russian, English, Kazakh)
    # (a bare «фигура» is not one: «развивай фигуры» is advice; «потеряешь фигуру» says it with «потеряешь»)
    "piece": r"кон[ьяюеи]\w*|кон[её]м|коней|слон\w*|ладь\w*|ладей|ферз\w*|корол\w*|пешк\w*|пешек"
             r"|knights?|bishops?|rooks?|queens?|kings?|pawns?"
             r"|уәзір\w*|патша\w*|сарбаз\w*|піл\w*|тура\w*",
    # check, mate, stalemate
    "check": r"шах\w*|мат|мата|мату|матом|мате|пат\w*|checks?|checkmate\w*|mates?|stalemate\w*",
    # the move called the best: the engine's own first move says it
    "best": r"лучш\w*\s+(?:всего|ход\w*|ответ\w*|продолжени\w*)|лучше\s+всего|сильнейш\w*|сильнее\s+всего"
            r"|правильн\w*|точн\w*\s+(?:всего|ход\w*)|best(?:\s+(?:move|reply))?|strongest|correct\s+move",
    # material and evaluation
    "eval": r"материал\w*|лишн\w*|перевес\w*|преимуществ\w*|выигр\w*|проигр\w*|теря\w*|потер\w*|ничь\w*|равн\w*"
            r"|лучше|хуже|выгодн\w*|невыгодн\w*|безнад\w*|решающ\w*|отыгр\w*|отда\w*|жертв\w*|размен\w*"
            r"|material|extra|advantage|winning|wins?|losing|lose|loses|lost|draw\w*|equal\w*|better|worse|sacrifice\w*"
            r"|trade\w*|exchange\w*",
    # a capture told in words: the move that makes it says it
    "capture": r"забира\w*|забер\w*|забрать|взять|взяти\w*|возьм\w*|бер[её]\w*|брать|съе\w*|бьешь|captur\w*"
               r"|recaptur\w*|takes?|taking|took",
    # motifs and plans
    "motif": r"вилк\w*|связк\w*|связа\w*|связыва\w*|сквозн\w*|ловушк\w*|угроз\w*|гроз\w*|ловит\w*|запира\w*|заперт\w*"
             r"|двойн\w+\s+удар\w*|открыт\w+\s+(?:нападени|шах)\w*|превращ\w*|прорыв\w*|проходн\w*|рокиров\w*"
             r"|forks?|pins?|pinned|skewer\w*|traps?|trapped|threat\w*|promot\w*|castl\w*",
    # relation verbs
    "relation": r"напада\w*|нападет|напал\w*|атаку\w*|атакова\w*|бь[её]т|бьют|бить|бил\w*|защищ\w*|защит\w*|прикры\w*"
                r"|держ\w*|контрол\w*|нацел\w*|давит|давят|давить|давил\w*|давлени\w*|давя|целит\w*|смотрит"
                r"|под\s+бо\w+|под\s+удар\w*|висит|висят"
                r"|attack\w*|defend\w*|protect\w*|guard\w*|hits?|controls?|covers?|hanging|undefended"
                # what a move is said to do to a point (R3 03.11, VERDICT 1102b §1c: «укрепить ходом Be7», «Be2
                # укрепляет c2» passed as no board word): strengthen, support, guard, block, close, threaten
                r"|укреп\w*|подкреп\w*|поддерж\w*|стереж\w*|стерег\w*|охраня\w*|охран\w*|угрож\w*|блокир\w*"
                r"|заблокир\w*|перекр\w*|закрыва\w*|закрыть\w*|закро\w*|закрыл\w*|закрой\w*"
                r"|strengthen\w*|reinforc\w*|support\w*|block\w*|threaten\w*",
    # quantifiers and modality the claims do not carry
    "quant": r"только(?!\s+что)|лишь|единственн\w*|вс[её](?!\s+(?:равно|ещ[её]|же|таки)(?![\w-]))|всех|всем"
             r"|оба|обе|обоих|вынужд\w*|обязан\w*|нельзя|невозможн\w*"
             r"|никак\w*|никуда|некуда|ни\s+одн\w*|не\s+мо(?:жет|гут|чь)|only|both|all|must|forced|cannot|can't|never",
    # what the claims carry as a negation («ничем не защищена»)
    "neg": r"ничем|нечем|никем|некому|никто|ничто|ничего|nothing|nobody|none",
}
_WORD_RE = {kind: re.compile(r"(?<![\w-])(?:" + rx + r")(?![\w-])", re.IGNORECASE) for kind, rx in _WORDS.items()}
_PIECE_OF = [(re.compile(r"(?<![\w-])(?:кон[ьяюеи]\w*|кон[её]м|коней|knights?)(?![\w-])", re.I), chess.KNIGHT),
             (re.compile(r"(?<![\w-])(?:слон\w*|bishops?|піл\w*)(?![\w-])", re.I), chess.BISHOP),
             (re.compile(r"(?<![\w-])(?:ладь\w*|ладей|rooks?|тура\w*)(?![\w-])", re.I), chess.ROOK),
             (re.compile(r"(?<![\w-])(?:ферз\w*|queens?|уәзір\w*)(?![\w-])", re.I), chess.QUEEN),
             (re.compile(r"(?<![\w-])(?:корол\w*|kings?|патша\w*)(?![\w-])", re.I), chess.KING),
             (re.compile(r"(?<![\w-])(?:пешк\w*|пешек|pawns?|сарбаз\w*)(?![\w-])", re.I), chess.PAWN)]


# A name, not a relation: «берлинская защита», «защита Каро-Канн», «английская атака», "the Sicilian Defence" — an
# opening's name says nothing about what defends or attacks what on the board (live 02.11 st2#4: «Это испанская партия,
# берлинская защита» was unproven by «защита»). A national or place adjective, or a capitalised name after the noun.
_NAME_NOUN = r"(?:защит(?:а|ы|е|у|ой)|атак(?:а|и|е|у|ой)|гамбит\w*)"
_NAME = re.compile(r"(?<![\w-])[А-ЯЁа-яё][а-яё-]*(?:ск|цк)(?:ая|ой|ую|ие|их)\s+" + _NAME_NOUN + r"(?![\w-])"
                   r"|(?<![\w-])" + _NAME_NOUN + r"\s+[А-ЯЁ][а-яё]{2,}(?:[-–][А-ЯЁа-яё][а-яё]+)?(?![\w-])"
                   r"|(?<![\w-])[A-Z][\w-]+\s+(?:Defen[cs]e|Attack|Gambit)(?![\w-])")


_IDIOM = re.compile(r"(?<![\w-])(?:вс[её]\s+равно|все\s+равно)(?![\w-])", re.IGNORECASE)


@dataclass
class Anchor:
    kind: str  # square | move | piece | check | eval | motif | relation | quant | neg
    start: int
    end: int
    text: str
    san: str = ""  # a move: its SAN without the number
    piece: Optional[int] = None  # a piece word: its kind


def anchors(text: str) -> list:
    """The board words of *text* (as ``normalized`` gives it), in order."""
    out: list = []
    taken: list = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    from src.answer_check import _MOVE, _to_san

    for m in _MOVE_TOKEN.finditer(text):
        token = m.group(0)
        converted, _ = _to_san(token.replace("0-0-0", "O-O-O").replace("0-0", "O-O").replace(":", "x").replace("×", "x"))
        mv = _MOVE.search(converted)
        if not mv:
            continue
        bare = re.fullmatch(r"[a-h][1-8]", mv["san"]) and not _NUMBERED.match(token)
        if bare:
            continue  # a bare square is read as a square below
        out.append(Anchor("move", m.start(), m.end(), token, san=mv["san"] + (mv["check"] or "")))
        taken.append((m.start(), m.end()))
    for m in _SQUARE.finditer(text):
        if free(m.start(), m.end()):
            out.append(Anchor("square", m.start(), m.end(), m.group(1)))
    taken.extend((m.start(), m.end()) for m in _NAME.finditer(text))  # an opening's name is no relation
    taken.extend((m.start(), m.end()) for m in _IDIOM.finditer(text))  # «всё равно» is "anyway", no equality
    for kind, rx in _WORD_RE.items():
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            piece = None
            if kind == "piece":
                piece = next((pt for prx, pt in _PIECE_OF if prx.fullmatch(m.group(0))), None)
            out.append(Anchor(kind, m.start(), m.end(), m.group(0), piece=piece))
            taken.append((m.start(), m.end()))
    out.sort(key=lambda a: a.start)
    return out


# ── the engine's own line ───────────────────────────────────────────────────────────────────────────────────────
def _bare(san: str) -> str:
    return (san or "").rstrip("+#!?")


def engine_moves(sentence_moves: list, ctx: Any) -> Optional[list]:
    """The moves of *sentence_moves* (SAN, in order) as played from the board on the screen when they are the first
    moves of one of the engine's lines of the turn (``ctx.engine_lines``: SAN lists from ``ctx.current``):
    [(board before, move, san as played)], or None."""
    current = getattr(ctx, "current", None)
    lines = list(getattr(ctx, "engine_lines", None) or [])
    if current is None or not sentence_moves or not lines:
        return None
    want = [_bare(s) for s in sentence_moves]
    for line in lines:
        if not line or len(line) < len(want):
            continue
        if [_bare(s) for s in line[:len(want)]] != want:
            continue
        board = current.copy(stack=False)
        played = []
        try:
            for san in line[:len(want)]:
                move = board.parse_san(san)
                played.append((board.copy(stack=False), move, board.san(move)))
                board.push(move)
        except ValueError:
            continue
        # «Nf3#» said of a move that is not mate, «+» of one that gives no check: not the engine's move as said
        if any(s.endswith("#") and not p[2].endswith("#") or s.endswith("+") and not p[2].endswith(("+", "#"))
               for s, p in zip(sentence_moves, played)):
            continue
        return played
    return None


# A move told as already made: «ты сыграл Кc6», «я ответил 3.Кc3», «мой последний ход — 1...Кf6».
_TOLD = re.compile(r"(?<![\w-])(?:сыграл\w*|ответил\w*|пош[её]л|пошла|пошли|сходил\w*|вышел|вышла|встал\w*|взял\w*|забрал\w*"
                   r"|побил\w*|сделал\w*|последни\w+\s+ход\w*|played|answered|replied|moved|took|captured|last\s+move)"
                   r"(?![\w-])", re.IGNORECASE)


def record_moves(sentence_moves: list, ctx: Any) -> Optional[list]:
    """The moves of *sentence_moves* (move anchors, in order) as plies of the game on the board (``ctx.game_moves``, from
    the start position): [(board before, move, san as played)], or None when one is not in the record — with its
    number, at that very ply; with «+»/«#», giving it."""
    record = list(getattr(ctx, "game_moves", None) or [])
    if not record or not sentence_moves:
        return None
    board = chess.Board()
    plies = []
    for raw in record:
        try:
            move = board.parse_san(str(raw))
        except ValueError:
            try:
                move = chess.Move.from_uci(str(raw))
            except ValueError:
                break
            if move not in board.legal_moves:
                break
        plies.append((len(plies), board.copy(stack=False), move, board.san(move)))
        board.push(move)
    out = []
    for a in sentence_moves:
        found = [p for p in plies if _bare(p[3]) == _bare(a.san)]
        num = re.match(r"\s*(\d{1,3})\s?(\.\.\.|…|\.)", a.text)
        if num:
            ply = 2 * (int(num.group(1)) - 1) + (1 if num.group(2) in ("...", "…") else 0)
            found = [p for p in found if p[0] == ply]
        if a.san.endswith("#"):
            found = [p for p in found if p[3].endswith("#")]
        elif a.san.endswith("+"):
            found = [p for p in found if p[3].endswith(("+", "#"))]
        if not found:
            return None
        out.append(found[-1][1:])
    return out


# ── the proof ───────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Proof:
    status: str  # neutral | proven | unproven
    why: str = ""
    words: list = field(default_factory=list)  # the board words that were not proven


def _record(sentence: str, ctx: Any) -> tuple:
    """(the text the relation checker read, [(claim, status)]) for *sentence*, as it recorded them while checking it —
    by that very text: a record of another text (or none) leaves the sentence's words with no claim to lie in."""
    text = normalized(sentence)
    rec = (getattr(ctx, "relation_verdicts", None) or {}).get(text)
    if rec and rec[0] == text:
        return rec
    return text, ()


def prove(sentence: str, ctx: Any) -> Proof:
    """Whether every board word of *sentence* — already checked with no issue on *ctx* — is proven: inside a relation
    claim the judge found true, or part of the engine's own line from the board on the screen. Never raises."""
    try:
        return _prove(sentence, ctx)
    except Exception as exc:  # noqa: BLE001 — what cannot be proven is not shown
        return Proof("unproven", f"proof failed: {type(exc).__name__}")


# ── relations the sentence states, proven on the board (R3 03.11) ───────────────────────────────────────────────
# What a relation word asks of the board when no claim the judge found true carries it (VERDICT 1102b §1c: «Слон c4
# бьёт по f7, поэтому этот пункт стоит укрепить ходом Be7» was proven word by word — Be7 the engine's move, «бьёт по
# f7» true — while Be7 does not defend f7). The move the sentence names is the means: the piece it moves must hold the
# relation, on the board after it, to the point the sentence is about. Words of no relation the attack map decides
# (block, close, pin, hang) are proven only inside a true claim.
_MEANS_REL = [
    (re.compile(r"^(?:защи\w*|укреп\w*|подкреп\w*|поддерж\w*|прикры\w*|стереж\w*|стерег\w*|охран\w*|держ\w*|"
                r"defend\w*|protect\w*|guard\w*|support\w*|reinforc\w*|strengthen\w*|covers?)$", re.I), "defend"),
    (re.compile(r"^(?:напада\w*|нападет|напал\w*|атаку\w*|атакова\w*|бь[её]т|бьют|бить|угрож\w*|attack\w*|hits?|"
                r"threaten\w*)$", re.I), "attack"),
    (re.compile(r"^(?:нацел\w*|целит\w*|смотрит|давит|давят|давить|давил\w*|давлени\w*|давя)$", re.I), "aim"),
    (re.compile(r"^(?:контрол\w*|controls?)$", re.I), "hold"),
]
# A check-giving verb: «даёт шах», «с шахом», «объявит шах» — the check of a move, not the one on the board.
_GIVES_CHECK = re.compile(r"(?<![\w-])(?:да[её]т|дать|даст|дава\w*|объяв\w*|поставит|ставит|с\s+шахом|gives?|giving|"
                          r"with\s+check)(?![\w-])", re.IGNORECASE)
# «только» / «лишь» / «единственный» before the defender a true defence claim names: the whole list of defenders.
_ONLY = re.compile(r"^(?:только|лишь|единственн\w*|only)$", re.IGNORECASE)
_CASTLE = re.compile(r"^(?:рокиров\w*|castl\w*)$", re.IGNORECASE)
_LONG = re.compile(r"(?<![\w-])(?:длинн\w*|ферзев\w*|long|queenside)(?![\w-])|O-O-O|0-0-0", re.IGNORECASE)
_SHORT = re.compile(r"(?<![\w-])(?:коротк\w*|королевск\w*|short|kingside)(?![\w-])", re.IGNORECASE)
# «укрепляя центр»: the centre is its four squares — the relation holds to one of them
_CENTRE = re.compile(r"(?<![\w-])(?:центр|центра|центру|центром|центре|cent(?:er|re))(?![\w-])", re.IGNORECASE)
CENTRE_SQUARES = ("d4", "e4", "d5", "e5")


_WHITE_WORD = re.compile(r"(?<![\w-])(?:бел\w*|white)(?![\w-])", re.IGNORECASE)
_BLACK_WORD = re.compile(r"(?<![\w-])(?:ч[её]рн\w*|black)(?![\w-])", re.IGNORECASE)
_YOU_WORD = re.compile(r"(?<![\w-])(?:ты|тебе|тебя|твой|твоя|твоего|твоему|твоим|you|your)(?![\w-])", re.IGNORECASE)
_ME_WORD = re.compile(r"(?<![\w-])(?:я|мне|меня|мой|моя|моего|моему|моим)(?![\w-])", re.IGNORECASE)


def _side_in_check(text: str, board: chess.Board, ctx: Any) -> bool:
    """The side the sentence names (белые/чёрные, ты/я) is the side in check on *board* — the side to move; a sentence
    that names no side speaks of the check on the board."""
    white, black = bool(_WHITE_WORD.search(text)), bool(_BLACK_WORD.search(text))
    if white and black:
        return False
    if white or black:
        return board.turn == (chess.WHITE if white else chess.BLACK)
    you, me = bool(_YOU_WORD.search(text)), bool(_ME_WORD.search(text))
    if you or me:
        student = getattr(ctx, "student_color", None)
        if student is None:
            return you and not me  # «ты» is the side to move when nobody said which side the student plays
        return not (you and me) and board.turn == (student if you else not student)
    return True


def _after_boards(played: Optional[list]) -> list:
    """[(board after the move, move, the moved piece's kind)] for the moves *played* (the engine's line or the game's
    record), each board remembering its move (claim_scene._after: «конь» binds to the knight that just moved)."""
    from src.claim_scene import _after

    out = []
    for board, move, _san in played or ():
        mover = board.piece_at(move.from_square)
        if mover is None:
            continue
        out.append((_after(board, move), move, mover.piece_type))
    return out


def _judged_after(claim: Any, after: list, ctx: Any) -> bool:
    """A claim the check left unjudged (its subject a piece kind with no square), true on the board after a move the
    sentence names that moved a piece of that kind: «лучший ход — Nc3: конь нападает на ферзя на d5»."""
    from src.claim_judge import judge_on
    from src.claim_types import PIECE_TYPE

    s = getattr(claim, "subj", None)
    if s is None or s.sq or not s.piece or claim.neg or claim.question or getattr(claim, "presup", ""):
        return False
    for board, _move, kind in after:
        if PIECE_TYPE.get(s.piece) != kind:
            continue
        try:
            v, _ = judge_on(claim, board, ctx)
        except Exception:  # noqa: BLE001
            v = None
        if v is True:
            return True
    return False


def _means_holds(a: Anchor, text: str, words: list, after: list, targets: list, ctx: Any) -> bool:
    """The relation word *a* stated of the move the sentence names nearest to it: on the board after that move, the
    piece it moved holds the relation to every point the sentence is about (*targets*) — or, with no square named, to
    one square of the centre the sentence names («Играй d3, укрепляя центр»)."""
    from src.claim_judge import judge_on
    from src.claim_types import Claim, Ref

    rel = next((r for rx, r in _MEANS_REL if rx.match(a.text)), None)
    zone = not targets and bool(_CENTRE.search(text))
    if zone:
        targets = list(CENTRE_SQUARES)
    if rel is None or not after or not targets:
        return False
    moves = [w for w in words if w.kind == "move"]
    if not moves and len(after) == 1:
        # «Играй d3, укрепляя центр»: the pawn move written as its square
        moves = [w for w in words if w.kind == "square" and w.text == chess.square_name(after[0][1].to_square)][:1]
    if not moves or len(moves) != len(after):
        return False
    nearest = min(range(len(moves)), key=lambda i: min(abs(moves[i].start - a.end), abs(a.start - moves[i].end)))
    board, move, _kind = after[nearest]
    prev = getattr(board, "rel_prev", None)
    if prev is not None and prev.is_castling(move):
        return False  # two pieces move: which one is the means, the words do not say
    mover = chess.square_name(move.to_square)
    held = []
    for t in targets:
        v = None
        if t != mover:
            # the piece on the point is named: a piece defends only its own side's, attacks only the other's
            there = board.piece_at(chess.parse_square(t))
            obj = Ref(sq=t, piece=there.symbol().upper()) if there is not None else Ref(sq=t)
            claim = Claim(rel=rel, subj=Ref(sq=mover), objs=(obj,))
            try:
                v, _ = judge_on(claim, board, ctx)
            except Exception:  # noqa: BLE001
                v = None
        held.append(v is True)
    return any(held) if zone else all(held)


def _only_holds(a: Anchor, text: str, claims: list, board: Optional[chess.Board]) -> bool:
    """«Коня b1 прикрывает только ладья a1», «f7 защищает только король»: the defender a true defence claim names right
    after «только» is every defender of the piece it defends, on the board the claim was judged on."""
    from src.claim_judge import defenders
    from src.claim_types import PIECE_TYPE

    if board is None or not _ONLY.match(a.text):
        return False
    following = text[a.end:a.end + 40].lower().split()[:3]
    for claim in claims:
        if claim.rel != "defend" or claim.neg or claim.subj is None:
            continue
        s = claim.subj
        named = (s.text or "").lower()
        if not any(w.strip(",.;:!?—–-«»") in (named, s.sq or "#") for w in following if w):
            continue  # «только» is not before this claim's defender
        objs = [o for o in claim.objs if o is not None and o.sq]
        if len(objs) != 1:
            continue
        t = chess.parse_square(objs[0].sq)
        occupant = board.piece_at(t)
        if occupant is None:
            continue
        dfs = defenders(board, t, occupant.color)
        if not dfs:
            continue
        if s.sq:
            if dfs == [chess.parse_square(s.sq)]:
                return True
        elif s.piece and all(board.piece_at(d).piece_type == PIECE_TYPE[s.piece] for d in dfs) and len(dfs) == 1:
            return True
    return False


def _prove(sentence: str, ctx: Any) -> Proof:
    text, verdicts = _record(sentence, ctx)
    words = anchors(text)
    if not words:
        return Proof("neutral")
    moves = [a for a in words if a.kind == "move"]
    played = engine_moves([a.san for a in moves], ctx) if moves else None
    if not moves:
        # «Играй e4»: a pawn move written as its square — the engine's first move when its line starts with it
        first = next((a for a in words if a.kind == "square"), None)
        played = engine_moves([first.text], ctx) if first is not None else None
    elif played is None and _TOLD.search(text):
        # moves told as made: the game's own record proves them (and what they moved, took, gave)
        played = record_moves(moves, ctx)
    after = _after_boards(played) if played else []
    true_claims = []
    for claim, status in verdicts or ():
        if getattr(claim, "question", ""):
            continue
        if status == "true" or (status not in ("false",) and after and _judged_after(claim, after, ctx)):
            true_claims.append(claim)
    spans = []  # the relation words of the claims found true
    claim_squares: set = set()  # …and the squares and pieces they are about
    claim_pieces: set = set()
    claim_objects: list = []  # the points they are about (what is attacked, defended): a means relation's targets
    current = getattr(ctx, "current", None)
    for claim in true_claims:
        if tuple(getattr(claim, "span", (0, 0))) != (0, 0):
            spans.append((claim.span[0], claim.span[1], claim))
        for ref in [claim.subj, claim.to, *claim.objs]:
            if ref is None:
                continue
            if ref.sq:
                claim_squares.add(ref.sq)
                if ref.piece is None and current is not None:
                    try:
                        found = current.piece_at(chess.parse_square(ref.sq))
                    except ValueError:
                        found = None
                    if found is not None:
                        claim_pieces.add(found.piece_type)
            if ref.piece:
                claim_pieces.add(chess.Piece.from_symbol(ref.piece).piece_type)
        for ref in claim.objs:
            if ref is not None and ref.sq and ref.sq not in claim_objects:
                claim_objects.append(ref.sq)
    line_squares: set = set()
    line_pieces: set = set()
    gives = {"check": False, "mate": False, "castle": False}
    move_squares: set = set()
    if played:
        for board, move, san in played:
            line_squares.update({chess.square_name(move.from_square), chess.square_name(move.to_square)})
            move_squares.update({chess.square_name(move.from_square), chess.square_name(move.to_square)})
            mover = board.piece_at(move.from_square)
            if mover:
                line_pieces.add(mover.piece_type)
            taken = board.piece_at(move.to_square) if not board.is_en_passant(move) else chess.Piece(chess.PAWN, not board.turn)
            if taken:
                line_pieces.add(taken.piece_type)
            gives["check"] |= san.endswith(("+", "#"))
            gives["capture"] = gives.get("capture", False) or board.is_capture(move)
            gives["mate"] |= san.endswith("#")
            if board.is_castling(move):
                line_pieces.update({chess.KING, chess.ROOK})
                gives["castle"] = "long" if chess.square_file(move.to_square) < 4 else "short"
                # the rook moves too: «ладья встала на f1» after 0-0 (live 02.11 st2#4 was unproven by «f1»)
                rank = chess.square_rank(move.from_square)
                kingside = chess.square_file(move.to_square) == 6 or chess.square_file(move.to_square) == 7
                line_squares.update({chess.square_name(chess.square(7 if kingside else 0, rank)),
                                     chess.square_name(chess.square(5 if kingside else 3, rank)),
                                     chess.square_name(chess.square(6 if kingside else 2, rank))})
            if not san[0].isupper():
                line_squares.add(san[-2:] if san[-1].isdigit() else _bare(san)[-2:])
    # The board on the screen gives check (or mate) itself: «…а не сам шах» said of it, with no move named and no
    # check-giving verb (live 02.11 st3#10, after 4...Qxe4+).
    on_board = {"check": False, "mate": False}
    if current is not None and not moves and not _GIVES_CHECK.search(text) and _side_in_check(text, current, ctx):
        on_board = {"check": current.is_check(), "mate": current.is_checkmate()}
    # The points a means relation is about: what the true claims attack or defend, else the squares the sentence names
    # outside its moves.
    targets = list(claim_objects) or [a.text for a in words if a.kind == "square" and a.text not in move_squares]

    def inside(a: Anchor) -> Optional[Any]:
        return next((c for s, e, c in spans if s <= a.start and a.end <= e), None)

    # A relation proven of the move («подкрепить ходом Be3» with Be3 defending d4) proves the points it holds to, and
    # what stands on them, as a true claim would.
    means = {id(a) for a in words if a.kind == "relation" and inside(a) is None
             and _means_holds(a, text, words, after, targets, ctx)}
    if means:
        named = [t for t in targets if t in {w.text for w in words if w.kind == "square"}] or targets
        for t in named:
            claim_squares.add(t)
            for board in [current] + [b for b, _m, _k in after[-1:]]:
                found = board.piece_at(chess.parse_square(t)) if board is not None else None
                if found is not None:
                    claim_pieces.add(found.piece_type)

    unproven = []
    for a in words:
        claim = inside(a)
        if a.kind == "move":
            ok = played is not None
        elif a.kind == "quant":
            # «только», «все», «вынужден»: no claim carries them — except «только» before the one defender of a piece
            # on the board on the screen (a sentence that names a move may be about the board after it)
            ok = not moves and played is None and _only_holds(a, text, true_claims, current)
        elif a.kind == "neg":
            ok = claim is not None and (getattr(claim, "neg", False) or getattr(claim, "rel", "") == "undefended")
        elif claim is not None:
            ok = True
        elif a.kind == "relation":
            ok = id(a) in means
        elif a.kind == "square":
            ok = a.text in line_squares or a.text in claim_squares
        elif a.kind == "piece":
            ok = a.piece is not None and (a.piece in line_pieces or a.piece in claim_pieces)
        elif a.kind == "best":
            ok = played is not None  # the moves it names are the engine's line, from its first
        elif a.kind == "capture":
            ok = bool(gives.get("capture"))
        elif a.kind == "check":
            low = a.text.lower()
            ok = (gives["mate"] or on_board["mate"]) if low.startswith(("мат", "checkmate", "mate")) else (
                (gives["check"] or on_board["check"]) if low.startswith(("шах", "check")) else False)
        elif a.kind == "motif":
            # «рокировка» told of the castling played — of its side, when the sentence names one
            side = "long" if _LONG.search(text) else ("short" if _SHORT.search(text) else None)
            ok = bool(gives["castle"]) and bool(_CASTLE.match(a.text)) and side in (None, gives["castle"])
        else:
            ok = False
        if not ok:
            unproven.append(a.text)
    if unproven:
        return Proof("unproven", "not proven: " + ", ".join(dict.fromkeys(unproven)), list(dict.fromkeys(unproven)))
    return Proof("proven")


# ── the context the rewrite read ────────────────────────────────────────────────────────────────────────────────
# Counters and records of the whole turn: kept as they grew, the rewrite's calls included.
_KEEP = {"relation_stats", "relation_shadow", "relation_verdicts"}


def snapshot(ctx: Any) -> Optional[dict]:
    """What the check knows after the draft's sentences so far (the scene, the lines written, the antecedents, the
    boards the answer's moves added): a rewrite that is abandoned leaves the draft to be read from here, not from
    sentences the student never saw. One level of each field is copied. Never raises."""
    try:
        import copy
        import dataclasses

        names = [f.name for f in dataclasses.fields(ctx)] + [k for k in vars(ctx) if k not in
                                                             {f.name for f in dataclasses.fields(ctx)}]
        return {n: copy.copy(getattr(ctx, n)) for n in names if n not in _KEEP and hasattr(ctx, n)}
    except Exception:  # noqa: BLE001
        return None


def restore(ctx: Any, snap: Optional[dict]) -> None:
    """Put *snap* back (fields added since are left). Never raises."""
    if not snap:
        return
    for name, value in snap.items():
        try:
            setattr(ctx, name, value)
        except Exception:  # noqa: BLE001
            pass


# ── what a cut leaves (R3 03.11) ────────────────────────────────────────────────────────────────────────────────
# 39 of 41 rewrites on the live run of 02.11 were abandoned and the flagged sentence simply left out; what followed it
# often leaned on it: «точнее, ферзь e4 атакует коня b1…» (st3#8, the rest of a sentence split at «...»), «Поэтому…»,
# «Кроме того…», a list whose item 2 was cut going on with «3.», a blank line doubled. The draft's words are kept; only
# the word that points back at the sentence the student never saw goes, and the list is counted again.
# (src/answer_check.strip_leaning_start stays as it is: the /learn tutor and the game comment use it.)
_LEANS_ON_CUT = re.compile(
    r"^(\s*(?:[>#-]+\s*)?)([*_]{0,2})(?:поэтому|потому\s+что|значит|отсюда|именно\s+поэтому|из-за\s+этого|в\s+итоге|"
    r"тогда|точнее|вернее|то\s+есть|иначе\s+говоря|к\s+тому\s+же|более\s+того|причем|вдобавок|ведь|и|а|"
    r"therefore|thus|hence|so|that'?s\s+why|this\s+means|in\s+other\s+words|more\s+precisely|moreover|furthermore|"
    r"and|i\.e\.)(?![а-яёa-z])([*_]{0,2})[\s,—–:-]*", re.IGNORECASE)
# …but not the first word of a fixed phrase or a pair (fix1103, review-fp x01/x02/x05/x06): "So far", "So long as",
# "Thus far", "So that", «Тогда как», «И так», «А то», a correlative «И X, и Y» / «Ни X, ни Y», a hyphenated
# file name («а-пешка»). The word stays, and so does the sentence as the draft wrote it.
_KEEPS_START = re.compile(
    r"^\s*(?:[>#-]+\s*)?[*_]{0,2}(?:"
    r"[а-яёa-z]{1,9}-[а-яёa-z]"
    r"|(?:so|thus|and)\s+(?:far|long|that|much|many|as|to|on|forth|called)(?![a-z])"
    r"|тогда\s+как(?![а-яё])|и\s+(?:так|то|все\s*же|всё\s*же)(?![а-яё])|а\s+то(?![а-яё])"
    r"|(?P<pair>и|ни)\s+[^.!?;:\n]*?,\s*(?P=pair)\s"
    r")", re.IGNORECASE)
_FRAGMENT_START = re.compile(r"^(\s*)(?:\.\.\.|…|[,;:—–-])+\s*")
_SAN_START = re.compile(r"[a-h](?:[1-8]|x[a-h])")
_ITEM = re.compile(r"^(\s*)(\d{1,2})([.)])(\s+)(?![KQRBNКФЛСO0]?[a-h]?[1-8]?[x:×]?[a-h][1-8]|O-O|0-0)")
_SHOWN_ITEM = re.compile(r"(?:^|\n)[ \t]*(\d{1,2})[.)][ \t]+(?![KQRBNКФЛСO0]?[a-h]?[1-8]?[x:×]?[a-h][1-8]|O-O|0-0)")


def mend_after_cut(text: str, shown: str = "") -> str:
    """*text*, the first words shown after a sentence left out (or the answer's very first words), without what points
    back at the sentence the student never saw: a leaning word («Затем», «Поэтому», «точнее»), a fragment's leading
    «…» or dash; a lowercase start capitalised when it opens a new sentence. A move («e4 — …») stays as written."""
    from src.answer_check import strip_leaning_start

    if not (text or "").strip():
        return text
    out = text
    f = _FRAGMENT_START.match(out)
    if f and len(out) - f.end() >= 12:
        out = f.group(1) + out[f.end():]
    for _ in range(3):  # «и тогда …», «а значит, …»: each word that leans back
        if _KEEPS_START.match(out):
            break
        leaned = strip_leaning_start(out)
        if leaned == out:
            m = _LEANS_ON_CUT.match(out)
            if m and len(out) - m.end() >= 12:
                mark = "" if m.group(3) else m.group(2)
                leaned = m.group(1) + mark + out[m.end():]
        if leaned == out:
            break
        out = leaned
    lead = len(out) - len(out.lstrip())
    body = out[lead:]
    body_start = len(body) - len(body.lstrip("*_«\"("))
    first = body[body_start:body_start + 1]
    opens = not shown.strip() or shown.rstrip()[-1:] in ".!?…:»\"" or shown.endswith("\n")
    if first.islower() and opens and not _SAN_START.match(body[body_start:]):
        body = body[:body_start] + first.upper() + body[body_start + 1:]
    return out[:lead] + body


# A list of candidate moves: «1. d3 — …», «2. Qe2: …» — a number, one move, then a dash or a colon (fix1103, review-fp
# x03: «3. Nc3 — …» after a cut «2. Qe2 — …» kept its 3). It is a list, not a game's move numbers, when every move
# of it is legal on the board the answer is about (the candidates of one position).
_MOVE_ITEM_SAN = r"(?:[KQRBNКФЛС]?[a-h]?[1-8]?[x:×]?[a-h][1-8](?:=[QRBN])?|O-O-O|O-O|0-0-0|0-0)[+#]?"
_MOVE_ITEM = re.compile(r"^(\s*)(\d{1,2})([.)])(\s+)(?P<san>" + _MOVE_ITEM_SAN + r")\s*[—–:-]")
_SHOWN_MOVE_ITEM = re.compile(r"(?:^|\n)[ \t]*(\d{1,2})[.)][ \t]+(?P<san>" + _MOVE_ITEM_SAN + r")\s*[—–:-]")


def _candidate_list(sans: list, board) -> bool:
    """Every move of *sans* is legal on *board*: the items are candidates of one position, not moves of a game."""
    if board is None or not sans:
        return False
    from src.answer_check import _to_san

    for san in sans:
        try:
            board.parse_san(_to_san(san)[0].replace("0", "O").rstrip("+#"))
        except ValueError:
            return False
    return True


def renumber_item(text: str, shown: str, cut: Iterable[str] = (), board=None) -> str:
    """A numbered item after a cut one goes on the list as it is shown: «1. …» shown, «2. …» cut, «3. …» becomes «2. …»;
    the list's first item cut, the next one is «1.». A line that opens with a move number («3. Nf3») is not an item,
    unless it is one of a list of candidate moves legal on *board* («1. d3 — …», «3. Nc3 — …»)."""
    m = _ITEM.match(text or "")
    if not m:
        mm = _MOVE_ITEM.match(text or "")
        if not mm:
            return text
        shown_moves = list(_SHOWN_MOVE_ITEM.finditer(shown or ""))
        cut_moves = [c for c in (_MOVE_ITEM.match((c or "").lstrip()) for c in cut or ()) if c]
        if not _candidate_list([mm["san"]] + [x["san"] for x in shown_moves] + [c["san"] for c in cut_moves], board):
            return text
        n = int(mm.group(2))
        if shown_moves:
            want = int(shown_moves[-1].group(1)) + 1
        elif cut_moves:
            want = 1
        else:
            return text
        if n <= want:
            return text
        return mm.group(1) + str(want) + text[mm.end(1) + len(mm.group(2)):]
    n = int(m.group(2))
    items = list(_SHOWN_ITEM.finditer(shown or ""))
    if items:
        want = int(items[-1].group(1)) + 1
    elif any(_ITEM.match((c or "").lstrip()) for c in cut or ()):
        want = 1
    else:
        return text
    if n <= want:
        return text
    return m.group(1) + str(want) + text[m.end(1) + len(m.group(2)):]
