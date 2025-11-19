"""
Configuration tests for image-api.

Tests the type-safe Pydantic configuration system.
"""

import pytest
from pydantic import ValidationError

from app.core.config import ImageSizesConfig, Settings


# ============================================================================
# ImageSizesConfig tests
# ============================================================================

@pytest.mark.unit
def test_image_sizes_default_values():
    """Test ImageSizesConfig has correct default values."""
    config = ImageSizesConfig()

    assert config.thumbnail == 150
    assert config.medium == 600
    assert config.large == 1200
    assert config.original == 4096


@pytest.mark.unit
def test_image_sizes_custom_values():
    """Test ImageSizesConfig accepts custom values."""
    config = ImageSizesConfig(
        thumbnail=100,
        medium=500,
        large=1000,
        original=3000,
    )

    assert config.thumbnail == 100
    assert config.medium == 500
    assert config.large == 1000
    assert config.original == 3000


@pytest.mark.unit
def test_image_sizes_validation_negative():
    """Test ImageSizesConfig rejects negative dimensions."""
    with pytest.raises(ValidationError) as exc_info:
        ImageSizesConfig(thumbnail=-100)

    errors = exc_info.value.errors()
    assert len(errors) > 0
    assert "positive" in str(errors[0]["msg"]).lower()


@pytest.mark.unit
def test_image_sizes_validation_zero():
    """Test ImageSizesConfig rejects zero dimensions."""
    with pytest.raises(ValidationError) as exc_info:
        ImageSizesConfig(thumbnail=0)

    errors = exc_info.value.errors()
    assert len(errors) > 0
    assert "positive" in str(errors[0]["msg"]).lower()


@pytest.mark.unit
def test_image_sizes_validation_too_large():
    """Test ImageSizesConfig rejects dimensions over 8192."""
    with pytest.raises(ValidationError) as exc_info:
        ImageSizesConfig(thumbnail=10000)

    errors = exc_info.value.errors()
    assert len(errors) > 0
    assert "too large" in str(errors[0]["msg"]).lower()


@pytest.mark.unit
def test_image_sizes_model_dump():
    """Test ImageSizesConfig can be converted to dict for iteration."""
    config = ImageSizesConfig()
    data = config.model_dump()

    assert isinstance(data, dict)
    assert "thumbnail" in data
    assert "medium" in data
    assert "large" in data
    assert "original" in data

    # Should be usable in loops (like in processing.py)
    for variant_name, dimension in data.items():
        assert isinstance(variant_name, str)
        assert isinstance(dimension, int)
        assert dimension > 0


@pytest.mark.unit
def test_image_sizes_serialization():
    """Test ImageSizesConfig serializes correctly for API responses."""
    config = ImageSizesConfig()

    # This is what FastAPI does internally
    serialized = config.model_dump()

    assert serialized == {
        "thumbnail": 150,
        "medium": 600,
        "large": 1200,
        "original": 4096,
    }


# ============================================================================
# Settings integration tests
# ============================================================================

@pytest.mark.unit
def test_settings_has_image_sizes():
    """Test Settings contains IMAGE_SIZES field."""
    settings = Settings()

    assert hasattr(settings, "IMAGE_SIZES")
    assert isinstance(settings.IMAGE_SIZES, ImageSizesConfig)


@pytest.mark.unit
def test_settings_image_sizes_type_safe():
    """Test Settings.IMAGE_SIZES provides type-safe access."""
    settings = Settings()

    # Should have typed attributes (IDE autocomplete works)
    assert hasattr(settings.IMAGE_SIZES, "thumbnail")
    assert hasattr(settings.IMAGE_SIZES, "medium")
    assert hasattr(settings.IMAGE_SIZES, "large")
    assert hasattr(settings.IMAGE_SIZES, "original")

    # Should be integers
    assert isinstance(settings.IMAGE_SIZES.thumbnail, int)
    assert isinstance(settings.IMAGE_SIZES.medium, int)
    assert isinstance(settings.IMAGE_SIZES.large, int)
    assert isinstance(settings.IMAGE_SIZES.original, int)
