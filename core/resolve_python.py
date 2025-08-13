"""Python package version resolution."""

import asyncio
import re

import httpx
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .models import ManifestEntry, ResolutionResult


class PythonResolver:
    """Resolver for Python package versions."""

    def __init__(
        self,
        python_version: str | None = None,
        timeout: float = 30.0,
        max_concurrency: int = 6,
    ):
        """Initialize Python resolver.
        
        Args:
            python_version: Target Python version (e.g., "3.11")
            timeout: Request timeout in seconds
            max_concurrency: Maximum concurrent requests
        """
        self.python_version = python_version
        self.timeout = timeout
        self.max_concurrency = max_concurrency
        self._cache: dict[str, dict] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def get_latest_version(self, package_name: str) -> str:
        """Get latest version for a package.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Latest version string
        """
        metadata = await self._fetch_package_metadata(package_name)
        if not metadata:
            raise Exception(f"Package {package_name} not found")

        # Use info.version as authoritative latest
        if "info" in metadata and "version" in metadata["info"]:
            return metadata["info"]["version"]

        # Fallback: find max version from releases
        releases = metadata.get("releases", {})
        if not releases:
            raise Exception(f"No releases found for package {package_name}")

        versions = [Version(v) for v in releases.keys()]
        return str(max(versions))

    async def resolve_entry(self, entry: ManifestEntry) -> ResolutionResult:
        """Resolve a manifest entry to latest compatible version.
        
        Args:
            entry: Manifest entry to resolve
            
        Returns:
            Resolution result with chosen version
        """
        async with self._semaphore:
            metadata = await self._fetch_package_metadata(entry.name)
            if not metadata:
                raise Exception(f"Package {entry.name} not found")

            releases = metadata.get("releases", {})
            if not releases:
                raise Exception(f"No releases found for package {entry.name}")

            # Filter available versions
            available_versions = []
            for version_str in releases.keys():
                try:
                    version = Version(version_str)
                    # Filter by Python version compatibility if specified
                    if self._is_compatible_with_python(releases[version_str], version_str):
                        available_versions.append(version)
                except Exception:
                    continue  # Skip invalid versions

            if not available_versions:
                raise Exception(f"No compatible versions found for {entry.name}")

            # Apply version constraints if present
            if entry.spec:
                try:
                    spec_set = SpecifierSet(entry.spec)
                    compatible_versions = [v for v in available_versions if v in spec_set]
                    if compatible_versions:
                        chosen_version = max(compatible_versions)
                        reason = f"Latest version satisfying constraint {entry.spec}"
                    else:
                        # No versions satisfy constraint, use latest available
                        chosen_version = max(available_versions)
                        reason = f"No versions satisfy {entry.spec}, using latest available"
                except Exception:
                    # Invalid spec, use latest
                    chosen_version = max(available_versions)
                    reason = f"Invalid constraint {entry.spec}, using latest available"
            else:
                # No constraints, use latest
                chosen_version = max(available_versions)
                reason = "Latest available version (no constraints)"

            # Add Python version context to reason
            if self.python_version:
                reason += f" for Python {self.python_version}"

            # Calculate semver delta
            semver_delta = self._calculate_semver_delta(entry, str(chosen_version))

            return ResolutionResult(
                entry=entry,
                chosen_version=str(chosen_version),
                reason=reason,
                semver_delta=semver_delta,
            )

    async def resolve_entries(self, entries: list[ManifestEntry]) -> list[ResolutionResult]:
        """Resolve multiple entries concurrently.
        
        Args:
            entries: List of manifest entries to resolve
            
        Returns:
            List of resolution results
        """
        tasks = [self.resolve_entry(entry) for entry in entries]
        return await asyncio.gather(*tasks)

    async def _fetch_package_metadata(self, package_name: str) -> dict | None:
        """Fetch package metadata from PyPI.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Package metadata dict or None if not found
        """
        # Check cache first
        if package_name in self._cache:
            return self._cache[package_name]

        url = f"https://pypi.org/pypi/{package_name}/json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                response.raise_for_status()

                metadata = response.json()
                # Cache the result
                self._cache[package_name] = metadata
                return metadata

        except httpx.TimeoutException:
            raise Exception(f"Timeout fetching metadata for {package_name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise Exception(f"HTTP error fetching {package_name}: {e}")
        except Exception as e:
            raise Exception(f"Network error fetching {package_name}: {e}")

    def _is_compatible_with_python(self, release_files: list[dict], version_str: str) -> bool:
        """Check if a release is compatible with target Python version.
        
        Args:
            release_files: List of release file metadata
            version_str: Version string being checked
            
        Returns:
            True if compatible, False otherwise
        """
        if not self.python_version:
            return True  # No filtering if no target Python version

        # Check requires_python from release files
        for file_info in release_files:
            if "requires_python" in file_info:
                try:
                    requires_python = file_info["requires_python"]
                    if requires_python:
                        spec_set = SpecifierSet(requires_python)
                        target_version = Version(self.python_version)
                        if target_version not in spec_set:
                            return False
                except Exception:
                    continue  # Skip invalid requires_python specs

        return True

    def _calculate_semver_delta(self, entry: ManifestEntry, new_version: str) -> str:
        """Calculate semantic version delta.
        
        Args:
            entry: Original manifest entry
            new_version: New version to compare against
            
        Returns:
            Semver delta: "major", "minor", "patch", or "unknown"
        """
        if not entry.spec:
            return "unknown"  # No baseline to compare

        try:
            # Extract current version from spec if it's pinned
            current_version = None
            if entry.spec.startswith("=="):
                current_version = entry.spec[2:].strip()
            elif re.match(r"^\d+\.", entry.spec):
                # Plain version number
                current_version = entry.spec.strip()

            if not current_version:
                return "unknown"

            old_ver = Version(current_version)
            new_ver = Version(new_version)

            # Compare versions properly
            if new_ver > old_ver:
                if new_ver.major > old_ver.major:
                    return "major"
                elif new_ver.minor > old_ver.minor:
                    return "minor"
                elif new_ver.micro > old_ver.micro:
                    return "patch"

            return "unknown"

        except Exception:
            return "unknown"
