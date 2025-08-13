# Project: Paste‑to‑Update Dependencies (Prototype Bootstrapper)

**Tagline:** Paste a manifest → get the latest *compatible* versions, a clean diff, and optional OSV security notes. Zero repo setup. Built for greenfield prototypes.

---

## 0) Executive Summary

LLM scaffolds often emit stale or broken dependency manifests (`requirements.txt`, `pyproject.toml`, `package.json`, etc.). Production teams rely on Renovate/Dependabot, but those assume a repo + CI and generate noisy PRs. For prototypes, we want a fast, manual, *trustable* refresh with compatibility checks.

**This MVP** delivers a minimal CLI + micro‑web UI that:

* Detects ecosystem(s) from pasted text or uploaded files.
* Resolves **latest compatible** versions using native resolvers (Python/JS first).
* Annotates changes with semver risk and **OSV** advisories.
* Outputs an updated manifest + unified diff. Optional zip download.

Time‑to‑value: < 1 minute from paste to updated file. No GitHub app required.

---

## 1) PRD — Product Requirements Document

### 1.1 Problem & Goals

* **Problem:** LLM‑generated manifests are out of date, inconsistent, or incompatible with each other and with the target runtime.
* **Primary Goal:** One‑shot, on‑demand refresh to the newest versions **that still satisfy declared constraints** (e.g., Python marker `>=3.10`, semver ranges like `^4.2.0`).
* **Secondary Goals:**

  * Provide a readable **diff** with risk labels (patch/minor/major, EOL engine bumps).
  * Flag known vulnerabilities via **OSV**.
  * Preserve comments and formatting where practical (best‑effort for MVP).

### 1.2 Target Users / Personas

* **Rapid prototypers** (AI/DS engineers, hackathon teams) with throwaway repos.
* **Consultants** doing one‑time modernization on legacy code without CI.
* **Researchers/analysts** who need working environments without PR automation.

### 1.3 Jobs‑to‑Be‑Done (JTBD)

* *When* I paste a stale manifest, *I want* the latest compatible versions, *so that* I can run my prototype **today** without installing a repo bot.
* *When* versions jump, *I want* a risk summary and release links, *so that* I can decide to pin or adjust code later.

### 1.4 Scope (MVP)

* **Ecosystems:** Python and JavaScript first.

  * Python: `requirements.txt` (basic), `pyproject.toml` (poetry/PEP 621 minimal read), environment markers, `==`, `>=`, `<=`, `~=`.
  * JS: `package.json` with npm/pnpm/yarn semantics; honor ranges (`^`, `~`, `>=`, pinned).
* **Inputs:** Paste text or upload file(s). Single manifest required; multi‑file allowed.
* **Outputs:** Updated manifest(s) + unified diff; JSON change report; optional OSV notes.
* **UX:**

  * **CLI:** `depfix update --in requirements.txt --out requirements.updated.txt --engine python --python 3.11`.
  * **Web:** Single screen: paste/upload → options → “Update” → diff + download.

### 1.5 Out‑of‑Scope (MVP)

* No PR automation or repo auth.
* No transitive lockfile regeneration (e.g., `poetry.lock`, `package-lock.json`), but we may optionally **emit commands** to regenerate locks.
* No multi‑platform build matrix testing; optional local quick import test is stubbed.

### 1.6 Non‑Functional Requirements

* **Deterministic:** Same input + registry state → same output.
* **Transparent:** Show how each version was chosen (source, constraint, decision note).
* **Private:** Never store manifests server‑side beyond request lifecycle (in‑memory, ephemeral tmpfs). CLI is local by default.
* **Fast:** < 5s typical for 30 deps; < 15s worst‑case on cold cache.

### 1.7 Success Metrics (MVP)

* TTV (time to valid updated manifest) median < 60s from page open.
* 90% of updates labelled **compatible** (no constraint violations).
* User perceived value: CSAT ≥ 4.2/5 in pilot feedback.

---

## 2) SDD — System Design Document

### 2.1 High‑Level Architecture

* **Modes:**

  1. **CLI (local‑first):** Python package `depfix` with adapters for Python/JS.
  2. **Micro‑Web:** FastAPI backend + simple React/Alpine front.
* **Core Engine:** Stateless orchestrator that:

  * Detects ecosystem → parses constraints → calls ecosystem resolver → normalizes results → generates diff/report → optional OSV lookup.
* **Caching:** On web service, per‑process LRU for registry metadata (respect cache headers). CLI can leverage local cache directories.

### 2.2 Components

1. **Detector** — Identify manifest type(s):

   * Heuristics by filename, extension, and content signatures (`[tool.poetry]`, `dependencies`, etc.).
