#!/bin/bash
# deploy-data.sh — publish data-builder/output to the GitHub Pages data repo.
#   bash scripts/deploy-data.sh          # sync + commit locally (prints push hint)
#   bash scripts/deploy-data.sh --push   # sync + commit + push to origin/main
# The gh-pages/ folder is a persistent git clone of your jetphotos-data repo;
# its .git is preserved across runs (only the data files are replaced).
set -euo pipefail
cd "$(dirname "$0")/.."

DATA_DIR="data-builder/output"
DEPLOY_DIR="data-builder/gh-pages"
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1

test -f "$DATA_DIR/index.json" || { echo "ERROR: $DATA_DIR/index.json missing. Build first."; exit 1; }

mkdir -p "$DEPLOY_DIR"
# Replace data content but keep .git (so this stays a real clone we can push).
find "$DEPLOY_DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp "$DATA_DIR/index.json" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/photos" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/categories" "$DEPLOY_DIR/"
cat > "$DEPLOY_DIR/_headers" <<'EOF'
/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=3600
EOF
touch "$DEPLOY_DIR/.nojekyll"

COUNT=$(ls "$DEPLOY_DIR/photos" | grep -c '\.json$' || true)
echo "Staged $COUNT photos into $DEPLOY_DIR"

if [ -d "$DEPLOY_DIR/.git" ]; then
  ( cd "$DEPLOY_DIR"
    git add -A
    if git diff --cached --quiet; then
      echo "No data changes to commit."
    else
      git commit -q -m "data: update (${COUNT} photos)"
      echo "Committed."
    fi
    if [ "$PUSH" = 1 ]; then
      git pull --rebase origin main >/dev/null 2>&1 || true
      git push origin main
      echo "Pushed to origin/main."
    else
      echo "Local commit only. Publish with:  bash scripts/deploy-data.sh --push"
    fi )
else
  echo ""
  echo "First-time setup (no .git yet):"
  echo "  cd $DEPLOY_DIR"
  echo "  git init && git add -A && git commit -m 'data: initial deploy'"
  echo "  git branch -M main && git remote add origin https://github.com/<you>/jetphotos-data.git"
  echo "  git push -u origin main   # then enable Pages: Settings > Pages > main / root"
fi
