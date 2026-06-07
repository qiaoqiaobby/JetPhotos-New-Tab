# PHASE 0 — Feasibility result

**Verdict: 可行，但需调整数据采集策略 (Feasible, with a data-acquisition strategy change).**

## Hypothesis 1 — Can JetPhotos CDN images load in an extension newtab page?
**Inconclusive in this environment; verify in real Chrome (likely YES).**

- This sandboxed network cannot reach the CDN: `cdn.jetphotos.com` returns `HTTP 403`
  and resolves to `198.18.0.69` (a benchmark/sentinel IP), i.e. outbound to it is blocked here.
- Therefore the CDN test must be run in your real browser. A ready-made probe extension is
  provided: **`phase0-cdn-test/`**.
  - Load it via `chrome://extensions` → Developer mode → *Load unpacked* → select `phase0-cdn-test/`.
  - Open a new tab; paste **real** CDN URLs (from a photo page's `og:image`, or right-click →
    Copy image address); the page reports which of `full` / `400` / `200` load + timing.
- Expectation (per the static doc, §6): an extension page's Referer is `chrome-extension://…`,
  which most CDNs don't hotlink-block, so `full` will usually load. If `full` is blocked, the
  runtime auto-degrades `full → 400 → 200`, and finally to the bundled placeholder.

## Hypothesis 2 — Is the JetPhotos photo page parseable?
**YES for the fields, but NOT via plain HTTP scraping.**

- `https://www.jetphotos.com/photo/...` returns **`HTTP 403` — Cloudflare "Attention Required"
  (CAPTCHA)** to `curl`/`requests`. Direct-fetch scraping is blocked. (I did not attempt to
  bypass the CAPTCHA.)
- The page *structure* is parseable: the extraction rules are documented in
  `data-builder/PARSING_GUIDE.md` and the parser was **proven end-to-end** against a
  representative fixture (`data-builder/samples/990001.html`), correctly extracting
  aircraft type / registration / airline / photographer (+ profile) / airport (ICAO/IATA/
  country) / image_url and deriving the three CDN sizes.
- **Adjustment:** acquire HTML via the browser, not via bots. The scraper supports
  `--from-html samples/` to parse pages you Save-As from your real (logged-in) browser.
  Manual metadata entry is the conservative fallback. (Future: a headless/rendering step or a
  Cloudflare-aware fetch can re-enable `python scraper.py` direct mode.)

## Core-field check (required ≥3: aircraft_type, photographer, image_url)
✅ All present and verified via the fixture parse:
`Boeing 747-830` · photographer `Jane Doe` · `https://cdn.jetphotos.com/full/6/123456_1700000000.jpg`.

## Decision
Proceed to Phases 1–5. Build pipeline + extension are complete and verified offline. Real data
collection uses the `--from-html` path (rights-cleared, browser-saved pages) instead of automated
scraping. Live CDN image loading to be confirmed once via `phase0-cdn-test/` in real Chrome.
