"""Any game from the database, asked for in any words, reaches the board (live site, 03.11).

Three answers of the production coach on 03.11, Chess Empire site:
  * «Найди в базе партию Синдаров — Накамура (Майами 2026) и загрузи её на доску…» — search_web
    seven times, «ни партии, ни турнира я найти не смог»;
  * «Загрузи партию Sindarov — Nakamura 2026 из базы партий» — the Lichess/Chess.com imports,
    «такой партии у меня в базе нет»;
  * «Покажи последнюю партию Карлсена из базы на доске» — «в базе только данные о встречах, а не
    сами ходы».
The tool subset (src/tool_selector.py) sent neither search_master_games nor get_game_pgn on any of
them, and search_master_games matched «Карлсен» against Latin names. Covered here:
  * keywords match their words in any case form (``_word_matches``, the forms table);
  * a request for a particular game brings search_master_games, and get_game_pgn comes with it
    (``asks_for_game``, companions) — ordinary questions get nothing extra;
  * names in Russian / Kazakh / another Latin spelling find the player; two names find their game;
    year bounds hold for TWIC's dotted dates;
  * get_game_pgn(show=true) puts the whole game on the board through load_pgn.
"""

import json
import re
import sqlite3

import pytest

from src import tool_selector as ts
from src.player_names import (
    event_terms,
    known_player_in,
    mentions_player,
    name_patterns,
    names_two_players,
    normalized_pattern,
    split_players,
)
from src.tools import twic_search

from ._stem_forms_2026_11_03 import FORMS, NOT_FORMS, PHRASE_FORMS

LIVE = [
    "Найди в базе партию Синдаров — Накамура (Майами 2026) и загрузи её на доску, хочу сам пролистать ходы",
    "Загрузи партию Sindarov — Nakamura 2026 из базы партий",
    "Покажи последнюю партию Карлсена из базы на доске",
]

# A particular game asked for: RU / EN / KK, inflected names, pairs, years, events, the database.
ASKS_FOR_GAME = LIVE + [
    "Найди партию Карлсена с Каруаной",
    "Покажи последнюю партию Гукеша",
    "Открой партию Непомнящего против Ding Liren",
    "Есть ли в базе партии Абдусатторова?",
    "Загрузи партию Каспаров — Топалов 1999",
    "Хочу посмотреть партию из турнира претендентов 2024",
    "Какие партии сыграл Фирузджа в 2025 году?",
    "Найди партию Синдарова на Кубке мира",
    "Покажи мне игру Накамуры против Карлсена",
    "Поищи партии Эригайси за 2025 год",
    "Загрузи на доску партию Аронян — Каруана",
    "Найди в базе последнюю партию Хикару Накамуры",
    "Открой партию Ding — Nepomniachtchi из матча 2023 года",
    "Последняя партия Карлсена — покажи её",
    "Партия Карпов — Каспаров, 16-я партия матча 1985 года, загрузи",
    "Покажи партию Таля против Ботвинника",
    "Как сыграли Синдаров и Накамура в Майами?",
    "Кто выиграл в партии Гукеш — Дин?",
    "Покажи партии Горячкиной с чемпионата мира",
    "Найди мне партию Fischer vs Spassky 1972",
    "Load the game Sindarov vs Nakamura from the database",
    "Show me Carlsen's latest game",
    "Find Gukesh's games from the 2024 Candidates",
    "Open the game Caruana vs Nakamura, Miami 2026",
    "Can you find a game between Firouzja and Carlsen?",
    "Show me the last game of Hikaru Nakamura on the board",
    "Pull up Kasparov vs Topalov, Wijk aan Zee 1999",
    "Find me a game from the Tata Steel tournament",
    "Is there a game of Abdusattorov in the database?",
    "Карлсеннің соңғы ойынын көрсет",
    "Синдаров — Накамура партиясын тақтаға жүкте",
    "Базадан Каруананың ойындарын тап",
    "Гукештің 2024 жылғы ойынын көрсет",
    "Накамура мен Карлсеннің партиясын тап",
    "Найдите, пожалуйста, партию Вашье-Лаграва",
    "Загрузите партию с олимпиады 2024",
    "Какая была последняя партия у Синдарова?",
    "Поставь на доску партию Капабланка — Алехин",
    "Открой из базы партию 2026 года",
    "Партию Дубова из базы можешь показать?",
    "Есть партии Синдарова против Накамуры?",
    "Хочу пролистать партию Абдусатторов — Гукеш",
    "Найди партию с Майами 2026, где играл Накамура",
    "загрузи партию карлсена из базы",
    "покажи последнюю игру непомнящего",
]

