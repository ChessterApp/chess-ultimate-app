"""Unit tests for prompt versioning (src.prompt_builder.get_prompt_version)."""

from unittest.mock import patch

import pytest

from src import prompt_builder as pb


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the module-level version cache around each test."""
    pb._prompt_version_cache = None
    pb._prompt_version_mtime = None
    yield
    pb._prompt_version_cache = None
    pb._prompt_version_mtime = None


@pytest.mark.unit
class TestPromptVersion:
    def test_version_is_10_hex_chars(self):
        v = pb.get_prompt_version()
        assert isinstance(v, str)
        assert len(v) == 10
        int(v, 16)  # valid hex

    def test_version_stable_across_calls(self):
        assert pb.get_prompt_version() == pb.get_prompt_version()

    def test_version_changes_with_template_constant(self):
        v1 = pb.get_prompt_version()
        pb._prompt_version_cache = None
        pb._prompt_version_mtime = None
        with patch.object(pb, "PROMPT_TEMPLATE_VERSION", "2"):
            v2 = pb.get_prompt_version()
        assert v1 != v2

    def test_version_changes_with_soul_content(self):
        a = pb._compute_prompt_version("SOUL A")
        b = pb._compute_prompt_version("SOUL B")
        assert a != b
        assert a == pb._compute_prompt_version("SOUL A")  # deterministic

    def test_recomputes_when_mtime_changes(self, tmp_path):
        soul = tmp_path / "SOUL.md"
        soul.write_text("original persona")

        class _Dir:
            def __truediv__(self, _name):
                return soul

        with patch("src.config.PROFILE_DIR", _Dir()):
            v1 = pb.get_prompt_version()
            # Rewrite content AND bump mtime → recompute expected.
            import os
            soul.write_text("edited persona")
            st = soul.stat()
            os.utime(soul, (st.st_atime, st.st_mtime + 10))
            v2 = pb.get_prompt_version()
        assert v1 != v2

    def test_fallback_on_read_failure(self):
        # Force an error resolving SOUL.md; must still return a stable hash.
        with patch("src.config.PROFILE_DIR", None):
            v = pb.get_prompt_version()
        assert len(v) == 10
        int(v, 16)