2. **Parsers** — Convert text → internal model:

   * Python: parse lines, handle markers (`; python_version >= '3.10'`), extras, VCS URLs (MVP: passthrough/no update).
   * JS: parse `package.json` (`dependencies`, `devDependencies`).
3. **Resolvers** (adapters):

   * **PythonResolver**: shell out to `uv pip index` or use Python’s index APIs; compute **latest satisfying** version given specifier + markers + **target Python** (user option; default from system or parsed).
   * **NodeResolver**: query npm registry metadata (`dist-tags`, `versions`), apply semver ranges to pick max satisfying; respect `engines.node` if present.
4. **OSV Checker**:

   * For each (name, new\_version), query OSV; collect advisories; mark severity (if available).
5. **Risk Annotator**:

   * Semver delta (patch/minor/major). Python libs without semver use best‑effort PEP 440 comparison.
   * Engine constraints (e.g., requires Python 3.12).
6. **Renderer**:

   * **ManifestWriter**: write updated manifest preserving reasonable formatting (comments preserved in Python `requirements.txt` best‑effort; `package.json` pretty‑print with stable order).
   * **DiffGenerator**: unified diff + summary table.
7. **API Layer (Web)**:

   * `/api/update` accepts multipart or JSON; returns updated text + diff + report JSON.

### 2.3 Data Model (internal)

```ts
// Pseudotype
Manifest {
  ecosystem: 'python' | 'node';
  raw: string;
  entries: ManifestEntry[];
}

ManifestEntry {
  name: string;               // package name
  spec: string | null;        // raw constraint e.g. '>=2.0,<3.0' or '^4.2.0'
  markers?: string | null;    // python markers
  sourceType: 'pypi'|'npm'|'vcs'|'path'|'git'|'url';
  extras?: string[];
  dev?: boolean;              // node only
}

ResolutionResult {
  entry: ManifestEntry;
  chosenVersion: string;      // resolved max satisfying
  reason: string;             // rationale
  semverDelta: 'patch'|'minor'|'major'|'unknown';
  advisories?: OsvAdvisory[];
}
```

### 2.4 Algorithms (core logic)

**Latest Compatible Selection**

1. Parse spec → range set.
2. Fetch available versions (respect cache).
3. Filter versions by:

   * Satisfying the declared range (or any, if none).
   * Compatible with runtime engine (Python version / Node version), if detectable.
4. Choose **max(version)** after filters.
5. Annotate semver delta vs current locked/pinned version (if present), else vs lowest in range.
6. Optional: exclude versions with active high‑severity OSV advisories unless `--allow-vuln` flag.

**OSV Lookup**

* Input: ecosystem id (`PyPI`, `npm`), package name, version.
* Output: advisory list with id, summary, severity (if present), affected ranges.

### 2.5 API Design (Web MVP)

* `POST /api/update`

  * **Request:**

    * `files`: multipart file(s) *or* `content` (string) with `ecosystem` hint.
    * `options`: `{ engine: 'python'|'node'|'auto', pythonVersion?: '3.11', nodeVersion?: '20', allowMajor?: boolean, checkOSV?: boolean }`.
  * **Response:**

    ```json
    {
      "reports": [
        {
          "filename": "requirements.txt",
          "updated": "<text>",
          "diff": "<unified diff>",
          "changes": [
            {"name":"fastapi","from":"0.85.0","to":"0.112.0","delta":"major","osv": []}
          ],
          "notes": ["Python target set to 3.11"]
        }
      ]
    }
    ```

### 2.6 CLI Design

```
depfix update --in requirements.txt --out requirements.updated.txt \
  --engine python --python 3.11 --check-osv --only-compatible

# For Node
depfix update --in package.json --engine node --node 20 --out package.updated.json

# Multi-file
depfix update --in requirements.txt --in package.json --out outdir/
```

### 2.7 Error Handling

* **Network**: registry/OSV timeout → return partial updates + warnings; do not fail entire batch.
* **Invalid spec**: mark entry as `skipped` with message.
* **VCS/path deps**: preserve as‑is; report `non-updatable` in MVP.
* **Ecosystem mismatch**: return `400` with clear hint.

### 2.8 Security & Privacy

* Web: process manifests in memory; redact secrets lines if any (basic heuristics); no persistence beyond request lifecycle.
* CLI: local‑only operations by default.
* CORS limited to UI origin.

### 2.9 Performance Notes

* Parallelize resolver queries per entry (bounded concurrency: 6–8).
* Cache registry metadata by package name for session lifetime.

### 2.10 Observability

* Structured logs (JSON) with request id.
* Optional anonymous metrics (opt‑in) for pkg counts and duration.

---

## 3) Tech Spec — Implementation Details

### 3.1 Stack & Repo Layout

