"""import_game_from_url: link parsing, Chess.com TCN decoding, fetching, endpoint."""

import json
from unittest.mock import patch

import chess
import httpx
import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.tools.game_url import (
    GameUrlError, decode_tcn, fetch_game_by_url, looks_like_game_url, parse_game_url,
    _pgn_from_moves,
)

LICHESS_PGN = """[Event "Take Take Take Arena"]
[Site "https://lichess.org/kAdOQKeh"]
[Date "2026.04.08"]
[White "respects_55"]
[Black "DrNykterstein"]
[Result "0-1"]
[UTCDate "2026.04.08"]
[WhiteElo "2644"]
[BlackElo "3145"]
[ECO "B02"]
[Opening "Alekhine Defense"]

1. e4 Nf6 2. e5 Nd5 3. Nc3 Nxc3 4. dxc3 d6 0-1
"""

# First ten plies of a real Chess.com game (Hikaru – alexrustemov, 2026-09-23).
TCN_PREFIX = "lBZJmu!TkAJAfA0SgvYI"
TCN_PREFIX_UCI = ["d2d4", "d7d5", "e2e3", "g8f6", "c2c4", "d5c4", "f1c4", "e7e6", "g1f3", "c7c5"]
CHESSCOM_HEADERS = {
    "Event": "Live Chess", "Site": "Chess.com", "Date": "2026.09.23", "White": "Hikaru",
    "Black": "alexrustemov", "Result": "1-0", "ECO": "D00", "WhiteElo": 3439, "BlackElo": 3041,
    "TimeControl": "180", "SetUp": "1", "FEN": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
}


@pytest.mark.unit
@pytest.mark.parametrize("url, expected", [
    ("https://lichess.org/kAdOQKeh", ("lichess", "kAdOQKeh")),
    ("https://lichess.org/kAdOQKeh/black", ("lichess", "kAdOQKeh")),
    ("https://lichess.org/kAdOQKehAbCd", ("lichess", "kAdOQKeh")),   # 12-char player-side id
    ("lichess.org/kAdOQKeh#23", ("lichess", "kAdOQKeh")),
    ("https://lichess.org/game/export/kAdOQKeh", ("lichess", "kAdOQKeh")),
    ("https://www.chess.com/game/live/184239477800", ("chesscom", "184239477800")),
    ("https://www.chess.com/game/daily/9876", ("chesscom", "9876")),
    ("https://www.chess.com/analysis/game/live/184239477800?tab=review", ("chesscom", "184239477800")),
    ("https://chess.com/live/game/123", ("chesscom", "123")),
])
def test_parse_game_url(url, expected):
    assert parse_game_url(url) == expected
    assert looks_like_game_url(url)


@pytest.mark.unit
@pytest.mark.parametrize("url", ["", "https://chesster.io/coach", "https://lichess.org/@/DrNykterstein",
                                 "https://lichess.org/tv", "https://www.chess.com/member/hikaru", "что играть?"])
def test_parse_game_url_rejects(url):
    with pytest.raises(GameUrlError):
        parse_game_url(url)
    assert not looks_like_game_url(url)


@pytest.mark.unit
def test_decode_tcn_matches_real_game_prefix():
    assert decode_tcn(TCN_PREFIX) == TCN_PREFIX_UCI
    pgn = _pgn_from_moves(CHESSCOM_HEADERS, TCN_PREFIX_UCI)
    assert '[White "Hikaru"]' in pgn and '[Result "1-0"]' in pgn
    assert "1. d4 d5 2. e3 Nf6 3. c4 dxc4 4. Bxc4 e6 5. Nf3 c5" in pgn
    assert "SetUp" not in pgn  # standard start: no SetUp/FEN tags


@pytest.mark.unit
def test_decode_tcn_promotion_and_errors():
    # A pawn on b7 promoting to a queen on b8: 'b7' is index 49 → char '4'... derive rather than hardcode.
    a = 49  # b7
    b = 64 + 0 * 3 + 1  # queen, straight ahead
    tcn = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?{~}(^)[_]@#$,./&-*++="
    assert decode_tcn(tcn[a] + tcn[b]) == ["b7b8q"]
    with pytest.raises(GameUrlError):
        decode_tcn("abc")  # odd length
    with pytest.raises(GameUrlError):
        _pgn_from_moves(CHESSCOM_HEADERS, ["e2e5"])  # illegal → not understood


def _transport(routes: dict):
    def handler(request: httpx.Request):
        for prefix, response in routes.items():
            if str(request.url).startswith(prefix):
                return response() if callable(response) else response
        return httpx.Response(404, text="not found")
    return httpx.MockTransport(handler)