# Ordinary coach questions: no game from the database is asked for, nothing is added.
ORDINARY = [
    "Как называется этот дебют?",
    "Какой лучший ход в этой позиции?",
    "Объясни, что такое связка",
    "Дай мне задачу на вилку",
    "Давай сыграем партию, я белыми",
    "Сыграем ещё одну партию?",
    "Разбери мою последнюю партию",
    "Где я ошибся в этой партии?",
    "Покажи итальянскую партию",
    "Как играть против сицилианской защиты?",
    "Что такое цугцванг? Покажи пример на доске.",
    "Можно ли рокироваться, если король под шахом?",
    "Какой у меня рейтинг на lichess?",
    "Какие у меня слабые места?",
    "Что мне учить дальше?",
    "Покажи на доске защиту Каро-Канн",
    "Оцени позицию",
    "Как выиграть этот эндшпиль?",
    "Ферзь против ладьи — это выигрыш?",
    "Объясни план белых в Испанской партии",
    "Загрузи мою партию: 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6",
    "Сколько партий я сыграл в этом месяце?",
    "Какая у меня статистика по задачам?",
    "Почему ты так сыграл?",
    "Сдаюсь",
    "Верни ход",
    "What opening is this?",
    "What is the best move here?",
    "Explain the idea of the Queen's Gambit",
    "Let's play a game, I'm white",
    "Give me a puzzle on forks",
    "Can I castle here?",
    "Бұл қандай дебют?",
    "Маған тактикалық есеп бер",
    "Ойын ойнайық, мен ақпен",
    "Какие идеи у чёрных в этой позиции?",
    "Как улучшить игру в эндшпиле?",
    "Расскажи про Шотландскую партию",
    "Кто сейчас чемпион мира?",
    "Какой сейчас рейтинг у Карлсена?",
    "Что такое правило 50 ходов?",
    "Какую фигуру лучше взять?",
    "Есть ли тут мат в два хода?",
    "Покажи детский мат",
    "Как развивать фигуры в дебюте?",
    "Почему эта партия считается проигранной для белых?",
]


@pytest.fixture(scope="module")
def declarations():
    """The coach's real tool declarations, as the voice path and the selector see them."""
    from src.tool_bridge import build_tool_declarations
    from src.tools import discover_and_register

    discover_and_register()
    decls = build_tool_declarations()
    assert {"search_master_games", "get_game_pgn"} <= {d["name"] for d in decls}
    return decls


def _names(decls):
    return [d["name"] for d in decls]


# ── Keywords match their words in any case form ──────────────────────────────────────────

def _russian_stems():
    return sorted({s for stems in ts.TOOL_KEYWORDS.values() for s in stems
                   if re.search("[а-яё]", s) and not re.search("[әғқңөұүһі]", s) and " " not in s})


@pytest.mark.unit
def test_every_russian_keyword_has_its_forms_listed():
    missing = [s for s in _russian_stems() if s not in FORMS]
    assert not missing, f"add the case forms of these keywords to _stem_forms_2026_11_03.FORMS: {missing}"


