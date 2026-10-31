"""Serve an exported site under /ecfr-analyzer/ like GitHub Pages (static files with HTTP Range).

Usage: uv run python app/tests/e2e/serve.py <site dir> <port>
"""

import sys

import uvicorn
from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles

app = Starlette()
app.mount("/ecfr-analyzer", StaticFiles(directory=sys.argv[1], html=True))
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
