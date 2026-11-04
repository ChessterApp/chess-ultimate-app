"""The review of 03.11 on «any game from the database reaches the board» (src/tool_selector.py, src/player_names.py,
src/tools/twic_search.py, src/answer_check_db.py, src/server.py).

The live run (21 turns on a fixture database) and the selector review found, by class:
  * a follow-up turn («загрузи вторую», «а предыдущую?», «а против Гукеша?») lost the game tools — the selector saw
    only the current message — and the coach said the database gave nothing (``game_context_tools``);
  * a claim about the database no tool of the turn made went out unchecked (``db_claim_issues``);
  * the rewrite of a wrong sentence before a tool call stood in for the real answer and wrote «нет доступа к базе»
    while the game went on the board (the rewrite is called off by the tool call);
  * the loaded game was retold with invented moves (``move_list`` in the tool result, ``loaded_game_issues``);
  * search_master_games ranked below the top brought no get_game_pgn; «покажи партию ногербека», «Карлсен-Каруана»,
    «партейку», typos missed; English own-game questions lost get_user_games; openings, a new game, lessons and
    puzzles fired the game intent;
  * «Robert Hübner» was searched as «%Robert%»; a name the index stored with a replacement character, «Хюбнер»,
    «Мартинес» were not found.
"""

import json
import sqlite3
import threading
import time
from unittest.mock import MagicMock, patch

import chess
import pytest

from src import answer_check_db as acd
from src import tool_selector as ts
from src.answer_check import CheckContext
from src.boards import new_board
from src.player_names import count_players, name_patterns, names_two_players, split_players
from src.sessions import Session
from src.tools import twic_search


@pytest.fixture(scope="module")
def declarations():
    from src.tool_bridge import build_tool_declarations
    from src.tools import discover_and_register

    discover_and_register()
    return build_tool_declarations()


def _names(decls):
    return [d["name"] for d in decls]


def _select(declarations, query, carry=()):
    return _names(ts.select_tool_subset(declarations, query, topk=7, carry=carry))


S, P, U = "search_master_games", "get_game_pgn", "get_user_games"


# ── follow-up turns keep the game tools ─────────────────────────────────────────────────────────────────────────

FOLLOW_UPS = [
    "а предыдущую его партию?", "загрузи вторую", "а против Гукеша?", "а предыдущую?", "покажи следующую",
    "загрузи её", "покажи её на доске", "давай вторую", "открой первую из списка", "а с Каруаной?",
    "Загрузи эту партию на доску", "Да, загрузи её", "Хорошо, а ходы этой партии можешь показать?",
    "Давай третью партию", "А теперь поставь эту партию Карлсена на доску",
    "and the previous one?", "Load the second one", "show me the next one",
    "екіншісін жүкте", "алдыңғысын көрсет",
]


@pytest.mark.unit
@pytest.mark.parametrize("query", FOLLOW_UPS)
def test_follow_up_after_a_database_tool_keeps_search_and_pgn(declarations, query):
    carry = ts.game_context_tools(query, (), game_tools_turns_ago=1)
    assert carry == ts.GAME_TOOLS
    names = _select(declarations, query, carry)
    assert S in names and P in names


@pytest.mark.unit
@pytest.mark.parametrize("query", FOLLOW_UPS)
def test_follow_up_after_a_game_request_keeps_them(query):
    """A restarted server has no tool trail: the previous message asked for a game."""
    assert ts.game_context_tools(query, ("Покажи последнюю партию Карлсена из базы на доске",)) == ts.GAME_TOOLS


@pytest.mark.unit
@pytest.mark.parametrize("query", FOLLOW_UPS)
def test_follow_up_about_the_database_game_on_the_board_keeps_them(query):
    assert ts.game_context_tools(query, (), None, {"twic_game_id": 3622931}) == ts.GAME_TOOLS


