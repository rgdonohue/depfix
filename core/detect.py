"""Ecosystem detection for dependency manifests."""

import re


def identify(content: str, filename: str | None = None) -> str:
    """Detect ecosystem from content and filename hints.

    Args:
        content: The manifest file content
        filename: Optional filename for additional context

    Returns:
        Detected ecosystem: 'python', 'node', or 'unknown'
    """
    # Filename-based detection (takes precedence)
    if filename:
        if filename.endswith(("requirements.txt", "pyproject.toml")):
            return "python"
        if filename.endswith("package.json"):
            return "node"

    # Content-based detection
    # Python patterns
    python_patterns = [
        r"^[a-zA-Z0-9\-_]+\s*[><=!~]+\s*[\d\w\.\-]+",  # package>=1.0.0
        r"^[a-zA-Z0-9\-_]+\[.*?\]\s*[><=!~]+",  # package[extras]>=1.0.0
        r";\s*(?:sys_platform|python_version)",  # environment markers
    ]

    for pattern in python_patterns:
        if re.search(pattern, content, re.MULTILINE):
            return "python"

    # Node.js patterns
    node_patterns = [
        r'"dependencies"',
        r'"devDependencies"',
    ]

    for pattern in node_patterns:
        if re.search(pattern, content):
            return "node"

    return "unknown"
