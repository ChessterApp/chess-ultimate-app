"""O1 — deterministic stratified train/holdout split of the golden set.

Loads ``golden_v1.jsonl`` and splits it into a ~70% train / ~30% holdout set,
stratified by ``cohort`` × ``message_type`` so every (cohort, type) cell keeps
its proportion in both splits. The split is:

  * **deterministic** — same seed ⇒ byte-identical splits across runs/machines;
  * **stable at import** — no RNG is touched at import time; the seed is a
    parameter (CLI arg, default 13) and the RNG is created inside the function.

The holdout is scored ONCE for the final winner (see the optimizer) — it is
never used for candidate selection.
"""

import json
import random
from collections import defaultdict

DEFAULT_SEED = 13
DEFAULT_TRAIN_FRAC = 0.70


def load_dataset(path: str) -> list[dict]:
    """Load a golden ``.jsonl`` dataset into a list of case dicts."""
    cases: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _stratum_key(case: dict) -> tuple[str, str]:
    """The (cohort, message_type) cell a case belongs to."""
    return (str(case.get("cohort", "")), str(case.get("message_type", "")))


def stratify(cases: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group cases by their (cohort, message_type) stratum."""
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in cases:
        strata[_stratum_key(c)].append(c)
    return strata


def split_dataset(
    cases: list[dict],
    seed: int = DEFAULT_SEED,
    train_frac: float = DEFAULT_TRAIN_FRAC,
) -> tuple[list[dict], list[dict]]:
    """Deterministic stratified split into (train, holdout).

    Within each stratum the cases are sorted by ``id`` (stable canonical order),
    shuffled with a single seeded RNG, then the first ``round(n * train_frac)``
    go to train and the rest to holdout. Strata are processed in sorted key order
    so the whole split is reproducible for a given ``seed``.
    """
    rng = random.Random(seed)
    strata = stratify(cases)
    train: list[dict] = []
    holdout: list[dict] = []
    for key in sorted(strata):
        items = sorted(strata[key], key=lambda c: str(c.get("id", "")))
        rng.shuffle(items)
        n_train = round(len(items) * train_frac)
        train.extend(items[:n_train])
        holdout.extend(items[n_train:])
    train.sort(key=lambda c: str(c.get("id", "")))
    holdout.sort(key=lambda c: str(c.get("id", "")))
    return train, holdout


def split_summary(train: list[dict], holdout: list[dict]) -> dict:
    """Per-stratum counts for the plan/report printout."""
    def counts(cases: list[dict]) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for c in cases:
            out["|".join(_stratum_key(c))] += 1
        return dict(sorted(out.items()))

    return {
        "n_train": len(train),
        "n_holdout": len(holdout),
        "train_by_stratum": counts(train),
        "holdout_by_stratum": counts(holdout),
    }
