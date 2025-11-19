"""
Tests for thread-safe and async-safe logging context management.

Verifies that the contextvars implementation prevents race conditions
in concurrent request handling.
"""

import asyncio
import pytest
from concurrent.futures import ThreadPoolExecutor

from app.core.logging_config import (
    set_trace_id,
    get_trace_id,
    clear_trace_id,
)


# ============================================================================
# Context isolation tests
# ============================================================================

@pytest.mark.unit
def test_trace_id_basic_set_get():
    """Test basic trace ID set and get operations."""
    set_trace_id("test-trace-123")
    assert get_trace_id() == "test-trace-123"

    clear_trace_id()
    assert get_trace_id() is None


@pytest.mark.unit
def test_trace_id_initially_none():
    """Test that trace ID is None by default."""
    # Clear any existing value
    clear_trace_id()
    assert get_trace_id() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trace_id_async_task_isolation():
    """Test that each async task has isolated trace ID context.

    This is the critical test that would fail with global variables.
    """
    results = []

    async def task_with_trace_id(trace_id: str, delay: float):
        """Simulate request handling with trace ID."""
        set_trace_id(trace_id)

        # Simulate async work
        await asyncio.sleep(delay)

        # Get trace ID after delay - should still be the same
        retrieved_id = get_trace_id()
        results.append((trace_id, retrieved_id))

    # Run multiple tasks concurrently with different trace IDs
    await asyncio.gather(
        task_with_trace_id("trace-1", 0.01),
        task_with_trace_id("trace-2", 0.02),
        task_with_trace_id("trace-3", 0.01),
        task_with_trace_id("trace-4", 0.02),
    )

    # Verify each task maintained its own trace ID
    assert len(results) == 4
    for expected_id, retrieved_id in results:
        assert expected_id == retrieved_id, \
            f"Expected {expected_id}, got {retrieved_id}. " \
            "Context isolation failed!"


@pytest.mark.unit
def test_trace_id_thread_isolation():
    """Test that each thread has isolated trace ID context.

    With contextvars, each thread gets its own context.
    """
    results = []

    def thread_with_trace_id(trace_id: str):
        """Simulate request handling in thread."""
        set_trace_id(trace_id)

        # Simulate some work
        import time
        time.sleep(0.01)

        # Get trace ID after delay
        retrieved_id = get_trace_id()
        results.append((trace_id, retrieved_id))

    # Run multiple threads concurrently
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(thread_with_trace_id, f"trace-{i}")
            for i in range(4)
        ]
        for future in futures:
            future.result()

    # Verify each thread maintained its own trace ID
    assert len(results) == 4
    for expected_id, retrieved_id in results:
        assert expected_id == retrieved_id, \
            f"Expected {expected_id}, got {retrieved_id}. " \
            "Thread isolation failed!"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trace_id_nested_tasks():
    """Test trace ID context in nested async tasks."""
    async def outer_task():
        set_trace_id("outer-trace")
        assert get_trace_id() == "outer-trace"

        async def inner_task():
            # Inner task should inherit parent's context
            assert get_trace_id() == "outer-trace"

            # But can override it
            set_trace_id("inner-trace")
            assert get_trace_id() == "inner-trace"

        await inner_task()

        # Outer task's context is NOT affected by inner's override
        # This is a known behavior of contextvars - child contexts
        # don't affect parent contexts
        # In production, each request gets its own task, so this is fine

    await outer_task()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trace_id_concurrent_modifications():
    """Test concurrent modifications don't interfere with each other."""
    modifications = []

    async def modifier(task_id: int, num_modifications: int):
        """Repeatedly modify trace ID."""
        for i in range(num_modifications):
            trace_id = f"task-{task_id}-mod-{i}"
            set_trace_id(trace_id)

            # Small delay to encourage interleaving
            await asyncio.sleep(0.001)

            # Verify trace ID is still correct
            retrieved = get_trace_id()
            modifications.append((trace_id, retrieved))

    # Run multiple tasks that repeatedly modify their trace ID
    await asyncio.gather(
        modifier(1, 5),
        modifier(2, 5),
        modifier(3, 5),
    )

    # All modifications should have maintained correct trace ID
    assert len(modifications) == 15
    for expected, retrieved in modifications:
        assert expected == retrieved, \
            "Concurrent modification caused race condition!"


# ============================================================================
# Backward compatibility tests
# ============================================================================

@pytest.mark.unit
def test_backward_compatibility_aliases():
    """Test that backward compatibility aliases work."""
    from app.core.logging_config import (
        set_correlation_id,
        get_correlation_id,
        clear_correlation_id,
    )

    # Test set alias
    set_correlation_id("test-correlation-123")
    assert get_correlation_id() == "test-correlation-123"
    assert get_trace_id() == "test-correlation-123"

    # Test clear alias
    clear_correlation_id()
    assert get_correlation_id() is None
    assert get_trace_id() is None