@pytest.mark.unit
@pytest.mark.parametrize("stem", sorted(FORMS))
def test_keyword_matches_its_case_forms(stem):
    norm = stem.replace("ё", "е")
    failed = [f for f in FORMS[stem] if not ts._word_matches(f.replace("ё", "е"), norm)]
    assert not failed, f"{stem!r} does not match {failed}"


@pytest.mark.unit
@pytest.mark.parametrize("stem", sorted(NOT_FORMS))
def test_keyword_does_not_take_another_word(stem):
    assert not [f for f in NOT_FORMS[stem] if ts._word_matches(f, stem)]


@pytest.mark.unit
@pytest.mark.parametrize("phrase", sorted(PHRASE_FORMS))
def test_phrase_matches_word_by_word(phrase):
    failed = [f for f in PHRASE_FORMS[phrase] if not ts._phrase_matches(ts._token_list(f), phrase.split())]
    assert not failed


@pytest.mark.unit
def test_base_keyword_reaches_the_database_tool():
    decl = {"name": "search_master_games", "description": ""}
    for q in ("Найди в базе партию", "Партии из базы", "Открой базу партий", "Есть такая партия в базе?"):
        assert ts._score(ts._tokenize(q) - ts._STOPWORDS_NORM, decl, q) >= 1, q


@pytest.mark.unit
def test_web_search_is_not_the_database():
    """«Найди в базе …» scored the web search («найди в» was its keyword) — prod 03.11, search_web ×7."""
    decl = {"name": "search_web", "description": ""}
    q = "Найди в базе партию Синдаров — Накамура"
    assert ts._score(ts._tokenize(q) - ts._STOPWORDS_NORM, decl, q) == 0


# ── A particular game asked for ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("query", ASKS_FOR_GAME)
def test_asks_for_game(query):
    assert ts.asks_for_game(query)


@pytest.mark.unit
@pytest.mark.parametrize("query", ORDINARY)
def test_ordinary_question_is_no_game_request(query):
    assert not ts.asks_for_game(query)


@pytest.mark.unit
@pytest.mark.parametrize("query", ASKS_FOR_GAME)
def test_game_request_gets_search_and_pgn(declarations, query):
    names = _names(ts.select_tool_subset(declarations, query, topk=7))
    assert "search_master_games" in names and "get_game_pgn" in names, names
    assert set(ts.CORE_TOOLS) & set(_names(declarations)) <= set(names)  # core never pushed out


@pytest.mark.unit
@pytest.mark.parametrize("query", ORDINARY)
def test_ordinary_question_gets_nothing_extra(declarations, query):
    """Core + the topk ranked tools, as before — the intent and the companions add nothing.
    (The before/after diff of these sets on ecdadca9 is in the build report: none changed.)"""
    names = _names(ts.select_tool_subset(declarations, query, topk=7))
    core = [n for n in _names(declarations) if n in ts.CORE_TOOLS]
    assert len(names) == len(core) + 7, names


@pytest.mark.unit
def test_live_queries_before_and_after(declarations):
    """The three live questions: none of them had either tool before; all have both now."""
    for q in LIVE:
        names = _names(ts.select_tool_subset(declarations, q, topk=7))
        assert {"search_master_games", "get_game_pgn"} <= set(names), (q, names)
    names = _names(ts.select_tool_subset(declarations, LIVE[0], topk=7))
    assert "search_web" not in names


# ── Companions ───────────────────────────────────────────────────────────────────────────

def _decl(name, description=""):
    return {"name": name, "description": description, "parameters": {}}


@pytest.mark.unit
def test_companion_from_description():
    decls = [
        _decl("board_control"),
        _decl("find_widgets", "Find widgets by colour. Use fetch_widget with a returned id to show one."),
        _decl("fetch_widget", "Fetch one widget."),
        *[_decl(f"other_{i}") for i in range(10)],
    ]
    out = _names(ts.select_tool_subset(decls, "find widgets colour", topk=2, core=frozenset({"board_control"})))
    assert out[:2] == ["board_control", "find_widgets"]
    assert "fetch_widget" in out


