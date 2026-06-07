"""
validator.py — CDN URL liveness verification for the JetPhotos New Tab pipeline.

A photo's image is only useful if the CDN actually serves it to a third-party
context. This module HEAD-requests each candidate URL (full / thumb / fallback)
and reports which sizes are reachable.

Standalone usage:
    python validator.py                # verify every output/photos/*.json
    python validator.py URL [URL ...]  # verify ad-hoc URLs

Importable:
    from validator import verify_cdn_access, verify_photo_record

NOTE (Phase 0 finding): JetPhotos sits behind Cloudflare and the CDN may answer
403 to automated clients / sandboxed networks even when the same URL loads fine
inside a real Chrome extension (whose Referer is chrome-extension://...). Treat a
red result here as "verify manually in a real browser", not necessarily "dead".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - dependency hint
    requests = None

OUTPUT_DIR = Path(__file__).parent / "output"
PHOTOS_DIR = OUTPUT_DIR / "photos"
TIMEOUT = 8

# A real-browser-ish UA. Some CDNs gate on obviously-bot UAs.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    # Empty Referer mirrors the chrome-extension:// case most closely.
    "Referer": "",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def verify_cdn_access(image_url: str, timeout: int = TIMEOUT) -> tuple[bool, str]:
    """
    Return (ok, detail). ok=True means the URL responded 200 with an image-ish
    content-type (or at least a 200/redirect). detail is a short status string.
    """
    if not image_url:
        return False, "empty-url"
    if requests is None:
        return False, "requests-not-installed"

    try:
        resp = requests.head(image_url, headers=HEADERS, timeout=timeout,
                             allow_redirects=True)
        code = resp.status_code
        ctype = resp.headers.get("Content-Type", "")
        # Some CDNs disallow HEAD; retry with a tiny ranged GET.
        if code in (403, 405):
            resp = requests.get(image_url, headers={**HEADERS, "Range": "bytes=0-0"},
                                timeout=timeout, allow_redirects=True, stream=True)
            code = resp.status_code
            ctype = resp.headers.get("Content-Type", ctype)
            resp.close()
        ok = code in (200, 206) and ("image" in ctype or ctype == "")
        return ok, f"HTTP {code} {ctype or '?'}"
    except Exception as e:  # noqa: BLE001 - network is best-effort here
        return False, f"err:{type(e).__name__}"


def verify_photo_record(record: dict, timeout: int = TIMEOUT) -> dict:
    """
    Verify a single photo dict. Returns a summary:
        {"id":..., "full":bool, "thumb":bool, "fallback":bool,
         "best": "full"|"thumb"|"fallback"|None, "details": {...}}
    """
    out = {"id": record.get("id"), "details": {}}
    best = None
    for key in ("image_url", "thumb_url", "fallback_url"):
        url = record.get(key)
        if not url:
            out[_short(key)] = False
            continue
        ok, detail = verify_cdn_access(url, timeout)
        out[_short(key)] = ok
        out["details"][_short(key)] = detail
        if ok and best is None:
            best = _short(key)
    out["best"] = best
    return out


def _short(key: str) -> str:
    return {"image_url": "full", "thumb_url": "thumb", "fallback_url": "fallback"}.get(key, key)


def verify_all(photos_dir: Path = PHOTOS_DIR, timeout: int = TIMEOUT) -> dict:
    """Verify every photos/*.json. Returns aggregate stats and writes nothing."""
    files = sorted(photos_dir.glob("*.json"))
    if not files:
        print(f"No photo JSON files in {photos_dir}", file=sys.stderr)
        return {"total": 0, "pass": 0, "rate": 0.0}

    passed = 0
    results = []
    for i, f in enumerate(files, 1):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(files)}] XX {f.name} (bad json: {e})")
            continue
        summary = verify_photo_record(rec, timeout)
        any_ok = bool(summary["best"])
        passed += any_ok
        results.append(summary)
        mark = "OK " if any_ok else "XX "
        best = summary["best"] or "-"
        det = summary["details"].get("full", "")
        print(f"[{i}/{len(files)}] {mark} {summary['id']:>12}  best={best:8} {det}")

    rate = passed / len(files) if files else 0.0
    print(f"\nCDN verification: {passed}/{len(files)} reachable "
          f"({rate*100:.1f}%)  threshold=80%  -> {'PASS' if rate >= 0.8 else 'BELOW THRESHOLD'}")
    return {"total": len(files), "pass": passed, "rate": rate, "results": results}


if __name__ == "__main__":
    if requests is None:
        print("requests is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(2)

    args = sys.argv[1:]
    if args:
        for url in args:
            ok, detail = verify_cdn_access(url)
            print(f"{'OK ' if ok else 'XX '} {detail:24}  {url}")
    else:
        verify_all()
