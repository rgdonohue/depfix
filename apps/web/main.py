"""FastAPI web application for DepFix."""

import asyncio
from io import StringIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.detect import identify
from core.models import ResolutionResult
from core.parse_python import parse_requirements
from core.resolve_python import PythonResolver

app = FastAPI(
    title="DepFix",
    description="Update dependency manifests to latest compatible versions",
    version="0.1.0",
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="apps/web/static"), name="static")


class UpdateRequest(BaseModel):
    """Request model for updating dependencies."""
    content: str
    python_version: Optional[str] = None
    ecosystem: Optional[str] = None
    dry_run: bool = True


class UpdateResponse(BaseModel):
    """Response model for dependency updates."""
    original_content: str
    updated_content: str
    changes: list[dict]
    has_changes: bool
    ecosystem: str


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main application page."""
    return get_index_html()


@app.get("/favicon.ico")
async def favicon():
    """Return a simple favicon to prevent 404 errors."""
    # Simple 1x1 transparent PNG
    favicon_data = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00'
        b'\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\x12IDAT\x08\x1dc\xf8\x00\x00'
        b'\x00\x01\x00\x01u\x02\x81\xa3\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return Response(content=favicon_data, media_type="image/png")


@app.post("/api/update", response_model=UpdateResponse)
async def update_dependencies(request: UpdateRequest):
    """Update dependencies from text content."""
    try:
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="No content provided")

        # Detect ecosystem
        ecosystem = request.ecosystem or identify(content)
        
        if ecosystem != "python":
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported ecosystem: {ecosystem}. Only Python is currently supported."
            )

        # Parse manifest
        manifest = parse_requirements(content)
        
        if not manifest.entries:
            raise HTTPException(status_code=400, detail="No dependencies found to update")

        # Resolve versions
        resolver = PythonResolver(python_version=request.python_version)
        results = await resolver.resolve_entries(manifest.entries)

        # Check for changes and generate updated content
        has_changes = _has_changes(results)
        updated_content = _update_content(content, results) if has_changes else content
        
        # Format changes for UI
        changes = [
            {
                "name": result.entry.name,
                "current_version": result.entry.spec or "unspecified",
                "new_version": result.chosen_version,
                "reason": result.reason,
                "semver_delta": result.semver_delta,
                "has_change": _entry_has_change(result)
            }
            for result in results
        ]

        return UpdateResponse(
            original_content=content,
            updated_content=updated_content,
            changes=changes,
            has_changes=has_changes,
            ecosystem=ecosystem
        )

    except HTTPException:
        # Re-raise HTTP exceptions (don't convert to 500)
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing dependencies: {str(e)}")


@app.post("/api/upload", response_model=UpdateResponse)
async def upload_file(
    file: UploadFile = File(...),
    python_version: Optional[str] = Form(None),
    ecosystem: Optional[str] = Form(None)
):
    """Upload and process a requirements file."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        # Read file content
        content = await file.read()
        text_content = content.decode("utf-8")
        
        # Process using the same logic as text input
        request = UpdateRequest(
            content=text_content,
            python_version=python_version,
            ecosystem=ecosystem,
            dry_run=True
        )
        
        return await update_dependencies(request)
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text")
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.post("/api/download")
async def download_updated_file(request: UpdateRequest):
    """Generate and download an updated requirements file."""
    try:
        # Process the content to get updates
        response = await update_dependencies(request)
        
        if not response.has_changes:
            raise HTTPException(status_code=400, detail="No changes to download")
        
        # Create temporary file
        temp_file = Path("/tmp/requirements_updated.txt")
        temp_file.write_text(response.updated_content)
        
        return FileResponse(
            path=temp_file,
            filename="requirements_updated.txt",
            media_type="text/plain"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating file: {str(e)}")


def _has_changes(results: list[ResolutionResult]) -> bool:
    """Check if there are any actual changes."""
    return any(_entry_has_change(result) for result in results)


def _entry_has_change(result: ResolutionResult) -> bool:
    """Check if a single entry has changes."""
    if not result.entry.spec:
        return True  # No spec means it's a change (pinning to specific version)
    
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
    
    return False


def _update_content(content: str, results: list[ResolutionResult]) -> str:
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
            # Replace with pinned version if there's a change
            if _entry_has_change(result):
                new_line = f"{result.entry.name}=={result.chosen_version}"
                # Preserve any trailing comments
                if "#" in line:
                    comment = line.split("#", 1)[1]
                    new_line += f"  # {comment}"
                updated_lines.append(new_line)
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)
    
    return "\n".join(updated_lines)


