#!/usr/bin/env python3
"""Hermes's request contract: the body fields each POST/PUT/PATCH endpoint reads.

For every route in hermes/src the pydantic body model and its field names (by the JSON key
pydantic validates, so an alias wins), or null when the handler reads a raw dict. Read by AST,
never imported: server.py pulls in the engine, the LLM SDKs and Supabase.

The output is what the site's seam test checks its proxies against
(frontend/src/app/api/coach/__tests__/seam.contract.test.ts, 28.10): engine-note's proxy kept
only `fen` for two weeks and no test saw it. tests/unit/test_hermes_contract_fresh.py fails when
the committed JSON lags a model change.

    hermes/.venv/bin/python hermes/scripts/hermes_contract.py           # rewrite the JSON
    hermes/.venv/bin/python hermes/scripts/hermes_contract.py --check   # exit 1 if it is stale

Needs Hermes's Python (3.12+): src uses PEP 701 f-strings an older ast cannot parse.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

HERMES = Path(__file__).resolve().parents[1]
SRC = HERMES / "src"
OUT = HERMES.parent / "frontend" / "src" / "app" / "api" / "coach" / "__tests__" / "hermes_contract.json"
METHODS = ("post", "put", "patch")


def _name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _json_key(stmt: ast.AnnAssign) -> str | None:
    """The key pydantic reads for a class-body annotation, or None when it is not a field."""
    key = stmt.target.id if isinstance(stmt.target, ast.Name) else None
    if not key or key.startswith("_") or key == "model_config":
        return None
    ann = stmt.annotation
    if _name(ann.value if isinstance(ann, ast.Subscript) else ann) == "ClassVar":
        return None
    if isinstance(stmt.value, ast.Call) and _name(stmt.value.func) == "Field":
        for kw in stmt.value.keywords:
            if kw.arg in ("validation_alias", "alias") and isinstance(kw.value, ast.Constant):
                return kw.value.value
    return key


def _models(trees: list[ast.Module]) -> dict[str, list[str]]:
    """Every BaseModel subclass (also through other models) with its fields, bases' first."""
    classes = {n.name: n for t in trees for n in ast.walk(t) if isinstance(n, ast.ClassDef)}
    done: dict[str, list[str] | None] = {}

    def fields(name: str) -> list[str] | None:
        if name in done:
            return done[name]
        done[name] = None  # a cycle or a non-model base resolves to "not a model"
        cls = classes.get(name)
        if cls is None:
            return None
        inherited: list[str] = []
        is_model = False
        for base in cls.bases:
            b = _name(base)
            if b == "BaseModel":
                is_model = True
            elif b and (bf := fields(b)) is not None:
                is_model = True
                inherited += [f for f in bf if f not in inherited]
        if not is_model:
            return None
        own = [k for s in cls.body if isinstance(s, ast.AnnAssign) and (k := _json_key(s))]
        done[name] = inherited + [k for k in own if k not in inherited]
        return done[name]

    return {name: f for name in classes if (f := fields(name)) is not None}


def _body_model(fn: ast.FunctionDef | ast.AsyncFunctionDef, models: dict) -> str | None:
    found = []
    for arg in fn.args.args + fn.args.kwonlyargs:
        ann = arg.annotation
        # Optional[Model] / Annotated[Model, Body()] carry the model as their first type argument.
        while isinstance(ann, ast.Subscript):
            inner = ann.slice
            ann = inner.elts[0] if isinstance(inner, ast.Tuple) else inner
        if (n := _name(ann)) in models:
            found.append(n)
    if len(found) > 1:
        sys.exit(f"hermes_contract: {fn.name} takes two body models {found}; teach the script which is the body")
    return found[0] if found else None


def _router_prefix(tree: ast.Module, router: str) -> str:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(_name(t) == router for t in node.targets)
            and isinstance(node.value, ast.Call)
            and _name(node.value.func) == "APIRouter"
        ):
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return ""


def build_contract(paths: list[Path] | None = None) -> dict:
    """{"METHOD /path": {"model": name | None, "fields": [...] | None}} for hermes/src (or `paths`)."""
    if sys.version_info < (3, 12):
        sys.exit("hermes_contract: run it with Hermes's Python 3.12+ (hermes/.venv/bin/python)")
    files = sorted(paths if paths is not None else SRC.rglob("*.py"))
    trees = [ast.parse(Path(p).read_text(encoding="utf-8"), filename=str(p)) for p in files]
    for t in trees:
        for node in ast.walk(t):
            # A mount prefix lives in another module than the routes: refuse rather than write wrong paths.
            if isinstance(node, ast.Call) and _name(node.func) == "include_router" and any(
                kw.arg == "prefix" for kw in node.keywords
            ):
                sys.exit("hermes_contract: include_router(prefix=...) is not supported; extend the script")
    models = _models(trees)
    routes: dict[str, dict] = {}
    for t in trees:
        for fn in ast.walk(t):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in fn.decorator_list:
                if not (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr in METHODS
                    and d.args
                    and isinstance(d.args[0], ast.Constant)
                    and isinstance(d.args[0].value, str)
                ):
                    continue
                prefix = _router_prefix(t, _name(d.func.value) or "")
                key = f"{d.func.attr.upper()} {prefix}{d.args[0].value}"
                if key in routes:
                    sys.exit(f"hermes_contract: {key} is declared twice")
                model = _body_model(fn, models)
                routes[key] = {"model": model, "fields": models[model] if model else None}
    return dict(sorted(routes.items()))


def render(contract: dict) -> str:
    return json.dumps(contract, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when the committed JSON is stale")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    text = render(build_contract())
    if a.check:
        current = a.out.read_text(encoding="utf-8") if a.out.is_file() else ""
        if current != text:
            print(f"{a.out} is stale: run hermes/.venv/bin/python hermes/scripts/hermes_contract.py", file=sys.stderr)
            return 1
        return 0
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out} ({len(json.loads(text))} routes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
