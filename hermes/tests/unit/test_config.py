"""Unit tests for chess coach configuration loading."""

import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import src.config as config
from src.config import (
    PROFILE_DIR,
    PROJECT_ROOT,
    _expand_env_vars,
    get_api_key,
    get_model_config,
    get_port,
    load_profile_config,
    load_soul,
)


@pytest.fixture
def reload_config():
    """Reload src.config under a controlled environment, then restore baseline.

    Module-level flags are resolved from os.environ at import, so exercising the
    default vs an env override requires reloading the module.
    """
    def _reload(**env):
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return importlib.reload(config)

    saved = {k: os.environ.get(k) for k in ("COACH_TOOL_SUBSET", "COACH_TOOL_SUBSET_TOPK")}
    yield _reload
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(config)


@pytest.mark.unit
def test_coach_tool_subset_defaults_on(reload_config):
    """With no env override the tool-subset flag is ON and TOPK is 7."""
    cfg = reload_config(COACH_TOOL_SUBSET=None, COACH_TOOL_SUBSET_TOPK=None)
    assert cfg.COACH_TOOL_SUBSET is True
    assert cfg.COACH_TOOL_SUBSET_TOPK == 7


@pytest.mark.unit
def test_coach_tool_subset_env_override_disables(reload_config):
    """The env override still turns the flag off without a deploy."""
    cfg = reload_config(COACH_TOOL_SUBSET="false")
    assert cfg.COACH_TOOL_SUBSET is False


@pytest.mark.unit
def test_coach_tool_subset_topk_env_override(reload_config):
    """TOPK is configurable via the environment."""
    cfg = reload_config(COACH_TOOL_SUBSET_TOPK="3")
    assert cfg.COACH_TOOL_SUBSET_TOPK == 3


@pytest.mark.unit
def test_config_loads_from_yaml():
    """config.yaml loads and parses correctly."""
    config = load_profile_config()
    assert isinstance(config, dict)
    assert "model" in config
    assert "port" in config


@pytest.mark.unit
def test_config_env_substitution():
    """Environment variable substitution works in config values."""
    with patch.dict(os.environ, {"TEST_VAR_XYZ": "replaced_value"}):
        result = _expand_env_vars("key: ${TEST_VAR_XYZ}")
        assert "replaced_value" in result

    # Unset vars should stay as-is
    result = _expand_env_vars("key: ${NONEXISTENT_VAR_12345}")
    assert "${NONEXISTENT_VAR_12345}" in result


@pytest.mark.unit
def test_coach_persona_loads():
    """SOUL.md loads and contains chess coach content."""
    soul = load_soul()
    assert isinstance(soul, str)
    assert len(soul) > 100
    assert "Chess Coach" in soul
    assert "Coaching Method" in soul
    assert "Socratic" in soul


@pytest.mark.unit
def test_model_routing_config():
    """Model routing config has expected tiers and defaults."""
    config = load_profile_config()
    model_config = get_model_config(config)
    assert model_config["default"] == "google/gemini-2.5-flash"
    assert model_config["provider"] == "openrouter"
    assert "tiers" in model_config
    tiers = model_config["tiers"]
    assert "fast" in tiers
    assert "analysis" in tiers
    assert "deep" in tiers


@pytest.mark.unit
def test_port_config():
    """Port is configured to 8642."""
    config = load_profile_config()
    port = get_port(config)
    assert port == 8642
