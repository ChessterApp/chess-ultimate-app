"""Test that all chess tool schemas use flat format (no OpenAI envelope wrapper).

The Hermes registry wraps each schema in {"type": "function", "function": ...}
at registration time. If a tool schema already includes that wrapper, the LLM
receives a double-nested definition and cannot call the tool.

Every SCHEMA dict in hermes/src/tools/*.py must be a flat dict with:
  - "name": str
  - "parameters": dict
  - "description": str  (optional but expected)
And must NOT contain "type": "function" or "function": {...} at top level.
"""

import importlib
import pkgutil
from pathlib import Path

import pytest


def _collect_schemas():
    """Import all tool modules and collect every *_SCHEMA constant."""
    tools_dir = Path(__file__).resolve().parent.parent.parent / "src" / "tools"
    schemas = []

    for finder, module_name, is_pkg in pkgutil.iter_modules([str(tools_dir)]):
        if module_name.startswith("_"):
            continue
        mod = importlib.import_module(f"src.tools.{module_name}")
        for attr_name in dir(mod):
            if attr_name.endswith("_SCHEMA"):
                schema = getattr(mod, attr_name)
                if isinstance(schema, dict):
                    schemas.append((module_name, attr_name, schema))

    return schemas


ALL_SCHEMAS = _collect_schemas()


@pytest.mark.parametrize(
    "module_name,schema_name,schema",
    ALL_SCHEMAS,
    ids=[f"{m}.{s}" for m, s, _ in ALL_SCHEMAS],
)
class TestToolSchemaFormat:
    def test_no_openai_envelope(self, module_name, schema_name, schema):
        """Schema must not contain the OpenAI function wrapper."""
        assert "type" not in schema or schema.get("type") != "function", (
            f"{module_name}.{schema_name} is wrapped in OpenAI envelope "
            f'(has "type": "function"). Remove the wrapper — the registry adds it.'
        )
        assert "function" not in schema, (
            f"{module_name}.{schema_name} has a top-level 'function' key. "
            f"Remove the envelope wrapper — the registry adds it."
        )

    def test_has_required_keys(self, module_name, schema_name, schema):
        """Schema must have 'name' and 'parameters' at top level."""
        assert "name" in schema, (
            f"{module_name}.{schema_name} is missing 'name' key."
        )
        assert "parameters" in schema, (
            f"{module_name}.{schema_name} is missing 'parameters' key."
        )

    def test_name_is_string(self, module_name, schema_name, schema):
        """Schema 'name' must be a non-empty string."""
        assert isinstance(schema["name"], str) and schema["name"], (
            f"{module_name}.{schema_name} 'name' must be a non-empty string."
        )

    def test_parameters_is_object_type(self, module_name, schema_name, schema):
        """Schema 'parameters' must have type 'object'."""
        params = schema["parameters"]
        assert isinstance(params, dict), (
            f"{module_name}.{schema_name} 'parameters' must be a dict."
        )
        assert params.get("type") == "object", (
            f"{module_name}.{schema_name} 'parameters.type' must be 'object'."
        )


def test_all_schemas_discovered():
    """Ensure we found a reasonable number of schemas (guards against broken discovery)."""
    assert len(ALL_SCHEMAS) >= 20, (
        f"Expected at least 20 tool schemas, found {len(ALL_SCHEMAS)}. "
        "Check that tool modules are importable."
    )
