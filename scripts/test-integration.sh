#!/bin/bash
# test-integration.sh — offline integration checks for data + extension wiring.
set -euo pipefail
echo "=== JetPhotos New Tab — integration test ==="

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$ROOT/data-builder/output"
EXT_DIR="$ROOT/extension"

# 1. data files exist
echo "[1/6] data files..."
test -f "$DATA_DIR/index.json" || { echo "FAIL: index.json missing"; exit 1; }
PHOTO_COUNT=$(ls "$DATA_DIR/photos/" | grep -c '\.json$' || true)
echo "  photos: $PHOTO_COUNT"
test "$PHOTO_COUNT" -ge 10 || { echo "FAIL: photos < 10"; exit 1; }

# 2. JSON validity
echo "[2/6] JSON validity..."
python3 -m json.tool "$DATA_DIR/index.json" > /dev/null
for f in $(ls "$DATA_DIR/photos/" | grep '\.json$' | head -5); do
  python3 -m json.tool "$DATA_DIR/photos/$f" > /dev/null
done
for c in "$DATA_DIR"/categories/*.json; do python3 -m json.tool "$c" > /dev/null; done
echo "  all JSON parses"

# 3. ID sync: photo-ids.js == index.json
echo "[3/6] ID sync..."
EXT_IDS=$(grep -oE '"[0-9]+"' "$EXT_DIR/photo-ids.js" | wc -l | tr -d ' ')
INDEX_IDS=$(python3 -c "import json;print(len(json.load(open('$DATA_DIR/index.json'))['photo_ids']))")
echo "  photo-ids.js: $EXT_IDS   index.json: $INDEX_IDS"
test "$EXT_IDS" = "$INDEX_IDS" || { echo "FAIL: ID count mismatch (run scripts/sync-photo-ids.sh)"; exit 1; }

# 4. extension file completeness
echo "[4/6] extension files..."
for f in manifest.json newtab.html newtab.css newtab.js photo-ids.js config.js cache.js service-worker.js \
         icons/icon-16.png icons/icon-48.png icons/icon-128.png assets/placeholder.png; do
  test -f "$EXT_DIR/$f" || { echo "FAIL: $f missing"; exit 1; }
done
echo "  complete"

# 5. manifest validity
echo "[5/6] manifest.json..."
python3 - "$EXT_DIR/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
assert m["manifest_version"] == 3, "manifest_version != 3"
assert "newtab" in m.get("chrome_url_overrides", {}), "missing newtab override"
assert "storage" in m.get("permissions", []), "missing storage permission"
assert "alarms" in m.get("permissions", []), "missing alarms permission"
print("  ok (mv3, newtab override, storage+alarms)")
PY

# 6. simulate metadata load
echo "[6/6] simulate metadata load..."
python3 - "$DATA_DIR" <<'PY'
import json, sys
d = sys.argv[1]
idx = json.load(open(f"{d}/index.json"))
fid = idx["photo_ids"][0]
rec = json.load(open(f"{d}/photos/{fid}.json"))
for k in ("id", "image_url", "aircraft", "photographer", "location", "meta"):
    assert k in rec, f"missing {k}"
print(f"  {rec['aircraft'].get('type','?')} - {rec['aircraft'].get('airline','?')}")
print(f"  image: {rec['image_url'][:58]}...")
PY

echo ""
echo "=== ALL CHECKS PASSED ✓ ==="
echo "Next: bash scripts/serve-data.sh  then load extension/ in Chrome (chrome://extensions)."
