"""Tests for ecosystem detection."""


from core.detect import identify


class TestEcosystemDetection:
    """Test ecosystem detection from filenames and content."""

    def test_detect_python_by_filename(self):
        """Should detect Python from requirements.txt filename."""
        assert identify("", "requirements.txt") == "python"
        assert identify("", "pyproject.toml") == "python"

    def test_detect_node_by_filename(self):
        """Should detect Node.js from package.json filename."""
        assert identify("", "package.json") == "node"

    def test_detect_python_by_content(self):
        """Should detect Python from requirements content patterns."""
        content = "fastapi==0.85.0\nuvicorn>=0.18.0"
        assert identify(content) == "python"

        content_with_markers = 'uvloop>=0.17.0; sys_platform != "win32"'
        assert identify(content_with_markers) == "python"

        content_with_extras = "fastapi[all]>=0.85.0"
        assert identify(content_with_extras) == "python"

    def test_detect_node_by_content(self):
        """Should detect Node.js from package.json content patterns."""
        content = '''
        {
          "dependencies": {
            "express": "^4.18.0"
          }
        }
        '''
        assert identify(content) == "node"

        content_dev = '{"devDependencies": {"jest": "^29.0.0"}}'
        assert identify(content_dev) == "node"

    def test_detect_unknown_for_ambiguous(self):
        """Should return unknown for unclear content."""
        assert identify("", "unknown.txt") == "unknown"
        assert identify("some random text") == "unknown"
        assert identify("") == "unknown"

    def test_filename_takes_precedence(self):
        """Filename should take precedence over content when both present."""
        # Package.json content but requirements.txt filename
        content = '{"dependencies": {"express": "^4.18.0"}}'
        assert identify(content, "requirements.txt") == "python"
