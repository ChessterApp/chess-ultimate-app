"""How an ending of ≤ 7 pieces ends, as the coach says it, judged by the endgame tablebase (2026-10-30).

Production check of 29.10 (set B, «square»): «Я чёрными, мой ход. Догонит ли мой король пешку?» on
8/8/8/P3k3/8/8/8/7K b — the coach answered «Нет, не догонит. Твоя пешка проходит.», and the tablebase says
draw (1...Kd5 and 1...Kd6 catch the pawn). src/answer_check_rules._result_issues judges the result only when it
is named — «это выигрыш», «это ничья»; a race verdict says the same thing in other words and went through.

Each claim here is turned into a result from the pieces on the board, and the tablebase decides it:

  * the king catches the pawn («догонит», «успеет», «остановит», "catches") — the pawn's side does not win;
    judged only when that pawn is all the side has besides its king;
  * the king does not catch it, the pawn queens («не догонит», «проходит в ферзи», «пешку не остановить»,
    "queens") — the pawn's side wins; judged only against a bare king (a queen against a bare king wins);
  * «ничью удержишь», «спасёшься» — that side does not lose; «спасения нет», «ничью не удержать» — it loses;
    «не выиграешь», «выиграть нельзя» — it does not win.

Whose pawn and whose king: the colour named («белая пешка», «твой король», «ты догонишь»), the square of the
pawn («пешка a5»), or the only side with pawns; «твой», «ты» are the student (the colour the question gives —
«Я чёрными» —, a game's colour, else the side to move, as everywhere in the checker). A short answer with no
subject («Нет, не догонит.») takes it from the question it answers.

Only claims about this board are judged: a condition («если король пойдёт на e4…»), a purpose («чтобы
удержать ничью…»), advice («нужно догонять»), a rule in general («как правило»), a question and a quote are
left alone; so are (review 30.10) a condition after the claim («пешка проходит, если…», «…после 1...Ke4», «при
ходе белых»), someone's belief or a statement rejected («Кажется, что…», «Ты пишешь, что… — это не так»), another
position (a study, a diagram, the rule of the square, «там»), a concession the sentence takes back («успевает
встать перед пешкой, но … они выигрывают»), «выиграть темп / пешку», an attempt («пытается спастись»), and a side
known only by a guess («ему», a bare «спасения нет» when the student's colour is not named). An infinitive is a
claim only with its denial or «можно» («Удержать ничью здесь нельзя» says the side loses).

A claim after a line written in the sentence («после Kd5 a6 Kc6 — ничья») is judged at the line's end when the
line is legal from the board in front of the student: from the tablebase cache at once, else in the answer's
engine stage (pop_pending / judge_pending — a network lookup never runs inside check_sentence).

Plan 31.10 (P5), three more detectors, each with its own switch (src/config.detector_mode):

  * ``race_distance`` — the race said in words of distance: «твой король слишком далеко», «далеко от пешки», «не
    дотянется», «опаздывает», «вне квадрата» say the king does not catch the pawn («не слишком далеко»: it does).
    A king word must stand in the clause: «Пешка слишком далеко» is not the race (judge [J]). The tablebase result
    in ctx decides, and the issue names the moves that keep the result when the turn has the tablebase's answer.
  * ``mate_squares`` — «мат возможен / случается / бывает только в углу», «ладьёй мат ставится только на краю»: a
    claim about where a bare king can be mated in KQK, KRK, KBBK, KBNK or KNNK, judged against
    src/data/mate_squares.json (scripts/build_mate_squares.py): a verb of possibility against the squares where a
    mate exists, a verb of forcing («ставится», «можно поставить», «форсированно») against where it can be forced.
  * ``king_direction`` (shadow) — a king move advised or forbidden by its direction in a tablebase position («не
    гонись по диагонали», «вставай на одну вертикаль с пешкой»): forbidding a direction every keeping move takes,
    or advising one no keeping move takes, is wrong. Logged, never cut, until graded in production.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chess

from src.claim_scope import CONDITIONAL, NOW, YES_NO, denied_before

logger = logging.getLogger(__name__)

_W = r"(?<![а-яёa-zәғқңөұүһі])"
_E = r"(?![а-яёa-zәғқңөұүһі])"

# ── The claims ──────────────────────────────────────────────────────────────
# (pattern, role, polarity): «chase» — the king gets the pawn; «run» — the pawn gets through; «hold» — the side
# does not lose; «win» — the side wins. Polarity None: «не» before the verb decides; False: the form denies.
_CHASE_RU = (r"догон(?:ит|ишь|ят|ите|яет|яешь|яют)|догонит|догнать|поймает|поймаешь|поймают|поймать|лов(?:ит|ишь|ят)|"
             r"перехват(?:ит|ишь|ят|ить)|"
             r"успе(?:ет|ешь|ют|ете|вает|ваешь|вают|ть)")
# «задержит пешку на пару ходов» is a delay, not the pawn stopped (review 30.10: a KPK lesson the defender loses
# on the opposition was cut): only «остановит» says the pawn does not get through.
_STOP_RU = r"останов(?:ит|ишь|ят|ить)"
_CHASE_EN = r"catch(?:es)?|caught|catching\s+up|stops?|stopping|make\s+it\s+in\s+time|in\s+time"
_RUN_RU = (r"проход(?:ит|ят)(?:\s+в\s+ферзи)?|пройд[её]т(?:\s+в\s+ферзи)?|прорв[её]тся|"
           r"превращ(?:ается|аются)|превратится|станет\s+ферз[её]м|ид[её]т\s+в\s+ферзи|выйдет\s+в\s+ферзи|"
           r"дойд[её]т\s+до\s+(?:поля\s+превращения|восьмой|первой|(?:поля\s+)?(?:[a-h][18]))|"
           r"провед(?:[её]шь|[её]т|ут|[её]те)|провести|проводят|проводит|проводишь")
_RUN_EN = r"queens|promotes|will\s+queen|will\s+promote|goes\s+through|runs\s+through|is\s+unstoppable|can'?t\s+be\s+stopped|cannot\s+be\s+stopped"
_HOLD_RU = (r"удерж(?:ит|ишь|ат|ите|ать|ивает|иваешь)\s+(?:[а-я]+\s+)?ничь\w*|ничь\w*\s+(?:[а-я]+\s+)?удерж(?:ит|ишь|ат|ать|ивается)|"
            r"спас(?:[её]шься|[её]тся|ешься|утся|тись|ти\s+партию)|спасения\s+нет|спасения\s+не\s+будет")
_HOLD_EN = r"holds?\s+(?:the\s+)?draw|hold\s+(?:the\s+)?draw|save\s+the\s+game|saves\s+the\s+game|no\s+way\s+to\s+save"
_WIN_RU = (r"выиграешь|выиграет|выиграют|выиграете|выигрыша\s+нет|выигрыша\s+не\s+будет|"
           r"(?:не\s+)?выиграть(?=\s+(?:здесь\s+|тут\s+)?(?:нельзя|не\s+получится|невозможно|можно|получится))|не\s+выиграть")
_WIN_EN = r"can'?t\s+win|cannot\s+win|will\s+win|can\s+win|wins\s+by\s+force"
# The race in words of distance (plan 31.10, race_distance): «слишком далеко», «далеко от пешки», «не дотянется»,
# «опаздывает», «вне квадрата» — the king does not catch the pawn; «не слишком далеко» — it does. Only with a king
# word in the clause (_claim): «Пешка слишком далеко» is not the race.
_FAR_RU = (r"слишком\s+далеко|далеко\s+от\s+(?:пешк\w*|не[её])|не\s+дотян(?:ется|ешься|утся)|"
           r"опаздыва(?:ет|ешь|ют)|опозда(?:ет|ешь|ют)|вне\s+квадрат\w*|за\s+пределами\s+квадрат\w*")
_FAR_EN = r"too\s+far(?:\s+away)?|outside\s+(?:the\s+|its\s+)?square"
_FAR = re.compile(r"^(?:" + _FAR_RU + "|" + _FAR_EN + r")$")

# Kazakh: the denial is a suffix, so each polarity is its own form.
_KK = [
    (re.compile(_W + r"(?:қуып\s+жете\s+алмайды|жете\s+алмайды|жетпейді|үлгермейді|үлгере\s+алмайды)" + _E), "chase", False),
    (re.compile(_W + r"(?:қуып\s+жетеді|үлгереді)" + _E), "chase", True),
    (re.compile(_W + r"(?:өтпейді|өте\s+алмайды|ферзьге\s+айналмайды)" + _E), "run", False),
    (re.compile(_W + r"(?:өтіп\s+кетеді|ферзьге\s+айналады|ферзь\s+болады)" + _E), "run", True),
]
_CLAIMS = [
    (re.compile(_W + r"(?P<v>" + _CHASE_RU + "|" + _STOP_RU + r")" + _E), "chase", None),
    (re.compile(r"(?<![a-z])(?P<v>" + _CHASE_EN + r")(?![a-z])"), "chase", None),
    (re.compile(_W + r"(?P<v>" + _RUN_RU + r")" + _E), "run", None),
    (re.compile(r"(?<![a-z])(?P<v>" + _RUN_EN + r")(?![a-z])"), "run", None),
    (re.compile(_W + r"(?P<v>" + _HOLD_RU + r")" + _E), "hold", None),
    (re.compile(r"(?<![a-z])(?P<v>" + _HOLD_EN + r")(?![a-z])"), "hold", None),
    (re.compile(_W + r"(?P<v>" + _WIN_RU + r")" + _E), "win", None),
    (re.compile(r"(?<![a-z])(?P<v>" + _WIN_EN + r")(?![a-z])"), "win", None),
]
# polarity "far": the form says the king does not catch the pawn unless a denial stands before it.
_FAR_CLAIMS = [
    (re.compile(_W + r"(?P<v>" + _FAR_RU + r")" + _E), "chase", "far"),
    (re.compile(r"(?<![a-z])(?P<v>" + _FAR_EN + r")(?![a-z])"), "chase", "far"),
]
# The result named after a written line: «после Kd5 a6 Kc6 — ничья». Without a line, «это ничья» is
# _result_issues' (answer_check_rules.py).
_RESULT_AFTER_LINE = re.compile(_W + r"(?P<v>ничь[яюе]|ничейн\w+|выигрыш\w*|draw|win\s+for\s+(?:white|black))" + _E)

# Verbs that only mean the race when a pawn is the object: «остановить атаку» is not one.
_NEEDS_PAWN = re.compile(r"^(?:останов|stop|успе|in\s+time|make\s+it)")
_PAWN_WORD = re.compile(_W + r"(?:пешк\w*|pawns?|пешка\w*|пешкан\w*|квадрат\w*|square)" + _E)
_KING_WORD = re.compile(_W + r"(?:корол\w*|kings?|король\w*|корольді)" + _E)
# «успеет к пешке», «успеет догнать», «успеет в квадрат», «успеет к полю превращения»: the chase. Not «успевает
# встать перед пешкой» / "in time to stand in front": in a king-and-pawn ending the defender often gets there and
# still loses on the opposition (review 30.10) — reaching the pawn is not stopping it.
_CHASE_OBJECT = re.compile(r"^\s*(?:[а-яa-z*]+\s+){0,2}?(?:к\s+пешк|догнат|поймат|остановит|перехватит|"
                           r"в\s+квадрат|войти\s+в\s+квадрат|к\s+полю|на\s+поле\s+превращ|"
                           r"вовремя|to\s+the\s+pawn|back)", re.IGNORECASE)
# "in time to stand in front of the pawn": an infinitive after "in time to" that is not the catch.
_EN_IN_TIME_TO = re.compile(r"^\s*to\s+(?!catch|stop|reach\s+the\s+(?:pawn|square)|get\s+(?:to\s+)?the\s+pawn|enter)[a-z]+")
# «к своей пешке», "its own pawn": the king goes to its own pawn, not after the other side's (review 30.10).
_OWN_PAWN = re.compile(r"(?<![а-я])сво(?:ей|ю|я|ей|ими|их)\s+пешк|(?:its|his|their)\s+own\s+pawn")
# An infinitive governed by a finite verb before it is part of that claim: «не успевает её догнать» is one claim,
# «не успевает», not a second «догнать» without the denial (prod programme 23.10).
_GOVERNOR = re.compile(r"(?:успе\w*|мо(?:жет|жешь|гут|жете|жно)|смож\w*|получится|удастся|удаст\w*|нельзя|сумеет|сумеешь)"
                       r"\s+(?:[а-я]+\s+)?$")
_GOVERNED_BY_NEXT = re.compile(r"^\s*(?:[а-я]+\s+){0,3}?(?:успе\w*|смож\w*|сумее\w*|удаст\w*|получит\w*)(?![а-я])")
# A move told in words before the claim («Король уходит слишком далеко от пешки — … не успеваешь»; «…Kc6, и король
# встаёт перед пешкой — ничья»): the claim is about the position after it, which the check does not have.
_NARRATED = re.compile(_W + r"(?:ид[её]т|ид[её]шь|идут|пойд[её]т|пойд[её]шь|пойдут|уходит|уйд[её]т|уходишь|отходит|отступает|"
                       r"встает|вста[её]т|встанет|встанешь|забира\w+|забер[её]\w*|бер[её]т|бер[её]шь|берут|взял\w*|возьм[её]\w*|"
                       r"съеда\w+|съест|играет|играют|сыграет|сыграют|отвечает|отвечают|отвечаешь|ответит|ходит|сходит|"
                       r"переходит|перейд[её]т|прид[её]т|подходит|подойд[её]т|двига\w+|продвига\w+|"
                       r"goes|moves|takes|captures|plays|answers|replies|steps|walks|comes)" + _E)
# «пешку ты не догонишь в лоб, а встанешь у неё на дороге» (prod 28.10): a manner denied, not the result.
_MANNER = re.compile(r"^\s*(?:в\s+лоб|напрямую|прямо|сразу|по\s+прямой|по\s+диагонали|просто\s+так|head-on|directly|straight)")
_INFINITIVE = re.compile(r"^\s*(?:[а-я]+\s+){0,1}?[а-я]+(?:ть|ться|ти|чь)(?![а-я])")
# «пешка успеет пройти/дойти/превратиться»: the run.
_RUN_OBJECT = re.compile(r"^\s*(?:[а-яa-z]+\s+){0,2}?(?:пройти|дойти|превратиться|прорваться|стать\s+ферз|провести)", re.IGNORECASE)

# What makes a claim not one about this board.
_PURPOSE = re.compile(_W + r"(?:чтобы|чтоб|дабы|in\s+order\s+to|so\s+that|to)" + _E)
_ADVICE = re.compile(_W + r"(?:нужно|надо|должен|должна|должны|стоит|старайся|постарайся|попробуй|пытайся|важно|"
                     r"need\s+to|needs\s+to|must|should|have\s+to|has\s+to|try\s+to|keep|"
                     r"керек|тиіс)" + _E)
# A rule in general or another position: a study, a diagram, the rule of the square stated, «позиция, где … —
# там» (review 30.10: the square lesson explains the rule in exactly these sentences).
_GENERAL = re.compile(_W + r"(?:как\s+правило|обычно|всегда|никогда|в\s+таких|в\s+подобных|такие|таких|подобн\w+|"
                      r"в\s+общем|в\s+принципе|по\s+правилам|правило\s+гласит|теоретически|"
                      r"правил(?:о|а|у|ом)|этюд\w*|диаграмм\w*|рети|сравни\w*|там|в\s+(?:той|другой|такой)\s+позиции|"
                      r"в\s+позиции,?\s+где|позици\w*,\s+где|из\s+урока|в\s+уроке|в\s+примере|на\s+примере|"
                      r"usually|always|never|typically|in\s+general|in\s+such|such\s+(?:endings|positions)|as\s+a\s+rule|"
                      r"the\s+rule|rule\s+of\s+the\s+square|study|diagram|r[eé]ti|compare|in\s+the\s+position\s+where|"
                      r"in\s+that\s+position|in\s+the\s+lesson|"
                      r"әдетте|әрқашан)" + _E)
# Another move than the one on the board or in the line: «Kd5! Любой другой ход — и пешку уже не догнать»,
# «Играй Kd5: без этого пешку не догнать» (review 30.10).
_ALTERNATIVE = re.compile(_W + r"(?:иначе|а\s+то|или|либо|вместо|без|друг(?:ой|им|ие|ого)|ин(?:ой|ым)|"
                          r"otherwise|or\s+else|instead|or|without|any\s+other)" + _E)
_CLAUSE_END = re.compile(r"[.;:!?()\n—–]|,\s*(?=(?:а|но|однако|зато|хотя|поэтому|потому|так\s+что|и\s+тогда|тогда|если|"
                         r"когда|пока|while|but|so|because|if|when|unless)" + _E + ")")
# A condition after the claim: «пешка проходит, если король пойдёт не туда», «…после 1...Ke4», «только при ходе
# белых» (review 30.10: a condition after a comma is the normal Russian order).
_AFTER_CONDITION = re.compile(_W + r"(?:если|когда|пока|после|при(?!\s+этом)|при\s+условии|лишь\s+бы|только\s+бы|if|when|"
                              r"unless|as\s+long\s+as|provided|after|with\s+(?:white|black)\s+to\s+(?:move|play)|егер|кезде)" + _E)
_CONDITION_NEXT = re.compile(r"\s*,\s*(?:только\s+|лишь\s+|но\s+только\s+|only\s+)?(?:если|когда|пока|при|после|if|when|unless|"
                             r"after|as\s+long\s+as|provided)" + _E)
# The side to move named in the sentence («при ходе белых», «с ходом белых», «ход у белых», "with White to move"):
# when it is not the side to move on the board, the sentence is about the other turn (review 30.10).
_TURN_NAMED = re.compile(r"(?<![а-яa-z])(?:(?:при|с)\s+ход(?:е|ом)\s+|ход\s+(?:у\s+)?|(?:если|когда)\s+ходят\s+)"
                         r"(?P<ru>бел|ч[её]рн)\w*|(?P<en>white|black)\s+to\s+(?:move|play)|(?P<en2>white|black)\s+(?:moves|is\s+on\s+move)\s+first")
# Someone else's belief, a doubt, an attempt: «Кажется, что…», «Не факт, что…», «Ты пишешь, что…», «Белые надеются,
# что…», «пытается спастись» — not the coach saying it (review 30.10).
_REPORTED = re.compile(_W + r"(?:кажется|казалось|показалось|не\s+факт|вряд\s+ли|неизвестно|непонятно|сомнительно|якобы|будто|"
                       r"пишешь|пишете|написал\w*|говоришь|говорите|сказал\w*|думаешь|думаете|думают|думает|считаешь|"
                       r"считаете|считают|считает|надеются|надеется|надеешься|надеетесь|рассчитыва\w+|ожидают|ожидаешь|"
                       r"уверен[аы]?\s+ли|по-твоему|по\s+твоему|"
                       r"seems?|seemed|looks\s+like|you\s+(?:think|say|said|wrote|believe)|(?:they|white|black)\s+(?:think|hope|believe)s?|"
                       r"hopes?|not\s+sure|unlikely)" + _E)
_REJECTED = re.compile(_W + r"(?:(?:это|that'?s|that\s+is|it'?s|this\s+is)\s+(?:не\s+так|неправда|неверно|не\s+верно|"
                       r"иллюзи\w*|ошибк\w*|заблуждени\w*|not\s+(?:so|true|the\s+case)|wrong|an?\s+illusion|a\s+mistake)|"
                       r"на\s+деле\s+нет)" + _E)
_ATTEMPT = re.compile(_W + r"(?:пыта\w+|пробу\w+|старает\w*|стараются|tries|trying|attempts?)" + _E)
# A concession the same sentence takes back: «Твой король успевает встать перед пешкой, но у белых оппозиция, и они
# выигрывают», «Король задержит пешку на пару ходов, однако белые всё равно проведут её в ферзи» (review 30.10):
# the result is what comes after «но / однако», which is judged on its own.
_CONCESSION = re.compile(r"(?:^|[\s,;—–-])(?:но|однако|зато|а\s+вот|but|however|yet|still)" + _E
                         + r".*?" + _W + r"(?:выигр\w*|проигр\w*|ничь\w*|провед\w*|провод\w*|проход\w*|пройд\w*|ферз\w*|"
                         r"спас\w*|удерж\w*|wins?|winning|loses?|draw|queens?|promot\w*|holds?)" + _E)
# «Кто выиграет», «Выиграет тот, кто…»: who wins is the question, not said.
_WHO = re.compile(_W + r"(?:кто|тот|who|whoever)" + _E)
# «выиграешь темп / время / пешку / оппозицию», "win a tempo / the pawn": material or time, not the game. Only a
# win with no object, or with «партию / игру», is the result (review 30.10).
_WIN_OBJECT = re.compile(_W + r"(?:темп\w*|времени|время|пешк\w*|фигур\w*|материал\w*|качеств\w*|оппозици\w*|гонк\w*|"
                         r"пол[ея]|ход|ходы|ладь\w*|ферз\w*|кон[яей]|слон\w*|tempo|tempi|time|pawn|pawns|piece|material|"
                         r"exchange|opposition|race|square|move|rook|queen|knight|bishop|a|an)" + _E)
_WIN_ALONE = re.compile(r"^\s*(?:$|[.,;:!?)—–-]|(?:партию|игру|матч|эндшпиль|окончание|здесь|тут|уже|сейчас|легко|точно|"
                        r"обязательно|наверняка|все\s+равно|без\s+труда|белые|черные|ты|вы|они|"
                        r"the\s+game|the\s+ending|here|now|easily|anyway|by\s+force|this)(?![а-яa-z]))")
# «ферзь появляется раньше, чем вы её догоните» (prod 23.10): a comparison, not a claim.
_COMPARE = re.compile(_W + r"(?:чем|прежде|до\s+того|than|before)" + _E)
_HYPO = re.compile(_W + r"(?:бы|would|could|might)" + _E)
_QUOTES = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”")

# Whose king, whose pawn.
_STUDENT_WORD = re.compile(_W + r"(?:тво\w+|ваш\w*|ты|вы|тебе|тебя|вам|вас|your|you|сенің|сен|сіз)" + _E)
# «мой король», «мне ничью не удержать» (not «я»: «Я думаю, король догонит» is no subject).
_COACH_WORD = re.compile(_W + r"(?:мо[йяеи]\w*|мне|меня|мной|my|me|менің)" + _E)
# «Ему уже не спастись», «он догонит»: a side named by a pronoun only — whose is not known here (review 30.10).
_THIRD_PERSON = re.compile(_W + r"(?:он|она|они|ему|ей|им|его|ее|их|he|she|they|him|them)" + _E)
_WHITE_WORD = re.compile(_W + r"(?:бел\w+|white|ақ|ақтар\w*)" + _E)
_BLACK_WORD = re.compile(_W + r"(?:ч[её]рн\w+|black|қара|қаралар\w*)" + _E)
_OPPONENT_WORD = re.compile(_W + r"(?:соперник\w*|противник\w*|opponent\w*|қарсылас\w*)" + _E)
_SECOND_PERSON_VERB = re.compile(r"(?:ешь|ишь|ёшь|ете|ите|ёте)$")
# «Я чёрными», «я играю за белых», "I'm Black": the student's colour in the question.
# Only words of playing stand between («Я думаю, белые тут выигрывают?» names no colour of the student's).
_STUDENT_COLOUR = re.compile(r"(?<![а-яa-z])(?:я|i'?m|i\s+am|i\s+play)\s+(?:(?:играю|играл\w*|сейчас|тут|здесь|сегодня|"
                             r"за|сам|playing|play|as|the|on|with)\s+){0,3}?"
                             r"(?P<c>бел\w*|ч[её]рн\w*|white|black|ақ(?:пын|тармын)?|қара(?:мын|лармын)?)(?![а-яәғқңөұүһі])")
SQ = r"[a-h][1-8]"


def _student(ctx) -> Optional[chess.Color]:
    """The student's colour: the game's, the one the question names («Я чёрными»), else the side to move."""
    if getattr(ctx, "student_color", None) is not None:
        return ctx.student_color
    m = _STUDENT_COLOUR.search(getattr(ctx, "question", "") or "")
    if m:
        return chess.WHITE if m["c"].startswith(("бел", "white", "ақ")) else chess.BLACK
    board = getattr(ctx, "current", None)
    return board.turn if board is not None else None


def _student_named(ctx) -> bool:
    """The student's colour is known, not guessed from the side to move."""
    return getattr(ctx, "student_color", None) is not None or bool(_STUDENT_COLOUR.search(getattr(ctx, "question", "") or ""))


