"""Player and event names as the student says them → the Latin spellings the TWIC database holds.

The master-games database stores names the way TWIC prints them: Latin, surname first
(«Sindarov,Javokhir», «Nepomniachtchi,I»). A student — and the model after them — names the
player in Russian or Kazakh, inflected («последнюю партию Карлсена», «Синдаров — Накамура»), or in
another Latin spelling («Javohir», «Hubner»). Before 03.11 search_master_games ran ``LIKE
'%Карлсен%'`` and found nothing, and the coach told the student the game was not in the base.

``name_patterns`` turns one name into a few LIKE patterns, OR-ed in the query (kept parameterized):
  * a known player in any Russian form (the table below: spellings no letter-by-letter
    transliteration reaches — Nepomniachtchi, Caruana, Aronian, Ding);
  * any other Cyrillic name: the case ending dropped, then transliterated with the common
    alternatives (х → kh/h, я → ya/ia/ja, й → y/i, к → c/k as one ``_``), at most ``MAX_VARIANTS``;
  * a Latin name: as given, plus its kh/h and umlaut variants (ü → u/ue) — and nothing else, so a
    plain Latin surname costs the query exactly what it did before.

``mentions_player`` serves the tool selector (src/tool_selector.py): whether a message names a
player — a known one in any form or script, or a capitalised name that is not the first word of a
sentence and not an opening's name.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from typing import Optional

# At most this many LIKE patterns per name: every pattern is checked against both name columns of
# every row the search walks, under the 3 s budget of src/tools/_sqlite_budget.py.
MAX_VARIANTS = 4

_CYR = re.compile(r"[а-яёәғқңөұүһі]", re.IGNORECASE)
_VOWELS = "аеёиоуыэюяәөұүі"

# Players whose Latin spelling a letter-by-letter transliteration does not reach (or reaches only
# among many false ones), by the start of their Russian (and Kazakh) name in any case form. The
# patterns are LIKE patterns over white_name / black_name ("Surname,Firstname" in TWIC).
KNOWN_PLAYERS: tuple = (
    # (regex for one lowercased token, LIKE patterns)
    (r"карлсен\w*|магнус\w*", ("%Carlsen%",)),
    (r"накамур\w*|хикару", ("%Nakamura%",)),
    (r"синдаров\w*|жавохир\w*|джавохир\w*", ("%Sindarov%",)),
    (r"гукеш\w*", ("%Gukesh%",)),
    (r"каруан\w*|фабиано", ("%Caruana%",)),
    (r"непомнящ\w*|непо", ("%Nepomniachtchi%",)),
    (r"аронян\w*", ("%Aronian%",)),
    (r"лижэн\w*|лижен\w*|лирен\w*|дин|дина|дину|дином|дине", ("Ding,%", "Ding %")),
    (r"фируздж\w*|алиреза", ("%Firouzja%",)),
    (r"абдусатторов\w*|нодирбек\w*", ("%Abdusattorov%",)),
    (r"праггнанандх\w*|прагнанандх\w*|прагг\w*|прагнанд\w*", ("%Praggnanandhaa%", "%Praggnanandha%")),
    (r"эригайси\w*|аргун\w*", ("%Erigaisi%",)),
    (r"гири", ("Giri,%",)),
    (r"уэсли|уэсл\w*", ("So,%",)),
    (r"вашье\w*|лаграв\w*", ("%Vachier%",)),
    (r"мамедьяров\w*|мамедъяров\w*|мамедяров\w*|шахрияр\w*", ("%Mamedyarov%",)),
    (r"раджабов\w*|радджабов\w*|радждабов\w*", ("%Radjabov%",)),
    (r"карякин\w*", ("%Karjakin%",)),
    (r"грищук\w*", ("%Grischuk%",)),
    (r"есипенко", ("%Esipenko%",)),
    (r"артемьев\w*|артемьеву", ("%Artemiev%",)),
    (r"ниман\w*|нимани", ("%Niemann%",)),
    (r"рапорт\w*", ("%Rapport%",)),
    (r"вэй|вей", ("Wei,Yi%", "Wei Yi%")),
    (r"петросян\w*", ("%Petrosian%",)),
    (r"спасск\w*", ("%Spassky%",)),
    (r"фишер\w*", ("%Fischer%",)),
    (r"корчно\w*", ("%Korchnoi%",)),
    (r"алехин\w*", ("%Alekhine%",)),
    (r"капабланк\w*", ("%Capablanca%",)),
    (r"стейниц\w*|штейниц\w*", ("%Steinitz%",)),
    (r"морфи", ("%Morphy%",)),
    (r"андерсен\w*|андерсс\w*", ("%Anderssen%",)),
    (r"кизерицк\w*", ("%Kieseritzky%",)),
    (r"тарраш\w*", ("%Tarrasch%",)),
    (r"нимцович\w*", ("%Nimzowitsch%", "%Nimzovich%")),
    (r"эйве", ("%Euwe%",)),
    (r"бронштейн\w*", ("%Bronstein%",)),
    (r"полугаевск\w*", ("%Polugaevsky%",)),
    (r"костенюк\w*", ("%Kosteniuk%",)),
    (r"асаубаев\w*", ("%Assaubayeva%",)),
    (r"ифань", ("Hou,Yifan%", "Hou Yifan%")),
    (r"вэньцзюнь\w*|вэньцзюн\w*", ("Ju,Wenjun%", "Ju Wenjun%")),
    (r"таль|таля|талю|талем|тале", ("Tal,%",)),
    (r"каспаров\w*", ("%Kasparov%",)),
    (r"карпов\w*", ("%Karpov%",)),
    (r"крамник\w*", ("%Kramnik%",)),
    (r"ананд\w*", ("%Anand%",)),
    (r"топалов\w*", ("%Topalov%",)),
    (r"иванчук\w*", ("%Ivanchuk%",)),
    (r"гельфанд\w*", ("%Gelfand%",)),
    (r"свидлер\w*", ("%Svidler%",)),
    (r"широв\w*", ("%Shirov%",)),
    (r"леко", ("Leko,%",)),
    (r"полгар", ("%Polgar%",)),
    (r"ботвинник\w*", ("%Botvinnik%",)),
    (r"смыслов\w*", ("%Smyslov%",)),
    (r"ласкер\w*", ("%Lasker%",)),
    (r"чигорин\w*", ("%Chigorin%",)),
    (r"дубов\w*", ("%Dubov%",)),
    (r"андрейкин\w*", ("%Andreikin%",)),
    (r"горячкин\w*", ("%Goryachkina%",)),
    (r"лагно", ("%Lagno%",)),
    (r"кейми|keymer", ("%Keymer%",)),
    (r"кеймер\w*", ("%Keymer%",)),
)
_KNOWN = tuple((re.compile(rf"(?:{rx})", re.IGNORECASE), pats) for rx, pats in KNOWN_PLAYERS)

# Latin names the model or the student may give for a known player (lower case, any form).
_KNOWN_LATIN = re.compile(
    r"(?<![a-z])(?:carlsen|nakamura|sindarov|gukesh|caruana|nepomniachtchi|nepo|aronian|ding|firouzja|"
    r"abdusattorov|praggnanandhaa|pragg|erigaisi|giri|wesley\s+so|vachier|mamedyarov|radjabov|karjakin|"
    r"grischuk|esipenko|artemiev|niemann|rapport|wei\s+yi|kasparov|karpov|kramnik|anand|topalov|ivanchuk|"
    r"gelfand|svidler|shirov|polgar|botvinnik|smyslov|petrosian|spassky|fischer|korchnoi|alekhine|"
    r"capablanca|steinitz|morphy|anderssen|lasker|tal|keymer|dubov|goryachkina|lagno|hou\s+yifan|"
    r"ju\s+wenjun|kosteniuk)(?:'s)?(?![a-z])", re.IGNORECASE)

# Events by their Russian names (the model sometimes passes the student's words).
KNOWN_EVENTS: tuple = (
    (r"майам\w*", "Miami"),
    (r"вейк\w*|вийк\w*|тата", "Wijk"),
    (r"претендент\w*", "Candidates"),
    (r"олимпиад\w*", "Olympiad"),
    (r"норвеги\w*|ставангер\w*", "Norway"),
    (r"синкфилд\w*", "Sinquefield"),
    (r"рапид\w*|быстр\w*", "Rapid"),
    (r"блиц\w*", "Blitz"),
    (r"кубок|кубк\w*", "Cup"),
    (r"чемпионат\w*", "Championship"),
    (r"мир|мира|мире|миру|world", "World"),
    (r"мемориал\w*", "Memorial"),
    (r"гран-при|гранпри", "Grand Prix"),
    (r"дубай\w*|дубае", "Dubai"),
    (r"сингапур\w*", "Singapore"),
    (r"астан\w*", "Astana"),
    (r"алмат\w*", "Almaty"),
    (r"ташкент\w*", "Tashkent"),
    (r"самарканд\w*", "Samarkand"),
    (r"торонто", "Toronto"),
    (r"мадрид\w*", "Madrid"),
    (r"лондон\w*", "London"),
    (r"берлин\w*", "Berlin"),
    (r"москв\w*", "Moscow"),
    (r"загреб\w*", "Zagreb"),
    (r"бухарест\w*", "Bucharest"),
    (r"батуми", "Batumi"),
    (r"тбилиси", "Tbilisi"),
    (r"ченнаи", "Chennai"),
    (r"шарджа|шардж\w*", "Sharjah"),
)
# Words of an event argument that name no event («турнир в Майами 2026 года»).
_EVENT_STOP = re.compile(r"(?:турнир\w*|парти\w*|год\w*|в|на|по|из|и|с|со|до|от|среди|этап\w*|сезон\w*|"
                         r"\d+|\d+-?(?:й|го|м|я)?)", re.IGNORECASE)
_EVENTS = tuple((re.compile(rf"(?:{rx})", re.IGNORECASE), latin) for rx, latin in KNOWN_EVENTS)

# One Cyrillic letter → its Latin spellings, the usual one first. Kazakh letters too.
_TRANSLIT = {
    "а": ("a",), "б": ("b",), "в": ("v",), "г": ("g",), "д": ("d",), "е": ("e",), "ё": ("e", "yo"),
    "ж": ("zh", "j"), "з": ("z",), "и": ("i",), "й": ("y", "i"), "к": ("k", "c"), "л": ("l",), "м": ("m",),
    "н": ("n",), "о": ("o",), "п": ("p",), "р": ("r",), "с": ("s",), "т": ("t",), "у": ("u",), "ф": ("f",),
    "х": ("kh", "h"), "ц": ("ts", "tz", "c"), "ч": ("ch",), "ш": ("sh",), "щ": ("shch", "sch"), "ъ": ("",),
    "ы": ("y",), "ь": ("",), "э": ("e",), "ю": ("yu", "iu"), "я": ("ya", "ia", "ja"),
    "ә": ("a", "ae"), "ғ": ("g", "gh"), "қ": ("k", "q"), "ң": ("n", "ng"), "ө": ("o", "oe"), "ұ": ("u",),
    "ү": ("u", "ue"), "һ": ("h",), "і": ("i",),
}

# Case endings of a Russian surname (or a name) — dropped before transliterating: «Карлсена»,
# «Синдарову», «Горячкиной», «Непомнящего». The stripped form is a substring of the Latin one.
_NAME_ENDINGS = ("ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей", "ом", "ем", "ым", "им", "ою", "ею",
                 "ых", "их",
                 # Kazakh: «Абдумаликтің», «Синдаровпен», «Накамураға»
                 "тің", "тың", "нің", "ның", "дің", "дың", "мен", "бен", "пен", "ға", "ге", "қа", "ке", "ды", "ді",
                 "ны", "ні", "ты", "ті", "да", "де", "та", "те",
                 "а", "у", "е", "ы", "и", "я", "ю")

# Latin spellings that differ in the database: umlauts written out or dropped, kh/h.
_LATIN_SWAPS = (("ü", ("u", "ue")), ("ö", ("o", "oe")), ("ä", ("a", "ae")), ("ue", ("ü", "u")),
                ("oe", ("ö", "o")), ("ae", ("ä", "a")), ("é", ("e",)), ("á", ("a",)), ("ć", ("c",)),
                ("č", ("c",)), ("š", ("s",)), ("ž", ("z",)), ("ł", ("l",)), ("ø", ("o", "oe")))


def is_cyrillic(text: str) -> bool:
    return bool(_CYR.search(text or ""))


def _strip_name_ending(word: str) -> str:
    """«карлсена» → «карлсен»; never below four letters («гири» stays)."""
    for end in _NAME_ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 4:
            return word[: -len(end)]
    return word


def _translit_options(word: str) -> list:
    """Per-letter Latin options for a lowercased Cyrillic *word*."""
    options = []
    i = 0
    while i < len(word):
        ch = word[i]
        prev = word[i - 1] if i else ""
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in "иы" and nxt == "й" and i + 2 == len(word):  # «-ий», «-ый» at the end: y / iy / i
            options.append(("y", "iy", "i") if ch == "и" else ("y",))
            i += 2
            continue
        if ch == "к" and nxt == "с":
            options.append(("ks", "x"))
            i += 2
            continue
        if ch == "е" and (not prev or prev in _VOWELS + "ьъ"):  # «Есипенко», «Андреев»: e / ye
            options.append(("e", "ye"))
        elif ch == "к":
            options.append(("_",))  # k or c, one letter either way
        else:
            options.append(_TRANSLIT.get(ch, (ch,)))
        i += 1
    return options


def _combine(options: list, cap: int) -> list:
    """Spellings from per-letter *options*, the usual one first, then those with fewest unusual letters."""
    choices = [i for i, opts in enumerate(options) if len(opts) > 1]
    primary = [opts[0] for opts in options]
    out = ["".join(primary)]
    for k in range(1, len(choices) + 1):
        for positions in itertools.combinations(choices, k):
            for alts in itertools.product(*[options[p][1:] for p in positions]):
                spelled = list(primary)
                for p, alt in zip(positions, alts):
                    spelled[p] = alt
                word = "".join(spelled)
                if word not in out:
                    out.append(word)
                if len(out) >= cap:
                    return out
    return out


def _latin_variants(word: str, cap: int) -> list:
    """A Latin name as given plus its umlaut and kh/h spellings (nothing more for a plain name)."""
    out = [word]
    low = word.lower()
    for src, dsts in _LATIN_SWAPS:
        if src in low:
            for dst in dsts:
                out.append(re.sub(re.escape(src), dst, word, flags=re.IGNORECASE))
    if "kh" in low:
        out.append(re.sub("kh", "h", word, flags=re.IGNORECASE))
    elif re.search(r"[aeiou]h", low) and not re.search(r"[csztpg]h", low):
        out.append(re.sub(r"(?<=[aeiouAEIOU])h", "kh", word))  # «Javohir» → «Javokhir»
    seen: list = []
    for v in out:
        if v.lower() not in [s.lower() for s in seen]:
            seen.append(v)
    return seen[:cap]


def known_player(token: str) -> Optional[tuple]:
    """The LIKE patterns of a known player named by one *token* in any Russian form, or None."""
    low = (token or "").lower().replace("ё", "е")
    for rx, pats in _KNOWN:
        if rx.fullmatch(low):
            return pats
    return None


_NAME_TOKEN = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)


def name_patterns(name: str, cap: int = MAX_VARIANTS) -> list:
    """LIKE patterns (``%…%``) that find the player *name* in white_name / black_name.

    One name («Карлсен», «Magnus Carlsen», «Javohir Sindarov», «Непомнящего»): a known player
    by any word of it; otherwise its longest word, transliterated when Cyrillic."""
    tokens = _NAME_TOKEN.findall(name or "")
    if not tokens:
        return []
    for tok in tokens:
        pats = known_player(tok)
        if pats:
            return list(pats)
    word = max(tokens, key=len)
    if not is_cyrillic(word):
        return [f"%{v}%" for v in _latin_variants(word, cap)]
    base = _strip_name_ending(word.lower().replace("ё", "е"))
    return [f"%{v}%" for v in _combine(_translit_options(base), cap)]


def normalized_pattern(pattern: str) -> str:
    """A LIKE pattern over the raw name → the same over ``*_name_normalized`` (the site's column:
    lower case, accents dropped, the comma a space — backend/scripts/incremental_index.normalize_name)."""
    folded = unicodedata.normalize("NFKD", pattern)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return folded.lower().replace(",", " ").replace("  ", " ")


# «Синдаров — Накамура», «Carlsen vs Nakamura», «Карлсен против Каруаны», «Ding and Gukesh».
_PAIR_SPLIT = re.compile(r"\s+(?:[-—–]|vs\.?|v\.|versus|против|и|and|&|қарсы)\s+|\s*[—–]\s*|\s+-\s*|\s*-\s+",
                         re.IGNORECASE)


def split_players(text: str) -> list:
    """The one or two players a ``player`` argument names («Синдаров — Накамура» → two)."""
    parts = [p.strip(" ,.;") for p in _PAIR_SPLIT.split(text or "") if p and p.strip(" ,.;")]
    return parts[:2] if parts else []


def event_terms(event: str) -> list:
    """The words of an ``event`` argument, Russian ones in their database spelling («Майами» → Miami)."""
    out = []
    words = [w for chunk in (event or "").split() for w in (chunk.split("-") if is_cyrillic(chunk) else [chunk])]
    for word in words:
        low = word.lower().strip(" ,.;«»\"'").replace("ё", "е")
        latin = next((lat for rx, lat in _EVENTS if rx.fullmatch(low)), None)
        if latin:
            out.append(latin)
        elif is_cyrillic(low) and (len(low) < 3 or _EVENT_STOP.fullmatch(low)):
            continue
        elif is_cyrillic(low):
            out.append(_combine(_translit_options(_strip_name_ending(low)), 1)[0])
        elif low and not low.isdigit():  # a year is year_min / year_max, not a word of the event's name
            out.append(word.strip(" ,.;«»\"'"))
    return list(dict.fromkeys(out))


# ── Does a message name a player? (for the tool selector) ─────────────────────────────────

# Capitalised words that are no player (whole words, lower case): pronouns and verbs that open a
# clause, chess words, sides, names of things, and openings named by their adjective or eponym.
_NOT_NAMES = re.compile(
    r"(?:я|мне|меня|мой|моя|мою|мои|моей|ты|тебе|вы|он|она|мы|они|это|эта|этот|эти|как|что|где|когда|почему|"
    r"зачем|кто|какой|какая|какую|какие|покажи|найди|загрузи|открой|давай|дай|скажи|расскажи|объясни|можно|"
    r"а|и|но|да|нет|ой|ок|привет|спасибо|"
    r"бел(?:ые|ых|ым|ыми|ая|ую|ой|ый)|ч[её]рн(?:ые|ых|ым|ыми|ая|ую|ой|ый)|"
    r"ферз\w{0,3}|лад(?:ья|ьи|ье|ью|ьёй|ьей|ей|ьям)|слон\w{0,3}|кон(?:ь|я|ю|ем|ём|е|и|ей)|корол\w{0,3}|"
    r"пеш(?:ка|ки|ке|ку|кой|ек)|шах\w{0,2}|мат|"
    r"stockfish|стокфиш\w*|lichess|личес\w*|chess|fide|фиде|pgn|fen|eco|twic|elo|эло|ok|ai|ии|hermes|"
    r"гермес\w*|chesster|wikipedia|википеди\w*|google|гугл\w*|youtube|ютуб\w*|telegram|телеграм\w*|"
    r"i|the|and|or|but|is|can|could|what|who|why|how|show|find|load|open|please|let|my|me|white|black|"
    r"queen|rook|bishop|knight|king|pawn|opening|game|games|database|"
    r"english|french|italian|spanish|sicilian|scotch|dutch|slav|london|catalan|vienna|russian|indian|ruy|"
    r"lopez|caro|kann|pirc|benoni|benko|grunfeld|grünfeld|nimzo|scandinavian|najdorf|dragon|berlin|"
    r"petrov|petroff|philidor|alekhine's|"
    r"каро|канн|каро-канн|петров\w{0,2}|филидор\w{0,2}|найдорф\w{0,2}|грюнфельд\w{0,2}|бенони|пирц\w{0,2}|"
    r"нимцович\w{0,2}|бенко|колле|рети|"
    r"бұл|осы|маған|менің|қазір|сәлем|рахмет)",
    re.IGNORECASE)
# A capitalised adjective in -ская/-ской/-скую…: an opening («Испанская партия», «в Сицилианской»),
# not a surname — known players aside (Спасский).
_ADJECTIVE = re.compile(r"[^\W\d_]+(?:ск|цк)(?:ая|ую|ой|ий|ый|ое|ие|ые|их|ых|ым|ими|ыми|ого|ому|ом)", re.IGNORECASE)
_SENTENCE_START = re.compile(r"(?:^|[.!?…\n]|[«\"“(])\s*$")
_CAP_WORD = re.compile(r"(?<![\w-])([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][^\W\d_]{2,}(?:-[^\W\d_]+)?)(?![\w])")


def _named_words(text: str) -> list:
    """Capitalised words of *text* that read as a name: not a sentence's first word, not a chess word,
    not an adjective (an opening), not an opening's eponym («вариант Найдорфа», «защита Петрова»)."""
    out = []
    for m in _CAP_WORD.finditer(text or ""):
        word = m.group(1)
        before = text[: m.start()]
        if _SENTENCE_START.search(before):
            continue
        low = word.lower()
        if _NOT_NAMES.fullmatch(low):
            continue
        if is_cyrillic(word) and _ADJECTIVE.fullmatch(low) and not known_player(low):
            continue
        prev_word = re.search(r"([^\W\d_]+)\s*$", before)
        if prev_word and re.match(r"(?:вариант|защит|систем|гамбит|атак|дебют|начал|ловушк|variation|defen[cs]e|"
                                  r"system|gambit|attack|opening|trap)", prev_word.group(1), re.IGNORECASE):
            continue
        nxt = re.match(r"\s*([^\W\d_]+)", text[m.end():])
        if nxt and re.match(r"(?:opening|defen[cs]e|gambit|attack|game|system|variation|indian|partie)$",
                            nxt.group(1), re.IGNORECASE):
            continue
        out.append(word)
    return out


