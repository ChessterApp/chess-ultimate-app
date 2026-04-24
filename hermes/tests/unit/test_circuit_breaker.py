"""Unit tests for circuit breaker pattern."""

import time

import pytest

from src.middleware.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    stockfish_circuit,
    supabase_circuit,
    safe_tool_call,
)


@pytest.mark.unit
class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False

    def test_recovery_to_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_available is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=1)
        cb.record_failure()
        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=1)
        cb.record_failure()
        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_status_dict(self):
        cb = CircuitBreaker("test-svc")
        status = cb.status()
        assert status["name"] == "test-svc"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["is_available"] is True

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2
        cb.record_success()
        assert cb._failure_count == 0


@pytest.mark.unit
class TestGlobalCircuitBreakers:
    """Test that global circuit breakers are properly configured."""

    def test_stockfish_circuit_exists(self):
        assert stockfish_circuit.name == "stockfish"
        assert stockfish_circuit.failure_threshold == 3

    def test_supabase_circuit_exists(self):
        assert supabase_circuit.name == "supabase"
        assert supabase_circuit.failure_threshold == 5


@pytest.mark.unit
class TestSafeToolCall:
    """Tests for the safe_tool_call wrapper."""

    def test_successful_call(self):
        def ok_func():
            return {"result": "ok"}

        result = safe_tool_call(ok_func)
        assert result == {"result": "ok"}

    def test_handles_file_not_found(self):
        def bad_func():
            raise FileNotFoundError("stockfish missing")

        result = safe_tool_call(bad_func)
        assert "error" in result
        assert result["degraded"] is True

    def test_handles_generic_exception(self):
        def crash_func():
            raise RuntimeError("boom")

        result = safe_tool_call(crash_func)
        assert "error" in result
        assert "boom" in result["error"]
        assert result["degraded"] is True

    def test_passes_args_through(self):
        def add(a, b):
            return a + b

        assert safe_tool_call(add, 2, 3) == 5

    def test_passes_kwargs_through(self):
        def greet(name="world"):
            return f"hello {name}"

        assert safe_tool_call(greet, name="test") == "hello test"