@pytest.mark.unit
def test_the_trail_ends_and_own_games_are_not_carried():
    assert ts.game_context_tools("загрузи вторую", (), game_tools_turns_ago=ts.GAME_TRAIL_TURNS + 1) == ()
    assert ts.game_context_tools("загрузи вторую", (), game_tools_turns_ago=0) == ()  # this turn: not yet
    assert ts.game_context_tools("загрузи вторую", ("Как ставить мат ладьёй?",)) == ()
    assert ts.game_context_tools("а почему конь плохой?", (), None, {"twic_game_id": 1}) == ()
    assert ts.game_context_tools("Покажи мою последнюю партию", (), game_tools_turns_ago=1) == ()
    assert ts.game_context_tools("а мою партию с lichess загрузи", (), game_tools_turns_ago=1) == ()


@pytest.mark.unit
def test_carried_tools_never_push_out_core_or_ranked(declarations):
    plain = _select(declarations, "Как ставить мат ладьёй?")
    carried = _select(declarations, "Как ставить мат ладьёй?", ts.GAME_TOOLS)
    assert carried[: len(plain)] == plain
    assert len(carried) - len(plain) <= ts.MAX_EXTRA_TOOLS


@pytest.mark.unit
def test_session_counts_the_turns_since_a_database_tool():
    s = Session(user_id="u")
    assert s.game_tools_turns_ago() is None
    s.add_message("user", "Какие партии Синдарова есть в базе?")
    s.note_game_tools()
    assert s.game_tools_turns_ago() == 0
    s.add_message("assistant", "Вот список.")
    s.add_message("user", "загрузи вторую")
    assert s.game_tools_turns_ago() == 1


@pytest.mark.unit
def test_the_board_remembers_its_database_game_until_another_replaces_it():
    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0"
    s = Session(user_id="u")
    board = s.ensure_board()
    s.apply_board_actions([{"type": "load_pgn", "pgn": pgn, "game_id": 3622931}], board_id=board.id)
    assert board.source.get("twic_game_id") == 3622931
    board.load_pgn(pgn, ply=2)  # the page saves the same game at another move: kept
    board.navigate("first")
    assert board.source.get("twic_game_id") == 3622931
    board.load_pgn("1. d4 d5 *")  # the student's own game: gone
    assert not (board.source or {}).get("twic_game_id")
    s.apply_board_actions([{"type": "load_pgn", "pgn": pgn, "game_id": 7}], board_id=board.id)
    s.apply_board_actions([{"type": "set_fen", "fen": chess.STARTING_FEN}], board_id=board.id)
    assert not (board.source or {}).get("twic_game_id")
    s.apply_board_actions([{"type": "load_pgn", "pgn": pgn, "game_id": 7}], board_id=board.id)
    s.apply_board_actions([{"type": "load_pgn", "pgn": "1. c4 e5 *"}], board_id=board.id)  # a famous game
    assert not (board.source or {}).get("twic_game_id")


# ── companions wherever search_master_games ranks ────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("query", [
    "Покажи, как Карлсен обыграл Каруану в 2018", "Найди Карлсен Непомнящий 2021 шестая",
    "show me how Carlsen beat Nepo in 2021", "Покажи Карлсен-Каруана 2018", "Найди Карлсен-Непомнящий",
    "Show Carlsen-Caruana", "Can you show Carlsen-Caruana from Norway Chess on the board?",
    "Загрузи Синдаров-Накамура",
])
def test_search_brings_pgn_wherever_it_ranks(declarations, query):
    names = _select(declarations, query)
    assert S in names and P in names


@pytest.mark.unit
def test_hyphen_pairs():
    assert split_players("Карлсен-Каруана") == ["Карлсен", "Каруана"]
    assert split_players("Carlsen-Caruana") == ["Carlsen", "Caruana"]
    assert split_players("Vachier-Lagrave") == ["Vachier-Lagrave"]
    assert split_players("Вашье-Лаграв") == ["Вашье-Лаграв"]
    assert names_two_players("Покажи Карлсен-Каруана 2018")
    assert not names_two_players("Турнир в Вейк-ан-Зее")
    assert not names_two_players("Защита Каро-Канн")
    assert not names_two_players("Сент-Луис 2024")


