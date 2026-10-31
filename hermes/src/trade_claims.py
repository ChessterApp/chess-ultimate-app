"""Trades told about a recorded game, judged against its score (plan 31.10, P6 owns the body; WP-0 stub).

«там белые отдали ферзя за ладью» (x-wc2021-g6) about a game in ``ctx.line_records``: true only if some exchange of
the game (src/game_record.exchanges) fits it exactly; otherwise the issue names the nearest real exchange («26.Qxc8
Rxc8 27.Rxc8 — White gave the queen for two rooks»). Detector name ``trades`` (src/config.detector_mode).
"""
from __future__ import annotations

from typing import Any


def trade_issues(sentence: str, ctx: Any) -> list[str]:
    """The issues of *sentence* (the answer check's normalised text) about trades in a recorded game; [] for now."""
    return []
