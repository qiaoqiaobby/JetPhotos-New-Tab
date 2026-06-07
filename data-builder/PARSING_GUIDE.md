# PARSING_GUIDE.md — JetPhotos photo-page extraction rules

> Status: derived from the documented JetPhotos DOM + verified against the
> `samples/990001.html` fixture (the live site is Cloudflare-gated, so selectors
> tagged **[verify-live]** should be confirmed once on a real saved page).
> The parser (`scraper.py::parse_photo_html`) tries several strategies per field
> and degrades gracefully, so a single DOM change rarely breaks extraction.

## Photo ID
From the URL / canonical / `og:url`: regex `"/photo/(\d+)"`.
Example: `https://www.jetphotos.com/photo/990001` → `990001`.

## image_url / thumb_url / fallback_url
Primary: `<meta property="og:image">` content (most stable).
Fallbacks: `img.large-photo__img[src]` **[verify-live]**, then any
`https://cdn.jetphotos.com/(full|\d+)/...jpg` found via regex.

CDN size variants are **derived**, not re-scraped, from the matched URL:
```
host = https://cdn.jetphotos.com
.../<size>/<rest>      where <size> ∈ {full, 200, 400, 640, ...}
image_url    = {host}/full/{rest}
thumb_url    = {host}/400/{rest}
fallback_url = {host}/200/{rest}
```
Example: `og:image = https://cdn.jetphotos.com/full/6/123456_1700000000.jpg`
→ thumb `.../400/6/123456_1700000000.jpg`, fallback `.../200/6/123456_1700000000.jpg`.

## aircraft.type
Selector: `a[href*="/aircraft/"]` → text. Fallback: first segment of `og:title`
before "Photo"/"|".
Example value: `"Boeing 747-830"`.

## aircraft.airline
Selector: `a[href*="/airline/"]` → text.  Example: `"Lufthansa"`.

## aircraft.registration
Selector: `a[href*="/registration/"]` → text.  Example: `"D-ABYA"`.

## photographer.name + profile_url
Selector: `a[href*="/photographer/"]` → text (name) + `href` (absolutised to
`https://www.jetphotos.com/...`). Name fallback: `og:title` `"Photo by (…)"`.
Example: name `"Jane Doe"`, profile `https://www.jetphotos.com/photographer/12345`.

## location.airport / icao / iata / country
Selector: `a[href*="/airport/"]` → text. ICAO/IATA/country parsed from the string:
- `\(([A-Z]{3})\s*/\s*([A-Z]{4})\)` → IATA, ICAO
- trailing `, <Country>` → country
Example: `"Frankfurt Airport (FRA / EDDF), Germany"` → iata `FRA`, icao `EDDF`,
country `Germany`.

## Label/value fallback
For any field still missing, `scraper.py::_scan_label_value_pairs` scans
`.header__info li, .additional-info li, dl, table tr, .photo-details li,
.information li` **[verify-live]** for `Label: Value` rows (Aircraft / Airline /
Reg / Location).

## meta.category
Computed by `classifier.py::classify(type, tags, airline, title)` →
one of widebody / narrowbody / military / cargo / retro / bizjet /
special_livery / helicopter / other.

## How to produce a real sample (given Cloudflare 403)
1. Open a photo page in your normal browser.
2. Save Page As → **Webpage, HTML Only** → `data-builder/samples/<id>.html`.
3. `python scraper.py --from-html samples/ --dry-run` to confirm extraction,
   then drop `--dry-run` to write `output/photos/<id>.json`.
