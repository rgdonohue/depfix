"""Tests for Python requirements.txt parsing."""

import pytest

from core.models import Manifest, ManifestEntry
from core.parse_python import parse_requirements


class TestPythonParser:
    """Test Python requirements.txt parsing."""

    def test_parse_single_requirement(self):
        """Should parse a single package requirement."""
        content = "fastapi==0.85.0"
        manifest = parse_requirements(content)

        assert manifest.ecosystem == "python"
        assert manifest.raw == content
        assert len(manifest.entries) == 1

        entry = manifest.entries[0]
        assert entry.name == "fastapi"
        assert entry.spec == "==0.85.0"
        assert entry.source_type == "registry"

    def test_parse_multiple_requirements(self):
        """Should parse multiple package requirements."""
        content = "fastapi==0.85.0\nuvicorn>=0.18.0\nrequests~=2.28.0"
        manifest = parse_requirements(content)

        assert len(manifest.entries) == 3
        
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[0].spec == "==0.85.0"
        
        assert manifest.entries[1].name == "uvicorn"
        assert manifest.entries[1].spec == ">=0.18.0"
        
        assert manifest.entries[2].name == "requests"
        assert manifest.entries[2].spec == "~=2.28.0"

    def test_parse_with_comments(self):
        """Should preserve comments and skip comment lines."""
        content = """# Web framework
fastapi==0.85.0  # Fast API framework
# Server
uvicorn>=0.18.0"""
        
        manifest = parse_requirements(content)
        
        # Should preserve original content
        assert "# Web framework" in manifest.raw
        
        # Should only parse package lines
        assert len(manifest.entries) == 2
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[1].name == "uvicorn"

    def test_parse_with_environment_markers(self):
        """Should parse environment markers correctly."""
        content = 'uvloop>=0.17.0; sys_platform != "win32"'
        manifest = parse_requirements(content)
        
        entry = manifest.entries[0]
        assert entry.name == "uvloop"
        assert entry.spec == ">=0.17.0"
        assert entry.markers == 'sys_platform != "win32"'

    def test_parse_with_extras(self):
        """Should parse package extras correctly."""
        content = "fastapi[all]==0.85.0"
        manifest = parse_requirements(content)
        
        entry = manifest.entries[0]
        assert entry.name == "fastapi"
        assert entry.spec == "==0.85.0"
        assert entry.extras == ["all"]

    def test_parse_complex_specifiers(self):
        """Should parse complex version specifiers."""
        content = "django>=3.2,<4.0"
        manifest = parse_requirements(content)
        
        entry = manifest.entries[0]
        assert entry.name == "django"
        assert entry.spec == ">=3.2,<4.0"

    def test_parse_with_blank_lines(self):
        """Should handle blank lines gracefully."""
        content = """fastapi==0.85.0

uvicorn>=0.18.0

"""
        manifest = parse_requirements(content)
        
        assert len(manifest.entries) == 2
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[1].name == "uvicorn"

    def test_parse_vcs_dependencies(self):
        """Should skip VCS dependencies and preserve as-is."""
        content = """fastapi==0.85.0
git+https://github.com/user/repo.git@v1.0.0#egg=custom-lib
uvicorn>=0.18.0"""
        
        manifest = parse_requirements(content)
        
        # Should only parse registry dependencies
        assert len(manifest.entries) == 2
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[1].name == "uvicorn"
        
        # Should preserve original content including VCS line
        assert "git+https://github.com/user/repo.git" in manifest.raw

    def test_parse_editable_dependencies(self):
        """Should skip editable dependencies."""
        content = """fastapi==0.85.0
-e ./local-package
uvicorn>=0.18.0"""
        
        manifest = parse_requirements(content)
        
        assert len(manifest.entries) == 2
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[1].name == "uvicorn"

    def test_parse_malformed_line_gracefully(self):
        """Should handle malformed lines gracefully and continue."""
        content = """fastapi==0.85.0
invalid-spec-line-here
uvicorn>=0.18.0"""
        
        manifest = parse_requirements(content)
        
        # Should parse valid lines and skip invalid ones
        assert len(manifest.entries) == 2
        assert manifest.entries[0].name == "fastapi"
        assert manifest.entries[1].name == "uvicorn"

    def test_parse_empty_file(self):
        """Should handle empty files gracefully."""
        content = ""
        manifest = parse_requirements(content)
        
        assert manifest.ecosystem == "python"
        assert manifest.raw == ""
        assert len(manifest.entries) == 0

    def test_parse_comments_only(self):
        """Should handle files with only comments."""
        content = """# This is a comment
# Another comment
"""
        manifest = parse_requirements(content)
        
        assert len(manifest.entries) == 0
        assert "# This is a comment" in manifest.raw