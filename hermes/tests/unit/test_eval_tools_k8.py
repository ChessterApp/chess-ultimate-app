"""K8 02.11 (verify1102 §6.7): the measuring tools judge a candidate on what it does, not on the noise of one run.

eval_prevent (e): a row is a "new cut" only when the base misses it in most of its runs — main's engine stage misses
trap-legal about one run in three, and one such miss failed the gate. The recorded baseline joins the vote."""
import importlib
import subprocess
import sys
from pathlib import Path

H = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(H / "scripts"))
ev = importlib.import_module("eval_prevent")


def _table(*rows):
    return {"table": [{"src": s, "id": i, "kind": k, "quote": q, "base": b, "branch": True} for s, i, k, q, b in rows]}


def test_a_flaky_miss_of_the_paired_base_run_is_not_a_new_cut():
    paired = _table(("sets", "fork-x", "wrong_attack_or_defence", "конь бьёт  ладью", False))
    key = ev._row_key(paired["table"][0])
    recorded = {"runs": 3, "rows": {key: 2}}
    votes = ev.base_votes([paired], recorded)
    assert votes[key] == (2, 4) and ev.base_cut(votes, key)


def test_a_row_the_base_cuts_once_in_three_is_still_new():
    paired = _table(("games", "st9#1", "wrong_number", "на две пешки больше", False))
    key = ev._row_key(paired["table"][0])
    votes = ev.base_votes([paired], {"runs": 3, "rows": {key: 1}})
    assert votes[key] == (1, 4) and not ev.base_cut(votes, key)


def test_more_base_runs_vote_by_majority_and_rows_differ_by_their_quote():
    rows = lambda b1, b2: _table(("sets", "op-a", "wrong_eval_or_line", "первая фраза", b1),  # noqa: E731
                                 ("sets", "op-a", "wrong_eval_or_line", "вторая фраза", b2))
    runs = [rows(False, True), rows(True, True), rows(True, False)]
    votes = ev.base_votes(runs, None)
    k1, k2 = (ev._row_key(t) for t in runs[0]["table"])
    assert k1 != k2
    assert votes[k1] == (2, 3) and ev.base_cut(votes, k1)
    assert votes[k2] == (2, 3) and ev.base_cut(votes, k2)
    assert not ev.base_cut(ev.base_votes([rows(False, False)], None), k1)


def test_the_recorded_baseline_round_trips(tmp_path):
    runs = [_table(("sets", "x", "other", "q", b)) for b in (True, False, True)]
    rec = ev.record_base_caught(runs, "02bb40d0")
    assert rec["runs"] == 3 and list(rec["rows"].values()) == [2] and rec["tree"] == "02bb40d0"
    assert ev.base_cut(ev.base_votes([], rec), next(iter(rec["rows"])))


def test_the_committed_main_baseline_counts_trap_legal_as_mains():
    import json

    rec = json.loads((H / "tests" / "fixtures" / "prevent" / "main_caught.json").read_text())
    assert rec["runs"] == 3 and rec["tree"] == "02bb40d0"
    trap = {k: v for k, v in rec["rows"].items() if k.startswith("sets/trap-legal/")}
    assert trap and all(v == 2 for v in trap.values())


def test_the_real_path_and_the_latency_repeats_are_documented_in_the_cli():
    out = subprocess.run([sys.executable, str(H / "scripts" / "eval_relations.py"), "--help"], cwd=H, capture_output=True,
                         text=True, timeout=120).stdout
    assert "replay1031" in out and "--latency-repeats" in out
