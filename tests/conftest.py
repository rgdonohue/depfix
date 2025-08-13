"""Pytest configuration and fixtures."""


import pytest


@pytest.fixture
def sample_requirements():
    """Sample requirements.txt content for testing."""
    return "fastapi==0.85.0\nuvicorn>=0.18.0"


@pytest.fixture
def sample_package_json():
    """Sample package.json content for testing."""
    return """
{
  "name": "test-project",
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "~4.17.21"
  }
}
"""


@pytest.fixture
def temp_manifest_file(tmp_path):
    """Create a temporary manifest file for testing."""
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("fastapi==0.85.0")
    return manifest
