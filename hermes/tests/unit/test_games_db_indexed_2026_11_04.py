"""search_master_games on the name index, as the site searches (04.11).

``LIKE '%carlsen%'`` over the games table reads every row: 1.1–1.6 s on a million synthetic rows against a 3 s
budget, and production holds 4.35 M. The site's database page asks the index on the normalized names instead
(backend/api/openings.py: ``white_name_normalized LIKE 'tok%'`` / ``black_name_normalized LIKE 'tok%'`` as UNION
branches). The coach now does the same when the database has those indexes — and gives the same games as the pass
over every row on the same database.
"""

import sqlite3
import unicodedata

import pytest

from src.player_names import name_patterns
from src.tools import twic_search


def _normalize(name):  # backend/scripts/incremental_index.normalize_name
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return n.lower().replace(",", " ").replace("  ", " ").strip()


# The production schema (docs/history/TWIC_INDEXER_STATUS.md, backend/scripts/incremental_index.py).
SCHEMA = """CREATE TABLE games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    white_name TEXT, white_name_normalized TEXT,
    black_name TEXT, black_name_normalized TEXT,
    white_elo INTEGER, black_elo INTEGER,
    white_title TEXT, black_title TEXT,
    white_fide_id TEXT, black_fide_id TEXT,
    result TEXT, date TEXT, year INTEGER,
    eco TEXT, opening TEXT, variation TEXT,
    event TEXT, site TEXT, round TEXT,
    pgn_offset INTEGER, pgn_length INTEGER)"""
# The games indexes of production (docs/history/TWIC_INDEXER_STATUS.md «Indexes»).
NAME_INDEXES = ["CREATE INDEX idx_white_name ON games(white_name_normalized)",
                "CREATE INDEX idx_black_name ON games(black_name_normalized)"]
OTHER_INDEXES = ["CREATE INDEX idx_white_elo ON games(white_elo)", "CREATE INDEX idx_black_elo ON games(black_elo)",
                 "CREATE INDEX idx_date ON games(date)", "CREATE INDEX idx_year ON games(year)",
                 "CREATE INDEX idx_eco ON games(eco)", "CREATE INDEX idx_result ON games(result)",
                 "CREATE INDEX idx_event ON games(event)"]

ROWS = [  # id, white, black, result, date, eco, event
    (101, "Sindarov,Javokhir", "Nakamura,Hikaru", "1-0", "2026.10.25", "B90", "Miami Open 2026"),
    (102, "Nakamura,Hikaru", "Sindarov,Javokhir", "1/2-1/2", "2026.10.26", "C65", "Miami Open 2026"),
    (103, "Sindarov,Javokhir", "Abdusattorov,Nodirbek", "0-1", "2024.05.02", "E20", "Tashkent Open"),
    (104, "Carlsen,Magnus", "Caruana,Fabiano", "1-0", "2025.06.01", "C84", "Norway Chess"),
    (105, "Caruana,Fabiano", "Carlsen,Magnus", "1/2-1/2", "2026.06.02", "C67", "Norway Chess"),
    (106, "Karjakin,Sergey", "Carlsen,Magnus", "0-1", "2016.11.28", "C84", "World Championship"),
    (107, "Carlsen, Magnus", "Nakamura,Hikaru", "1-0", "2026.06.02", "B12", "Norway Chess"),  # same date as 105
    (108, "Huebner,Robert", "Tal,Mikhail", "1/2-1/2", "1979.05.05", "B18", "Montreal"),
    (109, "H�bner,R", "Karpov,Anatoly", "0-1", "1980.01.10", "E15", "Tilburg"),
    (110, "Hübner,Robert", "Kasparov,Garry", "1/2-1/2", "1985.03.03", "D37", "Hamburg"),
    (111, "St�hlberg,Gideon", "Tal,Mikhail", "0-1", "1962.04.04", "A00", "Stockholm"),
    (112, "Tal,Mikhail", "Botvinnik,Mikhail", "1-0", "1960.03.15", "B18", "World Championship"),
    (113, "Vitali,Natalia", "Talukdar,Ravi", "1-0", "2025.05.05", "A00", "Open"),
    (114, "Kovalev,Vladislav", "Khalifman,Alexander", "1-0", "2012.02.02", "A45", "Moscow Open"),
    (115, "Covalev,Ion", "Halifman,Petr", "0-1", "2013.03.03", "A46", "Chisinau Open"),
    (116, "Ding,Liren", "Gukesh,D", "0-1", "2024.12.12", "D02", "World Championship"),
    (117, "Gukesh,D", "Ding,Liren", "1-0", "2024.12.01", "B90", "World Championship"),
    (118, "Van Foreest,Jorden", "Giri,Anish", "1-0", "2021.01.31", "C54", "Tata Steel Masters"),
    (119, "So,Wesley", "Giri,Anish", "1/2-1/2", "2023.01.20", "C42", "Tata Steel Masters"),
    (120, "Sorensen,Ole", "Giri,Anish", "0-1", "2023.01.21", "C42", "Tata Steel Masters"),
    (121, "Vachier-Lagrave,Maxime", "Nepomniachtchi,Ian", "1/2-1/2", "2022.07.01", "C42", "FIDE Candidates"),
    (122, "Abdumalik,Zhansaya", "Assaubayeva,Bibisara", "1-0", "2025.05.05", "B12", "Almaty Women Open"),
    (123, "Nogerbek,Kazybek", "Carlsen,Magnus", "0-1", "2026.06.02", "A04", "Norway Chess"),  # same date again
    (124, "Car*ter,Jim", "Carlsen,Magnus", "0-1", "2001.01.01", "A00", "Weird Open"),
]


