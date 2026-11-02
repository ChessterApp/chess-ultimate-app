"""One stub for both of the engine stage's looks (K3 02.11).

The engine stage's verdicts (src/hypothetical.verify_recommendation, verify_line, src/line_verdict) read a search to a
fixed depth (src/hypothetical._engine_lines); the prompt's notes and the /learn tutor's main_rules() still read the
timed look (analyze_timed). A test that stubs the engine with an analyze_timed stand-in stubs both with it here.
"""


def stub_engine(monkeypatch, fake):
    """*fake*(fen, movetime_ms, multipv=1, min_depth=10, …) → an analysis dict: analyze_timed and the fixed-depth look."""
    monkeypatch.setattr("src.hypothetical.analyze_timed", fake)

    def _lines(fen, multipv, movetime_ms, depth, deadline=None):
        res = fake(fen, movetime_ms or 300, multipv=multipv)
        if not isinstance(res, dict) or "error" in res or not res.get("lines"):
            return None
        for line in res["lines"]:
            if depth:
                line["depth"] = max(int(line.get("depth") or 0), depth)
        return res

    monkeypatch.setattr("src.hypothetical._engine_lines", _lines)
