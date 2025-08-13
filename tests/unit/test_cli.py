"""Tests for CLI functionality."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from apps.cli.main import app
from core.models import ManifestEntry, ResolutionResult


class TestCLI:
    """Test CLI command interface."""

    def setup_method(self):
        """Setup test fixtures."""
        self.runner = CliRunner()

    def test_cli_help_command(self):
        """Should display help when called with --help."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "depfix" in result.output.lower()
        assert "update" in result.output.lower()

    def test_update_help_command(self):
        """Should display update command help."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "requirements.txt" in result.output or "package.json" in result.output

    def test_update_single_file_in_place(self, tmp_path):
        """Should update a requirements.txt file in place."""
        # Create test requirements file
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0\nuvicorn>=0.18.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            # Mock resolver
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                ),
                ResolutionResult(
                    entry=ManifestEntry(name="uvicorn", spec=">=0.18.0"),
                    chosen_version="0.32.0",
                    reason="Latest version satisfying constraint",
                    semver_delta="minor"
                )
            ]

            result = self.runner.invoke(app, [ str(req_file), "-i"])

            assert result.exit_code == 0
            # Check file was updated
            updated_content = req_file.read_text()
            assert "fastapi==0.115.0" in updated_content
            assert "uvicorn" in updated_content

    def test_update_with_output_file(self, tmp_path):
        """Should write updated content to specified output file."""
        # Create test requirements file
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        output_file = tmp_path / "requirements.updated.txt"

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                )
            ]

            result = self.runner.invoke(app, [
                str(req_file), "--out", str(output_file)
            ])

            assert result.exit_code == 0
            assert output_file.exists()
            content = output_file.read_text()
            assert "fastapi==0.115.0" in content

    def test_update_with_python_version(self, tmp_path):
        """Should pass Python version to resolver."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = []

            result = self.runner.invoke(app, [
                str(req_file), "--python", "3.11", "-i"
            ])

            # Check resolver was initialized with Python version
            mock_resolver_class.assert_called_once()
            call_kwargs = mock_resolver_class.call_args[1]
            assert call_kwargs.get("python_version") == "3.11"

    def test_update_dry_run(self, tmp_path):
        """Should not modify files in dry run mode."""
        req_file = tmp_path / "requirements.txt"
        original_content = "fastapi==0.85.0"
        req_file.write_text(original_content)

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                )
            ]

            result = self.runner.invoke(app, [
                str(req_file), "--dry-run"
            ])

            assert result.exit_code == 0
            # File should not be modified
            assert req_file.read_text() == original_content
            # Should show diff in output
            assert "fastapi" in result.output

    def test_update_json_format(self, tmp_path):
        """Should output JSON format when requested."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                )
            ]

            result = self.runner.invoke(app, [
                str(req_file), "--format", "json", "--dry-run"
            ])

            assert result.exit_code == 0
            # Should output valid JSON
            output_data = json.loads(result.output)
            assert "reports" in output_data
            assert len(output_data["reports"]) == 1

    def test_update_stdin_stdout(self):
        """Should read from stdin and write to stdout."""
        input_content = "fastapi==0.85.0\nuvicorn>=0.18.0"

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                ),
                ResolutionResult(
                    entry=ManifestEntry(name="uvicorn", spec=">=0.18.0"),
                    chosen_version="0.32.0",
                    reason="Latest version satisfying constraint",
                    semver_delta="minor"
                )
            ]

            result = self.runner.invoke(app, [
                "-", "--out", "-"
            ], input=input_content)

            assert result.exit_code == 0
            assert "fastapi==0.115.0" in result.output

    def test_update_ecosystem_auto_detection(self, tmp_path):
        """Should auto-detect ecosystem from file content."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.identify') as mock_detect:
            mock_detect.return_value = "python"

            with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
                mock_resolver = AsyncMock()
                mock_resolver_class.return_value = mock_resolver
                mock_resolver.resolve_entries.return_value = []

                result = self.runner.invoke(app, [ str(req_file), "-i"])

                # Should have called detect
                mock_detect.assert_called_once()

    def test_update_force_ecosystem(self, tmp_path):
        """Should respect --engine flag to force ecosystem."""
        req_file = tmp_path / "test.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = []

            result = self.runner.invoke(app, [
                str(req_file), "--engine", "python", "-i"
            ])

            # Should use Python resolver regardless of detection
            mock_resolver_class.assert_called_once()

    def test_update_no_changes_exit_code(self, tmp_path):
        """Should return exit code 2 when no changes needed."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            # Resolver returns same version (no changes)
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.85.0",  # Same version
                    reason="Already at latest",
                    semver_delta="unknown"
                )
            ]

            result = self.runner.invoke(app, [ str(req_file), "-i"])

            assert result.exit_code == 2  # No changes exit code

    def test_update_file_not_found(self):
        """Should handle file not found gracefully."""
        result = self.runner.invoke(app, [ "nonexistent.txt", "-i"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_update_network_error_handling(self, tmp_path):
        """Should handle network errors gracefully."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.side_effect = Exception("Network error")

            result = self.runner.invoke(app, [ str(req_file), "-i"])

            assert result.exit_code != 0  # Should fail gracefully

    def test_update_diff_display(self, tmp_path):
        """Should display diff by default."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.85.0")

        with patch('apps.cli.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest available version",
                    semver_delta="major"
                )
            ]

            result = self.runner.invoke(app, [ str(req_file), "--dry-run"])

            assert result.exit_code == 0
            # Should show diff-like output
            assert "fastapi" in result.output
            assert "0.85.0" in result.output
            assert "0.115.0" in result.output