def _db(layout: str, path=None) -> sqlite3.Connection:
    """``raw`` — names only; ``normalized`` — the site's normalized columns, no index on them;
    ``indexed`` — the normalized columns and their indexes, as on production."""
    conn = sqlite3.connect(str(path) if path else ":memory:")
    if layout == "raw":
        conn.execute("""CREATE TABLE games (id INTEGER PRIMARY KEY, white_name TEXT, black_name TEXT, result TEXT,
            date TEXT, eco TEXT, opening TEXT, event TEXT, white_elo INTEGER, black_elo INTEGER)""")
        conn.executemany("INSERT INTO games (id, white_name, black_name, result, date, eco, event) "
                         "VALUES (?,?,?,?,?,?,?)", ROWS)
    else:
        conn.execute(SCHEMA)
        conn.executemany(
            "INSERT INTO games (id, white_name, white_name_normalized, black_name, black_name_normalized, result, "
            "date, year, eco, event) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(i, w, _normalize(w), b, _normalize(b), r, d, int(d[:4]), e, ev) for i, w, b, r, d, e, ev in ROWS])
        for stmt in OTHER_INDEXES + (NAME_INDEXES if layout == "indexed" else []):
            conn.execute(stmt)
    conn.commit()
    return conn


def _ids(rows):
    return [r["id"] for r in rows]


# Everything the coach asks by surname, in any script, with the other filters.
QUERIES = [
    {"player": "Carlsen"}, {"player": "Карлсена"}, {"player": "Магнус Карлсен"}, {"player": "Magnus Carlsen"},
    {"player": "Sindarov"}, {"player": "Синдаров"}, {"player": "Javokhir Sindarov"}, {"player": "Жавохир"},
    {"player": "Nakamura"}, {"player": "Накамуры"}, {"player": "Hübner"}, {"player": "Hubner"}, {"player": "Huebner"},
    {"player": "Хюбнер"}, {"player": "Robert Hübner"}, {"player": "Hübner, Robert"}, {"player": "Stahlberg"},
    {"player": "Штальберг"}, {"player": "Таль"}, {"player": "Tal"}, {"player": "Дин"}, {"player": "Уэсли"},
    {"player": "Ковалев"}, {"player": "Kovalev"}, {"player": "Халифман"}, {"player": "Van Foreest"},
    {"player": "Вашье-Лаграв"}, {"player": "Абдумалик"}, {"player": "Ногербек"}, {"player": "Zzyzx"},
    {"player": "Некрасовского"}, {"player": "Car*ter"},
    {"player": "Sindarov", "opponent": "Nakamura"}, {"player": "Синдаров — Накамура"},
    {"player": "Carlsen", "opponent": "Caruana"}, {"player": "Карлсен-Каруана"}, {"player": "Gukesh", "opponent": "Ding"},
    {"player": "Накамура", "opponent": "Синдаров", "year_min": 2026, "year_max": 2026},
    {"player": "Carlsen", "year_min": 2026}, {"player": "Carlsen", "year_max": 2025},
    {"player": "Накамура", "event": "Майами 2026"}, {"player": "Nakamura", "event": "miami"},
    {"player": "Gukesh", "eco": "b90"}, {"player": "Carlsen", "result": "1-0"}, {"player": "Giri", "opening": "?"},
    {"player": "Carlsen", "limit": 2}, {"opponent": "Caruana"}, {"event": "Norway"}, {},
]


@pytest.mark.unit
def test_layout_is_read_from_the_database():
    assert twic_search.name_index_layout(_db("raw")) == {"normalized": False, "indexes": {}, "indexed": False}
    assert twic_search.name_index_layout(_db("normalized"))["indexed"] is False
    layout = twic_search.name_index_layout(_db("indexed"))
    assert layout["indexed"] is True
    assert layout["indexes"] == {"white_name_normalized": "idx_white_name", "black_name_normalized": "idx_black_name"}


@pytest.mark.unit
def test_an_index_in_another_collation_or_partial_does_not_count():
    conn = _db("normalized")
    conn.execute("CREATE INDEX w_nocase ON games(white_name_normalized COLLATE NOCASE)")
    conn.execute("CREATE INDEX b_part ON games(black_name_normalized) WHERE year > 2000")
    assert twic_search.name_index_layout(conn)["indexed"] is False
    conn.execute("CREATE INDEX w_b ON games(white_name_normalized, date)")  # a name first: its range serves
    conn.execute("CREATE INDEX b_b ON games(black_name_normalized)")
    assert twic_search.name_index_layout(conn)["indexed"] is True


@pytest.mark.unit
def test_layout_cached_per_file_and_renewed_when_the_file_changes(tmp_path):
    path = tmp_path / "games_index.db"
    conn = _db("normalized", path)
    assert twic_search.name_index_layout(conn)["indexed"] is False
    calls = []
    conn.set_trace_callback(calls.append)
    twic_search.name_index_layout(conn)
    assert not any("index_list" in c for c in calls)  # from the cache
    for stmt in NAME_INDEXES:
        conn.execute(stmt)
    conn.commit()
    assert twic_search.name_index_layout(conn)["indexed"] is True  # the file changed: read again


@pytest.mark.unit
@pytest.mark.parametrize("query", QUERIES, ids=[str(q) for q in QUERIES])
def test_indexed_path_gives_what_the_full_pass_gives(query):
    """The same games in the same order on the index as by reading every row of the same database."""
    full = _ids(twic_search.search_master_games(conn=_db("normalized"), **query))
    indexed = _ids(twic_search.search_master_games(conn=_db("indexed"), **query))
    assert indexed == full


@pytest.mark.unit
@pytest.mark.parametrize("query, expected", [
    ({"player": "Карлсена"}, [123, 107, 105, 104, 106, 124]),  # a day's games: the later id first
    ({"player": "Hübner"}, [110, 109, 108]),
    ({"player": "Хюбнер"}, [110, 109, 108]),
    ({"player": "Stahlberg"}, [111]),
    ({"player": "Таль"}, [108, 111, 112]),  # Tal,Mikhail — not Vitali or Talukdar
    ({"player": "Уэсли"}, [119]),  # So,Wesley — not Sorensen
    ({"player": "Ковалев"}, [115, 114]),  # «к» is k or c at the start of the name
    ({"player": "Халифман"}, [115, 114]),  # «х» is h or kh
    ({"player": "Синдаров — Накамура"}, [102, 101]),
    ({"player": "Nakamura", "event": "miami"}, [102, 101]),
])
def test_indexed_path_finds_the_games(query, expected):
    assert _ids(twic_search.search_master_games(conn=_db("indexed"), **query)) == expected


@pytest.mark.unit
def test_glob_takes_its_own_wildcards_literally():
    assert twic_search._glob("car*ter%") == "car[*]ter*"
    assert twic_search._glob("h_bner%") == "h?bner*"
    assert twic_search._glob("a[b?%") == "a[[]b[?]*"
    assert twic_search._glob_prefix("car[*]ter*") == "car"
    assert twic_search._glob_prefix("?ovalev*") == ""


@pytest.mark.unit
def test_a_word_inside_the_name_is_not_its_start():
    """The index answers by the start of the name — the surname, as TWIC writes it and as the site searches
    (backend/api/openings._longest_name_token: «substring search is not supported»). A first name alone, which
    the pass over every row found inside «sindarov javokhir», is not such a start."""
    assert _ids(twic_search.search_master_games(player="Javokhir", conn=_db("normalized"))) == [102, 101, 103]
    assert _ids(twic_search.search_master_games(player="Javokhir", conn=_db("indexed"))) == []


@pytest.mark.unit
def test_indexed_query_stays_parameterized():
    conn = _db("indexed")
    for evil in ("x' OR 1=1 --", "%'; DROP TABLE games; --", "Карлсен' --", "Car*", "[a-z]"):
        twic_search.search_master_games(player=evil, opponent=evil, event=evil, conn=conn)  # no SQL error
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == len(ROWS)


@pytest.mark.unit
def test_indexed_path_reads_the_name_index_only():
    conn = _db("indexed")
    sql = []
    conn.set_trace_callback(sql.append)
    twic_search.search_master_games(player="Синдаров", opponent="Накамура", year_min=2026, eco="B90",
                                    event="Miami", conn=conn)
    conn.set_trace_callback(None)
    query = next(s for s in sql if "FROM games" in s)
    assert "GLOB" in query and " UNION " in query and "LIKE '%sindarov%'" not in query
    plan = [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + query)]
    assert any("USING INDEX idx_white_name" in p or "USING INDEX idx_black_name" in p for p in plan), plan
    assert not any(p.startswith("SCAN games") for p in plan), plan
    assert not any("idx_date" in p or "idx_eco" in p or "idx_event" in p for p in plan), plan