* **Language:** Python 3.11+
* **CLI/Backend:** FastAPI + `httpx` (async), `uvicorn` for dev.
* **Front‑end (MVP):** Minimal HTMX/Alpine or small React SPA (choose simplest).
* **Semver/PEP 440:** `packaging` for Python; `node-semver` via subprocess or a tiny TS helper bundled for web.

```
repo/
  apps/
    cli/                 # depfix CLI (click/typer)
    web/                 # FastAPI app + minimal front-end
  core/
    detect.py
    parse_python.py
    parse_node.py
    resolve_python.py
    resolve_node.py
    osv.py
    annotate.py
    write_python.py
    write_node.py
    diff.py
    models.py
  tests/
    data/
      python_small.txt
      package_small.json
    unit/
    integration/
  scripts/
    dev_bootstrap.sh
    run_web.sh
  Dockerfile
  pyproject.toml
  README.md
```

### 3.2 Key Modules & Contracts

* `detect.identify(content, filename?) -> EcosystemGuess`
* `parse_python.parse(text) -> Manifest`
* `resolve_python.update(manifest, py_ver) -> list[ResolutionResult]`
* `write_python.render(manifest, results) -> str`
* `diff.unified(old:str, new:str) -> str`
* `osv.query(pkg, version, eco) -> list[Advisory]`

### 3.3 External Interfaces

* **PyPI**: simple JSON API per package (versions list). For accuracy + speed, shelling to `uv` is acceptable in MVP.
* **npm registry**: `https://registry.npmjs.org/<pkg>` (full metadata). Respect rate limits.
* **OSV API**: query by package/ecosystem + version.

### 3.4 Version Rules

* **Python**: PEP 440 specifiers; preserve markers; if no spec, default to `==<latest>` **or** configurable `~=<latest.major>.<latest.minor>`; MVP default: `==latest` to maximize determinism.
* **Node**: If original uses a range, keep the same operator but shift upper bound by choosing a new base:

  * For `^x.y.z` → rewrite to `^<latest major>.<latest minor>.<latest patch>`.
  * For pinned `x.y.z` → bump to exact latest (configurable).

### 3.5 Formatting Preservation

* Python: preserve comments and ordering; update only the version token in lines `name[extras] spec ; markers` where possible.
* Node: pretty‑print JSON with 2‑space indent, keep key order `dependencies`, `devDependencies`.

### 3.6 Security Notes

* If OSV finds **HIGH/CRITICAL**, annotate and (if `--block-high`) refuse bump to a vulnerable version.
* Add a `--prefer-lts` flag for Node to prefer versions compatible with LTS engines.

### 3.7 Testing Strategy

* **Unit:** parsing, resolution logic, diff generation, OSV mock.
* **Golden tests:** input → expected updated manifest (snapshot files).
* **Integration:** spin local server; send multipart request; validate JSON report.
* **Smoke:** `examples/` manifests from popular stacks.

### 3.8 Example I/O

**Input (requirements.txt):**

```
fastapi==0.85.0
uvicorn>=0.18
pydantic~=1.10
httpx
```

**Options:** `python=3.11, checkOSV=true`
**Output (summary):**

```
fastapi 0.85.0 → 0.115.0  [major]
uvicorn >=0.18 → 0.32.1   [compatible]
pydantic ~=1.10 → 1.10.18 [patch]
httpx * → 0.27.2          [new]
```

(+ unified diff, + updated file)

---

## 4) Delivery Plan for Cursor Agent (Task Graph)

### 4.1 Milestones

1. **M0 — Bootstrap (Day 0–0.5)**

   * Repo scaffold, dev deps, CI smoke (lint/test), Dockerfile.
2. **M1 — Python Path (Day 1–2)**

   * Detector+Parser (Python), Resolver (using `uv` or JSON API), Writer, Diff.
   * CLI command `depfix update` working for Python.
3. **M2 — OSV + Risk (Day 2–3)**

   * OSV checker, semver delta annotator, JSON report.
4. **M3 — Node Path (Day 3–4)**

   * `package.json` parser, npm resolver, writer, diff.
5. **M4 — Web UI (Day 4–5)**

   * FastAPI `/api/update`, minimal front; paste/upload → result panel.
6. **M5 — Polish (Day 5)**

   * Docs, examples, golden tests, performance tune.

### 4.2 Repo Issues (pre‑write for Agent)

* **#1 Scaffold repo + CI**

  * Create `pyproject.toml` (poetry or uv), add core folders, stub modules, pre‑commit.
