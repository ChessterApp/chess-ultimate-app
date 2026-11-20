"""Tester 20.11: a Chess960 game by its Lichess link — the board kept the earlier game, the coach reviewed this one.
Another variant than chess is refused with «variant:<name>» (src/tools/game_url.py); the page says it plainly."""

import pytest

from src.tools import game_url


def _fetch(monkeypatch, headers):
    pgn = "".join(f'[{k} "{v}"]\n' for k, v in headers.items()) + "\n1. e4 e5 2. Nf3 Nc6 1-0"
    monkeypatch.setattr(game_url, "_lichess_pgn", lambda gid, client: pgn)
    return game_url.fetch_game_by_url("https://lichess.org/abcdefgh", client=object())


@pytest.mark.unit
def test_chess960_is_refused_by_its_name(monkeypatch):
    with pytest.raises(game_url.GameUrlError, match=r"^variant:Chess960$"):
        _fetch(monkeypatch, {"White": "A", "Black": "B", "Variant": "Chess960"})


@pytest.mark.unit
@pytest.mark.parametrize("variant", [None, "Standard", "From Position"])
def test_standard_games_load(monkeypatch, variant):
    headers = {"White": "A", "Black": "B"}
    if variant:
        headers["Variant"] = variant
    assert _fetch(monkeypatch, headers)["white"] == "A"
