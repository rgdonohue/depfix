"""Core data models for DepFix."""

from dataclasses import dataclass


@dataclass
class ManifestEntry:
    """A single dependency entry in a manifest file."""

    name: str
    spec: str | None = None
    markers: str | None = None
    extras: list[str] | None = None
    source_type: str = "registry"  # registry, vcs, path, url


@dataclass
class Manifest:
    """A parsed dependency manifest."""

    ecosystem: str  # python, node
    raw: str
    entries: list[ManifestEntry]


@dataclass
class ResolutionResult:
    """Result of resolving a dependency to latest compatible version."""

    entry: ManifestEntry
    chosen_version: str
    reason: str
    semver_delta: str = "unknown"  # patch, minor, major, unknown
    advisories: list[dict] = None

    def __post_init__(self):
        if self.advisories is None:
            self.advisories = []


@dataclass
class UpdateReport:
    """Report of changes made to a manifest."""

    filename: str
    updated_content: str
    diff: str
    changes: list[ResolutionResult]
    notes: list[str]

    def __post_init__(self):
        if self.notes is None:
            self.notes = []
