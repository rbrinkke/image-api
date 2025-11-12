"""Unit tests for CircuitBreaker."""

import pytest
import asyncio
from datetime import datetime, timedelta

from app.core.authorization import CircuitBreaker, CircuitBreakerState
from app.core.config import settings


@pytest.mark.asyncio
class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    async def test_initial_state_is_closed(self, redis_client):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(redis_client)

        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.CLOSED.value
        assert status["failures"] == 0

    async def test_should_attempt_in_closed_state(self, redis_client):
        """Test requests are allowed in closed state."""
        cb = CircuitBreaker(redis_client)

        should_attempt = await cb.should_attempt()
        assert should_attempt is True

    async def test_record_success_in_closed_state(self, redis_client):
        """Test recording success in closed state."""
        cb = CircuitBreaker(redis_client)

        await cb.record_success()

        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.CLOSED.value
        assert status["failures"] == 0

    async def test_record_failure_increments_count(self, redis_client):
        """Test recording failure increments count."""
        cb = CircuitBreaker(redis_client)

        await cb.record_failure()

        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.CLOSED.value
        assert status["failures"] == 1

    async def test_circuit_opens_after_threshold_failures(self, redis_client):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(redis_client)

        # Record failures up to threshold
        threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        for i in range(threshold):
            await cb.record_failure()

        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.OPEN.value
        assert status["opened_at"] is not None

    async def test_should_attempt_fails_when_open(self, redis_client):
        """Test requests are blocked when circuit is open."""
        cb = CircuitBreaker(redis_client)

        # Open the circuit
        threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        for _ in range(threshold):
            await cb.record_failure()

        # Should not attempt
        should_attempt = await cb.should_attempt()
        assert should_attempt is False

    async def test_circuit_transitions_to_half_open_after_timeout(self, redis_client):
        """Test circuit transitions to half-open after timeout."""
        cb = CircuitBreaker(redis_client)

        # Open the circuit
        threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        for _ in range(threshold):
            await cb.record_failure()

        # Manually set opened_at to past
        state = await cb.get_status()
        past_time = datetime.utcnow() - timedelta(seconds=settings.CIRCUIT_BREAKER_TIMEOUT + 10)
        state["opened_at"] = past_time.isoformat()
        await cb._update_state(state)

        # Should transition to half-open and allow attempt
        should_attempt = await cb.should_attempt()
        assert should_attempt is True

        # Check state is half-open
        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.HALF_OPEN.value

    async def test_success_in_half_open_closes_circuit(self, redis_client):
        """Test successful call in half-open state closes circuit."""
        cb = CircuitBreaker(redis_client)

        # Open the circuit
        threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        for _ in range(threshold):
            await cb.record_failure()

        # Transition to half-open
        state = await cb.get_status()
        past_time = datetime.utcnow() - timedelta(seconds=settings.CIRCUIT_BREAKER_TIMEOUT + 10)
        state["opened_at"] = past_time.isoformat()
        state["state"] = CircuitBreakerState.HALF_OPEN.value
        await cb._update_state(state)

        # Record success
        await cb.record_success()

        # Should be closed now
        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.CLOSED.value
        assert status["failures"] == 0

    async def test_failure_in_half_open_reopens_circuit(self, redis_client):
        """Test failed call in half-open state reopens circuit."""
        cb = CircuitBreaker(redis_client)

        # Set to half-open state
        state = await cb.get_status()
        state["state"] = CircuitBreakerState.HALF_OPEN.value
        state["failures"] = settings.CIRCUIT_BREAKER_THRESHOLD - 1
        await cb._update_state(state)

        # Record failure
        await cb.record_failure()

        # Should reopen
        status = await cb.get_status()
        assert status["state"] == CircuitBreakerState.OPEN.value

    async def test_success_resets_failure_count(self, redis_client):
        """Test successful call resets failure count."""
        cb = CircuitBreaker(redis_client)

        # Record some failures
        await cb.record_failure()
        await cb.record_failure()

        status = await cb.get_status()
        assert status["failures"] >= 2

        # Record success
        await cb.record_success()

        # Failures should be reset
        status = await cb.get_status()
        assert status["failures"] == 0
        assert status["state"] == CircuitBreakerState.CLOSED.value

    async def test_get_status_shows_correct_info(self, redis_client):
        """Test get_status returns correct information."""
        cb = CircuitBreaker(redis_client)

        # Record failures
        for _ in range(2):
            await cb.record_failure()

        status = await cb.get_status()

        assert "state" in status
        assert "failures" in status
        assert "opened_at" in status
        assert status["failures"] == 2

    async def test_multiple_failure_calls(self, redis_client):
        """Test multiple failure calls correctly increment."""
        cb = CircuitBreaker(redis_client)

        for i in range(3):
            await cb.record_failure()
            status = await cb.get_status()
            assert status["failures"] == i + 1

    async def test_opened_at_timestamp_format(self, redis_client):
        """Test opened_at timestamp is in ISO format."""
        cb = CircuitBreaker(redis_client)

        # Open circuit
        threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        for _ in range(threshold):
            await cb.record_failure()

        status = await cb.get_status()
        assert status["opened_at"] is not None

        # Verify it's a valid ISO timestamp
        try:
            datetime.fromisoformat(status["opened_at"])
        except ValueError:
            pytest.fail("opened_at is not a valid ISO timestamp")

    async def test_concurrent_operations(self, redis_client):
        """Test concurrent circuit breaker operations."""
        cb = CircuitBreaker(redis_client)

        # Concurrent failures
        await asyncio.gather(
            cb.record_failure(),
            cb.record_failure(),
            cb.record_failure()
        )

        status = await cb.get_status()
        # At least 3 failures (may be more due to concurrency)
        assert status["failures"] >= 3

    async def test_state_persistence_across_instances(self, redis_client):
        """Test state is persisted across circuit breaker instances."""
        cb1 = CircuitBreaker(redis_client)

        # Record failures with first instance
        await cb1.record_failure()
        await cb1.record_failure()

        # Create new instance
        cb2 = CircuitBreaker(redis_client)

        # Should see same state
        status = await cb2.get_status()
        assert status["failures"] == 2