# ── «покажи партию <name>», diminutives, typos, Latin-typed Russian ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("query", [
    "покажи партию ногербека", "покажи партию казыбека ногербека", "покажи партию алишера сулейменова",
    "выведи партию жансаи абдумалик", "покажи партию махмуда ахмедова", "покажи партию сюй сянъюя",
    "поставь на доску партию бибисары асаубаевой",
    "Покажи партейку Таля", "найди партеечку Карлсена", "загрузи партиюшку Морфи",
    "найди парию Карлсена", "загрузи партю Каруаны", "Поищи партейку Спасского",
    "naidi partiyu Kasparova", "karlsen nakamura partiyu pokazhi",
    "а покажи-ка как играл дин лижэнь последнюю",
])
def test_game_asked_in_other_words(declarations, query):
    assert ts.asks_for_game(query)
    names = _select(declarations, query)
    assert S in names and P in names


# ── the student's own games ──────────────────────────────────────────────────────────────────────────────────────

OWN = [
    "Show my last game", "What did I do wrong in my last game?", "Analyze my recent games",
    "Find my game from yesterday", "Load my latest lichess game", "Open the game I just played",
    "Show me the games I played this week", "Load my last game",
    "Найди мою партию от вчера", "Покажи мою последнюю партию в базе", "Загрузи из моих партий последнюю",
    "Посмотри партию, сыгранную мной вчера",
]


@pytest.mark.unit
@pytest.mark.parametrize("query", OWN)
def test_own_games_get_user_games_and_not_the_master_database(declarations, query):
    names = _select(declarations, query)
    assert U in names
    assert S not in names and P not in names


@pytest.mark.unit
def test_own_game_with_a_master_named_keeps_the_database(declarations):
    names = _select(declarations, "Сравни мою партию с партией Карлсена против Каруаны")
    assert S in names and U in names


@pytest.mark.unit
@pytest.mark.parametrize("query", [
    "Загрузи вчерашнюю партию", "Открой последнюю партию", "Загрузи последнюю партию с личеса",
    "Загрузи последнюю партию с chess.com", "Мой ник на lichess Asan123, загрузи последнюю партию",
    "Загрузи партию моего соперника по турниру", "Open the game I just played",
    "Загрузи партию по ссылке https://lichess.org/xYz98765",
    "Открой партию по ссылке lichess.org/Zz11Yy22 и найди ошибки",
])
def test_own_game_is_no_master_request(query):
    assert not ts.asks_for_game(query)


# ── false positives ──────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("query", [
    "Открой урок про итальянскую партию", "Найди хорошие идеи для белых в шотландской партии",
    "Открой новую партию за белых", "Загрузи новую партию против тебя",
    "Давай сыграем партию как Карлсен против Каруаны", "Хочу задачи из партий Карлсена", "Дай задачу из партии Таля",
    "Кто выиграл Tata Steel 2025?",
])
def test_not_a_game_request(query):
    assert not ts.asks_for_game(query)


@pytest.mark.unit
def test_from_the_start_is_not_an_opening(declarations):
    assert "get_opening_stats" not in _select(declarations, "Покажи эту партию с начала")
    assert "get_opening_stats" in _select(declarations, "Какое начало партии лучше для новичка?")


@pytest.mark.unit
def test_a_tournament_is_not_two_players():
    assert count_players("Кто выиграл Tata Steel 2025?") >= 2  # the words alone read as names…
    assert not ts.asks_for_game("Кто выиграл Tata Steel 2025?")  # …but the event is taken out first


@pytest.mark.unit
@pytest.mark.parametrize("query", ["Who is better here?", "Explain the Lucena position"])
def test_description_words_of_other_tools_do_not_score(declarations, query):
    assert P not in _select(declarations, query)


# ── names ────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_two_word_name_needs_both_words():
    assert name_patterns("Robert Hübner")[:2] == ["%Hübner%Rob%", "%Robert%Hüb%"]
    assert name_patterns("Hübner, Robert")[0] == "%Hübner%Rob%"
    assert name_patterns("Daniil Dubov") == ["%Dubov%"]  # a known player by any word
    assert name_patterns("Hans Moke Niemann") == ["%Niemann%"]
    assert name_patterns("Robert Hübner", strict=False)[0] == "%Hübner%"  # the fallback: the surname, never «Robert»


