"""CLI application for DepFix."""

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from core.detect import identify
from core.models import ResolutionResult
from core.parse_python import parse_requirements
from core.resolve_python import PythonResolver

console = Console()


def format_diff_output(
    original_content: str, results: list[ResolutionResult], file_path: str
) -> str:
    """Format diff-style output showing changes."""
    lines = [f"--- {file_path}"]
    lines.append(f"+++ {file_path}")

    for result in results:
        if result.entry.spec:
            old_line = f"{result.entry.name}{result.entry.spec}"
        else:
            old_line = result.entry.name

        new_line = f"{result.entry.name}=={result.chosen_version}"

        # Only show changes
        if old_line != new_line:
            lines.append(f"-{old_line}")
            lines.append(f"+{new_line}")

    return "\n".join(lines)


def format_json_output(results: list[ResolutionResult]) -> str:
    """Format JSON output."""
    reports = []
    for result in results:
        reports.append({
            "name": result.entry.name,
            "current_version": result.entry.spec,
            "chosen_version": result.chosen_version,
            "reason": result.reason,
            "semver_delta": result.semver_delta,
        })

    return json.dumps({"reports": reports}, indent=2)


def update_manifest_content(content: str, results: list[ResolutionResult]) -> str:
    """Update manifest content with resolved versions."""
    lines = content.splitlines()
    updated_lines = []

    # Create lookup for resolved packages
    resolved = {result.entry.name: result for result in results}

    for line in lines:
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            updated_lines.append(line)
            continue

        # Try to match package name from the line
        package_name = None
        for name in resolved:
            if line.strip().startswith(name):
                package_name = name
                break

        if package_name and package_name in resolved:
            result = resolved[package_name]
            # Replace with pinned version
            new_line = f"{result.entry.name}=={result.chosen_version}"
            # Preserve any trailing comments
            if "#" in line:
                comment = line.split("#", 1)[1]
                new_line += f"  # {comment}"
            updated_lines.append(new_line)
        else:
            updated_lines.append(line)

    return "\n".join(updated_lines)


def has_changes(results: list[ResolutionResult]) -> bool:
    """Check if there are any actual changes."""
    for result in results:
        if result.entry.spec:
            # Extract current version from spec
            current_version = None
            if result.entry.spec.startswith("=="):
                current_version = result.entry.spec[2:].strip()
            elif result.entry.spec and not result.entry.spec.startswith((">=", "<=", ">", "<", "~=", "!=")):
                # Plain version number
                current_version = result.entry.spec.strip()

            if current_version and current_version != result.chosen_version:
                return True
            elif not current_version:
                # Constraint that's not exact pin, consider it a change
                return True
        else:
            # No spec means it's a change (pinning to specific version)
            return True

    return False


app = typer.Typer(
    name="depfix",
    help="DepFix - Update dependency manifests to latest compatible versions",
    add_completion=False,
)

@app.command()
def update(
    file_path: str = typer.Argument(help="Path to manifest file: requirements.txt, package.json (use '-' for stdin)"),
    output: str | None = typer.Option(None, "--out", "-o", help="Output file (use '-' for stdout)"),
    in_place: bool = typer.Option(False, "--in-place", "-i", help="Update file in place"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without applying"),
    python_version: str | None = typer.Option(None, "--python", help="Target Python version"),
    engine: str | None = typer.Option(None, "--engine", help="Force specific ecosystem"),
    format_type: str = typer.Option("diff", "--format", help="Output format"),
) -> None:
    """DepFix - Update dependency manifest to latest compatible versions."""

    try:
        # Read input
        if file_path == "-":
            content = sys.stdin.read()
            display_path = "<stdin>"
        else:
            path_obj = Path(file_path)
            if not path_obj.exists():
                console.print(f"Error: File {file_path} not found", style="red")
                raise typer.Exit(1)
            content = path_obj.read_text()
            display_path = file_path

        # Detect ecosystem
        if engine:
            ecosystem = engine
        else:
            filename = file_path if file_path != "-" else None
            ecosystem = identify(content, filename)

        if ecosystem != "python":
            console.print(f"Error: Unsupported ecosystem: {ecosystem}", style="red")
            raise typer.Exit(1)

        # Parse manifest
        manifest = parse_requirements(content)

        if not manifest.entries:
            console.print("No dependencies found to update")
            raise typer.Exit(0)

        # Resolve versions
        resolver = PythonResolver(python_version=python_version)
        results = asyncio.run(resolver.resolve_entries(manifest.entries))

        # Check for changes
        if not has_changes(results):
            if format_type == "json":
                console.print(format_json_output(results))
            else:
                console.print("No updates available")
            raise typer.Exit(2)  # No changes exit code

        # Generate output
        if format_type == "json":
            output_content = format_json_output(results)
        elif dry_run:
            output_content = format_diff_output(content, results, display_path)
        else:
            output_content = update_manifest_content(content, results)

        # Write output
        if dry_run:
            console.print(output_content)
        elif in_place and file_path != "-":
            Path(file_path).write_text(output_content)
            console.print(f"Updated {file_path}")
        elif output:
            if output == "-":
                console.print(output_content)
            else:
                Path(output).write_text(output_content)
                console.print(f"Wrote updated manifest to {output}")
        elif file_path == "-" and not output:
            # Default: stdin to stdout
            console.print(output_content)
        else:
            console.print("Error: Specify --in-place, --out, or --dry-run", style="red")
            raise typer.Exit(1)

    except typer.Exit:
        # Re-raise typer exits (like Exit(2) for no changes)
        raise
    except Exception as e:
        console.print(f"Error: {e}", style="red")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