@pytest.mark.unit
def test_companion_from_table():
    """search_master_games' companion holds even if its description stops naming it."""
    decls = [_decl("board_control"), _decl("search_master_games", "Search games."), _decl("get_game_pgn", "x")]
    decls += [_decl(f"other_{i}") for i in range(10)]
    out = _names(ts.select_tool_subset(decls, "Покажи партию Карлсена", topk=1, core=frozenset({"board_control"})))
    assert "search_master_games" in out and "get_game_pgn" in out


@pytest.mark.unit
def test_filler_brings_no_companion():
    """A tool that only filled a free place (score 0) or touched one word brings nothing."""
    decls = [_decl("board_control"), _decl("find_games_by_position", "Games that reached a position.")]
    decls += [_decl(f"other_{i}") for i in range(5)] + [_decl("get_game_pgn", "x")]
    out = _names(ts.select_tool_subset(decls, "Какой лучший ход в этой позиции?", topk=3,
                                       core=frozenset({"board_control"})))
    assert "find_games_by_position" in out and "get_game_pgn" not in out


@pytest.mark.unit
def test_extras_are_bounded_and_core_stays():
    many = " ".join(f"Use extra_{i} next." for i in range(10))
    decls = [_decl("board_control"), _decl("analyze_position"), _decl("lead", f"lead tool alpha beta. {many}")]
    decls += [_decl(f"extra_{i}") for i in range(10)]
    out = _names(ts.select_tool_subset(decls, "lead alpha beta", topk=1,
                                       core=frozenset({"board_control", "analyze_position"})))
    assert out[:3] == ["board_control", "analyze_position", "lead"]
    assert len(out) == 3 + ts.MAX_EXTRA_TOOLS


@pytest.mark.unit
def test_companions_of_real_tools(declarations):
    by = {d["name"]: d for d in declarations}
    names = set(by)
    assert "get_game_pgn" in ts.companions(by["search_master_games"], names)
    assert "get_game_pgn" in ts.companions(by["find_games_by_position"], names)


# ── Names in any spelling ────────────────────────────────────────────────────────────────

ROWS = [
    # id, white, black, result, date, eco, opening, event, pgn
    (3622931, "Sindarov,Javokhir", "Nakamura,Hikaru", "1-0", "2026.03.10", "C65", "Ruy Lopez",
     "WR Rapid Miami 2026", "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. d3 Bc5 5. c3 O-O 6. O-O d6 1-0"),
    (3622950, "Nakamura,Hikaru", "Sindarov,Javokhir", "1/2-1/2", "2026.03.11", "D37", "QGD",
     "WR Rapid Miami 2026", "1. d4 Nf6 2. c4 e6 3. Nf3 d5 1/2-1/2"),
    (3600001, "Carlsen,Magnus", "Caruana,Fabiano", "1-0", "2025.01.20", "C65", "Ruy Lopez",
     "Tata Steel Masters", "1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0"),
    (3610002, "Caruana,Fabiano", "Carlsen,Magnus", "0-1", "2026.02.01", "B90", "Sicilian",
     "Freestyle Weissenhaus", "1. e4 c5 2. Nf3 d6 0-1"),
    (3300003, "Nepomniachtchi,Ian", "Ding,Liren", "1/2-1/2", "2023.04.09", "C84", "Ruy Lopez",
     "World Championship", "1. e4 e5 2. Nf3 Nc6 1/2-1/2"),
    (3500004, "Gukesh,D", "Ding,Liren", "1-0", "2024.12.12", "D02", "QP", "World Championship",
     "1. d4 d5 2. Nf3 1-0"),
    (1100005, "Hübner,Robert", "Karpov,Anatoly", "1/2-1/2", "1980.05.01", "E12", "QID", "Tilburg",
     "1. d4 Nf6 2. c4 e6 1/2-1/2"),
    (3500006, "Aronian,Levon", "Firouzja,Alireza", "0-1", "2024.06.01", "C50", "Italian", "Norway Chess",
     "1. e4 e5 2. Nf3 Nc6 3. Bc4 0-1"),
    (3600007, "Abdusattorov,Nodirbek", "Gukesh,D", "1-0", "2025.01.25", "E20", "Nimzo", "Tata Steel Masters",
     "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 1-0"),
    (2900008, "Karjakin,Sergey", "Carlsen,Magnus", "0-1", "2016.11.28", "C84", "Ruy Lopez", "World Championship",
     "1. e4 e5 0-1"),
    (900009, "Tal,Mikhail", "Botvinnik,Mikhail", "1-0", "1960.03.15", "B18", "Caro-Kann", "World Championship",
     "1. e4 c6 1-0"),
    (3600010, "Vitali,Natalia", "Talukdar,Ravi", "1-0", "2025.05.05", "A00", "?", "Open", "1. e4 1-0"),
    (3600011, "Assaubayeva,Bibisara", "Goryachkina,Aleksandra", "1/2-1/2", "2025.06.06", "A00", "?",
     "Women Grand Prix", "1. d4 1/2-1/2"),
]