def get_index_html() -> str:
    """Return the main HTML page."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DepFix - Dependency Updater</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🔧</text></svg>">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css" rel="stylesheet">
        <style>
            .diff-line { font-family: 'Courier New', monospace; }
            .diff-added { background-color: #d4edda; color: #155724; }
            .diff-removed { background-color: #f8d7da; color: #721c24; }
            .upload-area { 
                border: 2px dashed #dee2e6; 
                padding: 2rem; 
                text-align: center; 
                border-radius: 0.375rem;
                transition: border-color 0.2s;
            }
            .upload-area:hover { border-color: #0d6efd; }
            .upload-area.dragover { border-color: #0d6efd; background-color: #f8f9fa; }
            .package-item { transition: background-color 0.2s; }
            .package-item:hover { background-color: #f8f9fa; }
            .semver-badge { font-size: 0.75rem; }
        </style>
    </head>
    <body>
        <div class="container-fluid py-4">
            <div class="row">
                <div class="col-12">
                    <div class="text-center mb-5">
                        <h1 class="display-4 fw-bold text-primary">DepFix</h1>
                        <p class="lead text-muted">Update your Python dependencies to the latest compatible versions</p>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-lg-6 mb-4">
                    <div class="card h-100">
                        <div class="card-header">
                            <h3 class="card-title mb-0">📄 Input Requirements</h3>
                        </div>
                        <div class="card-body">
                            <!-- File Upload -->
                            <div class="upload-area mb-3" id="uploadArea">
                                <h5>📁 Upload requirements.txt</h5>
                                <p class="text-muted mb-2">Drop your file here or click to browse</p>
                                <input type="file" id="fileInput" class="d-none" accept=".txt">
                                <button class="btn btn-outline-primary" onclick="document.getElementById('fileInput').click()">Choose File</button>
                            </div>
                            
                            <div class="text-center mb-3">
                                <span class="text-muted">--- OR ---</span>
                            </div>
                            
                            <!-- Text Input -->
                            <textarea 
                                id="requirementsInput" 
                                class="form-control font-monospace" 
                                rows="12" 
                                placeholder="Paste your requirements.txt content here:&#10;&#10;fastapi>=0.85.0&#10;uvicorn>=0.18.0&#10;requests>=2.28.0&#10;pandas>=1.4.0"
                            ></textarea>
                            
                            <!-- Options -->
                            <div class="row mt-3">
                                <div class="col-md-6">
                                    <label for="pythonVersion" class="form-label">🐍 Python Version</label>
                                    <input type="text" id="pythonVersion" class="form-control" placeholder="3.11" />
                                </div>
                                <div class="col-md-6">
                                    <label for="ecosystem" class="form-label">🔧 Ecosystem</label>
                                    <select id="ecosystem" class="form-select">
                                        <option value="">Auto-detect</option>
                                        <option value="python">Python</option>
                                    </select>
                                </div>
                            </div>
                            
                            <button id="analyzeBtn" class="btn btn-primary w-100 mt-3" disabled>
                                <span id="analyzeSpinner" class="spinner-border spinner-border-sm me-2 d-none"></span>
                                🔍 Analyze Dependencies
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-6 mb-4">
                    <div class="card h-100">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h3 class="card-title mb-0">📊 Update Preview</h3>
                            <button id="downloadBtn" class="btn btn-success btn-sm d-none">
                                📥 Download Updated
                            </button>
                        </div>
                        <div class="card-body">
                            <div id="resultsContainer" class="d-none">
                                <div id="summaryAlert"></div>
                                
                                <!-- Package Changes -->
                                <div id="changesContainer" class="mb-3"></div>
                                
                                <!-- Updated Content -->
                                <div class="mt-4">
                                    <h6>📝 Updated Requirements:</h6>
                                    <pre id="updatedContent" class="bg-light p-3 rounded font-monospace small"></pre>
                                </div>
                            </div>
                            
                            <div id="placeholderMessage" class="text-center text-muted py-5">
                                <i class="display-4 text-muted">📋</i>
                                <p class="mt-3">Upload a file or paste requirements to see updates</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            const fileInput = document.getElementById('fileInput');
            const uploadArea = document.getElementById('uploadArea');
            const requirementsInput = document.getElementById('requirementsInput');
            const analyzeBtn = document.getElementById('analyzeBtn');
            const analyzeSpinner = document.getElementById('analyzeSpinner');
            const resultsContainer = document.getElementById('resultsContainer');
            const placeholderMessage = document.getElementById('placeholderMessage');
            const summaryAlert = document.getElementById('summaryAlert');
            const changesContainer = document.getElementById('changesContainer');
            const updatedContent = document.getElementById('updatedContent');
            const downloadBtn = document.getElementById('downloadBtn');
            
            let currentResults = null;

            // File upload handling
            fileInput.addEventListener('change', handleFileSelect);
            uploadArea.addEventListener('click', () => fileInput.click());
            uploadArea.addEventListener('dragover', handleDragOver);
            uploadArea.addEventListener('drop', handleFileDrop);
            uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
            
            // Text input handling
            requirementsInput.addEventListener('input', () => {
                updateAnalyzeButton();
            });
            
            // Analyze button
            analyzeBtn.addEventListener('click', analyzeDependencies);
            
            // Download button
            downloadBtn.addEventListener('click', downloadUpdatedFile);

            function handleDragOver(e) {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            }
            
            function handleFileDrop(e) {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    handleFile(files[0]);
                }
            }
            
            function handleFileSelect(e) {
                const files = e.target.files;
                if (files.length > 0) {
                    handleFile(files[0]);
                }
            }
            
            function handleFile(file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    requirementsInput.value = e.target.result;
                    updateAnalyzeButton();
                };
                reader.readAsText(file);
            }
            
            function updateAnalyzeButton() {
                const hasContent = requirementsInput.value.trim().length > 0;
                analyzeBtn.disabled = !hasContent;
            }
            
            async function analyzeDependencies() {
                const content = requirementsInput.value.trim();
                if (!content) return;
                
                // Show loading state
                analyzeBtn.disabled = true;
                analyzeSpinner.classList.remove('d-none');
                
                try {
                    const response = await fetch('/api/update', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            content: content,
                            python_version: document.getElementById('pythonVersion').value || null,
                            ecosystem: document.getElementById('ecosystem').value || null,
                            dry_run: true
                        })
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.detail || 'Failed to analyze dependencies');
                    }
                    
                    const results = await response.json();
                    currentResults = results;
                    displayResults(results);
                    
                } catch (error) {
                    showError('Error analyzing dependencies: ' + error.message);
                } finally {
                    // Hide loading state
                    analyzeBtn.disabled = false;
                    analyzeSpinner.classList.add('d-none');
                }
            }
            
            function displayResults(results) {
                placeholderMessage.classList.add('d-none');
                resultsContainer.classList.remove('d-none');
                
                // Show summary
                const changesCount = results.changes.filter(c => c.has_change).length;
                const totalCount = results.changes.length;
                
                if (results.has_changes) {
                    summaryAlert.innerHTML = `
                        <div class="alert alert-success">
                            <strong>✅ ${changesCount} updates available</strong> out of ${totalCount} dependencies
                        </div>
                    `;
                    downloadBtn.classList.remove('d-none');
                } else {
                    summaryAlert.innerHTML = `
                        <div class="alert alert-info">
                            <strong>ℹ️ No updates needed</strong> - All ${totalCount} dependencies are up to date
                        </div>
                    `;
                    downloadBtn.classList.add('d-none');
                }
                
                // Show changes
                displayChanges(results.changes);
                
                // Show updated content
                updatedContent.textContent = results.updated_content;
            }
            
            function displayChanges(changes) {
                changesContainer.innerHTML = '';
                
                if (changes.length === 0) {
                    changesContainer.innerHTML = '<p class="text-muted">No dependencies found.</p>';
                    return;
                }
                
                const changesHtml = changes.map(change => {
                    const badgeClass = change.has_change ? 'bg-success' : 'bg-secondary';
                    const changeIcon = change.has_change ? '⬆️' : '✅';
                    const versionText = change.has_change ? 
                        `${change.current_version} → ${change.new_version}` : 
                        change.new_version;
                    
                    return `
                        <div class="package-item border rounded p-3 mb-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div class="flex-grow-1">
                                    <strong>${change.name}</strong>
                                    <div class="text-muted small mt-1">${change.reason}</div>
                                </div>
                                <div class="text-end">
                                    <span class="badge ${badgeClass} semver-badge">${changeIcon} ${versionText}</span>
                                    ${change.semver_delta !== 'unknown' ? 
                                        `<br><small class="text-muted">${change.semver_delta}</small>` : ''
                                    }
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
                
                changesContainer.innerHTML = `
                    <div>
                        <h6>📦 Package Analysis:</h6>
                        ${changesHtml}
                    </div>
                `;
            }
            
            async function downloadUpdatedFile() {
                if (!currentResults) return;
                
                try {
                    const response = await fetch('/api/download', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            content: currentResults.original_content,
                            python_version: document.getElementById('pythonVersion').value || null,
                            ecosystem: document.getElementById('ecosystem').value || null,
                            dry_run: false
                        })
                    });
                    
                    if (!response.ok) {
                        throw new Error('Failed to generate download');
                    }
                    
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'requirements_updated.txt';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                    
                } catch (error) {
                    showError('Error downloading file: ' + error.message);
                }
            }
            
            function showError(message) {
                summaryAlert.innerHTML = `
                    <div class="alert alert-danger">
                        <strong>❌ Error:</strong> ${message}
                    </div>
                `;
                resultsContainer.classList.remove('d-none');
                placeholderMessage.classList.add('d-none');
                downloadBtn.classList.add('d-none');
            }
            
            // Initialize
            updateAnalyzeButton();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)