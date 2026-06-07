#!/bin/bash
# package.sh — produce a Chrome Web Store zip from extension/, excluding dev files.
set -euo pipefail
cd "$(dirname "$0")/.."

EXT_DIR="extension"
BUILD_DIR="build"
VERSION=$(python3 -c "import json;print(json.load(open('$EXT_DIR/manifest.json'))['version'])")
ZIP="aviation-gallery-newtab-v${VERSION}.zip"

# Guard: make sure newtab.js ships the PROD config import, not the dev one.
if grep -Eq '^[[:space:]]*import CONFIG from "\./config\.dev\.js"' "$EXT_DIR/newtab.js"; then
  echo "ERROR: newtab.js is importing config.dev.js. Switch back to ./config.js before packaging." >&2
  exit 1
fi

rm -rf "$BUILD_DIR" "$ZIP"
mkdir -p "$BUILD_DIR"

for f in manifest.json newtab.html newtab.css newtab.js photo-ids.js config.js \
         cache.js service-worker.js; do
  cp "$EXT_DIR/$f" "$BUILD_DIR/"
done
cp -r "$EXT_DIR/icons" "$BUILD_DIR/"
cp -r "$EXT_DIR/assets" "$BUILD_DIR/"
# Intentionally NOT copied: config.dev.js, any test.html, samples, etc.

( cd "$BUILD_DIR" && zip -rq "../$ZIP" . )

SIZE_BYTES=$(wc -c < "$ZIP" | tr -d ' ')
SIZE_HR=$(du -h "$ZIP" | cut -f1)
echo "Packaged: $ZIP  ($SIZE_HR)"
echo "Contents:"
unzip -l "$ZIP" | sed 's/^/  /'

# Fail if it sneaked in a dev file or got huge (>100KB).
if unzip -l "$ZIP" | grep -Eq 'config\.dev\.js|test\.html|samples/'; then
  echo "ERROR: dev files found in package!" >&2; exit 1
fi
if [ "$SIZE_BYTES" -gt 102400 ]; then
  echo "ERROR: package >100KB ($SIZE_BYTES bytes)." >&2; exit 1
fi
echo "OK: package is clean and <100KB."