def _side_word(words: str, ctx, coach_speaks: bool = True) -> Optional[chess.Color]:
    """The colour the last side word of *words* names. In the coach's text «твой» is the student and «мой» the
    coach; in the student's question it is the other way round."""
    found = []
    for rx, kind in ((_WHITE_WORD, "w"), (_BLACK_WORD, "b"), (_STUDENT_WORD, "you"), (_COACH_WORD, "me"),
                     (_OPPONENT_WORD, "opp")):
        for m in rx.finditer(words):
            found.append((m.start(), kind))
    if not found:
        return None
    kind = max(found)[1]
    student = _student(ctx)
    if kind == "w":
        return chess.WHITE
    if kind == "b":
        return chess.BLACK
    if student is None:
        return None
    if kind == "opp":
        return not student
    if kind == "me" and coach_speaks and getattr(ctx, "student_color", None) is None:
        return None  # the coach's «мне», «мой» have a side only in a game against the student
    if (kind == "you") == coach_speaks:
        return student
    return not student


def _material_only(board: chess.Board, color: chess.Color, pawns: int) -> bool:
    """*color* has its king and exactly *pawns* pawns, nothing else."""
    pieces = [p for p in board.piece_map().values() if p.color == color and p.piece_type != chess.KING]
    return len(pieces) == pawns and all(p.piece_type == chess.PAWN for p in pieces)


