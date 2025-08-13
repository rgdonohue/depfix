"""Tests for Python package version resolution."""

from unittest.mock import patch

import pytest

from core.models import ManifestEntry
from core.resolve_python import PythonResolver


class TestPythonResolver:
    """Test Python package version resolution."""

    @pytest.mark.asyncio
    async def test_resolve_latest_version_simple(self):
        """Should resolve latest version for simple package."""
        resolver = PythonResolver()

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "info": {"version": "0.115.0"},
                "releases": {
                    "0.85.0": [{"upload_time": "2023-01-01T00:00:00Z"}],
                    "0.100.0": [{"upload_time": "2023-06-01T00:00:00Z"}],
                    "0.115.0": [{"upload_time": "2024-01-01T00:00:00Z"}]
                }
            }

            version = await resolver.get_latest_version("fastapi")
            assert version == "0.115.0"

    @pytest.mark.asyncio
    async def test_resolve_with_version_constraints(self):
        """Should resolve max satisfying version within constraints."""
        resolver = PythonResolver()
        entry = ManifestEntry(name="fastapi", spec=">=0.85.0,<0.110.0")

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "releases": {
                    "0.85.0": [],
                    "0.100.0": [],
                    "0.109.0": [],
                    "0.115.0": []  # This should be excluded by <0.110.0
                }
            }

            result = await resolver.resolve_entry(entry)
            assert result.chosen_version == "0.109.0"
            assert result.entry == entry
            assert "constraint" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_resolve_with_python_version_filtering(self):
        """Should filter versions based on target Python version."""
        resolver = PythonResolver(python_version="3.11")
        entry = ManifestEntry(name="typing-extensions", spec=">=4.0.0")

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "releases": {
                    "4.0.0": [{"requires_python": ">=3.7"}],
                    "4.5.0": [{"requires_python": ">=3.8"}],
                    "4.8.0": [{"requires_python": ">=3.8"}],
                    "4.9.0": [{"requires_python": ">=3.12"}]  # Should be excluded
                }
            }

            result = await resolver.resolve_entry(entry)
            assert result.chosen_version == "4.8.0"
            assert "python 3.11" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_resolve_with_environment_markers(self):
        """Should handle environment markers in resolution."""
        resolver = PythonResolver()
        entry = ManifestEntry(
            name="uvloop",
            spec=">=0.17.0",
            markers='sys_platform != "win32"'
        )

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "releases": {
                    "0.17.0": [],
                    "0.18.0": [],
                    "0.19.0": []
                }
            }

            result = await resolver.resolve_entry(entry)
            assert result.chosen_version == "0.19.0"
            assert result.entry.markers == 'sys_platform != "win32"'

    @pytest.mark.asyncio
    async def test_resolve_no_version_spec_pins_latest(self):
        """Should pin to latest version when no spec given."""
        resolver = PythonResolver()
        entry = ManifestEntry(name="requests", spec=None)

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "info": {"version": "2.31.0"},
                "releases": {
                    "2.28.0": [],
                    "2.30.0": [],
                    "2.31.0": []
                }
            }

            result = await resolver.resolve_entry(entry)
            assert result.chosen_version == "2.31.0"
            assert "latest" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_resolve_semver_delta_calculation(self):
        """Should calculate semver delta correctly."""
        resolver = PythonResolver()

        # Test major version change - use range constraint so resolver picks latest
        entry = ManifestEntry(name="fastapi", spec=">=0.85.0")
        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = {
                "releases": {"0.85.0": [], "1.0.0": [], "0.90.0": []}
            }

            result = await resolver.resolve_entry(entry)
            # Should pick 1.0.0 (latest satisfying >=0.85.0)
            assert result.chosen_version == "1.0.0"

        # Now test delta calculation with exact constraint for comparison
        delta = resolver._calculate_semver_delta(
            ManifestEntry(name="fastapi", spec="==0.85.0"),
            "1.0.0"
        )
        assert delta == "major"

    @pytest.mark.asyncio
    async def test_resolve_concurrent_requests(self):
        """Should handle multiple concurrent resolution requests."""
        resolver = PythonResolver(max_concurrency=3)

        entries = [
            ManifestEntry(name="fastapi", spec=">=0.85.0"),
            ManifestEntry(name="uvicorn", spec=">=0.18.0"),
            ManifestEntry(name="requests", spec=">=2.28.0")
        ]

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.side_effect = [
                {"releases": {"0.85.0": [], "0.115.0": []}},
                {"releases": {"0.18.0": [], "0.32.0": []}},
                {"releases": {"2.28.0": [], "2.31.0": []}}
            ]

            results = await resolver.resolve_entries(entries)

            assert len(results) == 3
            assert results[0].chosen_version == "0.115.0"
            assert results[1].chosen_version == "0.32.0"
            assert results[2].chosen_version == "2.31.0"

    @pytest.mark.asyncio
    async def test_resolve_handles_network_error_gracefully(self):
        """Should handle network errors gracefully."""
        resolver = PythonResolver()
        entry = ManifestEntry(name="nonexistent-package")

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")

            with pytest.raises(Exception) as exc_info:
                await resolver.resolve_entry(entry)
            assert "Network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resolve_handles_package_not_found(self):
        """Should handle package not found errors."""
        resolver = PythonResolver()
        entry = ManifestEntry(name="nonexistent-package")

        with patch.object(resolver, '_fetch_package_metadata') as mock_fetch:
            mock_fetch.return_value = None

            with pytest.raises(Exception) as exc_info:
                await resolver.resolve_entry(entry)
            assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_resolve_caches_package_metadata(self):
        """Should cache package metadata for repeated requests."""
        resolver = PythonResolver()

        # Directly test the caching mechanism by pre-populating cache
        test_metadata = {
            "info": {"version": "1.0.0"},
            "releases": {"1.0.0": []}
        }

        # Populate cache directly
        resolver._cache["test-package"] = test_metadata

        # Mock the HTTP client to ensure it's never called
        with patch('httpx.AsyncClient') as mock_client:
            result = await resolver.get_latest_version("test-package")
            assert result == "1.0.0"
            # Client should never be instantiated since we hit cache
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_respects_timeout(self):
        """Should respect timeout settings."""
        resolver = PythonResolver(timeout=1.0)

        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock a slow response
            async def slow_response(*args, **kwargs):
                import asyncio
                await asyncio.sleep(2.0)  # Longer than timeout

            mock_get.side_effect = slow_response

            entry = ManifestEntry(name="test-package")
            with pytest.raises(Exception):  # Should timeout
                await resolver.resolve_entry(entry)

    def test_resolver_initialization(self):
        """Should initialize resolver with correct defaults."""
        resolver = PythonResolver()

        assert resolver.python_version is None  # Auto-detect
        assert resolver.timeout == 30.0
        assert resolver.max_concurrency == 6

    def test_resolver_custom_initialization(self):
        """Should initialize resolver with custom settings."""
        resolver = PythonResolver(
            python_version="3.11",
            timeout=10.0,
            max_concurrency=4
        )

        assert resolver.python_version == "3.11"
        assert resolver.timeout == 10.0
        assert resolver.max_concurrency == 4
