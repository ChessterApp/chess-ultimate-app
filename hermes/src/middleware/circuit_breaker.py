"""Circuit breaker pattern for external service calls.

Tracks failures to external services (Stockfish, Supabase) and
opens the circuit after a threshold, preventing cascading failures.
"""

import logging
import threading
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject calls
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for a single external service."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (
                    self._last_failure_time
                    and time.monotonic() - self._last_failure_time >= self.recovery_timeout
                ):
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit %s transitioning to HALF_OPEN", self.name)
            return self._state

    @property
    def is_available(self) -> bool:
        """Check if requests should be allowed through."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                return self._half_open_calls < self.half_open_max_calls
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit %s recovered, now CLOSED", self.name)
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit %s re-opened after half-open failure", self.name)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit %s OPEN after %d failures",
                    self.name,
                    self._failure_count,
                )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0

    def status(self) -> dict:
        """Return current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "is_available": self.is_available,
        }


# Global circuit breakers for external services
stockfish_circuit = CircuitBreaker("stockfish", failure_threshold=3, recovery_timeout=60)
supabase_circuit = CircuitBreaker("supabase", failure_threshold=5, recovery_timeout=30)


def safe_tool_call(func, *args, **kwargs):
    """Wrap a tool call with try/except, returning structured error on failure."""
    try:
        result = func(*args, **kwargs)
        return result
    except FileNotFoundError:
        stockfish_circuit.record_failure()
        return {"error": "Stockfish engine unavailable", "degraded": True}
    except Exception as exc:
        logger.exception("Tool call failed: %s", func.__name__ if hasattr(func, '__name__') else str(func))
        return {"error": f"Tool error: {str(exc)}", "degraded": True}