def _clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The bounds of the clause the claim at start..end stands in."""
    left = 0
    for m in _CLAUSE_END.finditer(text, 0, start):
        left = m.end()
    m = _CLAUSE_END.search(text, end)
    return left, (m.start() if m else len(text))


def _in_quotes(text: str, at: int) -> bool:
    return any(m.start() < at < m.end() for m in _QUOTES.finditer(text))


def _pawn_square(words: str, board: chess.Board) -> Optional[int]:
    """The pawn the clause names by its square («пешка a5», «пешку на a5»)."""
    named = [chess.parse_square(s) for s in re.findall(r"(?<![a-z0-9])(" + SQ + r")(?![0-9])", words)]
    pawns = [sq for sq in named if board.piece_type_at(sq) == chess.PAWN]
    return pawns[-1] if pawns and len({board.color_at(sq) for sq in pawns}) == 1 else None


# ── Turning a claim into a result ───────────────────────────────────────────

def _claim(text: str, m, role: str, positive: bool, board: chess.Board, ctx, question_words: str = "") -> Optional[dict]:
    """{'side', 'wins', 'meaning', 'owner_note'} the claim says about *board*, or None when it cannot be told."""
    left, right = _clause(text, m.start(), m.end())
    before = text[left:m.start()]
    clause = text[left:right]
    verb = m.group("v") if "v" in (m.re.groupindex or {}) else m.group(0)
    whites = [sq for sq in board.pieces(chess.PAWN, chess.WHITE)]
    blacks = [sq for sq in board.pieces(chess.PAWN, chess.BLACK)]
    student = _student(ctx)
    note = ""

    if role in ("chase", "run"):
        after = text[m.end():right]
        if _FAR.match(verb) and not _KING_WORD.search(clause):
            return None  # «Пешка слишком далеко»: no king named, not the race (plan 31.10 [J])
        # The race is the subject: a pawn in the clause («король догонит пешку», «пешка проходит»), «её», or the
        # question this answers («Догонит ли мой король пешку?» — «Нет, не догонит.»). «Диагональ проходит через
        # центр», «остановить атаку» are not the race.
        if not (_PAWN_WORD.search(clause) or re.search(r"(?<![а-я])е[её](?![а-я])", clause)
                or (role == "chase" and _CHASE_OBJECT.match(after))
                or (question_words and _PAWN_WORD.search(question_words))):
            return None
        if role == "run" and re.match(r"\s*(?:через|по|мимо|к|на|сквозь|вдоль|through\s+(?![a-z]*\s*queen)|past)(?![а-яa-z])", after) \
                and "ферз" not in verb:
            return None  # «пешка проходит на d6», «проходит мимо»: a move, not the queening
        if role == "chase" and _OWN_PAWN.search(after):
            return None  # «белый король успевает к своей пешке»: not the chase
        if role == "chase" and _NEEDS_PAWN.match(verb):
            subject = _race_subject(before, question_words) if verb.startswith("успе") else "king"
            if subject == "pawn" or (verb.startswith("успе") and _RUN_OBJECT.match(after)):
                role = "run"  # «пешка успеет пройти», «Да, успеет.» to «Моя пешка успеет?» (review 30.10)
            elif subject is None:
                return None
            elif verb.startswith("успе") and _INFINITIVE.match(after) and not _CHASE_OBJECT.match(after):
                return None  # «ваш король не успевает поддержать пешку» (prod 19.10): not the chase
            elif verb.startswith("in") and _EN_IN_TIME_TO.match(after):
                return None  # "in time to stand in front of the pawn": reaching it, not stopping it
        # The pawn's side.
        runner: Optional[chess.Color] = None
        sq = _pawn_square(clause, board)
        if sq is not None:
            runner = board.color_at(sq)
        if role == "chase":
            king_m = list(_KING_WORD.finditer(before))
            chaser = None
            if king_m:
                chaser = _side_word(before[max(0, king_m[-1].start() - 20):king_m[-1].end()], ctx)
            if chaser is None:
                subj = _side_word(before, ctx)
                if subj is not None:
                    chaser = subj
                elif _SECOND_PERSON_VERB.search(verb) and not verb.startswith(("catch", "stop")):
                    chaser = student
            if chaser is None and question_words:
                qk = list(_KING_WORD.finditer(question_words))
                if qk:
                    chaser = _side_word(question_words[max(0, qk[-1].start() - 20):qk[-1].end()], ctx, coach_speaks=False)
            if chaser is not None:
                if runner is not None and runner == chaser:
                    return None  # «белый король успевает вернуться» — the pawn's own king, not the chase
                runner = not chaser
        else:
            pawn_m = list(_PAWN_WORD.finditer(before))
            owner = None
            if pawn_m:
                owner_words = before[max(0, pawn_m[-1].start() - 20):pawn_m[-1].end()]
                owner = _side_word(owner_words, ctx)
            elif before.strip():
                owner = _side_word(before, ctx)  # «белые проводят пешку», «ты проведёшь»
            if owner is None and _SECOND_PERSON_VERB.search(verb):
                owner = student
            if owner is not None and runner is None:
                mine = whites if owner == chess.WHITE else blacks
                theirs = blacks if owner == chess.WHITE else whites
                if not mine and theirs and pawn_m and _STUDENT_WORD.search(owner_words) and _student_named(ctx):
                    # «Твоя пешка проходит» when the student has none: the pawn is the other side's (prod 29.10).
                    note = (f"; the pawn is {'White' if not owner else 'Black'}'s, not the student's "
                            f"(the student plays {'White' if owner else 'Black'})")
                    owner = not owner
                runner = owner
        if runner is None:
            sides = {c for c, ps in ((chess.WHITE, whites), (chess.BLACK, blacks)) if ps}
            if len(sides) != 1:
                return None
            runner = sides.pop()
        mine = whites if runner == chess.WHITE else blacks
        if not mine:
            return None
        chaser = not runner
        gets_through = (role == "run") == positive  # the pawn queens / the king does not catch it
        name, other = ("White", "Black") if runner == chess.WHITE else ("Black", "White")
        where = f" on {chess.square_name(sq)}" if sq is not None else (f" on {chess.square_name(mine[0])}" if len(mine) == 1 else "")
        if gets_through:
            if not _material_only(board, chaser, 0):
                return None  # the pawn may queen and the game still be a draw: other material counts
            said = (f"the {name.lower()} pawn{where} queens" if role == "run"
                    else f"the {other.lower()} king does not catch the {name.lower()} pawn{where}")
            return {"side": runner, "wins": True, "meaning": f"{said}, so {name} wins", "note": note}
        if not _material_only(board, runner, 1):
            return None  # catching one pawn of several decides nothing
        said = (f"the {name.lower()} pawn{where} does not get through" if role == "run"
                else f"the {other.lower()} king catches the {name.lower()} pawn{where}")
        return {"side": runner, "wins": False, "meaning": f"{said}, so {name} does not win", "note": note}

    # «hold» / «win»: a side's result.
    if role == "win" and not verb.startswith("выигрыша"):
        after = text[m.end():right]
        if _WHO.search(before) or not _WIN_ALONE.match(after) or _WIN_OBJECT.search(after[:40]):
            return None  # «Кто выиграет», «выиграешь темп», "win a tempo": not the game's result
    if role == "hold" and re.match(r"\s*(?:[а-я]+\s+)?(?:от|from)(?![а-яa-z])", text[m.end():right]):
        return None  # «спасётся от шахов только на время»: escapes the checks, not the game (review 30.10)
    side = _side_word(before + m.group(0), ctx)  # «белые удержат ничью», «ничью ты удержишь»; «удержишь»: the student
    if side is None:
        # «Ему уже не спастись», the coach's «мне» outside a game, or a bare «спасения нет» whose student is only
        # guessed from the side to move — the side is not known, and a guess must not cut a true sentence
        # (review 30.10: «Спасения нет: чёрный король уже прижат к краю» was read as White's).
        if _THIRD_PERSON.search(before) or _COACH_WORD.search(before):
            return None
        if not _student_named(ctx) and not re.search(r"(?:[еиё]шь|[еиё]те|[еиё]шься|[еиё]тесь)(?![а-я])", m.group(0)):
            return None  # «удержишь», «спасёшься» speak to the student; a bare «спасения нет» names no one
        side = student
    if side is None:
        return None
    name = "White" if side == chess.WHITE else "Black"
    other = "Black" if side == chess.WHITE else "White"
    if role == "hold":
        lost = verb.startswith(("спасения", "no way")) or not positive
        if lost:
            return {"side": not side, "wins": True, "meaning": f"{name} cannot save the game, so {other} wins", "note": ""}
        return {"side": not side, "wins": False, "meaning": f"{name} holds the draw, so {other} does not win", "note": ""}
    denied = verb.startswith(("выигрыша", "не ", "can't", "cannot")) or not positive \
        or bool(re.search(r"нельзя|не\s+получится|невозможно", text[m.end():m.end() + 30]) and verb.startswith("выиграть"))
    if denied:
        return {"side": side, "wins": False, "meaning": f"{name} cannot win", "note": ""}
    return {"side": side, "wins": True, "meaning": f"{name} wins", "note": ""}


_INFINITIVE_IN = re.compile(r"(?<![а-я])[а-я]+(?:ть|ти|чь|тись|ться)(?![а-я])")
_DENIED_AFTER = re.compile(r"\s*(?:[а-яa-z]+\s+){0,3}?(?:нельзя|невозможно|не\s+получится|не\s+выйдет|не\s+удастся|"
                           r"не\s+суждено|никак\s+не\s+получится)(?![а-я])")
_CAN_AFTER = re.compile(r"\s*(?:[а-яa-z]+\s+){0,3}?(?:можно|возможно)(?![а-я])")
_NOUN_PAWN = re.compile(_W + r"(?:пешка|пешки|pawns?)" + _E)  # the pawn as the subject (nominative)
_NOUN_KING = re.compile(_W + r"(?:король|корол\w*|kings?)" + _E)
_NOUN_PERSON = re.compile(_W + r"(?:ты|вы|я|you|i|white|black|бел\w+|ч[её]рн\w+)" + _E)


def _race_subject(before: str, question_words: str) -> Optional[str]:
    """Who «успеет»: 'pawn' («пешка успевает первой»; «Да, успеет» to «Моя пешка успеет?»), 'king', or None when
    the answer's subject cannot be told from a pawn-only question."""
    nouns = [(mm.start(), "pawn") for mm in _NOUN_PAWN.finditer(before)] + \
            [(mm.start(), "king") for mm in _NOUN_KING.finditer(before)]
    if nouns:
        return max(nouns)[1]
    pawn_question = bool(question_words and _PAWN_WORD.search(question_words) and not _KING_WORD.search(question_words)
                         and re.search(r"(?<![а-я])успе", question_words))
    if not pawn_question:
        return "king"
    return None if _NOUN_PERSON.search(before) else "pawn"


