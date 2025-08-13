"""Test that project structure is correct and modules can be imported."""

import core.detect
import core.models
import core.parse_node
import core.parse_python
from core.models import Manifest, ManifestEntry


def test_core_modules_importable():
    """Ensure core modules can be imported."""
    # This will fail if modules have syntax errors or missing dependencies

    # Basic smoke test - ensure key classes exist
    assert hasattr(core.models, "Manifest")
    assert hasattr(core.models, "ManifestEntry")
    assert hasattr(core.models, "ResolutionResult")
    assert hasattr(core.detect, "identify")


def test_model_creation():
    """Test that basic models can be instantiated."""
    entry = ManifestEntry(name="fastapi", spec="==0.85.0")
    assert entry.name == "fastapi"
    assert entry.spec == "==0.85.0"

    manifest = Manifest(ecosystem="python", raw="", entries=[entry])
    assert manifest.ecosystem == "python"
    assert len(manifest.entries) == 1
