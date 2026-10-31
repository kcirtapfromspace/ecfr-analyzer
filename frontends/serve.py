"""Serve a built candidate under /ecfr-analyzer/ like GitHub Pages (static files, HTTP Range).

Usage: uv run --with starlette --with uvicorn python serve.py <dir> <port>
"""

import sys

import uvicorn
from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles

app = Starlette()
app.mount("/ecfr-analyzer", StaticFiles(directory=sys.argv[1], html=True, follow_symlink=True))
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
