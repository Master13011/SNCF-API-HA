"""Common fixtures for the SNCF Trains tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    yield