def _wrong(claim: dict, board: chess.Board, result: str, raw: Optional[dict], where: str = "") -> Optional[str]:
    """The issue when the tablebase's *result* ('White wins' / 'Black wins' / 'draw') contradicts *claim*."""
    name = "White" if claim["side"] == chess.WHITE else "Black"
    if claim["wins"] == (result == f"{name} wins"):
        return None
    truth = "it is a draw with best play" if result == "draw" else f"{result} with best play"
    extra = ""
    if raw:
        mover = "White" if board.turn == chess.WHITE else "Black"
        keeping = [k for k in (raw.get("keeping") or []) if k]
        total = board.legal_moves.count()
        if result == "draw" and keeping and len(keeping) < total:
            extra = f" — {mover} holds it only with {', '.join(keeping[:6])}; every other move loses"
        elif result == f"{mover} wins" and raw.get("best_san"):
            extra = f" — the winning move is {raw['best_san']}"
        elif result != "draw":
            extra = f" — every {mover} move loses"
    return (f"the sentence says {claim['meaning']}{where}, but the endgame tablebase (exact) says {truth}"
            f"{extra}{claim.get('note', '')}")


# ── The sentence ────────────────────────────────────────────────────────────

def _line_board(text: str, at: int, ctx) -> tuple[Optional[chess.Board], str, int]:
    """(board, line, first move's offset) the claim at *at* is about when a line written in this sentence comes
    before it and is legal from the board in front of the student, move after move; (None, '', -1) otherwise,
    and (current, '', -1) when no move is written before the claim."""
    from src.answer_check_rules import _WRITTEN_MOVE

    written = [w.start() for w in _WRITTEN_MOVE.finditer(text[:at])]
    trail = getattr(ctx, "scene_trail", []) or []
    if not trail:
        return (ctx.current, "", -1) if not written else (None, "", -1)
    # Where each move of the line stands in the sentence: the moves before the claim are the line it ends.
    found, pos = [], 0
    for san, after, move in trail:
        token = san.rstrip("+#").lower()
        hit = re.compile(r"(?<![a-z])" + re.escape(token)).search(text, pos)  # «e5» is not the end of «ke5»
        i = hit.start() if hit else -1
        if i < 0:
            return None, "", -1  # written in another notation: where the line stops is not known
        if i >= at:
            break
        found.append((i, san, after, move))
        pos = i + len(token)
    if not found:
        return (ctx.current, "", -1) if not written else (None, "", -1)
    last_end = found[-1][0] + len(found[-1][1].rstrip("+#"))
    spans = [(i, i + len(san.rstrip("+#"))) for i, san, *_ in found]
    for sq in re.finditer(r"(?<![a-z0-9])[a-h](?:x[a-h])?[1-8](?![0-9])", text[:at]):
        if any(a <= sq.start() < b for a, b in spans):
            continue
        if sq.start() >= last_end:
            # «Kd4? a6 — …», «после Kd5 и a6 ты успеваешь»: the line goes on with a move the check did not follow
            # (or names a square of a position it did not reach) — where it ends is not known.
            return None, "", -1
        if re.search(r"(?:на|в|к|с|поле|on|to)\s*$", text[max(0, sq.start() - 8):sq.start()]):
            continue  # «встаёт на c6»: a square, not a move
        near = any(re.fullmatch(r"[\s,.…\d]{0,6}", text[sq.end():a]) or re.fullmatch(r"[\s,.…\d?!]{0,6}", text[b:sq.start()])
                   for a, b in spans)
        if near:
            return None, "", -1  # «e5 Kf4 Kf6»: a pawn move of the line that the check did not follow
    if _NARRATED.search(text[last_end:at]):
        return None, "", -1  # «…Kc6, и король встаёт перед пешкой — ничья»: the line goes on in words
    starts = {i for i, *_ in found}
    if any(w not in starts for w in written):
        return None, "", -1  # a move written before the claim did not join the line
    board = ctx.current.copy(stack=False)
    for _i, _san, after, move in found:
        if move not in board.legal_moves:
            return None, "", -1  # the line does not start from the board (another position, a side branch)
        board.push(move)
        if board.board_fen() != after.board_fen():
            return None, "", -1
    return board, " ".join(san for _i, san, *_ in found), found[0][0]