def known_player_in(text: str) -> bool:
    """*text* names a known player in any form or script («карлсена», «Carlsen's», «Накамуре»)."""
    if _KNOWN_LATIN.search(text or ""):
        return True
    for tok in _NAME_TOKEN.findall((text or "").lower()):
        if len(tok) >= 3 and known_player(tok):
            return True
    return False


def mentions_player(text: str) -> bool:
    """*text* names a player: a known one, or a capitalised name (see ``_named_words``)."""
    return known_player_in(text) or bool(_named_words(text))


_PAIR = re.compile(
    r"(?<![\w-])([^\W\d_]{3,})(?:\s*[—–]\s*|\s+-\s*|\s*-\s+|\s+(?:vs\.?|v\.|versus|против|қарсы|with|against|с|со|и|"
    r"and)\s+)([^\W\d_]{3,})(?![\w-])",
    re.IGNORECASE)


def names_two_players(text: str) -> bool:
    """*text* names two players against each other («Синдаров — Накамура», "Carlsen vs Nakamura")."""
    named = {w.lower() for w in _named_words(text)}
    for m in _PAIR.finditer(text or ""):
        sides = [m.group(1), m.group(2)]
        if all(s.lower() in named or known_player(s) or _KNOWN_LATIN.fullmatch(s) for s in sides):
            return True
    return False
