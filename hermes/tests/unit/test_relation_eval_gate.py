"""The relation checker's evaluation harness in --gate mode on the fixtures (plan 30.10 §5): the numbers of
tests/fixtures/relations/gates.json hold — the legacy baseline, and the relation checker flagging no true and no
not-checkable eval row and breaking no true claim of the triage answers.

The functional bounds are deterministic and hold exactly. The latency bound is a property of the machine as much as of
the code (verify1102 §4: p99 0.974 ms against 1.0 alone, a failure inside validate.sh, which runs the corpora next to
pytest), so it is judged on the harness's median of three timing passes, with headroom for a shared machine, and not
judged at all on a machine with more runnable processes than cores — there a p99 measures the queue, not the code."""
import json
import os
import resource
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

H = Path(__file__).resolve().parents[2]
SCRIPT = H / "scripts" / "eval_relations.py"
GATES = json.loads((H / "tests" / "fixtures" / "relations" / "gates.json").read_text())
LATENCY = ("relation_p99_ms", "check_sentence_p99_ms", "relation_p99_corpus_ms")
CORPUS_ONLY = ("corpus_relation_flags", "corpus_sentences", "check_sentence_p99_ms", "relation_p99_corpus_ms")
HEADROOM = 2.0  # the latency bound is the integrator's, measured alone; pytest shares the machine with other work
REPEATS = 3


def _run(*args):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    res = subprocess.run([sys.executable, str(SCRIPT), "--gate", "--no-sample", *args], cwd=H, capture_output=True,
                         text=True, timeout=600)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return res, (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)


@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("eval") / "eval.json"
    res, cpu_seconds = _run("--latency-repeats", str(REPEATS), "--json", str(out))
    return res, cpu_seconds, json.loads(out.read_text())


def test_the_gate_holds_on_the_fixtures(fixture_run):
    res, _, report = fixture_run
    m = report["metrics"]
    for k in [k for k in list(GATES["min"]) + list(GATES["max"]) if k not in CORPUS_ONLY]:
        assert k in m, k  # every gated number is computed on the fixtures alone
    bad = [f"{k} {m[k]} < {v}" for k, v in GATES["min"].items() if k in m and k not in LATENCY and m[k] < v]
    bad += [f"{k} {m[k]} > {v}" for k, v in GATES["max"].items() if k in m and k not in LATENCY and m[k] > v]
    assert not bad, bad
    # the harness's own verdict differs from the one above only by the latency bound
    if res.returncode != 0:
        assert "GATE FAIL" in res.stdout, res.stdout[-2000:] + res.stderr[-2000:]
        fails = res.stdout.split("GATE FAIL:", 1)[1].splitlines()[0]
        assert all(part.strip().split(" ")[0] in LATENCY for part in fails.split(";")), fails


def test_the_relation_latency_holds(fixture_run):
    _, cpu_seconds, report = fixture_run
    lat = report["latency"]
    assert lat["passes"] == REPEATS and len(set(lat["calls"])) == 1, lat  # every pass times the same calls
    assert cpu_seconds < 25 * REPEATS, cpu_seconds  # the harness stays cheap (CPU, not the wall clock of a busy machine)
    load = os.getloadavg()[0] / (os.cpu_count() or 1)
    bound = GATES["max"]["relation_p99_ms"] * HEADROOM
    if load > 1.0:
        warnings.warn(f"relation latency not judged: load {load:.1f} a core; median p99 {lat['p99_wall_median']} ms "
                      f"(passes {lat['p99_wall']}, cpu {lat['p99_cpu']})")
        return
    assert lat["p99_wall_median"] <= bound, lat


def test_a_breach_fails_the_gate(tmp_path):
    gates = tmp_path / "gates.json"
    gates.write_text(json.dumps({"min": {"triage_union": 45}, "max": {"eval_true_legacy": 0}}))
    res, _ = _run("--latency-repeats", "1", "--gates", str(gates))
    assert res.returncode == 1
    assert "GATE FAIL" in res.stdout and "triage_union" in res.stdout and "eval_true_legacy" in res.stdout