def _db(normalized: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    extra = ", white_name_normalized TEXT, black_name_normalized TEXT" if normalized else ""
    conn.execute(f"""CREATE TABLE games (id INTEGER PRIMARY KEY, white_name TEXT, black_name TEXT, result TEXT,
        date TEXT, eco TEXT, opening TEXT, event TEXT, pgn TEXT, white_elo INTEGER, black_elo INTEGER,
        pgn_offset INTEGER DEFAULT 0, pgn_length INTEGER DEFAULT 0{extra})""")
    for r in ROWS:
        if normalized:
            conn.execute("INSERT INTO games (id, white_name, black_name, result, date, eco, opening, event, pgn, "
                         "white_name_normalized, black_name_normalized) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (*r, normalized_pattern(r[1]), normalized_pattern(r[2])))
        else:
            conn.execute("INSERT INTO games (id, white_name, black_name, result, date, eco, opening, event, pgn) "
                         "VALUES (?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    return conn


def _ids(rows):
    return [r["id"] for r in rows]


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Синдаров", "Синдарова", "Синдарову", "Синдаровым", "синдаров", "Javohir",
                                  "Javokhir Sindarov", "Sindarov", "Жавохир Синдаров"])
def test_player_in_any_spelling(name):
    rows = twic_search.search_master_games(player=name, conn=_db())
    assert set(_ids(rows)) == {3622931, 3622950}
    assert _ids(rows)[0] == 3622950  # newest first: the latest game leads


@pytest.mark.unit
@pytest.mark.parametrize("name, expected", [
    ("Карлсен", {3600001, 3610002, 2900008}),
    ("Карлсена", {3600001, 3610002, 2900008}),
    ("Магнус Карлсен", {3600001, 3610002, 2900008}),
    ("Накамура", {3622931, 3622950}),
    ("Хикару Накамуры", {3622931, 3622950}),
    ("Каруаной", {3600001, 3610002}),
    ("Непомнящего", {3300003}),
    ("Дин Лижэнь", {3300003, 3500004}),
    ("Гукеш", {3500004, 3600007}),
    ("Гукештің", {3500004, 3600007}),
    ("Ароняна", {3500006}),
    ("Фирузджа", {3500006}),
    ("Абдусатторова", {3600007}),
    ("Карякин", {2900008}),
    ("Таль", {900009}),
    ("Горячкиной", {3600011}),
    ("Асаубаева", {3600011}),
])
def test_russian_names(name, expected):
    assert set(_ids(twic_search.search_master_games(player=name, conn=_db()))) == expected


@pytest.mark.unit
def test_short_name_is_anchored_to_the_surname():
    """«Таль» is Tal,Mikhail — not Vitali,Natalia or Talukdar."""
    assert _ids(twic_search.search_master_games(player="Таль", conn=_db())) == [900009]


@pytest.mark.unit
@pytest.mark.parametrize("kwargs", [
    {"player": "Синдаров — Накамура"},
    {"player": "Sindarov vs Nakamura"},
    {"player": "Sindarov", "opponent": "Nakamura"},
    {"player": "Накамура", "opponent": "Синдаров"},
    {"player": "Синдаров против Накамуры"},
])
def test_two_players(kwargs):
    rows = twic_search.search_master_games(conn=_db(), **kwargs)
    assert set(_ids(rows)) == {3622931, 3622950}


@pytest.mark.unit
def test_two_players_exclude_their_other_games():
    rows = twic_search.search_master_games(player="Carlsen", opponent="Caruana", conn=_db())
    assert set(_ids(rows)) == {3600001, 3610002}  # not Karjakin — Carlsen


@pytest.mark.unit
def test_year_bounds_hold_for_dotted_dates():
    """TWIC dates are «2026.03.10»: year_max=2026 used to leave out every game of 2026."""
    rows = twic_search.search_master_games(player="Синдаров", year_min=2026, year_max=2026, conn=_db())
    assert set(_ids(rows)) == {3622931, 3622950}
    rows = twic_search.search_master_games(player="Carlsen", year_max=2025, conn=_db())
    assert set(_ids(rows)) == {3600001, 2900008}
    rows = twic_search.search_master_games(player="Carlsen", year_min="2026", conn=_db())
    assert _ids(rows) == [3610002]


@pytest.mark.unit
def test_event_in_russian():
    rows = twic_search.search_master_games(player="Накамура", event="Майами 2026", conn=_db())
    assert set(_ids(rows)) == {3622931, 3622950}
    assert event_terms("турнир претендентов 2024") == ["Candidates"]


@pytest.mark.unit
def test_last_game_is_first():
    rows = twic_search.search_master_games(player="Карлсена", limit=1, conn=_db())
    assert _ids(rows) == [3610002]


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Hubner", "Huebner", "Hübner"])
def test_umlauts_on_the_normalized_columns(name):
    """With the site's normalized name columns, «Hubner» finds «Hübner» as the database page does."""
    assert _ids(twic_search.search_master_games(player=name, conn=_db(normalized=True))) == [1100005]


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Hübner", "Huebner"])
def test_umlaut_variants_on_raw_names(name):
    assert _ids(twic_search.search_master_games(player=name, conn=_db())) == [1100005]


@pytest.mark.unit
def test_russian_names_on_the_normalized_columns():
    rows = twic_search.search_master_games(player="Синдаров — Накамура", conn=_db(normalized=True))
    assert set(_ids(rows)) == {3622931, 3622950}
    assert set(_ids(twic_search.search_master_games(player="Дин", conn=_db(normalized=True)))) == {3300003, 3500004}


@pytest.mark.unit
def test_query_stays_parameterized():
    for evil in ("x' OR 1=1 --", "%'; DROP TABLE games; --", "Карлсен' --"):
        twic_search.search_master_games(player=evil, conn=_db())  # no SQL error
    conn = _db()
    twic_search.search_master_games(player="'; DROP TABLE games; --", opponent="x", conn=conn)
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == len(ROWS)


@pytest.mark.unit
def test_latin_name_costs_what_it_did():
    """A plain Latin surname is one pattern, as before (the 3 s budget of _sqlite_budget)."""
    assert name_patterns("Carlsen") == ["%Carlsen%"]
    assert name_patterns("Magnus Carlsen") == ["%Carlsen%"]
    assert len(name_patterns("Некрасовского")) <= 4


@pytest.mark.unit
def test_split_players_keeps_hyphenated_names():
    assert split_players("Vachier-Lagrave") == ["Vachier-Lagrave"]
    assert split_players("Синдаров — Накамура") == ["Синдаров", "Накамура"]


@pytest.mark.unit
def test_name_detection():
    assert known_player_in("последнюю партию карлсена")
    assert known_player_in("Show me Carlsen's game")
    assert mentions_player("Покажи последнюю партию Эригайси")
    assert not mentions_player("Объясни план белых в Испанской партии")
    assert not mentions_player("Покажи на доске защиту Каро-Канн")
    assert names_two_players("Синдаров — Накамура")
    assert names_two_players("партия Андерсена против Кизерицкого")
    assert not names_two_players("Ферзь против ладьи — это выигрыш?")


# ── The game on the board ────────────────────────────────────────────────────────────────

@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "games_index.db"
    disk = sqlite3.connect(path)
    _db().backup(disk)
    disk.close()
    monkeypatch.setattr(twic_search, "TWIC_DB_PATH", str(path))
    return path


@pytest.mark.unit
def test_search_then_pgn_then_board(db_file):
    """search_master_games → get_game_pgn(show=true) → load_pgn with every move of the game."""
    from src.board_protocol import LoadPgn, parse_pgn_moves

    rows = json.loads(twic_search._handle_search_master_games({"player": "Синдаров", "opponent": "Накамура",
                                                               "year_min": 2026, "year_max": 2026}))
    first = next(r for r in rows if r["white_name"].startswith("Sindarov"))
    out = json.loads(twic_search._handle_get_game_pgn({"game_id": first["id"], "show": True}))
    assert out["headers"]["White"] == "Sindarov,Javokhir"
    actions = out["board_actions"]
    assert [a["type"] for a in actions] == ["load_pgn"]
    loaded = LoadPgn(pgn=actions[0]["pgn"])
    assert loaded.moves == parse_pgn_moves(out["pgn"])
    assert len(loaded.moves) == 12  # the whole game, not its opening
    assert "Sindarov" in loaded.loaded


@pytest.mark.unit
def test_pgn_without_show_leaves_the_board(db_file):
    out = json.loads(twic_search._handle_get_game_pgn({"game_id": 3622931}))
    assert "pgn" in out and "board_actions" not in out


@pytest.mark.unit
def test_unreadable_game_is_not_shown(db_file, monkeypatch):
    monkeypatch.setattr(twic_search, "get_game_pgn",
                        lambda game_id: {"pgn": "1. e4 e5 2. Ke7?? Qxx9", "headers": {}})
    out = json.loads(twic_search._handle_get_game_pgn({"game_id": 1, "show": True}))
    assert "board_actions" not in out and out["shown"] is False


@pytest.mark.unit
def test_shown_game_respects_the_strict_board_lock(db_file, monkeypatch):
    """Under a strict lock (a live game, the student's own position) the load is dropped and the
    model told so — the same rule as every tool that puts a position up (src/board_truth.py)."""
    from src.board_truth import board_truth

    import src.sessions as sessions

    raw = twic_search._handle_get_game_pgn({"game_id": 3622931, "show": True})
    monkeypatch.setattr(sessions, "board_lock_strict_for", lambda kwargs: True)
    kept = json.loads(board_truth(raw, {}))
    assert "board_actions" not in kept and kept.get("board_hint")


@pytest.mark.unit
def test_tool_schemas_offer_it():
    assert "opponent" in twic_search.SEARCH_GAMES_SCHEMA["parameters"]["properties"]
    assert "show" in twic_search.GET_PGN_SCHEMA["parameters"]["properties"]
    assert "get_game_pgn" in twic_search.SEARCH_GAMES_SCHEMA["description"]


@pytest.mark.unit
def test_prompt_says_how_and_forbids_claims_without_the_tool():
    from src.prompt_builder import VOICE_TOOL_LAYER, build_system_prompt

    text = build_system_prompt(soul_content="soul")
    assert "show=true" in text and "never say you searched the database" in text
    assert "get_game_pgn with show=true" in VOICE_TOOL_LAYER
