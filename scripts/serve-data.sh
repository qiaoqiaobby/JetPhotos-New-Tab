#!/bin/bash
# serve-data.sh — serve data-builder/output over HTTP with permissive CORS,
# so the extension (config.dev.js -> http://localhost:8080) can fetch metadata.
set -euo pipefail
cd "$(dirname "$0")/../data-builder/output"

PORT="${PORT:-8080}"
echo "Serving $(pwd)"
echo "  → http://localhost:${PORT}/index.json"
echo "  CORS: * (for Chrome extension testing).  Ctrl-C to stop."

python3 - "$PORT" <<'PY'
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(sys.argv[1])

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  " + (fmt % args) + "\n")

HTTPServer(('localhost', PORT), CORSHandler).serve_forever()
PY
