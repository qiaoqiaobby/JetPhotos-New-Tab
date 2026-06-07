# PARSING_GUIDE.md — JetPhotos photo-page extraction rules

> Status: **verified against a real saved page** (`samples/11354279.html`,
> EI-IJM Ryanair 737 MAX). The single most reliable source is the `og:title`
> meta tag; semantic `/aircraft/` `/airline/` links are used where cleaner.
> Implemented in `scraper.py::parse_photo_html`.

## og:title — the primary source ⭐
Format: **`REG | TYPE | AIRLINE | PHOTOGRAPHER | JetPhotos`**
Example: `EI-IJM | Boeing 737-8-200 MAX | Ryanair | Seres23 | JetPhotos`
Parsed by `_parse_og_title()` → `{reg, type, airline, photographer}` (drops the
trailing "JetPhotos"). Used as the source of truth for **registration** and
**photographer name**, and as fallback for type/airline.

## Photo ID
From URL / `<link rel=canonical>` / `og:url`: `"/photo/(\d+)"`. e.g. `11354279`.

## image_url / thumb_url / fallback_url
Primary: `<meta property="og:image">`.
Fallbacks: `img.large-photo__img[src]`, then regex any
`https://cdn.jetphotos.com/(full|\d+)/...jpg`.
Sizes are **derived** by swapping the size segment:
`og:image = .../full/6/1075880_1716278472.jpg`
→ thumb `.../400/6/...`, fallback `.../200/6/...`.

## aircraft.type
`a[href*="/aircraft/"]` text → e.g. `Boeing 737-8-200 MAX`. Fallback: `og:title[1]`.

## aircraft.airline
`a[href*="/airline/"]` text → e.g. `Ryanair`. Fallback: `og:title[2]`.

## aircraft.registration
`og:title[0]` (clean), e.g. `EI-IJM`.
⚠️ The `a[href*="/registration/"]` link text is **`EI-IJM photos`** — the
` photos` suffix is stripped by `_clean_reg()`.

## photographer.name + profile_url
**Name:** `og:title[3]` → e.g. `Seres23`.
⚠️ The author's own `/photographer/` link text is just **`Profile`** / `Photos`
(not the name), and the page also lists *other* photographers (related photos).
**profile_url:** `_photographer_href()` picks the numeric `/photographer/<id>`
link whose text is `Profile`/`Photos` → e.g. `.../photographer/185667`.

## location (airport / icao / iata / country)
`a[href*="/airport/"]` first link text, e.g.
`Budapest Liszt Ferenc - LHBP, Hungary`. Parsed by `_split_airport()`:
- `(FRA / EDDF)` → iata=FRA, icao=EDDF  (older format)
- `- LHBP` → icao=LHBP                  (current format)
- trailing `, Country` → country
- display **name** is cleaned to `Budapest Liszt Ferenc`.

## meta.category
`classifier.py::classify(type, ...)` → widebody / narrowbody / military / cargo /
retro / bizjet / special_livery / helicopter / other. (737 MAX → narrowbody.)

## Verified real-page output (11354279)
```json
{ "aircraft": {"type":"Boeing 737-8-200 MAX","registration":"EI-IJM","airline":"Ryanair"},
  "photographer": {"name":"Seres23","profile_url":".../photographer/185667"},
  "location": {"airport":"Budapest Liszt Ferenc","icao":"LHBP","country":"Hungary"},
  "image_url": "https://cdn.jetphotos.com/full/6/1075880_1716278472.jpg" }
```

## Producing samples (Cloudflare blocks bots)
1. Open a photo page in your browser → **Save As → Webpage** → `samples/<id>.html`.
2. `python scraper.py --from-html samples/ --dry-run` (verify), then without
   `--dry-run` to write `output/photos/<id>.json`.
(Files named `_*.html` are skipped, e.g. the synthetic `_fixture-990001.html`.)
