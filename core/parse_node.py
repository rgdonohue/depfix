"""Node.js package.json parsing."""

from .models import Manifest


def parse_package_json(content: str) -> Manifest:
    """Parse package.json content into Manifest.

    Args:
        content: The package.json file content

    Returns:
        Parsed Manifest object
    """
    # Placeholder implementation - will be developed via TDD
    raise NotImplementedError("Node.js parsing not yet implemented")
