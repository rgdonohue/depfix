#!/usr/bin/env python3
"""Start the DepFix web application."""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting DepFix Web Application...")
    print("📍 URL: http://localhost:8000")
    print("📄 API docs: http://localhost:8000/docs")
    print("🛑 Press Ctrl+C to stop")
    print()
    
    uvicorn.run(
        "apps.web.main:app",
        host="0.0.0.0", 
        port=8000,
        reload=True,
        reload_dirs=["apps", "core"]
    )