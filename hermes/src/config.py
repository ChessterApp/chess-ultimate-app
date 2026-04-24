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