def _about_this_board(text: str, start: int, end: int, line_from: int) -> bool:
    left, right = _clause(text, start, end)
    clause_before = text[left:start]
    if _in_quotes(text, start) or text.rstrip().endswith("?") or re.match(r"\s+ли(?![а-я])", text[end:end + 4]):
        return False
    if _GENERAL.search(text) or _HYPO.search(text[left:right]):
        return False
    if _PURPOSE.search(clause_before) or _ADVICE.search(clause_before) or _COMPARE.search(clause_before):
        return False
    if _AFTER_CONDITION.search(text[end:right]) or _CONDITION_NEXT.match(text, right):
        return False  # «догонит, если сыграет Kd5», «пешка проходит, если король пойдёт не туда»
    if _REPORTED.search(text[:start]) or _REJECTED.search(text[end:]) or _ATTEMPT.search(clause_before):
        return False  # «Кажется, что король догонит…», «Ты пишешь, что пешка проходит, — это не так», «пытается спастись»
    if _CONCESSION.search(text[end:]):
        return False  # «успевает встать перед пешкой, но … они выигрывают»: the result is said after «но»
    if line_from >= 0:
        # A line: a condition may introduce it («после Kd5 a6 Kc6 — ничья», «если Ke4, пешка проходит»), not
        # stand between it and the claim («Kd5, и если белые ошибутся…») or offer another line («…или Kd6»).
        between = text[line_from:start]
        if _AFTER_CONDITION.search(between) or _ALTERNATIVE.search(text[:start]) or _HYPO.search(text[:start]):
            return False
        return True
    if CONDITIONAL.search(text[:start]):
        return False  # «Если помедлишь, … твоя пешка уже никуда не пройдёт» (prod programme 23.10): «уже» is no anchor
    if _NARRATED.search(text[:start]):
        return False  # «Король уходит слишком далеко — … догнать её ты уже не успеваешь»: after a move told in words
    if _ALTERNATIVE.search(text[:start]):
        return False
    return True


