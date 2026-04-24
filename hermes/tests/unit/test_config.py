"""Unit tests for chess coach configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

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
