# Aviation Gallery — New Tab

A Chrome (Manifest V3) new-tab extension that shows a full-screen aviation photo every time
you open a tab. Architecture clones **Google Earth View**: the extension ships only a list of
photo IDs; metadata is fetched at runtime from static JSON, and images load straight from the
JetPhotos CDN.

```
extension (photo-ids.js, <50KB)  →  GitHub Pages (photos/{id}.json)  →  JetPhotos CDN (image)
        Layer 1                            Layer 2                          Layer 3
```

Three layers are fully decoupled: updating the photo library is a `git push` of new JSON — the
extension binary never changes.

## Repo layout
```
extension/          # the Chrome extension (load this in chrome://extensions)
  manifest.json  newtab.{html,css,js}  photo-ids.js  config.js  config.dev.js
  cache.js  service-worker.js  icons/  assets/placeholder.png
data-builder/       # one-shot Python build tool: curated URLs -> structured JSON
  scraper.py  classifier.py  validator.py  make_sample_data.py
  curated-urls.txt  requirements.txt  PARSING_GUIDE.md  samples/  output/
scripts/            # helpers (assets, sync, serve, test, deploy, package)
phase0-cdn-test/    # throwaway extension to verify CDN image loading in real Chrome
PHASE0_RESULT.md    # feasibility findings
```

## Quick start (local dev)
```bash
# 1) (sample data is already generated; to regenerate:)
cd data-builder && python3 make_sample_data.py --clean && cd ..

# 2) sync the ID list into the extension
bash scripts/sync-photo-ids.sh

# 3) sanity check everything
bash scripts/test-integration.sh        # 6/6 expected

# 4) serve the data locally
bash scripts/serve-data.sh               # http://localhost:8080  (Ctrl-C to stop)

# 5) point the extension at localhost: in extension/newtab.js switch the config import
#    to  ./config.dev.js , then load extension/ via chrome://extensions (Load unpacked).
#    Remember to switch back to ./config.js before packaging.
```

## Data pipeline & rights
The build tool turns a curated list of JetPhotos photo URLs into `output/photos/{id}.json`
plus `index.json` and `categories/*.json`.

> **Heads up (Phase 0):** `jetphotos.com` is behind Cloudflare and returns **HTTP 403** to
> plain scrapers, so direct `python scraper.py` fetching is blocked. The supported workflow is
> `--from-html`: open each curated page in your browser, *Save As → HTML only* into
> `data-builder/samples/<id>.html`, then `python scraper.py --from-html samples/`.

```bash
cd data-builder
pip install -r requirements.txt
python3 scraper.py --from-html samples/ --dry-run   # confirm extraction
python3 scraper.py --from-html samples/             # write JSON
python3 scraper.py --stats                          # category + CDN-verify stats
python3 validator.py                                # CDN liveness (>80% target)
```

**Rights & compliance.** Images belong to the photographers; the CDN belongs to JetPhotos.
This extension is a *discovery/attribution* tool (photographer credit, "Powered by JetPhotos",
"View original" link, no downloads). The current `output/` is **synthetic sample data**
(`meta._sample: true`) — replace it with real, **rights-cleared** photos you have permission to
feature, and confirm JetPhotos' Terms before publishing. The extension is source-agnostic:
`DATA_BASE_URL` in `config.js` can point at any host.

## Deploy
```bash
bash scripts/deploy-data.sh     # stages data-builder/gh-pages/ + push instructions
# set extension/config.js DATA_BASE_URL to https://<you>.github.io/jetphotos-data
bash scripts/package.sh         # -> aviation-gallery-newtab-v<version>.zip  (<100KB)
```

## Keyboard
`Space` / `→` next · `←` previous (session) · `F` favorite · `I` toggle info · `Esc` hide info.

## Maintenance
- Add photos: append URLs → `scraper.py --from-html` (or `--incremental`) → `sync-photo-ids.sh`
  → `deploy-data.sh` → push. New tabs pick up new data automatically.
- Update bundled IDs: `sync-photo-ids.sh` then publish a new extension version.
- JetPhotos redesign: update selectors per `data-builder/PARSING_GUIDE.md`.

See `PHASE0_RESULT.md` for the feasibility analysis that shaped these choices.