_ELLIPTIC_Q = re.compile(_W + r"(?:догон\w*|догнат\w*|успе\w*|поймае\w*|поймат\w*|остановит\w*|проход\w*|пройд\w*|"
                         r"удерж\w*|спас\w*|выигр\w*|ничь\w*|catch\w*|queen\w*|hold|save|win|қуып|үлгер\w*|өте\w*)" + _E)


def _mode(name: str, ctx) -> str:
    """The detector's switch (src/config.detector_mode): 'on', 'shadow' or 'off'; 'off' when it cannot be read."""
    try:
        from src.config import detector_mode

        return detector_mode(name, ctx)
    except Exception:  # noqa: BLE001
        return "off"


def _shadow(name: str, text: str, issues: list, ctx) -> None:
    """A shadow detector's issue: logged and kept on ctx.detector_shadow, never shown or cut."""
    logger.info("detector %s (shadow): %r -> %s", name, text[:160], issues)
    try:
        log = getattr(ctx, "detector_shadow", None)
        if log is None:
            log = []
            ctx.detector_shadow = log
        log.append((name, text, list(issues)))
    except Exception:  # noqa: BLE001
        pass


def _gated(name: str, text: str, issues: list, ctx) -> list:
    """*issues* as the detector's switch lets them through."""
    if not issues:
        return []
    mode = _mode(name, ctx)
    if mode == "on":
        return issues
    if mode == "shadow":
        _shadow(name, text, issues, ctx)
    return []


def outcome_issues(text: str, ctx) -> list[str]:
    """The outcome claims of *text* (lower case, ё → е) that the tablebase contradicts, then where a mate can stand
    (mate_square_issues) and the king's direction (king_direction_issues, shadow). A claim at the end of a line
    whose position is not in the tablebase cache yet is left in ctx for pop_pending."""
    out = []
    try:
        out += _gated("mate_squares", text, mate_square_issues(text, ctx), ctx)
    except Exception:  # noqa: BLE001 — a broken table must never block an answer
        logger.debug("mate_squares failed", exc_info=True)
    out += _race_issues(text, ctx)
    try:
        out += _gated("king_direction", text, king_direction_issues(text, ctx), ctx)
    except Exception:  # noqa: BLE001
        logger.debug("king_direction failed", exc_info=True)
    return out


def _race_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    if board is None or len(board.piece_map()) > 7 or not board.is_valid() or board.is_game_over():
        return []
    far_mode = _mode("race_distance", ctx)
    claims = []
    for rx, role, polarity in _CLAIMS + _KK + (_FAR_CLAIMS if far_mode != "off" else []):
        for m in rx.finditer(text):
            claims.append((m.start(), m, role, polarity))
    for m in _RESULT_AFTER_LINE.finditer(text):
        claims.append((m.start(), m, "result", True))
    if not claims:
        return []
    claims.sort(key=lambda c: c[0])
    question = getattr(ctx, "question", "") or ""
    # An answer to a question about the race («Нет, не догонит.», «Нет, король не успевает») takes what the
    # sentence leaves out — the pawn, whose king — from the question.
    elliptic = bool(_ELLIPTIC_Q.search(question)) and (bool(_PAWN_WORD.search(question)) or (
        not _PAWN_WORD.search(text) and not _KING_WORD.search(text)))
    issues = []
    seen_spans = []
    for start, m, role, polarity in claims:
        if any(a <= start < b for a, b in seen_spans):
            continue  # «удержишь ничью» is one claim, not «удержишь» and «ничью»
        seen_spans.append((m.start(), m.end()))
        target, line, line_from = _line_board(text, start, ctx)
        if target is None:
            continue
        if role == "result" and not line:
            continue  # «это ничья» on the board: _result_issues
        if not _about_this_board(text, start, m.end(), line_from):
            continue
        # A sentence after a line written before it, with no word that brings it back to the board, may be about
        # the line's end («Сыграешь Ke4 — a6. Теперь пешку не догнать.»): not judged.
        prev = getattr(ctx, "scene_before", None)
        if not line and prev and prev[0] is not None and prev[2] <= 3 and not NOW.search(text) and not YES_NO.search(text):
            continue
        if not line:
            turn = _TURN_NAMED.search(text)
            if turn and (turn["ru"] or turn["en"] or turn["en2"]).startswith(("бел", "white")) != (target.turn == chess.WHITE):
                continue  # «Пешка проходит только при ходе белых» with Black to move: the other turn (review 30.10)
        denied_here = bool(denied_before(text, start) or re.search(r"(?:^|\s)(?:не|ни|not|never)\s+(?:\w+\s+)?$",
                                                                    text[max(0, start - 16):start]))  # «уже не догнать»
        denied_after = False
        if role != "win" and _INFINITIVE_IN.search(m.group(0)):
            # An infinitive is a claim only with what says whether it can be done: «уже не догнать», «ничью не
            # удержать»; «Удержать ничью здесь нельзя», «Пешку догнать уже не выйдет» — the denial after it (review
            # 30.10: these true sentences were read as the opposite); «догнать пешку можно».
            denied_after = bool(_DENIED_AFTER.match(text, m.end()))
            if not denied_after:
                if _GOVERNOR.search(text[max(0, start - 30):start]) or _GOVERNED_BY_NEXT.match(text[m.end():]):
                    continue  # governed: the finite verb («не успевает её догнать», «догнать её ты не успеваешь») is the claim
                if not (denied_here or re.search(r"(?:^|\s)не\s", m.group(0)) or _CAN_AFTER.match(text, m.end())):
                    continue  # «Твоя задача — удержать ничью», «спастись в центре»: a goal, not a result
            denied_here = denied_here or denied_after
        if denied_here and (_MANNER.match(text[m.end():]) or re.match(r"[^.;:!?()\n—–]*,\s*а\s", text[m.end():])):
            continue  # «не догонишь в лоб, а встанешь на дороге»: the denial is of the manner, «а» says what is
        if polarity == "far":
            # «слишком далеко» — the king does not catch the pawn; «не слишком далеко» — it does.
            positive = bool(denied_here)
        else:
            positive = polarity if polarity is not None else not (
                denied_here or re.search(r"(?:^|\s)(?:не|not)\s", m.group(0))  # «ничью не удержать»
                or re.search(r"no\s+longer\s+$", text[max(0, start - 12):start]))
        if role == "result":
            v = m.group("v")
            if v.startswith(("ничь", "ничейн", "draw")):
                claim = {"side": target.turn, "wins": False, "meaning": "it is a draw", "note": ""}
                claim2 = {"side": not target.turn, "wins": False, "meaning": "it is a draw", "note": ""}
                parsed = [claim, claim2] if positive else []
            else:
                continue  # «выигрыш» after a line: whose is not said
        else:
            c = _claim(text, m, role, bool(positive), target, ctx, question if elliptic else "")
            if c and polarity == "far" and far_mode != "on":
                c["shadow"] = "race_distance"  # logged, never cut (COACH_DETECTORS_SHADOW)
            parsed = [c] if c else []
        for claim in parsed:
            if not target.is_valid() or len(target.piece_map()) > 7:
                break
            if target.is_game_over():
                break
            if line:
                found = _cached(target)
                if found is None:
                    _remember(ctx, text, target, claim, line)
                    continue
                raw = found[1]
                if not raw:
                    break
                from src.board_rules import tablebase_white_result

                issue = _wrong(claim, target, tablebase_white_result(target, raw), raw, f" after {line}")
            else:
                result = getattr(ctx, "tablebase", None)
                if not result:
                    break
                found = _cached(target)
                issue = _wrong(claim, target, result, found[1] if found else None)
            if issue and claim.get("shadow"):
                _shadow(claim["shadow"], text, [issue], ctx)
                break
            if issue:
                issues.append(issue)
                break
    return list(dict.fromkeys(issues))[:1]


def _cached(board: chess.Board):
    try:
        from src.board_rules import tablebase_cached

        return tablebase_cached(board)
    except Exception:  # noqa: BLE001
        return None


# ── Lines: the tablebase asked in the engine stage ──────────────────────────

def _remember(ctx, text: str, board: chess.Board, claim: dict, line: str) -> None:
    pending = getattr(ctx, "outcome_pending", None)
    if pending is None:
        pending = {}
        try:
            ctx.outcome_pending = pending
        except Exception:  # noqa: BLE001
            return
    pending.setdefault(_key(text), []).append((board.fen(), claim, line))


