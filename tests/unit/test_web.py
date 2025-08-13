"""Tests for web application functionality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.web.main import app
from core.models import ManifestEntry, ResolutionResult


class TestWebApp:
    """Test web application endpoints."""

    def setup_method(self):
        """Setup test fixtures."""
        self.client = TestClient(app)

    def test_home_page(self):
        """Should serve the main HTML page."""
        response = self.client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "DepFix" in response.text
        assert "Dependency Updater" in response.text

    def test_update_api_success(self):
        """Should successfully process dependency updates."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec=">=0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest version satisfying constraint >=0.85.0",
                    semver_delta="minor"
                ),
                ResolutionResult(
                    entry=ManifestEntry(name="requests", spec=">=2.28.0"),
                    chosen_version="2.32.4",
                    reason="Latest version satisfying constraint >=2.28.0",
                    semver_delta="minor"
                )
            ]
            
            response = self.client.post("/api/update", json={
                "content": "fastapi>=0.85.0\nrequests>=2.28.0",
                "python_version": None,
                "ecosystem": None,
                "dry_run": True
            })
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["ecosystem"] == "python"
            assert data["has_changes"] is True
            assert len(data["changes"]) == 2
            assert "fastapi==0.115.0" in data["updated_content"]
            assert "requests==2.32.4" in data["updated_content"]

    def test_update_api_empty_content(self):
        """Should handle empty content gracefully."""
        response = self.client.post("/api/update", json={
            "content": "",
            "dry_run": True
        })
        
        assert response.status_code == 400
        assert "No content provided" in response.json()["detail"]

    def test_update_api_no_dependencies(self):
        """Should handle content with no dependencies."""
        with patch('apps.web.main.identify') as mock_identify:
            mock_identify.return_value = "python"
            
            response = self.client.post("/api/update", json={
                "content": "# Just a comment\n\n# Another comment",
                "dry_run": True
            })
            
            assert response.status_code == 400
            assert "No dependencies found" in response.json()["detail"]

    def test_update_api_unsupported_ecosystem(self):
        """Should handle unsupported ecosystems."""
        with patch('apps.web.main.identify') as mock_identify:
            mock_identify.return_value = "node"
            
            response = self.client.post("/api/update", json={
                "content": "fastapi>=0.85.0",
                "dry_run": True
            })
            
            assert response.status_code == 400
            assert "Unsupported ecosystem: node" in response.json()["detail"]

    def test_update_api_with_python_version(self):
        """Should pass Python version to resolver."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec=">=0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest version satisfying constraint >=0.85.0 for Python 3.11",
                    semver_delta="minor"
                )
            ]
            
            response = self.client.post("/api/update", json={
                "content": "fastapi>=0.85.0",
                "python_version": "3.11",
                "dry_run": True
            })
            
            assert response.status_code == 200
            
            # Check that resolver was called with Python version
            mock_resolver_class.assert_called_once_with(python_version="3.11")

    def test_update_api_forced_ecosystem(self):
        """Should respect forced ecosystem."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = []
            
            response = self.client.post("/api/update", json={
                "content": "fastapi>=0.85.0",
                "ecosystem": "python",
                "dry_run": True
            })
            
            # Should not call identify since ecosystem is forced
            with patch('apps.web.main.identify') as mock_identify:
                assert response.status_code == 200
                mock_identify.assert_not_called()

    def test_update_api_no_changes(self):
        """Should handle cases with no changes needed."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.115.0"),
                    chosen_version="0.115.0",
                    reason="Already at latest version",
                    semver_delta="unknown"
                )
            ]
            
            response = self.client.post("/api/update", json={
                "content": "fastapi==0.115.0",
                "dry_run": True
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["has_changes"] is False
            assert data["original_content"] == data["updated_content"]

    def test_upload_file_success(self):
        """Should successfully process uploaded file."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec=">=0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest version satisfying constraint >=0.85.0",
                    semver_delta="minor"
                )
            ]
            
            file_content = "fastapi>=0.85.0\nrequests>=2.28.0"
            files = {"file": ("requirements.txt", file_content, "text/plain")}
            
            response = self.client.post("/api/upload", files=files)
            
            assert response.status_code == 200
            data = response.json()
            assert data["has_changes"] is True
            assert "fastapi" in data["updated_content"]

    def test_upload_file_with_form_data(self):
        """Should handle file upload with additional form parameters."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = []
            
            file_content = "fastapi>=0.85.0"
            files = {"file": ("requirements.txt", file_content, "text/plain")}
            data = {"python_version": "3.11", "ecosystem": "python"}
            
            response = self.client.post("/api/upload", files=files, data=data)
            
            assert response.status_code == 200
            mock_resolver_class.assert_called_once_with(python_version="3.11")

    def test_upload_file_no_file(self):
        """Should handle missing file upload."""
        response = self.client.post("/api/upload", files={})
        
        assert response.status_code == 422  # FastAPI validation error

    def test_upload_file_invalid_encoding(self):
        """Should handle files with invalid UTF-8 encoding."""
        # Create a file with invalid UTF-8 bytes
        invalid_content = b'\x80\x81\x82'  # Invalid UTF-8 sequence
        files = {"file": ("requirements.txt", invalid_content, "text/plain")}
        
        response = self.client.post("/api/upload", files=files)
        
        assert response.status_code == 400
        assert "valid UTF-8" in response.json()["detail"]

    def test_download_file_with_changes(self):
        """Should generate downloadable file when changes exist."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec=">=0.85.0"),
                    chosen_version="0.115.0",
                    reason="Latest version satisfying constraint >=0.85.0",
                    semver_delta="minor"
                )
            ]
            
            response = self.client.post("/api/download", json={
                "content": "fastapi>=0.85.0",
                "dry_run": False
            })
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert "fastapi==0.115.0" in response.text

    def test_download_file_no_changes(self):
        """Should handle download request when no changes exist."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.return_value = [
                ResolutionResult(
                    entry=ManifestEntry(name="fastapi", spec="==0.115.0"),
                    chosen_version="0.115.0",
                    reason="Already at latest version",
                    semver_delta="unknown"
                )
            ]
            
            response = self.client.post("/api/download", json={
                "content": "fastapi==0.115.0",
                "dry_run": False
            })
            
            assert response.status_code == 400
            assert "No changes to download" in response.json()["detail"]

    def test_api_error_handling(self):
        """Should handle resolver errors gracefully."""
        with patch('apps.web.main.PythonResolver') as mock_resolver_class:
            mock_resolver = AsyncMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve_entries.side_effect = Exception("Network error")
            
            response = self.client.post("/api/update", json={
                "content": "fastapi>=0.85.0",
                "dry_run": True
            })
            
            assert response.status_code == 500
            assert "Error processing dependencies" in response.json()["detail"]
            assert "Network error" in response.json()["detail"]

    def test_has_changes_logic(self):
        """Should correctly detect when entries have changes."""
        from apps.web.main import _entry_has_change
        
        # Test no change - exact pin with same version
        no_change_result = ResolutionResult(
            entry=ManifestEntry(name="fastapi", spec="==0.115.0"),
            chosen_version="0.115.0",
            reason="Already at latest",
            semver_delta="unknown"
        )
        assert _entry_has_change(no_change_result) is False
        
        # Test change - exact pin with different version
        change_result = ResolutionResult(
            entry=ManifestEntry(name="fastapi", spec="==0.85.0"),
            chosen_version="0.115.0",
            reason="Update available",
            semver_delta="minor"
        )
        assert _entry_has_change(change_result) is True
        
        # Test change - range constraint (always considered a change)
        range_result = ResolutionResult(
            entry=ManifestEntry(name="fastapi", spec=">=0.85.0"),
            chosen_version="0.115.0",
            reason="Latest satisfying constraint",
            semver_delta="minor"
        )
        assert _entry_has_change(range_result) is True
        
        # Test change - no spec (always considered a change)
        no_spec_result = ResolutionResult(
            entry=ManifestEntry(name="fastapi", spec=None),
            chosen_version="0.115.0",
            reason="Pinning to latest",
            semver_delta="unknown"
        )
        assert _entry_has_change(no_spec_result) is True