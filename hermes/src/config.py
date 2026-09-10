"""Configuration loader for Hermes Chess Coach."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "profiles" / "chess-coach"


def load_env(env_path: Path = None) -> None:
    """Load .env file from project root."""
    if env_path is None:
        env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


# Load .env before any module-level os.environ reads below. server.py's own
# load_env() call happens after `import src.config`, which is too late for the
# flags evaluated at import time (e.g. COACH_MEMORY_WRITER stayed False even
# with COACH_MEMORY_WRITER=1 in .env).
load_env()


def load_profile_config(config_path: Path = None) -> dict:
    """Load and return the chess coach profile config.yaml with env var substitution."""
    if config_path is None:
        config_path = PROFILE_DIR / "config.yaml"
    with open(config_path) as f:
        raw = f.read()
    # Substitute ${VAR} patterns with environment variables
    expanded = _expand_env_vars(raw)
    return yaml.safe_load(expanded)


def _expand_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} and $VAR_NAME patterns with env values."""
    import re
    def _replace(match):
        var_name = match.group(1) or match.group(2)
        return os.environ.get(var_name, match.group(0))
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', _replace, text)


def load_soul(soul_path: Path = None) -> str:
    """Load and return the SOUL.md coach persona content."""
    if soul_path is None:
        soul_path = PROFILE_DIR / "SOUL.md"
    return soul_path.read_text()


def get_port(config: dict = None) -> int:
    """Get the configured service port."""
    if config is None:
        config = load_profile_config()
    return int(config.get("port", 8642))


def get_model_config(config: dict = None) -> dict:
    """Get model routing configuration."""
    if config is None:
        config = load_profile_config()
    return {
        "default": config.get("model", {}).get("default", "google/gemini-2.5-flash"),
        "provider": config.get("model", {}).get("provider", "openrouter"),
        "tiers": config.get("model_tiers", {}),
    }


def get_api_key() -> str:
    """Get the HERMES_API_KEY for request authentication."""
    return os.environ.get("HERMES_API_KEY", "")


# Mastra CCP (chess-coach-protocol) analysis service. Hermes calls this HTTP
# endpoint to reuse Mastra's PositionPrompter for board analysis, falling back
# to the local Python port on any failure.
MASTRA_CCP_URL = os.environ.get(
    "MASTRA_CCP_URL", "http://localhost:3000/api/position-analysis"
)
# Short timeout (seconds) so a slow/unreachable Mastra never blocks a coach turn.
MASTRA_CCP_TIMEOUT = float(os.environ.get("MASTRA_CCP_TIMEOUT", "2.0"))


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment flag (1/true/yes/on -> True)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Coach input hygiene: NFKC-normalize inbound free-text user messages and strip
# zero-width/control chars (mirrors Mastra's UnicodeNormalizer). Default OFF so
# production behavior is byte-identical; enable with COACH_NORMALIZE_INPUT=true.
COACH_NORMALIZE_INPUT = _env_flag("COACH_NORMALIZE_INPUT", False)

# Semantic tool subsetting: select a query-relevant topK subset of chess tools
# per turn instead of sending all ~20 schemas. Default ON to shrink the per-turn
# token payload and cache-align the tool block; the always-present core set keeps
# board/engine tools available every turn. Disable without a deploy with
# COACH_TOOL_SUBSET=false. The topK (excluding the core set) is configurable.
COACH_TOOL_SUBSET = _env_flag("COACH_TOOL_SUBSET", True)
COACH_TOOL_SUBSET_TOPK = int(os.environ.get("COACH_TOOL_SUBSET_TOPK", "7"))

# Per-student memory writer (CL Phase 1): after each completed text-chat turn,
# a cheap off-request-path LLM call reflects on the turn and accumulates durable
# student facts (weaknesses/goals/style) into user_profiles, plus a Reflexion-
# lite failure-memory row when the engine refutes a coach move. Default OFF so
# behavior is byte-identical to today; enable with COACH_MEMORY_WRITER=1.
COACH_MEMORY_WRITER = _env_flag("COACH_MEMORY_WRITER", False)

# Game retrieval digest (CL Phase 1, Slice 2): inject a compact "Recent games"
# block into the system prompt from the student's own reviewed games
# (coach_game_insights). Context injection only — never writes anywhere. Default
# OFF so behavior is byte-identical to today; enable with COACH_GAME_RAG=1.
COACH_GAME_RAG = _env_flag("COACH_GAME_RAG", False)

# Coaching playbook (CL Phase 2, Slice 1): inject a compact "Coaching playbook
# (engine-verified)" block into the system prompt from an evolving store of
# distilled, engine-verified coaching patterns (coach_playbook). Context
# injection only on the turn path — the Generator/Reflector/Curator curation
# loop runs OFFLINE via scripts/build_playbook.py, never inline in a chat turn.
# Default OFF so behavior is byte-identical to today; enable with COACH_PLAYBOOK=1.
COACH_PLAYBOOK = _env_flag("COACH_PLAYBOOK", False)

# Automatic curriculum (CL Phase 2, Slice 2): inject a compact "Training focus
# (engine-measured)" block into the system prompt from a per-student curriculum
# (coach_curriculum) keyed on engine-measured learnability — the themes where the
# engine says the student blunders most, at a difficulty near their ~50% solve-
# rate frontier. Context injection only on the turn path — the curriculum is
# computed OFFLINE via scripts/build_curriculum.py (deterministic aggregation, no
# LLM calls), never inline in a chat turn. Default OFF so behavior is byte-
# identical to today; enable with COACH_CURRICULUM=1.
COACH_CURRICULUM = _env_flag("COACH_CURRICULUM", False)

# Best-of-N with engine selection (CL Phase 2, Slice 3): for a position-anchored
# coach turn, generate several candidate explanations, let the ENGINE rank the
# correctness channel (via engine_grounded), then a cheap-tier LLM judge picks
# the clearest among the engine-PASSING candidates only. The engine gatekeeps
# correctness; the judge can never promote an engine-failing candidate. Applies
# only to analysis turns with a known FEN; the winner is streamed through the
# existing SSE machinery so the client contract is unchanged. Default OFF so
# behavior is byte-identical to today (same single agent.chat call, same
# streaming, zero extra model/engine calls); enable with COACH_BESTOFN=1.
#   COACH_BESTOFN_N         — candidates to generate (default 2, hard max 4).
#   COACH_BESTOFN_BUDGET_MS — wall-clock budget for the whole pipeline (default
#                             4500ms; candidates generate concurrently so this
#                             fits under 5s); on overrun the best-scored-so-far
#                             (or first candidate) is returned so the user always
#                             gets a reply.
COACH_BESTOFN = _env_flag("COACH_BESTOFN", False)
COACH_BESTOFN_N = int(os.environ.get("COACH_BESTOFN_N", "2"))
COACH_BESTOFN_BUDGET_MS = int(os.environ.get("COACH_BESTOFN_BUDGET_MS", "4500"))

# Self-hosted engine MCP: connect to external MCP servers configured in
# ~/.hermes/config.yaml (mcp_servers) at startup and expose their tools to the
# coach under `mcp-*` toolsets. Default OFF so the coach runs on native
# in-process tools only and behavior is byte-identical; enable with
# COACH_MCP_ENABLED=true (and configure mcp_servers). See engine-mcp/.
COACH_MCP_ENABLED = _env_flag("COACH_MCP_ENABLED", False)
