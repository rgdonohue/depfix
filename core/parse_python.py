"""Python requirements.txt and pyproject.toml parsing."""

import re

from packaging.requirements import InvalidRequirement, Requirement

from .models import Manifest, ManifestEntry


class RequirementsParser:
    """Parser for Python requirements.txt files."""

    def __init__(self):
        # Patterns for lines to skip
        self.skip_patterns = [
            r"^\s*#",  # Comment lines
            r"^\s*$",  # Empty lines
            r"^-e\s+",  # Editable installs
            r"^git\+",  # Git URLs
            r"^hg\+",  # Mercurial URLs
            r"^svn\+",  # SVN URLs
            r"^bzr\+",  # Bazaar URLs
            r"^https?://",  # Direct URLs
            r"^file://",  # File URLs
            r"^\./",  # Local paths
            r"^-r\s+",  # Include other requirements files
            r"^-f\s+",  # Find links
            r"^--",  # Other pip options
        ]

    def _should_skip_line(self, line: str) -> bool:
        """Check if a line should be skipped during parsing."""
        stripped = line.strip()
        if not stripped:
            return True

        return any(re.match(pattern, stripped) for pattern in self.skip_patterns)

    def _parse_requirement_line(self, line: str) -> ManifestEntry | None:
        """Parse a single requirement line using packaging library."""
        stripped = line.strip()
        if not stripped:
            return None

        try:
            # Remove inline comments for parsing, but they're preserved in raw content
            line_for_parsing = stripped.split("#")[0].strip()
            if not line_for_parsing:
                return None

            req = Requirement(line_for_parsing)

            return ManifestEntry(
                name=req.name,
                spec=str(req.specifier) if req.specifier else None,
                markers=str(req.marker) if req.marker else None,
                extras=list(req.extras) if req.extras else None,
                source_type="registry",
            )

        except InvalidRequirement:
            # Skip malformed requirements gracefully
            return None

    def parse(self, content: str) -> Manifest:
        """Parse requirements.txt content into Manifest."""
        lines = content.splitlines()
        entries: list[ManifestEntry] = []

        for line in lines:
            if self._should_skip_line(line):
                continue

            entry = self._parse_requirement_line(line)
            if entry:
                entries.append(entry)

        return Manifest(ecosystem="python", raw=content, entries=entries)


def parse_requirements(content: str) -> Manifest:
    """Parse requirements.txt content into Manifest.

    Args:
        content: The requirements.txt file content

    Returns:
        Parsed Manifest object
    """
    parser = RequirementsParser()
    return parser.parse(content)
