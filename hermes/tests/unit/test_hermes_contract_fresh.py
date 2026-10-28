"""The site's seam contract (hermes_contract.json) matches Hermes's request models.

The site test frontend/src/app/api/coach/__tests__/seam.contract.test.ts checks that every
field the page sends and Hermes reads gets through the site's proxy. It reads Hermes's side
from a committed JSON; this test fails when a request model changes and the JSON was not
regenerated (28.10: engine-note lost session_id in the proxy and no test saw it).
"""

import importlib.util
import json
import textwrap
from pathlib import Path

import pytest

HERMES = Path(__file__).resolve().parents[2]
REPO = HERMES.parent
SCRIPT = HERMES / "scripts" / "hermes_contract.py"
CONTRACT = REPO / "frontend" / "src" / "app" / "api" / "coach" / "__tests__" / "hermes_contract.json"
REGEN = "hermes/.venv/bin/python hermes/scripts/hermes_contract.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("hermes_contract", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
class TestHermesContractFresh:
    def test_committed_json_matches_request_models(self):
        if not (REPO / "frontend").is_dir():
            pytest.skip("hermes-only checkout: no site to hold the contract")
        assert CONTRACT.is_file(), f"missing {CONTRACT.relative_to(REPO)}; run {REGEN}"
        committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
        fresh = _load_script().build_contract()
        assert committed == fresh, f"hermes_contract.json is stale; run {REGEN} and commit it"

    def test_the_seam_endpoints_are_in_the_contract(self):
        # The endpoints whose proxies once dropped a field: if the extractor stops seeing them, the site test goes blind.
        fresh = _load_script().build_contract()
        assert fresh["POST /api/coach/voice/engine-note"]["fields"] == ["fen", "session_id"]
        assert "pgn" in fresh["POST /api/coach/voice/idea"]["fields"]
        assert fresh["POST /api/coach/tool/{name}"]["model"] == "ToolDispatchRequest"
        assert fresh["POST /api/coach/sessions/{session_id}/game/{board_id}/resign"] == {"model": None, "fields": None}


@pytest.mark.unit
class TestExtractor:
    """The AST reader on small sources: what a body carries is what pydantic validates."""

    def _contract(self, tmp_path, src):
        f = tmp_path / "mod.py"
        f.write_text(textwrap.dedent(src), encoding="utf-8")
        return _load_script().build_contract([f])

    def test_aliases_inheritance_and_non_fields(self, tmp_path):
        out = self._contract(tmp_path, """
            from typing import ClassVar, Optional
            from fastapi import APIRouter
            from pydantic import BaseModel, Field
            router = APIRouter(prefix="/api/x")
            class Base(BaseModel):
                fen: str
                model_config = {"extra": "ignore"}
            class Req(Base):
                _private: int = 0
                LIMIT: ClassVar[int] = 3
                from_: str = Field(alias="from")
                pgn: Optional[str] = None
            @router.post("/y/{name}")
            async def y(name: str, body: Optional[Req] = None):
                pass
            @router.get("/z")
            async def z():
                pass
        """)
        assert out == {"POST /api/x/y/{name}": {"model": "Req", "fields": ["fen", "from", "pgn"]}}

    def test_unknown_router_prefix_fails_loudly(self, tmp_path):
        with pytest.raises(SystemExit):
            self._contract(tmp_path, """
                app.include_router(r, prefix="/api")
            """)


def test_a_closed_data_directory_is_treated_as_absent(tmp_path, monkeypatch):
    """28.10, CI: /root exists but is closed on the runner; is_dir()/is_file() raised PermissionError there."""
    from pathlib import Path

    from src import openings_book, puzzle_db

    def closed(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "is_dir", closed)
    monkeypatch.setattr(Path, "is_file", closed)
    assert openings_book._readable_dir("/root/chess-app/backend/data/openings") is False
    assert puzzle_db.db_available("/root/hermes-chess/data/puzzles.db") is False
