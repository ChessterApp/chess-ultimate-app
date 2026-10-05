"""The site's engine server behind ENGINE_API_URL (src/tools/stockfish.py, 2026-10-05)."""

import pytest

from src.tools import stockfish


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.mark.unit
def test_the_servers_answer_takes_the_local_shape(monkeypatch):
    import httpx

    fen = "rnbqkbnr/pp2pp1p/6p1/2p3NQ/4p3/8/PPPP1PPP/RNB1KB1R b KQkq - 0 5"  # Black to move
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.update(url=url, body=json, headers=headers, timeout=timeout)
        return _Resp({"depth": 14, "evaluation": {"type": "cp", "value": -250}, "bestMove": "g6h5", "pv": ["gxh5", "Nxh7"],
                      "lines": [{"evaluation": {"type": "cp", "value": -250}, "bestMove": "g6h5", "pv": ["gxh5", "Nxh7"]},
                                {"evaluation": {"type": "mate", "value": 3}, "bestMove": "d8a5", "pv": ["Qa5+"]}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "https://engine.chesster.io")
    monkeypatch.setattr(stockfish, "ENGINE_API_TOKEN", "secret")
    out = stockfish.analyze_position(fen, depth=16, multipv=2, movetime_ms=300)
    assert out["remote"] is True and calls["url"] == "https://engine.chesster.io/analyze"
    assert calls["headers"] == {"X-Engine-Token": "secret"} and calls["body"] == {"fen": fen, "multipv": 2, "movetime": 0.3}
    first, second = out["lines"]
    # -250 cp from White's side with Black to move → +2.5 for the side to move; SAN → UCI
    assert first["score"] == 2.5 and first["pv"] == "g6h5 g5h7" and first["depth"] == 14
    # mate in 3 for White, Black to move → -3 for the side to move
    assert second["mate_in"] == -3 and second["score"] == -10000 and second["pv"] == "d8a5"


@pytest.mark.unit
def test_a_failing_server_falls_back_to_the_local_engine(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "https://engine.chesster.io")
    monkeypatch.setattr(stockfish, "_analyze_position", lambda *a, **k: {"lines": [{"multipv": 1, "score": 0.1, "pv": "e2e4"}]})
    out = stockfish.analyze_position("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", depth=10, multipv=1)
    assert out["lines"][0]["pv"] == "e2e4" and "remote" not in out


@pytest.mark.unit
def test_without_the_variable_the_local_engine_is_used(monkeypatch):
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    monkeypatch.setattr(stockfish, "_analyze_position", lambda *a, **k: {"lines": [{"multipv": 1, "score": 0.0, "pv": "d2d4"}]})
    assert stockfish.analyze_position("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")["lines"][0]["pv"] == "d2d4"