@pytest.mark.unit
def test_fetch_lichess_game():
    client = httpx.Client(transport=_transport({
        "https://lichess.org/game/export/kAdOQKeh": httpx.Response(200, text=LICHESS_PGN),
    }))
    out = fetch_game_by_url("https://lichess.org/kAdOQKeh/black", client=client)
    assert out["source"] == "lichess" and out["game_id"] == "kAdOQKeh"
    assert (out["white"], out["black"], out["result"]) == ("respects_55", "DrNykterstein", "0-1")
    assert out["white_elo"] == 2644 and out["eco"] == "B02" and out["opening"] == "Alekhine Defense"
    assert out["pgn"].startswith("[Event")
    assert out["date"] == "2026.04.08"


@pytest.mark.unit
def test_fetch_lichess_unknown_and_rate_limited():
    client = httpx.Client(transport=_transport({
        "https://lichess.org/game/export/aaaaaaaa": httpx.Response(404),
        "https://lichess.org/game/export/bbbbbbbb": httpx.Response(429),
    }))
    with pytest.raises(GameUrlError, match="private or wrong id"):
        fetch_game_by_url("https://lichess.org/aaaaaaaa", client=client)
    with pytest.raises(GameUrlError, match="rate limit"):
        fetch_game_by_url("https://lichess.org/bbbbbbbb", client=client)


@pytest.mark.unit
def test_fetch_chesscom_game_via_tcn():
    callback = {"game": {"id": 184239477800, "moveList": TCN_PREFIX, "pgnHeaders": CHESSCOM_HEADERS}, "players": {}}
    client = httpx.Client(transport=_transport({
        "https://www.chess.com/callback/live/game/184239477800": httpx.Response(200, json=callback),
    }))
    out = fetch_game_by_url("https://www.chess.com/game/live/184239477800", client=client)
    assert out["source"] == "chesscom" and out["white"] == "Hikaru" and out["black_elo"] == 3041
    assert "1. d4 d5 2. e3 Nf6" in out["pgn"]
    board = chess.Board()
    for mv in TCN_PREFIX_UCI:
        board.push_uci(mv)


@pytest.mark.unit
def test_fetch_chesscom_falls_back_to_archive_when_tcn_is_garbage():
    callback = {"game": {"id": 1, "moveList": "zzzz", "pgnHeaders": CHESSCOM_HEADERS}}
    archive = {"games": [
        {"url": "https://www.chess.com/game/live/2", "pgn": "[White \"x\"]\n\n1. e4 *"},
        {"url": "https://www.chess.com/game/live/1", "pgn": LICHESS_PGN.replace("respects_55", "Hikaru")},
    ]}
    client = httpx.Client(transport=_transport({
        "https://www.chess.com/callback/live/game/1": httpx.Response(200, json=callback),
        "https://api.chess.com/pub/player/hikaru/games/2026/09": httpx.Response(200, json=archive),
    }))
    out = fetch_game_by_url("https://www.chess.com/game/live/1", client=client)
    assert out["white"] == "Hikaru" and "1. e4 Nf6" in out["pgn"]


@pytest.mark.unit
def test_fetch_chesscom_unknown_game():
    client = httpx.Client(transport=_transport({
        "https://www.chess.com/callback/live/game/5": httpx.Response(200, json={"game": {"pgnHeaders": {}}}),
    }))
    with pytest.raises(GameUrlError, match="no game data"):
        fetch_game_by_url("https://www.chess.com/game/live/5", client=client)


@pytest.mark.unit
class TestImportUrlEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_returns_the_game(self):
        with patch("src.tools.game_url.fetch_game_by_url", return_value={"pgn": "1. e4 *", "white": "a", "black": "b"}):
            resp = self.client.post("/api/coach/import-url", headers={"X-User-Id": "u"},
                                    json={"url": "https://lichess.org/kAdOQKeh"})
        assert resp.status_code == 200 and resp.json()["white"] == "a"

    def test_bad_link_is_400_with_readable_message(self):
        resp = self.client.post("/api/coach/import-url", headers={"X-User-Id": "u"},
                                json={"url": "https://chesster.io/coach"})
        assert resp.status_code == 400
        assert "Lichess and Chess.com" in resp.json()["detail"]

    def test_upstream_failure_is_502(self):
        with patch("src.tools.game_url.fetch_game_by_url", side_effect=httpx.ConnectError("boom")):
            resp = self.client.post("/api/coach/import-url", headers={"X-User-Id": "u"},
                                    json={"url": "https://lichess.org/kAdOQKeh"})
        assert resp.status_code == 502

    def test_requires_user(self):
        resp = self.client.post("/api/coach/import-url", json={"url": "https://lichess.org/kAdOQKeh"})
        assert resp.status_code in (400, 401)


@pytest.mark.unit
def test_tool_handler_reports_errors_as_json():
    from src.tools.game_url import _handle_import_game_from_url

    out = json.loads(_handle_import_game_from_url({"url": "https://example.com/x"}))
    assert "error" in out
    with patch("src.tools.game_url.fetch_game_by_url", return_value={"pgn": "1. e4 *"}):
        out = json.loads(_handle_import_game_from_url({"url": "https://lichess.org/kAdOQKeh"}))
    assert out["pgn"] == "1. e4 *" and "load_pgn" in out["hint"]
