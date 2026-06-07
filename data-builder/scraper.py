#!/usr/bin/env python3
"""
scraper.py — One-shot build tool: curated JetPhotos photo URLs -> structured JSON.

This is a *build* tool, not a long-running crawler. It reads curated-urls.txt,
extracts metadata per photo, classifies it, optionally verifies CDN liveness,
and writes output/photos/{id}.json plus output/index.json and
output/categories/{cat}.json.

Modes:
    python scraper.py --dry-run          # parse + print, write nothing
    python scraper.py                    # full run (direct fetch)
    python scraper.py --incremental      # only IDs not already in output/photos/
    python scraper.py --from-html DIR    # parse saved HTML files instead of fetching
    python scraper.py --verify-only      # re-verify CDN URLs of existing records
    python scraper.py --stats            # print category/verification stats
    python scraper.py --limit N          # cap how many URLs to process

Cloudflare note (Phase 0): www.jetphotos.com returns HTTP 403 to plain requests.
On such networks, use --from-html: save each photo page from a real browser to
samples/<id>.html, then `python scraper.py --from-html samples/`.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from classifier import classify, ALL_CATEGORIES

# ── Paths & config ───────────────────────────────────────────────────
BASE = Path(__file__).parent
URLS_FILE = BASE / "curated-urls.txt"
OUTPUT_DIR = BASE / "output"
PHOTOS_DIR = OUTPUT_DIR / "photos"
CATEGORIES_DIR = OUTPUT_DIR / "categories"
INDEX_FILE = OUTPUT_DIR / "index.json"
ERRORS_LOG = BASE / "errors.log"

DELAY_RANGE = (3.0, 5.0)
DATA_VERSION = "1.0.0"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.jetphotos.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CDN_RE = re.compile(r"https?://cdn\.jetphotos\.com/(?:full|\d+)/[^\s\"'<>)]+\.(?:jpg|jpeg|png)",
                    re.IGNORECASE)


# ── Small utilities ──────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_error(msg: str) -> None:
    line = f"{now_iso()}  {msg}"
    print(f"  ! {msg}", file=sys.stderr)
    with ERRORS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def photo_id_from_url(url: str) -> str | None:
    m = re.search(r"/photo/(\d+)", url)
    return m.group(1) if m else None


def read_curated_urls() -> list[str]:
    if not URLS_FILE.exists():
        return []
    urls = []
    for raw in URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def derive_cdn_sizes(any_cdn_url: str) -> dict:
    """
    Given any cdn.jetphotos.com image URL, derive full / thumb(400) / fallback(200).
    JetPhotos paths look like  https://cdn.jetphotos.com/<size>/<a>/<file>.jpg
    where <size> is 'full' or a pixel width (200/400/640/...).
    """
    m = re.match(r"(https?://cdn\.jetphotos\.com)/(full|\d+)/(.+)$", any_cdn_url, re.IGNORECASE)
    if not m:
        # Unknown shape — return as-is for full, leave others empty.
        return {"image_url": any_cdn_url, "thumb_url": "", "fallback_url": ""}
    host, _size, rest = m.group(1), m.group(2), m.group(3)
    return {
        "image_url": f"{host}/full/{rest}",
        "thumb_url": f"{host}/400/{rest}",
        "fallback_url": f"{host}/200/{rest}",
    }


# ── HTML parsing ─────────────────────────────────────────────────────

def _meta(soup, prop: str) -> str:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (tag.get("content") or "").strip() if tag else ""


def _link_text(soup, href_contains: str) -> tuple[str, str]:
    """Return (text, href) of the first <a> whose href contains the fragment."""
    a = soup.find("a", href=lambda h: h and href_contains in h)
    if not a:
        return "", ""
    return a.get_text(strip=True), a.get("href", "")


def parse_photo_html(html: str, url: str = "") -> dict:
    """
    Extract a photo record from a JetPhotos photo-page HTML string.

    Uses several strategies per field (semantic <a> links -> og:meta -> regex)
    so it degrades gracefully if one part of the DOM changes. Selectors marked
    'verify against live DOM' in PARSING_GUIDE.md.
    """
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 not installed (pip install -r requirements.txt)")

    soup = BeautifulSoup(html, "lxml" if _have_lxml() else "html.parser")

    # Canonical URL / id
    canonical = ""
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = link["href"].strip()
    og_url = _meta(soup, "og:url")
    page_url = url or canonical or og_url
    pid = photo_id_from_url(page_url) or photo_id_from_url(canonical) or photo_id_from_url(og_url)

    # Image URL: og:image is the most reliable, then large-photo img, then regex.
    img = _meta(soup, "og:image")
    if not img:
        node = soup.select_one("img.large-photo__img, img#photo-img, .photo img, img[src*='cdn.jetphotos.com']")
        if node:
            img = (node.get("src") or node.get("data-src") or "").strip()
    if not img:
        m = CDN_RE.search(html)
        img = m.group(0) if m else ""
    sizes = derive_cdn_sizes(img) if img else {"image_url": "", "thumb_url": "", "fallback_url": ""}

    # Semantic links
    aircraft_type, _ = _link_text(soup, "/aircraft/")
    airline, _ = _link_text(soup, "/airline/")
    registration, _ = _link_text(soup, "/registration/")
    photographer, photographer_href = _link_text(soup, "/photographer/")
    airport, airport_href = _link_text(soup, "/airport/")

    # Fallback: parse the og:title — typically "Type Reg Airline Photo by Name | id"
    og_title = _meta(soup, "og:title") or (soup.title.get_text() if soup.title else "")
    if not aircraft_type and og_title:
        aircraft_type = re.split(r"\s+(?:Photo|Aviation Photo|\|)", og_title)[0].strip()
    if not photographer and og_title:
        mph = re.search(r"[Pp]hoto by ([^|]+?)\s*(?:\||$)", og_title)
        if mph:
            photographer = mph.group(1).strip()

    # Definition-list fallback (label/value rows) for fields still missing.
    if not (aircraft_type and airline and registration and airport):
        kv = _scan_label_value_pairs(soup)
        aircraft_type = aircraft_type or kv.get("aircraft", "")
        airline = airline or kv.get("airline", "")
        registration = registration or kv.get("reg", kv.get("registration", ""))
        airport = airport or kv.get("location", kv.get("airport", ""))

    icao, iata, country = _split_airport(airport)

    rec = {
        "id": pid or "",
        "jetphotos_url": page_url or (f"https://www.jetphotos.com/photo/{pid}" if pid else ""),
        "image_url": sizes["image_url"],
        "thumb_url": sizes["thumb_url"],
        "fallback_url": sizes["fallback_url"],
        "aircraft": {
            "type": aircraft_type,
            "registration": registration,
            "airline": airline,
        },
        "photographer": {
            "name": photographer,
            "profile_url": _abs_url(photographer_href),
        },
        "location": {
            "airport": airport,
            "icao": icao,
            "iata": iata,
            "country": country,
        },
        "meta": {
            "category": classify(aircraft_type, airline=airline, title=og_title),
            "tags": [],
            "cdn_verified": None,
            "scraped_at": now_iso(),
        },
    }
    return rec


def _scan_label_value_pairs(soup) -> dict:
    """Best-effort scrape of 'Label: Value' rows from common JetPhotos containers."""
    pairs: dict[str, str] = {}
    candidates = soup.select(
        ".header__info li, .additional-info li, dl, table tr, .photo-details li, .information li"
    )
    for el in candidates:
        text = el.get_text(" ", strip=True)
        m = re.match(r"([A-Za-z .#]+?)\s*[:#]\s*(.+)", text)
        if m:
            key = m.group(1).strip().lower().rstrip(".").replace(" ", "")
            pairs.setdefault(key, m.group(2).strip())
    return pairs


def _split_airport(airport: str) -> tuple[str, str, str]:
    """Pull ICAO/IATA/country out of an airport string when present, e.g.
    'Frankfurt Airport (FRA / EDDF), Germany'."""
    icao = iata = country = ""
    m = re.search(r"\(([A-Z]{3})\s*/\s*([A-Z]{4})\)", airport)
    if m:
        iata, icao = m.group(1), m.group(2)
    mc = re.search(r",\s*([A-Za-z .'-]+)$", airport)
    if mc:
        country = mc.group(1).strip()
    return icao, iata, country


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return "https://www.jetphotos.com" + (href if href.startswith("/") else "/" + href)


_LXML = None
def _have_lxml() -> bool:
    global _LXML
    if _LXML is None:
        try:
            import lxml  # noqa: F401
            _LXML = True
        except ImportError:
            _LXML = False
    return _LXML


# ── Fetching ─────────────────────────────────────────────────────────

def fetch_html(url: str) -> str | None:
    if requests is None:
        log_error("requests not installed; cannot fetch. Use --from-html or pip install -r requirements.txt")
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 403 and ("cloudflare" in resp.text.lower() or "attention required" in resp.text.lower()):
            log_error(f"403 Cloudflare block for {url} — use --from-html (save page from a real browser)")
            return None
        if resp.status_code != 200:
            log_error(f"HTTP {resp.status_code} for {url}")
            return None
        return resp.text
    except Exception as e:  # noqa: BLE001
        log_error(f"fetch failed {url}: {type(e).__name__}: {e}")
        return None


# ── Output writers ───────────────────────────────────────────────────

def write_record(rec: dict) -> None:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    (PHOTOS_DIR / f"{rec['id']}.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_all_records() -> list[dict]:
    out = []
    for f in sorted(PHOTOS_DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            log_error(f"bad json {f.name}: {e}")
    return out


def generate_indexes() -> None:
    records = load_all_records()
    ids = [r["id"] for r in records if r.get("id")]
    ids_sorted = sorted(set(ids), key=lambda x: (len(x), x))

    INDEX_FILE.write_text(json.dumps({
        "version": DATA_VERSION,
        "updated_at": now_iso(),
        "total": len(ids_sorted),
        "photo_ids": ids_sorted,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)
    by_cat: dict[str, list[str]] = {c: [] for c in ALL_CATEGORIES}
    for r in records:
        cat = (r.get("meta") or {}).get("category", "other")
        by_cat.setdefault(cat, []).append(r.get("id"))
    for cat, cat_ids in by_cat.items():
        cat_ids = sorted(set(filter(None, cat_ids)), key=lambda x: (len(x), x))
        (CATEGORIES_DIR / f"{cat}.json").write_text(json.dumps({
            "category": cat,
            "count": len(cat_ids),
            "photo_ids": cat_ids,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nGenerated index.json ({len(ids_sorted)} ids) and "
          f"{len([c for c in by_cat if by_cat[c]])} non-empty category files.")


# ── Commands ─────────────────────────────────────────────────────────

def cmd_scrape(args) -> int:
    if not (args.dry_run or args.from_html) and requests is None:
        print("requests not installed. pip install -r requirements.txt (or use --from-html).",
              file=sys.stderr)
        return 2
    if BeautifulSoup is None:
        print("beautifulsoup4 not installed. pip install -r requirements.txt", file=sys.stderr)
        return 2

    # Build the worklist
    work: list[tuple[str, str]] = []  # (id, source) where source is url or html path
    if args.from_html:
        html_dir = Path(args.from_html)
        if not html_dir.is_absolute():
            html_dir = BASE / html_dir
        files = sorted(p for p in html_dir.glob("*.html") if not p.name.startswith("_"))
        for p in files:
            pid = p.stem if p.stem.isdigit() else None
            work.append((pid or p.stem, str(p)))
    else:
        for url in read_curated_urls():
            pid = photo_id_from_url(url)
            if not pid:
                log_error(f"cannot parse photo id from {url}")
                continue
            work.append((pid, url))

    if args.incremental:
        work = [(pid, src) for (pid, src) in work if not (PHOTOS_DIR / f"{pid}.json").exists()]

    if args.limit:
        work = work[: args.limit]

    if not work:
        print("Nothing to do (worklist empty). Check curated-urls.txt or --from-html dir.")
        return 0

    print(f"Processing {len(work)} item(s)  "
          f"[{'dry-run' if args.dry_run else 'from-html' if args.from_html else 'fetch'}]\n")

    ok = 0
    for i, (pid, src) in enumerate(work, 1):
        # Acquire HTML
        if args.from_html:
            try:
                html = Path(src).read_text(encoding="utf-8", errors="ignore")
                url = ""
            except Exception as e:  # noqa: BLE001
                log_error(f"read failed {src}: {e}")
                continue
        else:
            url = src
            html = fetch_html(url)
            if html is None:
                print(f"[{i}/{len(work)}] XX {pid} (fetch failed)")
                if not args.dry_run:
                    time.sleep(random.uniform(*DELAY_RANGE))
                continue

        # Parse
        try:
            rec = parse_photo_html(html, url=url)
        except Exception as e:  # noqa: BLE001
            log_error(f"parse failed {pid}: {type(e).__name__}: {e}")
            print(f"[{i}/{len(work)}] XX {pid} (parse failed)")
            continue

        if not rec.get("id"):
            rec["id"] = pid
            rec["jetphotos_url"] = rec["jetphotos_url"] or f"https://www.jetphotos.com/photo/{pid}"

        # Optional CDN verification
        if args.verify and rec["image_url"]:
            try:
                from validator import verify_cdn_access
                vok, _ = verify_cdn_access(rec["image_url"])
                if not vok and rec["thumb_url"]:
                    vok, _ = verify_cdn_access(rec["thumb_url"])
                rec["meta"]["cdn_verified"] = bool(vok)
            except Exception:  # noqa: BLE001
                rec["meta"]["cdn_verified"] = None

        type_str = rec["aircraft"]["type"] or "?"
        airline_str = rec["aircraft"]["airline"] or "?"
        cat = rec["meta"]["category"]

        if args.dry_run:
            print(f"[{i}/{len(work)}] ~~ {pid}  {type_str} - {airline_str}  [{cat}]")
            print(f"        img: {rec['image_url'][:72] or '(none)'}")
        else:
            if not rec["image_url"] and not args.keep_imageless:
                log_error(f"no image_url for {pid}; skipping write (use --keep-imageless to keep)")
                print(f"[{i}/{len(work)}] XX {pid} (no image url)")
            else:
                write_record(rec)
                ok += 1
                print(f"[{i}/{len(work)}] OK {pid} - {type_str} - {airline_str}  [{cat}]")

        # Polite delay only when actually hitting the network
        if not args.dry_run and not args.from_html and i < len(work):
            time.sleep(random.uniform(*DELAY_RANGE))

    if not args.dry_run:
        generate_indexes()
    print(f"\nDone. {ok}/{len(work)} written.  Errors logged to {ERRORS_LOG.name if ERRORS_LOG.exists() else '(none)'}")
    return 0


def cmd_verify_only(args) -> int:
    from validator import verify_all, verify_photo_record
    records = load_all_records()
    if not records:
        print("No records to verify.")
        return 0
    passed = 0
    for i, rec in enumerate(records, 1):
        summary = verify_photo_record(rec)
        rec["meta"]["cdn_verified"] = bool(summary["best"])
        passed += bool(summary["best"])
        write_record(rec)
        print(f"[{i}/{len(records)}] {'OK' if summary['best'] else 'XX'} {rec['id']} best={summary['best']}")
    rate = passed / len(records)
    print(f"\nVerified {passed}/{len(records)} ({rate*100:.1f}%).")
    generate_indexes()
    return 0


def cmd_stats(args) -> int:
    records = load_all_records()
    total = len(records)
    if total == 0:
        print("No records. Run the scraper first.")
        return 0
    by_cat: dict[str, int] = {}
    verified = 0
    unverified = 0
    for r in records:
        cat = (r.get("meta") or {}).get("category", "other")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        cv = (r.get("meta") or {}).get("cdn_verified")
        if cv is True:
            verified += 1
        elif cv is None:
            unverified += 1
    print(f"=== Build stats ===\nTotal photos: {total}\n")
    print("By category:")
    for cat in ALL_CATEGORIES:
        if by_cat.get(cat):
            print(f"  {cat:16} {by_cat[cat]:>4}")
    extra = set(by_cat) - set(ALL_CATEGORIES)
    for cat in sorted(extra):
        print(f"  {cat:16} {by_cat[cat]:>4}  (unexpected)")
    checked = total - unverified
    rate = (verified / checked * 100) if checked else 0.0
    print(f"\nCDN verified: {verified}/{checked} checked ({rate:.1f}%), {unverified} unverified")
    return 0


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JetPhotos New Tab build scraper")
    p.add_argument("--dry-run", action="store_true", help="parse & print, write nothing")
    p.add_argument("--incremental", action="store_true", help="skip IDs already in output/photos/")
    p.add_argument("--from-html", metavar="DIR", help="parse saved *.html files instead of fetching")
    p.add_argument("--verify-only", action="store_true", help="re-verify CDN URLs of existing records")
    p.add_argument("--stats", action="store_true", help="print category & verification stats")
    p.add_argument("--verify", action="store_true", help="verify CDN URL during scrape")
    p.add_argument("--limit", type=int, default=0, help="cap number of items processed")
    p.add_argument("--keep-imageless", action="store_true", help="write records even without image_url")
    return p


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.stats:
        return cmd_stats(args)
    if args.verify_only:
        return cmd_verify_only(args)
    return cmd_scrape(args)


if __name__ == "__main__":
    raise SystemExit(main())
