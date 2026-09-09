"""Offline prompt-optimization harness (CL Phase 1, Slice 3).

Proposes improved versions of the coach's ``SOUL.md`` instruction block, scored
by the Phase 0 engine-grounded metric (:mod:`src.eval.engine_grounded`), and
emits candidate diffs + eval reports for HUMAN review. It NEVER edits SOUL.md in
place, never touches the serving path, and never deploys anything.

Importing anything here pulls in the eval harness, which installs the minimal
``tools.registry`` stub when the real hermes-agent framework is absent (CI /
bare checkout) — see :mod:`src.eval._bootstrap`.
"""

from src.eval._bootstrap import ensure_tools_importable

ensure_tools_importable()