def _key(text: str) -> str:
    """The sentence as check_sentence hands it to the rules (no Markdown emphasis, ё → е, Cyrillic files as Latin,
    lower case), so the gate's own copy of it finds its claims: «После Kd2 Kg7 Kc3 — **ничья**.» is remembered by
    its stripped text and popped by the raw one (review 30.10: every bold line-end claim stayed unjudged)."""
    from src.answer_check import _EMPHASIS

    text = _EMPHASIS.sub("", text or "").replace("ё", "е")
    text = re.sub(r"(?<![а-яА-Яa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))",
                  lambda m: {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}[m.group(1).lower()],
                  text)
    return re.sub(r"\s+", " ", text.lower()).strip()


def pop_pending(ctx, sentence: str) -> list:
    """The claims of *sentence* at the end of a line whose tablebase verdict check_sentence did not have."""
    pending = getattr(ctx, "outcome_pending", None) or {}
    return pending.pop(_key(sentence), [])


def judge_pending(items: list) -> Optional[str]:
    """Ask the tablebase (network, ≤ COACH_TABLEBASE_TIMEOUT_S, cached) about each line's end; the first
    contradicted claim's issue, or None. Never raises — run it off the event loop."""
    try:
        from src.board_rules import tablebase, tablebase_white_result

        for fen, claim, line in items[:4]:  # a board asked once: the answers are cached
            board = chess.Board(fen)
            raw = tablebase(board)
            if not raw:
                continue
            issue = _wrong(claim, board, tablebase_white_result(board, raw), raw, f" after {line}")
            if issue and claim.get("shadow"):
                logger.info("detector %s (shadow): %s", claim["shadow"], issue)
                continue
            if issue:
                return issue
    except Exception:  # noqa: BLE001 — a lookup that fails leaves the sentence as it is
        return None
    return None


def tablebase_from_cache(ctx) -> None:
    """Set ctx.tablebase (and the engine evaluation it makes exact) for the board in front of the student from
    the tablebase answers this turn has already fetched — the board facts ask the tablebase too, so a turn whose
    engine line was late (the facts-only fallback), whose lookup missed the line's 0.5 s, or a live game (the
    game's facts, no line) told the model the result and left the check without it (30.10)."""
    board = getattr(ctx, "current", None)
    if board is None or getattr(ctx, "tablebase", None) or len(board.piece_map()) > 7:
        return
    found = _cached(board)
    if not found or not found[1]:
        return
    try:
        from src.board_rules import tablebase_white_result

        ctx.tablebase = tablebase_white_result(board, found[1])
        ctx.engine_eval = 0.0 if ctx.tablebase == "draw" else (20.0 if ctx.tablebase.startswith("White") else -20.0)
    except Exception:  # noqa: BLE001
        return


# ── Where a mate can stand (plan 31.10, mate_squares) ───────────────────────
# «Мат случается только если чёрный король сам забредёт в угол» (two knights, prod 29.10): mate with K+N+N is
# possible on the edge far from any corner too. A claim «mate only <in the corner | on the edge>» about one of the
# five basic endings is judged against src/data/mate_squares.json (scripts/build_mate_squares.py).
_MATE_DATA = Path(__file__).resolve().parent / "data" / "mate_squares.json"
_MATE_WORD = re.compile(_W + r"(?:мат|мата|мату|матом|мате|маты|матов|матовая|матовую|матовой|заматова\w*|замату\w*|"
                        r"мату(?:ет|ют|ешь|ем)|матова(?:ть|ли|л)|checkmate[sd]?|checkmating|mate[sd]?|mating)" + _E)
_ONLY = re.compile(_W + r"(?:только|лишь|исключительно|only)" + _E)
_CORNER_WORD = r"угол|угл[аеуы]|углах|углам|углов\w*|corners?"
_EDGE_WORD = r"кра(?:й|я|ю|е|ях|ям|ями)|бортик\w*|edges?|side\s+of\s+the\s+board"
# «только» + up to 8 words + a preposition + up to 2 words + the place: «только если король сам забредёт в угол»,
# «только прижатого к краю короля», «только у самого края доски, в углу».
_ONLY_PLACE = re.compile(r"\s*(?:[^\s.;!?—–:]+\s+){0,8}?(?:в|во|на|у|к|по|in|on|at|to|into|near|along)\s+"
                         r"(?:[^\s.;!?—–:]+\s+){0,2}?(?P<place>" + _CORNER_WORD + "|" + _EDGE_WORD + r")" + _E)
_MORE_PLACE = re.compile(r"(?:\s+[^\s.;!?—–:,]+){0,2}?\s*(?:,|или|и|либо|or|and)\s*(?:[^\s.;!?—–:]+\s+){0,3}?"
                         r"(?P<place>" + _CORNER_WORD + "|" + _EDGE_WORD + r")" + _E)
_MATE_DENIAL = re.compile(_W + r"(?:не|нет|нельзя|невозможн\w*|никогда|ни\s+в\s+коем|not|never|cannot|can'?t|impossible)" + _E)
# A verb of possibility: «случается», «бывает», «возможен», «получается» — judged on where a mate exists at all.
# Anything else («ставится», «можно поставить», «форсированно», «матует», no verb) is about the mate forced.
_POSSIBLE_VERB = re.compile(_W + r"(?:случа\w+|бывает|бывают|возмож\w+|получа\w+|происходит|встречается|возника\w+|"
                            r"может\s+(?:быть|случиться|получиться|возникнуть|произойти)|"
                            r"happens?|possible|can\s+(?:happen|occur|arise)|occurs?)" + _E)
# A concrete line or a mate in N is about one position, not the ending: «мат в два хода возможен только …»,
# «после Kc2 мат только в углу» — not judged.
_SPECIFIC = re.compile(r"(?<![a-zа-я])(?:[kqrbnкфлсн]р?[a-h]?x?[a-h][1-8]|\d+\.|o-o)|"
                       + _W + r"(?:ход\w*|move[sd]?|mate\s+in\s+\d|после|after)" + _E)
_ENDING_WORDS = [
    ("KBNK", re.compile(_W + r"(?:слон\w*\s+и\s+кон[еёя]\w*|кон[еёя]\w*\s+и\s+слон\w*|слон\w*\s+с\s+кон\w*|"
                        r"bishop\s+and\s+(?:a\s+)?knight|knight\s+and\s+(?:a\s+)?bishop)" + _E)),
    ("KBBK", re.compile(_W + r"(?:двумя\s+слонами|два\s+слона|двух\s+слонов|двух\s+слона|слоновой\s+пар\w*|"
                        r"пар\w*\s+слонов|two\s+bishops|bishop\s+pair)" + _E)),
    ("KNNK", re.compile(_W + r"(?:двумя\s+конями|два\s+коня|двух\s+коней|двух\s+коня|пар\w*\s+коней|"
                        r"two\s+knights)" + _E)),
    ("KQK", re.compile(_W + r"(?:ферз\w*|queen)" + _E)),
    ("KRK", re.compile(_W + r"(?:ладь\w*|ладей|rook)" + _E)),
]


