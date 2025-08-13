# DepFix CLI — Usage & Interface Spec (MVP)

## Purpose

Command‑line tool to update dependency manifests to the **latest compatible** versions for rapid prototypes without repo automation.

## Primary Command

`depfix update <paths...> [options]`

* Accepts one or more manifest paths.
* Supports `requirements.txt` (Python) and `package.json` (Node) in the MVP.
* `-` as a path means read from **stdin**; `--out -` writes to **stdout**.

### Minimal Examples

* Update a single Python manifest (write to new file in same dir).
* Edit in place.
* Process multiple files at once (Python + Node).
* Read from stdin and write to stdout.

(Exact example commands are in the project README; this spec defines behavior.)

## Behavior for `requirements.txt`

* **Detection:** If filename is `requirements.txt` or content matches Python requirement lines, treat as Python.
* **Parsing:**

  * Support comments `# ...`, blank lines, `name[extras]`, PEP 440 specifiers (`==`, `>=`, `<=`, `~=`, ranges), and **environment markers** (e.g., `; python_version >= '3.10'`).
  * Preserve non‑entry lines verbatim when writing.
* **Resolution:**

  * Determine target Python version (see `--python`), fetch available versions from the registry, filter by specifier + markers + target Python, and choose **max satisfying**.
  * If no version specifier is present, default policy is to **pin to latest** (deterministic), unless `--preserve-unpinned` is set.
* **Rendering:**

  * Only replace the version token; keep original ordering, comments, and markers.
* **Diff:**

  * Print a unified diff to the console unless `--quiet` is set.

## Key Options

* `--out <path | dir | ->`
  Where to write updated output. If a single input file is given and `--out` is a file path, write there; if multiple inputs, `--out` must be a **directory**. `--out -` writes to stdout.
* `-i, --in-place`
  Edit files in place. Mutually exclusive with `--out` unless `--out -` for diff only.
* `--engine <auto|python|node>`
  Force ecosystem when detection is ambiguous. Default `auto`.
* `--python <X.Y>`
  Target Python version for compatibility filtering (e.g., `3.11`). When omitted: infer from markers or use the interpreter’s version.
* `--node <major>`
  Target Node.js major (e.g., `20`). Node manifests only.
* `--check-osv` / `--block-high`
  Query OSV and annotate advisories; if `--block-high`, refuse to bump into known HIGH/CRITICAL vulns.
* `--allow-major` / `--no-allow-major`
  Allow or forbid major version jumps when a pinned version exists. Default allows major if still within declared range; forbid if explicitly pinned.
* `--dry-run`
  Do all work, print diff + report, **no file writes**.
* `--format <table|json>`
  Choose summary output format in the console. JSON includes a machine‑readable change report.
* `--timeout <seconds>`
  Network timeouts for registry/OSV queries.
* `--max-concurrency <N>`
  Cap parallel lookups.

## Exit Codes

* `0` — Success; files written or diff printed.
* `2` — No changes (already up‑to‑date).
* `3` — Blocked by policy (e.g., `--block-high` with HIGH/CRITICAL advisories).
* `4` — Parse error (malformed line/specifier).
* `5` — Resolver error (registry unavailable or invalid package).
* `6` — Network timeout or repeated transient failures.

## Reporting

* Console shows a compact table: package, from → to, semver delta, notes.
* `--format json` prints a structured report to stdout.
* Unified diff printed by default unless `--quiet`.

## Safety & Privacy

* Never sends file contents other than package names/versions to registries; uses public metadata endpoints.
* OSV lookups query only `{ecosystem, package, version}`.
* `--dry-run` for safe preview before writing.

## Examples (Behavioral Specs)

1. **Point at a single `requirements.txt` and edit in place**

   * Input: `depfix update requirements.txt -i --python 3.11 --check-osv`
   * Expected: Manifest rewritten with latest compatible versions; diff shown; exit `0`.

2. **Write to a new file without touching the original**

   * Input: `depfix update requirements.txt --out requirements.updated.txt`
   * Expected: New file created; original untouched; exit `0`.

3. **Multiple manifests with directory output**

   * Input: `depfix update requirements.txt package.json --out out/`
   * Expected: `out/requirements.txt` and `out/package.json` written; exit `0`.

4. **JSON report only (no write)**

   * Input: `depfix update requirements.txt --dry-run --format json`
   * Expected: JSON to stdout; exit `0` or `2` if no changes.

5. **Policy block on vulnerable latest**

   * Input: `depfix update requirements.txt --check-osv --block-high`
   * Expected: If latest has HIGH/CRITICAL advisory, process aborts with exit `3`.

## Notes on Edge Cases

* **VCS/URL/path deps**: left untouched and marked `non-updatable` in the report.
* **Marker‑exclusive deps** (e.g., `; python_version < '3.10'`): respected; if target `--python 3.11` excludes them, they remain but are flagged as not applicable.
* **Name normalization**: PEP 503 normalization for Python package names.
* **Non‑semver libs**: delta marked as `unknown` with PEP 440 comparison only.

## Future Flags (post‑MVP)

* `--lock` to regenerate lockfiles (`uv lock`, `npm install --package-lock-only`).
* `--prefer-lts` for Node.
* `--group dev` for grouped summaries.

---

**Answer to the core UX question:** Yes — the CLI is designed so you can *simply point at a `requirements.txt` file* and either update it in place or emit an updated copy, with a diff and (optionally) OSV annotations.
