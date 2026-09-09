"""Engine-grounded evaluation harness (Phase 0).

Measurement + safety substrate for continuous learning: an engine-grounded
auto-eval, a frozen golden set, an eval runner, and a CI regression gate. No
model/prompt behavior changes live here — this package only *measures*.

Importing the coach's tool modules (``src.tools.stockfish`` /
``src.tools.check_moves``) pulls in ``src/tools/__init__.py``, which imports the
``tools.registry`` from the hermes-agent framework. That framework is present in
the deployment/dev venv but NOT in CI or a bare offline checkout. So before any
tool import we install a minimal ``tools.registry`` stub *only when the real one
is absent* — the eval harness never registers tools, it just calls the pure
functions ``analyze_position`` / ``check_moves``.
"""

from src.eval._bootstrap import ensure_tools_importable

ensure_tools_importable()