@pytest.mark.unit
@pytest.mark.parametrize("name,expected", [
    ("Хюбнер", "%h_bner%"), ("Хюбнера", "%h_bner%"), ("Мартинес", "%martinez%"), ("Перес", "%perez%"),
])
def test_russian_spellings_of_latin_names(name, expected):
    assert expected in name_patterns(name)


def _names_db(tmp_path, rows):
    path = tmp_path / "games_index.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE games (id INTEGER PRIMARY KEY, white_name TEXT, black_name TEXT, result TEXT,
        date TEXT, eco TEXT, opening TEXT, event TEXT, white_elo INTEGER, black_elo INTEGER,
        pgn_offset INTEGER DEFAULT 0, pgn_length INTEGER DEFAULT 0)""")
    for r in rows:
        conn.execute("INSERT INTO games (id, white_name, black_name, result, date, eco, event) VALUES (?,?,?,?,?,?,?)",
                     r)
    conn.commit()
    conn.close()
    return path


@pytest.mark.unit
def test_names_stored_with_a_replacement_character_are_found(tmp_path):
    path = _names_db(tmp_path, [
        (1, "H�bner,Robert", "St�hlberg,Gideon", "1-0", "1978.03.15", "D37", "Bad Lauterberg"),
        (2, "Fischer,Robert James", "Spassky,Boris V", "1-0", "1972.07.23", "D59", "World Championship"),
        (3, "Mart�nez,David", "P�rez,Francisco", "1-0", "2010.01.01", "B90", "Open"),
        (4, "Naumann,Alexander", "Hubner,R", "0-1", "2001.01.01", "A00", "Bundesliga"),
    ])
    ids = lambda **kw: [g["id"] for g in twic_search.search_master_games(db_path=str(path), **kw)]  # noqa: E731
    assert ids(player="Stahlberg") == [1]
    assert ids(player="Ståhlberg") == [1]
    assert ids(player="Хюбнер") == [4, 1]
    assert ids(player="Robert Hübner") == [1]  # not Fischer, Robert James
    assert 1 in ids(player="Hubner, Robert")  # the second try: the surname in its spellings
    assert ids(player="Мартинес") == [3]
    assert ids(player="Niemann") == []  # the loose spelling never reaches «Naumann» while…
    assert ids(player="Naumann") == [4]


@pytest.mark.unit
def test_latin1_game_text_is_read_as_latin1(tmp_path, monkeypatch):
    pgn = ('[Event "Bad Lauterberg"]\n[White "Hübner,Robert"]\n[Black "Ståhlberg,Gideon"]\n[Result "1-0"]\n\n'
           "1. d4 d5 2. c4 e6 1-0\n").encode("latin-1")
    pgn_path = tmp_path / "twic.pgn"
    pgn_path.write_bytes(pgn)
    monkeypatch.setattr(twic_search, "PGN_FILE_PATH", str(pgn_path))
    assert "Ståhlberg" in twic_search._read_movetext(0, len(pgn))
    fixed = twic_search._fix_names({"White": "H�bner,Robert", "Black": "St�hlberg,Gideon", "Event": "x"},
                                   twic_search._read_movetext(0, len(pgn)))
    assert fixed["White"] == "Hübner,Robert" and fixed["Black"] == "Ståhlberg,Gideon"


# ── the moves of the loaded game ─────────────────────────────────────────────────────────────────────────────────

BERLIN = ('[White "Nakamura,Hikaru"]\n[Black "Firouzja,Alireza"]\n[Event "WR Rapid Miami 2026"]\n'
          '[Date "2026.10.17"]\n[Result "1/2-1/2"]\n\n'
          "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4 5. d4 Nd6 6. Bxc6 dxc6 7. dxe5 Nf5 8. Qxd8+ Kxd8 1/2-1/2")


@pytest.mark.unit
def test_move_list_says_who_moved_what_and_what_it_took():
    moves = twic_search.move_list(BERLIN)
    assert moves[6] == "4.O-O White castles kingside"
    assert moves[7] == "4...Nxe4 Black knight f6 takes pawn e4"
    assert moves[14] == "8.Qxd8+ White queen d1 takes queen d8, check"
    promo = twic_search.move_list('[FEN "8/3P4/8/8/8/8/k7/7K w - - 0 33"]\n[SetUp "1"]\n\n33. d8=R Kb2 34. Rb8+ *')
    assert promo[0] == "33.d8=R White pawn d7 to d8, promotes to rook"
    assert promo[2].endswith(", check")
    assert twic_search.move_list("not a game") == []


@pytest.mark.unit
def test_get_game_pgn_hands_the_moves_and_the_board_its_id(monkeypatch):
    monkeypatch.setattr(twic_search, "get_game_pgn", lambda game_id: {
        "id": game_id, "pgn": BERLIN, "headers": {}, "moves": twic_search.move_list(BERLIN),
        "note": twic_search.MOVES_NOTE})
    out = json.loads(twic_search._handle_get_game_pgn({"game_id": 3622927, "show": True}))
    assert out["moves"][7].startswith("4...Nxe4 Black knight")
    assert out["board_actions"][0]["game_id"] == 3622927


def _game_ctx(pgn=BERLIN):
    ctx = CheckContext.from_fens()
    ctx.db_tracked = True
    acd.note_board_game(ctx, pgn)
    return ctx


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Испанская партия, и уже на 4-м ходу белые взяли пешку на e4.",
    "Посмотрите на 7-й ход, как чёрная пешка пошла на e5.",
    "Дальше в партии 7...Ne4 и белые давят.",
    "На 8-м ходу чёрные забрали ладью.",
    "В этой партии после 5.d3 у белых тихая игра.",
    "Накамура сыграл 5.d3, и у белых тихая игра.",  # a side of the game named
    "После 5.d4 Nd6 6.Bxc6 dxc6 7.dxe5 Ne4 белые давят.",  # four plies of the game, then a move it did not have
])
def test_wrong_moves_of_the_loaded_game_are_caught(sentence):
    assert acd.game_db_issues(sentence.lower(), sentence, _game_ctx())


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "На 4-м ходу чёрные взяли пешку на e4 — берлинская защита.",
    "4...Nxe4 и 5.d4 Nd6 — главный путь.",
    "На 8-м ходу белые разменяли ферзей: 8.Qxd8+ Kxd8.",
    "Вместо 7...Nf5 можно было сыграть 7...Ne4.",  # an alternative, not the game
    "В партии Карлсен — Каруана на 4-м ходу белые взяли пешку на e4.",  # another game
    "В 2018 году на 4-м ходу белые взяли пешку на e4.",  # another game by its year
    "Пролистай партию и найди момент, где белые получили инициативу.",
])
def test_right_moves_and_other_games_pass(sentence):
    assert acd.game_db_issues(sentence.lower(), sentence, _game_ctx()) == []


@pytest.mark.unit
def test_nothing_is_judged_without_a_loaded_game():
    ctx = CheckContext.from_fens()
    sentence = "На 4-м ходу белые взяли пешку на e4."
    assert acd.game_db_issues(sentence.lower(), sentence, ctx) == []


@pytest.mark.unit
def test_rewrite_is_told_the_turn_tools_and_that_the_game_is_not_the_students():
    ctx = _game_ctx()
    acd.note_tool_result(ctx, "search_master_games", json.dumps([{"id": 1}]))
    note = acd.turn_tools_note(ctx)
    assert "search_master_games — found" in note and "4...Nxe4 Black knight f6 takes pawn e4" in note
    from src.server import _student_side_note

    side = _student_side_note(ctx)
    assert "Nakamura" in side and "never «ты»" in side


# ── claims about the database ────────────────────────────────────────────────────────────────────────────────────

DB_CLAIMS = [
    "Не получилось — я не вижу твоей прошлой партии Карлсена из базы: у меня в этом сеансе нет ссылки на неё, "
    "а поиск по базе мне сейчас ничего не вернул.",
    "Проверил, база в этот раз не отдала партию — попробуем ещё раз чуть позже.",
    "Честно скажу: партию Карлсен — Гукеш из базы сейчас достать не вышло — поиск по базе ничего не вернул.",
    "Не могу загрузить конкретную партию Абдусатторова против Синдарова — у меня нет доступа к базе партий.",
    "Разыграть партию по ходам я не могу — в базе у меня лежат только данные о встречах, а не сами ходы.",
    "Такой партии в базе нет.",
    "I couldn't find that game in the database.",
    "Не нашёл по базе — давай я возьму партию из открытых источников.",
]


def _db_ctx(*results):
    ctx = CheckContext.from_fens()
    ctx.db_tracked = True
    for tool, result in results:
        acd.note_tool_result(ctx, tool, json.dumps(result))
    return ctx


@pytest.mark.unit
@pytest.mark.parametrize("sentence", DB_CLAIMS)
def test_database_claim_without_the_tool_is_caught(sentence):
    assert acd.db_claim_issues(sentence.lower(), _db_ctx()) == [acd.DB_NOT_RUN_ISSUE]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", DB_CLAIMS[:4] + DB_CLAIMS[5:])
def test_database_claim_after_the_tool_found_it_is_caught(sentence):
    ctx = _db_ctx((S, [{"id": 3622931}]), (P, {"pgn": "1. e4 e5 *", "headers": {}}))
    assert acd.db_claim_issues(sentence.lower(), ctx) == [acd.DB_FOUND_ISSUE]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", DB_CLAIMS[:4] + DB_CLAIMS[5:])
def test_database_claim_after_an_empty_search_passes(sentence):
    assert acd.db_claim_issues(sentence.lower(), _db_ctx((S, []))) == []


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Если в базе такой партии нет, поищу её по сети.",
    "В базе «Мои партии» у тебя пока пусто — ни одной сохранённой партии.",
    "Партия уже на доске, листай ходы кнопками.",
    "В этой позиции у белых нет хода лучше.",
    "Нашёл в базе 12 партий Синдарова.",
])
def test_ordinary_sentences_are_no_database_claims(sentence):
    assert acd.db_claim_issues(sentence.lower(), _db_ctx()) == []


@pytest.mark.unit
def test_untracked_context_judges_nothing():
    ctx = CheckContext.from_fens()  # the voice check, the lesson tutor: no tool results recorded
    assert acd.db_claim_issues(DB_CLAIMS[0].lower(), ctx) == []


# ── the text turn: tools carried, the rewrite called off by a tool call ─────────────────────────────────────────

ST = chess.STARTING_FEN
USER = {"X-User-Id": "games-db-review"}


def _agent(script):
    """A fake model: *script* is a list of str (streamed text) and (tool, args, result) tuples (a tool call)."""
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        text = []
        for i, step in enumerate(script):
            if isinstance(step, tuple):
                tool, args, result = step
                agent.tool_start_callback(f"c{i}", tool, args)
                time.sleep(0.05)
                agent.tool_complete_callback(f"c{i}", tool, args, json.dumps(result))
            else:
                stream_callback(step)
                text.append(step)
                time.sleep(0.05)
        return "".join(text)

    agent.chat.side_effect = _chat
    return agent


@pytest.mark.unit
class TestTextTurn:
    @pytest.fixture(autouse=True)
    def _turn(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src import config
        from src.middleware.rate_limiter import rate_limiter
        from src.sessions import session_store

        session_store._sessions.clear()
        rate_limiter.reset()
        for name, value in (("COACH_TWO_STAGE", False), ("COACH_ENGINE_NOTE", False), ("COACH_OPENING_PRESTEP", False),
                            ("COACH_SITE_PUZZLE_LOOKUP", False), ("COACH_ANSWER_CHECK", True),
                            ("COACH_ANSWER_FIX", True), ("COACH_RELATION_CHECK", "off")):
            monkeypatch.setattr(config, name, value)
        self.client = TestClient(__import__("src.server", fromlist=["app"]).app)
        self.agent_kwargs = []
        self.fix_prompts = []
        yield
        session_store._sessions.clear()
        rate_limiter.reset()

    def _turn_with(self, script, message, session_id=None, fix_text="Нет доступа к базе партий.", wait_abort=False):
        from src.quick_reply import QuickReply
        from src.user_profile import UserProfile

        def _create(**kwargs):
            self.agent_kwargs.append(kwargs)
            return _agent(script)

        def _fix(**kwargs):
            self.fix_prompts.append(kwargs["messages"][1]["content"])
            if wait_abort:  # a slow rewrite: the tool call comes while it is still thinking
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not kwargs["should_abort"]():
                    time.sleep(0.01)
                if kwargs["should_abort"]():
                    return QuickReply(model=kwargs["model"])
            kwargs["on_delta"](fix_text)
            return QuickReply(model=kwargs["model"])

        body = {"message": message, "fen": ST}
        if session_id:
            body["session_id"] = session_id
        with patch("src.server._create_agent", side_effect=_create), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id="games-db-review")), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server.engine_note", return_value=None), \
                patch("src.server.log_event"):
            resp = self.client.post("/api/coach/chat", headers=USER, json=body)
        assert resp.status_code == 200
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        sid = next((f["session_id"] for f in frames if f.get("session_id")), session_id)
        return "".join(f.get("delta", "") for f in frames), frames, sid

    def test_follow_up_turn_gets_the_game_tools(self):
        found = [{"id": 3622931, "white_name": "Sindarov,Javokhir", "black_name": "Nakamura,Hikaru"},
                 {"id": 3622932, "white_name": "Caruana,Fabiano", "black_name": "Sindarov,Javokhir"}]
        _, _, sid = self._turn_with([(S, {"player": "Синдаров"}, found), "Вот две партии Синдарова."],
                                    "Какие партии Синдарова есть в базе за 2026 год?")
        assert self.agent_kwargs[0]["carry_tools"] == ()
        self._turn_with(["Загружаю."], "загрузи вторую", session_id=sid)
        assert self.agent_kwargs[1]["carry_tools"] == ts.GAME_TOOLS

    def test_claim_about_the_database_without_its_tool_is_cut(self):
        shown, _, _ = self._turn_with(["Поиск по базе ничего не вернул. ", "Уточни турнир, и я поищу."],
                                      "а против Гукеша?", fix_text="Давай поищу её в базе: назови год.")
        assert "ничего не вернул" not in shown
        assert "назови год" in shown
        assert "Database tools" not in self.fix_prompts[0]  # nothing ran: no results to quote

    def test_rewrite_before_a_tool_call_is_called_off(self):
        """t12: the draft's first sentence was flagged, the rewrite (no tools) said «нет доступа к базе» and stood in
        for the answer written after get_game_pgn had put the game on the board."""
        game = {"id": 3622952, "pgn": BERLIN, "headers": {"White": "Nakamura,Hikaru", "Black": "Firouzja,Alireza"},
                "moves": twic_search.move_list(BERLIN),
                "board_actions": [{"type": "load_pgn", "pgn": BERLIN, "game_id": 3622952}]}
        shown, frames, _ = self._turn_with(
            ["Поиск по базе ничего не вернул. ", (P, {"game_id": 3622952, "show": True}, game),
             "Партия Накамура — Фирузджа уже на доске, листай ходы."],
            "Загрузи партию Накамура — Фирузджа", wait_abort=True)
        assert "ничего не вернул" not in shown
        assert "Нет доступа" not in shown
        assert "уже на доске" in shown
        assert any(a.get("type") == "load_pgn" for f in frames for a in (f.get("board_actions") or []))

    def test_wrong_move_of_the_loaded_game_is_rewritten_with_its_move_list(self):
        game = {"id": 3622927, "pgn": BERLIN, "headers": {"White": "Nakamura,Hikaru", "Black": "Firouzja,Alireza"},
                "moves": twic_search.move_list(BERLIN),
                "board_actions": [{"type": "load_pgn", "pgn": BERLIN, "game_id": 3622927}]}
        shown, _, _ = self._turn_with(
            [(P, {"game_id": 3622927, "show": True}, game), "Партия на доске. ",
             "Уже на 4-м ходу белые взяли пешку на e4. "],
            "Покажи партию Накамура — Фирузджа", fix_text="На 4-м ходу чёрный конь взял пешку e4.")
        assert "белые взяли пешку" not in shown
        assert "чёрный конь взял" in shown
        assert "4...Nxe4 Black knight f6 takes pawn e4" in self.fix_prompts[0]