* **#2 Implement ecosystem detector**
* **#3 Python parser & writer with comments preserved**
* **#4 Python resolver with `uv` integration**
* **#5 Diff generator (unified) and JSON change report**
* **#6 OSV client (with retries and backoff)**
* **#7 Semver/PEP440 delta annotator**
* **#8 Node parser/writer**
* **#9 npm resolver**
* **#10 FastAPI endpoint + minimal UI**
* **#11 Tests: unit + integration + goldens**
* **#12 Dockerfile & README**

### 4.3 Acceptance Criteria (per milestone)

* **M1:** Given a Python manifest, `depfix update` emits updated file + diff; versions satisfy constraints; runtime `--python` respected.
* **M2:** JSON report includes semver delta and OSV advisories; `--block-high` prevents vulnerable bumps.
* **M3:** Same behavior for Node; `package.json` reprinted stable.
* **M4:** Web route accepts paste/upload; returns diff + updated text; no persistent storage.
* **M5:** All tests green; example manifests processed end‑to‑end < 10s.

### 4.4 Developer Experience (DX)

* `make dev` → installs deps, pre‑commit, run tests.
* `make web` → starts FastAPI + front.
* `make demo` → runs examples and writes `out/`.

---

## 5) Risk Register & Mitigations

* **Parsing edge cases:** comments, VCS, local paths → *Mitigation:* preserve as‑is, flag `non-updatable`.
* **Registry throttling:** npm rate limits → *Mitigation:* caching + bounded concurrency.
* **False confidence:** upgrades may still break at runtime → *Mitigation:* clear messaging; optional command suggestions to run tests/locks.
* **Formatting drift:** users care about whitespace → *Mitigation:* keep minimal re‑writes; provide `--no-reformat` where possible.

---

## 6) Future Extensions (Post‑MVP)

* Lockfile regeneration hooks (`uv lock`, `npm install --package-lock-only`).
* GitHub/GitLab PR mode.
* Multi‑manifest project graph diff (Python + Node + Dockerfile in one view).
* Release notes summarization per package.
* Additional ecosystems: Rust (Cargo), Go (go.mod), Java (Maven/Gradle), R.

---

## 7) Prompts & Instructions for Cursor Agent

**Global Agent Instructions:**

* Work milestone‑by‑milestone. Create small, reviewable PRs.
* For networked resolvers, first implement a pluggable interface; add a *mock* in tests.
* Emphasize deterministic output and explicit reasoning in commit messages.

**Task 1 Prompt (Scaffold):**

> Initialize a Python 3.11 project `depfix`. Add FastAPI, httpx, packaging, typer/click, uvicorn, pytest, ruff, mypy. Create the repo layout shown in Tech Spec §3.1. Add pre‑commit. Provide `make dev`, `make test`, `make web` targets.

**Task 2 Prompt (Detector):**

> Implement `core/detect.py` with `identify(content, filename)`. Return `'python'|'node'|'unknown'`. Use content signatures and filename hints.

**Task 3 Prompt (Python parse/write):**

> Implement line‑based parser for `requirements.txt` supporting comments, markers, extras, specifiers. Round‑trip a file with no changes. Writer must preserve non‑entry lines.

**Task 4 Prompt (Python resolve):**

> Implement `resolve_python.update()` that determines available versions (inject a provider; default to `uv` or PyPI JSON), filters by PEP 440 range and `pythonVersion`, and chooses the max satisfying. Return `ResolutionResult` entries.

**Task 5 Prompt (Diff & Report):**

> Implement unified diff and JSON change report with fields: name, from, to, delta, notes.

**Task 6 Prompt (OSV):**

> Implement `osv.query()` with retries; add `--check-osv` and `--block-high` flags in CLI.

**Task 7 Prompt (Node path):**

> Implement `parse_node`, `write_node`, and `resolve_node` using npm registry metadata. Support `dependencies` and `devDependencies`.

**Task 8 Prompt (Web API + UI):**

> Build `POST /api/update`. Accept paste or file upload. Return updated text + diff + JSON report. Implement a minimal front with paste box, options, and results panel.

**Task 9 Prompt (Tests):**

> Add unit and integration tests. Include golden snapshots in `tests/data/`. Ensure deterministic formatting.

**Task 10 Prompt (Docs & Docker):**

> Write README with quickstart, CLI usage, API example, and security notes. Create a slim Dockerfile.

---

## 8) Short Naming & Branding

* **Project codename:** **DepFix** or **FreshReqs**.
* CLI command: `depfix`.

---

## 9) Go/No‑Go Checklist (MVP Ready)

* [ ] Python manifests: parse → resolve → write → diff works.
* [ ] Node manifests: parse → resolve → write → diff works.
* [ ] OSV checks integrated and toggleable.
* [ ] Web endpoint returns full report for paste/upload.
* [ ] Tests green; examples ship; Docker image builds.

---

**Done right, this tool disappears into your flow: paste, update, move on.**
