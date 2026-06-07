#!/bin/bash
# deploy-data.sh — stage data-builder/output into a gh-pages/ folder ready to push.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA_DIR="data-builder/output"
DEPLOY_DIR="data-builder/gh-pages"

test -f "$DATA_DIR/index.json" || { echo "ERROR: $DATA_DIR/index.json missing. Build first."; exit 1; }

rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
cp "$DATA_DIR/index.json" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/photos" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/categories" "$DEPLOY_DIR/"

# GitHub Pages serves Access-Control-Allow-Origin:* by default. _headers is a no-op
# on GH Pages but harmless (and correct if you later move to Cloudflare/Netlify Pages).
cat > "$DEPLOY_DIR/_headers" <<'EOF'
/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=3600
EOF

# .nojekyll so files/dirs are served verbatim (no Jekyll processing).
touch "$DEPLOY_DIR/.nojekyll"

COUNT=$(ls "$DEPLOY_DIR/photos" | grep -c '\.json$' || true)
echo "Staged $COUNT photos into $DEPLOY_DIR"
echo ""
echo "Next (manual):"
echo "  1. Create a GitHub repo, e.g.  jetphotos-data"
echo "  2. cd $DEPLOY_DIR"
echo "  3. git init && git add -A && git commit -m 'data: initial deploy'"
echo "  4. git branch -M main && git remote add origin https://github.com/<you>/jetphotos-data.git"
echo "  5. git push -u origin main"
echo "  6. Repo Settings → Pages → Source: main / root"
echo "  7. Verify https://<you>.github.io/jetphotos-data/index.json"
echo "  8. Set DATA_BASE_URL in extension/config.js to that base URL."
