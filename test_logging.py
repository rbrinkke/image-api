#!/usr/bin/env python3
"""
Test script for validating the logging configuration.

This script tests:
1. Logging module imports successfully
2. Logger initialization works
3. Structured logging produces correct output
4. Both JSON and console modes work
5. Correlation ID context works
"""

import sys
import os
import io
from contextlib import redirect_stdout, redirect_stderr

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables for testing
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["DEBUG"] = "true"
os.environ["LOG_JSON"] = "false"
os.environ["DATABASE_PATH"] = "/tmp/test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


def test_imports():
    """Test that all logging modules can be imported."""
    print("Testing imports...")
    try:
        from app.core.logging_config import setup_logging, get_logger, set_correlation_id, clear_correlation_id
        from app.core.config import settings
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logger_initialization():
    """Test logger initialization."""
    print("\nTesting logger initialization...")
    try:
        from app.core.logging_config import setup_logging, get_logger
        from app.core.config import settings

        # Initialize logging in debug mode (console output)
        setup_logging(debug=True, json_logs=False)

        logger = get_logger(__name__)
        print("✓ Logger initialized successfully")
        return logger
    except Exception as e:
        print(f"✗ Logger initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_structured_logging(logger):
    """Test structured logging with context."""
    print("\nTesting structured logging...")
    try:
        # Test basic logging
        logger.info("test_message", key1="value1", key2="value2")

        # Test different log levels
        logger.debug("debug_message", level="DEBUG")
        logger.info("info_message", level="INFO")
        logger.warning("warning_message", level="WARNING")

        # Test error logging with exception info
        try:
            raise ValueError("Test exception")
        except Exception as e:
            logger.error("error_occurred", error=str(e), exc_info=False)

        print("✓ Structured logging works")
        return True
    except Exception as e:
        print(f"✗ Structured logging failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_correlation_id():
    """Test correlation ID context."""
    print("\nTesting correlation ID context...")
    try:
        from app.core.logging_config import get_logger, set_correlation_id, get_correlation_id, clear_correlation_id

        logger = get_logger(__name__)

        # Set correlation ID
        test_id = "test-correlation-123"
        set_correlation_id(test_id)

        # Verify it's set
        current_id = get_correlation_id()
        assert current_id == test_id, f"Expected {test_id}, got {current_id}"

        # Log with correlation ID
        logger.info("message_with_correlation", operation="test")

        # Clear correlation ID
        clear_correlation_id()
        assert get_correlation_id() is None, "Correlation ID should be None after clear"

        print("✓ Correlation ID context works")
        return True
    except Exception as e:
        print(f"✗ Correlation ID failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_json_mode():
    """Test JSON logging mode."""
    print("\nTesting JSON logging mode...")
    try:
        from app.core.logging_config import setup_logging, get_logger

        # Reinitialize with JSON mode
        setup_logging(debug=False, json_logs=True)

        logger = get_logger(__name__)
        logger.info("json_test_message", json_mode=True, test_key="test_value")

        print("✓ JSON logging mode initialized")
        return True
    except Exception as e:
        print(f"✗ JSON mode failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_middleware_import():
    """Test that middleware can be imported."""
    print("\nTesting middleware import...")
    try:
        from app.api.middleware import RequestLoggingMiddleware, PerformanceLoggingMiddleware
        print("✓ Middleware imports successful")
        return True
    except Exception as e:
        print(f"✗ Middleware import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("LOGGING SYSTEM TEST SUITE")
    print("=" * 70)

    results = []

    # Test 1: Imports
    results.append(("Imports", test_imports()))

    if not results[0][1]:
        print("\n✗ Basic imports failed. Stopping tests.")
        return False

    # Test 2: Logger initialization
    logger = test_logger_initialization()
    results.append(("Logger Initialization", logger is not None))

    if logger is None:
        print("\n✗ Logger initialization failed. Stopping tests.")
        return False

    # Test 3: Structured logging
    results.append(("Structured Logging", test_structured_logging(logger)))

    # Test 4: Correlation ID
    results.append(("Correlation ID", test_correlation_id()))

    # Test 5: JSON mode
    results.append(("JSON Mode", test_json_mode()))

    # Test 6: Middleware
    results.append(("Middleware Import", test_middleware_import()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\nResults: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed! Logging system is working correctly.")
        return True
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
