"""The relation checker's evaluation harness in --gate mode on the fixtures (plan 30.10 §5): the numbers of
tests/fixtures/relations/gates.json hold — the legacy baseline, and the relation checker flagging no true and no
not-checkable eval row and breaking no true claim of the triage answers."""
import json
import subprocess
import sys
import time
from pathlib import Path

H = Path(__file__).resolve().parents[2]
SCRIPT = H / "scripts" / "eval_relations.py"


def _run(*args):
    started = time.monotonic()
    res = subprocess.run([sys.executable, str(SCRIPT), "--gate", "--no-sample", *args], cwd=H, capture_output=True,
                         text=True, timeout=120)
    return res, time.monotonic() - started


def test_the_gate_holds_on_the_fixtures(tmp_path):
    out = tmp_path / "eval.json"
    res, seconds = _run("--json", str(out))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "GATE ok" in res.stdout
    assert seconds < 30, seconds
    m = json.loads(out.read_text())["metrics"]
    gates = json.loads((H / "tests" / "fixtures" / "relations" / "gates.json").read_text())
    for k in list(gates["min"]) + [k for k in gates["max"] if k not in ("corpus_relation_flags", "check_sentence_p99_ms")]:
        assert k in m, k  # every gated number is computed on the fixtures alone


def test_a_breach_fails_the_gate(tmp_path):
    gates = tmp_path / "gates.json"
    gates.write_text(json.dumps({"min": {"triage_union": 45}, "max": {"eval_true_legacy": 0}}))
    res, _ = _run("--gates", str(gates))
    assert res.returncode == 1
    assert "GATE FAIL" in res.stdout and "triage_union" in res.stdout and "eval_true_legacy" in res.stdout
