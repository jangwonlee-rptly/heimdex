"""Pytest configuration for heimdex_common tests."""

import pytest


@pytest.fixture(scope="session")
def test_user_id() -> str:
    """Standard test user ID."""
    return "test-user-123"


@pytest.fixture(scope="session")
def test_org_id() -> str:
    """Standard test organization ID (UUID format)."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture(scope="session")
def different_org_id() -> str:
    """Different organization ID for cross-tenant tests (UUID format)."""
    return "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