@pytest.mark.unit
def test_without_the_indexes_the_full_pass_stays():
    for layout in ("raw", "normalized"):
        conn = _db(layout)
        sql = []
        conn.set_trace_callback(sql.append)
        rows = twic_search.search_master_games(player="Sindarov", conn=conn)
        assert set(_ids(rows)) == {101, 102, 103}
        assert any("LIKE" in s and "GLOB" not in s for s in sql if "FROM games" in s)


@pytest.mark.unit
def test_a_spelling_without_a_literal_start_goes_the_full_pass(monkeypatch):
    """A name whose every spelling starts with a wildcard has no index range: the search reads every row, as before."""
    real = twic_search.name_patterns
    monkeypatch.setattr(twic_search, "name_patterns",
                        lambda name, **kw: ["_ovalev%"] if kw.get("anchored") else ["%_ovalev%"]
                        if "овал" in name else real(name, **kw))
    conn = _db("indexed")
    sql = []
    conn.set_trace_callback(sql.append)
    assert _ids(twic_search.search_master_games(player="Овалев", conn=conn)) == [115, 114]
    assert not any("GLOB" in s for s in sql)


@pytest.mark.unit
def test_anchored_spellings():
    assert name_patterns("Carlsen", anchored=True) == ["Carlsen%"]
    assert name_patterns("Таль", anchored=True) == ["Tal,%"]
    assert "H�bner%" in name_patterns("Hübner", anchored=True)
    assert set(name_patterns("Ковалев", anchored=True)[:2]) == {"kovalev%", "covalev%"}
    assert {"halifman%", "khalifman%"} <= set(name_patterns("Халифман", anchored=True))
    assert name_patterns("Robert Hübner", anchored=True)[0] == "Hübner%Rob%"
    # the substring patterns are what they were
    assert name_patterns("Carlsen") == ["%Carlsen%"]
    assert "%H_bner%" in name_patterns("Hübner")


@pytest.mark.unit
def test_search_check_reports_the_index(tmp_path):
    path = tmp_path / "games_index.db"
    _db("indexed", path).close()
    out = twic_search.search_check(str(path))
    assert out["indexed"] is True and "USING INDEX idx_white_name" in out["plan"]
    assert out["Синдаров — Накамура 2026"].startswith("2 games, newest 2026.10.26 id 102")
    path2 = tmp_path / "plain.db"
    _db("normalized", path2).close()
    out = twic_search.search_check(str(path2))
    assert out["indexed"] is False and out["Carlsen"].startswith("5 games")
