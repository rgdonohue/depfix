# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DepFix is a command-line tool and web service that updates dependency manifests (requirements.txt, package.json) to the latest compatible versions. It's designed for rapid prototyping environments where automated dependency bots like Renovate/Dependabot aren't practical.

**Core Value Proposition:** Paste a manifest → get the latest compatible versions, a clean diff, and optional OSV security notes. Zero repo setup required.

## Quick Start Commands

### Initial Setup
```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup project
uv init depfix && cd depfix
uv add fastapi uvicorn httpx packaging typer rich
uv add --dev pytest pytest-asyncio pytest-mock ruff mypy pre-commit
uv sync

# Development workflow
make dev          # Install deps, setup pre-commit  
make test         # Run test suite
make web          # Start FastAPI dev server
make lint         # Run ruff linting
make typecheck    # Run mypy type checking
```

### CLI Usage (planned interface)
```bash
depfix update requirements.txt -i --python 3.11
depfix update requirements.txt --check-osv --block-high
depfix update requirements.txt package.json --out outdir/
depfix update requirements.txt --dry-run --format json
```

## Architecture

### Repository Structure
```
repo/
  apps/cli/           # CLI with typer
  apps/web/           # FastAPI web API  
  core/               # Core logic modules
    detect.py         # Ecosystem detection
    parse_python.py   # Requirements.txt parser
    parse_node.py     # package.json parser  
    resolve_python.py # Python resolver (uv integration)
    resolve_node.py   # npm registry resolver
    osv.py           # OSV vulnerability checker
    models.py        # Data models
  tests/data/         # Test fixtures and golden files
```

### Core Components & Flow

1. **Detector** → identifies Python/Node from filename/content
2. **Parser** → extracts packages with constraints, preserves formatting
3. **Resolver** → queries registries for latest compatible versions
4. **OSV Checker** → scans for vulnerabilities (optional)
5. **Writer** → generates updated manifest preserving comments/structure
6. **Diff Generator** → shows changes with risk annotations

### Key Technical Decisions

- **Python 3.11+** with async/await throughout
- **uv** for Python package resolution (faster than pip)
- **httpx** for async HTTP with connection pooling
- **packaging** library for PEP 440 version handling
- **Preserve formatting** - comments, ordering, whitespace maintained

## Implementation Strategy

### TDD Approach
```bash
# Red-Green-Refactor cycle with commits:
git commit -m "test: add failing test for requirements parsing"
git commit -m "feat: minimal parser to pass test" 
git commit -m "refactor: robust parser with error handling"
```

### Milestones
1. **M0**: Project scaffold, core models, test infrastructure
2. **M1**: Python parsing/resolution with CLI integration
3. **M2**: OSV vulnerability checking and security policies
4. **M3**: Node.js package.json support
5. **M4**: Web API with FastAPI
6. **M5**: Polish, documentation, Docker

## Performance & Quality Requirements

### Performance Targets
- **< 5s** for 30 dependencies (typical)
- **< 15s** worst-case with cold cache
- **6-8 concurrent** registry queries max
- **30s timeout** per registry, 10s per OSV query

### Testing Requirements
- **Unit tests** with mocks for all core components
- **Golden tests** for exact output verification
- **Integration tests** for end-to-end flows
- **Performance benchmarks** in CI

### Code Quality
- **ruff** for formatting and linting
- **mypy** for type checking
- **pytest** with async support
- **Pre-commit hooks** for quality gates

## Key Behaviors

### Python Support
- Parse requirements.txt with comments, markers, extras
- Handle PEP 440 specifiers and environment markers  
- Pin to latest by default for deterministic results
- Preserve non-package lines (comments, VCS deps) as-is

### Node.js Support
- Parse package.json dependencies and devDependencies
- Respect semver ranges (^, ~, >=) when updating
- Query npm registry with proper rate limiting
- Maintain JSON formatting and key ordering

### Security Features
- OSV database integration for vulnerability scanning
- `--block-high` flag to prevent vulnerable updates
- Risk annotations (patch/minor/major semver changes)
- Privacy-first: no manifest storage beyond request lifecycle

## Error Handling & Exit Codes

- **Graceful degradation**: partial updates on network failures
- **Clear messaging**: skip malformed entries with warnings
- **Exit codes**: 0=success, 2=no changes, 3=blocked by policy, 4=parse error, 5=resolver error, 6=network timeout

## Important Implementation Notes

- Use **uv** commands for Python package operations where possible
- Implement **async/await** throughout for I/O operations
- Design **pluggable resolvers** for easier testing with mocks
- Focus on **preserving user formatting** in output files
- Add **comprehensive logging** for debugging resolution decisions