@lru_cache(maxsize=1)
def _mate_table() -> dict:
    try:
        return json.loads(_MATE_DATA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — no table, no judgement
        logger.warning("mate_squares: %s not readable", _MATE_DATA)
        return {}


def _board_ending(board) -> Optional[str]:
    """'KQK', 'KRK', 'KBBK' (bishops on both colours), 'KBNK' or 'KNNK' when the board is that ending."""
    if board is None:
        return None
    sides = []
    for color in (chess.WHITE, chess.BLACK):
        sides.append(sorted(p.piece_type for p in board.piece_map().values() if p.color == color
                            and p.piece_type != chess.KING))
    if sum(1 for s in sides if s) != 1:
        return None
    pieces = sides[0] or sides[1]
    color = chess.WHITE if sides[0] else chess.BLACK
    name = {(chess.QUEEN,): "KQK", (chess.ROOK,): "KRK", (chess.KNIGHT, chess.BISHOP): "KBNK",
            (chess.KNIGHT, chess.KNIGHT): "KNNK"}.get(tuple(pieces))
    if tuple(pieces) == (chess.BISHOP, chess.BISHOP):
        squares = list(board.pieces(chess.BISHOP, color))
        name = "KBBK" if len({(chess.square_file(q) + chess.square_rank(q)) % 2 for q in squares}) == 2 else None
    return name


def _sentence_ending(text: str) -> tuple[Optional[str], bool]:
    """(the ending the sentence names, whether it names more than one)."""
    found = []
    taken = []
    for name, rx in _ENDING_WORDS:
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue  # «слоном и конём» is not also «конём»
            taken.append((m.start(), m.end()))
            found.append(name)
    found = list(dict.fromkeys(found))
    return (found[0] if len(found) == 1 else None), len(found) > 1


def mate_square_issues(text: str, ctx) -> list[str]:
    """«Мат (случается | ставится) только в углу / на краю» that src/data/mate_squares.json contradicts."""
    if not _ONLY.search(text) or not _MATE_WORD.search(text):
        return []
    if text.rstrip().endswith("?") or _HYPO.search(text) or _REPORTED.search(text) or _REJECTED.search(text):
        return []
    if _SPECIFIC.search(text):
        return []
    table = (_mate_table() or {}).get("endings") or {}
    regions = {k: set(v) for k, v in ((_mate_table() or {}).get("regions") or {}).items()}
    if not table or not regions:
        return []
    for only in _ONLY.finditer(text):
        if re.search(r"(?:^|\s)(?:не|not)\s*$", text[max(0, only.start() - 5):only.start()]):
            continue  # «не только в углу»
        if _in_quotes(text, only.start()):
            continue
        pm = _ONLY_PLACE.match(text, only.end())
        if not pm:
            continue
        # The mate word stands in the same sentence part, before «только» or inside the stretch to the place.
        left = max([0] + [m.end() for m in re.finditer(r"[.;!?]", text[:only.start()])])
        mate = None
        for mm in _MATE_WORD.finditer(text, left, pm.end()):
            mate = mm
            break
        if mate is None:
            continue
        span = text[mate.start():pm.end()]
        if _MATE_DENIAL.search(span):
            continue  # «мат не ставится только …», «мата нет …»: a denial is not the claim
        places = {"corner" if re.match(_CORNER_WORD, pm["place"]) else "edge"}
        pos = pm.end()
        while True:
            more = _MORE_PLACE.match(text, pos)
            if not more:
                break
            places.add("corner" if re.match(_CORNER_WORD, more["place"]) else "edge")
            pos = more.end()
        name, several = _sentence_ending(text)
        if several:
            return []
        if name is None:
            name = _board_ending(getattr(ctx, "current", None))
        entry = table.get(name or "")
        if not entry:
            continue
        allowed = set().union(*(regions[p] for p in places))
        possible = set(entry.get("possible") or [])
        if possible <= allowed:
            continue  # «ладьёй мат ставится только на краю»: true
        verb_possible = bool(_POSSIBLE_VERB.search(text, mate.start(), pm.end() + 40))
        outside = sorted(possible - allowed, key=_middle_first)
        where_said = " or ".join("in the corner" if p == "corner" else "on the edge" for p in sorted(places))
        what = entry.get("name") or name
        example = (entry.get("example") or {}).get(outside[0])
        shown = f" — e.g. the bare king mated on {outside[0]}: {example}" if example else ""
        if verb_possible:
            never = " (it can never be forced)" if (entry.get("forced_outside") or {}).get("never_forced") else ""
            return [f"the sentence says that in {what} ({name}) mate happens only {where_said}, but mate is possible "
                    f"on the edge, not only in the corner: on {', '.join(outside[:8])} too{shown}{never}"]
        if len(places) != 1 or (entry.get("forced_outside") or {}).get(next(iter(places))) is not True:
            continue  # forced: judged only where the table has solved it
        return [f"the sentence says that in {what} ({name}) mate is forced only {where_said}, but the stronger side "
                f"can force the mate on the edge away from the corner as well: on {', '.join(outside[:8])}{shown}"]
    return []


def _middle_first(name: str) -> tuple:
    """Squares nearest the middle of an edge first (d8 before b8): the clearest example of «not in the corner»."""
    sq = chess.parse_square(name)
    f, r = chess.square_file(sq), chess.square_rank(sq)
    return (min(abs(f - 3.5), abs(r - 3.5)), name)


# ── The king's direction (plan 31.10, king_direction; shadow) ───────────────
# «Поэтому не гонись за ней по диагонали: вставай на одну вертикаль с пешкой» (prod 29.10, square: Kd5 and Kd6
# draw). Each king move of the side to move is sorted by the direction the sentence names; the tablebase's keeping
# moves decide: forbidding a direction every keeping move takes, or advising one no keeping move takes, is wrong.
_DIRECTIONS = [
    ("diagonal", re.compile(_W + r"(?:по\s+диагонал\w*|наискос\w*|diagonally|along\s+the\s+diagonal)" + _E)),
    ("pawn_file", re.compile(_W + r"(?:на\s+(?:одну\s+)?(?:вертикаль|линию)\s+(?:с\s+)?(?:е[её]|пешк\w*)|"
                             r"на\s+вертикаль\s+пешк\w*|onto\s+the\s+pawn'?s\s+file|on\s+the\s+same\s+file\s+as\s+the\s+pawn)" + _E)),
    ("file", re.compile(_W + r"(?:по\s+вертикал\w*|vertically|along\s+the\s+file)" + _E)),
    ("rank", re.compile(_W + r"(?:по\s+горизонтал\w*|horizontally|along\s+the\s+rank)" + _E)),
    ("toward_pawn", re.compile(_W + r"(?:прямо\s+к\s+(?:пешк\w*|не[йеё])|напрямую\s+к\s+(?:пешк\w*|не[йеё])|"
                               r"straight\s+(?:at|to|towards?)\s+the\s+pawn)" + _E)),
]
_KING_GO = re.compile(_W + r"(?:гонись|гоняйся|иди|идите|ходи|двигайся|двигай|вставай|встань|подходи|приближайся|"
                      r"веди|направляй|отступай|бег[иа]|go|move|walk|run|chase|head|step|approach)" + _E)


def _move_class(kind: str, board, move, pawn: int) -> bool:
    df = chess.square_file(move.to_square) - chess.square_file(move.from_square)
    dr = chess.square_rank(move.to_square) - chess.square_rank(move.from_square)
    if kind == "diagonal":
        return df != 0 and dr != 0
    if kind == "file":
        return df == 0
    if kind == "rank":
        return dr == 0
    if kind == "pawn_file":
        return chess.square_file(move.to_square) == chess.square_file(pawn)
    if kind == "toward_pawn":
        return chess.square_distance(move.to_square, pawn) < chess.square_distance(move.from_square, pawn)
    return False


def king_direction_issues(text: str, ctx) -> list[str]:
    """The direction advice of *text* that the tablebase's keeping moves contradict (one pawn against a bare king,
    the bare king's side to move)."""
    board = getattr(ctx, "current", None)
    if board is None or len(board.piece_map()) > 7 or not board.is_valid() or board.is_game_over():
        return []
    if not getattr(ctx, "tablebase", None) or not any(rx.search(text) for _k, rx in _DIRECTIONS):
        return []
    if text.rstrip().endswith("?") or _HYPO.search(text) or _GENERAL.search(text) or CONDITIONAL.search(text):
        return []
    mover = board.turn
    pawns = list(board.pieces(chess.PAWN, not mover))
    if len(pawns) != 1 or not _material_only(board, mover, 0) or not _material_only(board, not mover, 1):
        return []
    found = _cached(board)
    raw = found[1] if found else None
    if not raw:
        return []
    keeping = set()
    for san in raw.get("keeping") or []:
        try:
            keeping.add(board.parse_san(san))
        except ValueError:
            return []
    legal = list(board.legal_moves)
    if not keeping or len(keeping) >= len(legal):
        return []
    names = ", ".join(sorted(board.san(m) for m in keeping))
    result = getattr(ctx, "tablebase", "")
    keeps = "hold the draw" if result == "draw" else "keep the result"
    for kind, rx in _DIRECTIONS:
        for m in rx.finditer(text):
            left = max([0] + [x.end() for x in re.finditer(r"[.;:!?—–]", text[:m.start()])])
            right_m = re.search(r"[.;:!?—–]", text[m.end():])
            clause = text[left:m.end() + (right_m.start() if right_m else len(text))]
            go = list(_KING_GO.finditer(clause))
            if not go:
                continue
            named = _side_word(clause, ctx)
            if named is not None and named != mover:
                continue  # «белый король идёт по диагонали» with Black to move: not the chase
            forbidden = any(re.search(r"(?:^|\s)(?:не|never|don'?t|do\s+not)\s+(?:\w+\s+)?$", clause[:g.start()]) for g in go)
            cls = {mv for mv in legal if _move_class(kind, board, mv, pawns[0])}
            label = {"diagonal": "diagonally", "file": "along the file", "rank": "along the rank",
                     "pawn_file": "onto the pawn's file", "toward_pawn": "straight toward the pawn"}[kind]
            if forbidden and keeping <= cls:
                return [f"the sentence forbids the king to go {label}, but every move that keeps the result goes "
                        f"{label}: only {names} {keeps} (endgame tablebase)"]
            if not forbidden and not (cls & keeping):
                return [f"the sentence advises the king to go {label}, but no such move keeps the result: only "
                        f"{names} {keeps} (endgame tablebase)"]
    return []
