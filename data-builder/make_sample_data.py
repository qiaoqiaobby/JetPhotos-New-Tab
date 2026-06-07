#!/usr/bin/env python3
"""
make_sample_data.py — Generate a synthetic but schema-perfect demo dataset.

WHY THIS EXISTS
    The real source (jetphotos.com) is Cloudflare-gated (Phase 0: HTTP 403 to
    bots) and this sandbox cannot reach the CDN, so we cannot scrape real photos
    here. To let the extension + integration tests run end-to-end offline, this
    script emits ~30 realistic records spanning every category.

IMPORTANT
    These are PLACEHOLDERS. The image_url values are synthetic JetPhotos-style
    URLs that will NOT resolve, so the extension will gracefully fall back to the
    bundled placeholder. Replace this dataset with output from scraper.py once you
    have curated, rights-cleared photo URLs. Every record is marked meta._sample.

Usage:
    python make_sample_data.py            # write output/photos/*.json + indexes
    python make_sample_data.py --clean    # wipe output/photos first
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper import derive_cdn_sizes, generate_indexes, PHOTOS_DIR, OUTPUT_DIR
from classifier import classify

# (id, type, reg, airline, photographer, airport, icao, iata, country, category, tags)
SAMPLES = [
    # ── widebody ─────────────────────────────────────────────────────
    ("99000001", "Boeing 747-830", "D-ABYA", "Lufthansa", "Jane Doe",
     "Frankfurt Airport", "EDDF", "FRA", "Germany", "widebody", ["classic"]),
    ("99000002", "Airbus A380-861", "A6-EOA", "Emirates", "Sam Carter",
     "Dubai International Airport", "OMDB", "DXB", "United Arab Emirates", "widebody", ["sunset"]),
    ("99000003", "Boeing 787-9 Dreamliner", "JA873A", "All Nippon Airways", "Kenji Sato",
     "Tokyo Haneda Airport", "RJTT", "HND", "Japan", "widebody", ["takeoff"]),
    ("99000004", "Airbus A350-1041", "A7-ANA", "Qatar Airways", "Mariam Hassan",
     "Hamad International Airport", "OTHH", "DOH", "Qatar", "widebody", []),
    ("99000005", "Boeing 777-300ER", "B-KQA", "Cathay Pacific", "Wong Ka Ho",
     "Hong Kong International Airport", "VHHH", "HKG", "Hong Kong", "widebody", ["landing"]),
    ("99000006", "Airbus A330-343", "TC-JNZ", "Turkish Airlines", "Emre Yildiz",
     "Istanbul Airport", "LTFM", "IST", "Turkey", "widebody", []),
    ("99000007", "Boeing 747-436", "G-CIVB", "British Airways", "Oliver Smith",
     "London Heathrow Airport", "EGLL", "LHR", "United Kingdom", "widebody", ["retro_jet"]),
    ("99000008", "Airbus A380-841", "9V-SKA", "Singapore Airlines", "Lim Wei",
     "Singapore Changi Airport", "WSSS", "SIN", "Singapore", "widebody", ["air_to_air"]),
    # ── narrowbody ───────────────────────────────────────────────────
    ("99000009", "Boeing 737 MAX 8", "EI-HEN", "Ryanair", "Conor Walsh",
     "Dublin Airport", "EIDW", "DUB", "Ireland", "narrowbody", []),
    ("99000010", "Airbus A320-251N", "G-UZHA", "easyJet", "Holly Green",
     "London Gatwick Airport", "EGKK", "LGW", "United Kingdom", "narrowbody", ["sunrise"]),
    ("99000011", "Airbus A321-271NX", "N501DN", "Delta Air Lines", "Marcus Lee",
     "Hartsfield-Jackson Atlanta Airport", "KATL", "ATL", "United States", "narrowbody", []),
    ("99000012", "Embraer E190STD", "PH-EZA", "KLM Cityhopper", "Anouk Visser",
     "Amsterdam Schiphol Airport", "EHAM", "AMS", "Netherlands", "narrowbody", []),
    ("99000013", "Airbus A220-300", "YL-CSA", "airBaltic", "Janis Berzins",
     "Riga International Airport", "EVRA", "RIX", "Latvia", "narrowbody", ["snow"]),
    # ── military ─────────────────────────────────────────────────────
    ("99000014", "Lockheed Martin F-35A Lightning II", "18-5410", "United States Air Force",
     "Dale Foster", "Nellis Air Force Base", "KLSV", "LSV", "United States", "military", ["dynamic"]),
    ("99000015", "Boeing F/A-18E Super Hornet", "165663", "US Navy Blue Angels",
     "Rachel Adams", "NAS Pensacola", "KNPA", "NPA", "United States", "military", ["airshow"]),
    ("99000016", "Boeing C-17 Globemaster III", "ZZ177", "Royal Air Force",
     "Tom Bailey", "RAF Brize Norton", "EGVN", "BZZ", "United Kingdom", "military", []),
    ("99000017", "Eurofighter Typhoon FGR4", "ZK308", "Royal Air Force",
     "Gemma Clarke", "RAF Coningsby", "EGXC", "", "United Kingdom", "military", ["air_to_air"]),
    # ── cargo ────────────────────────────────────────────────────────
    ("99000018", "Boeing 747-8F", "LX-VCB", "Cargolux", "Pierre Muller",
     "Luxembourg Findel Airport", "ELLX", "LUX", "Luxembourg", "cargo", []),
    ("99000019", "Airbus A330-743L BelugaXL", "F-GXLG", "Airbus Transport International",
     "Claire Dubois", "Toulouse-Blagnac Airport", "LFBO", "TLS", "France", "cargo", ["unique"]),
    ("99000020", "Antonov An-124-100", "UR-82027", "Antonov Airlines", "Dmytro Kovalenko",
     "Leipzig/Halle Airport", "EDDP", "LEJ", "Germany", "cargo", ["heavy"]),
    # ── retro ────────────────────────────────────────────────────────
    ("99000021", "Aerospatiale/BAC Concorde 102", "G-BOAC", "British Airways",
     "Edward Hughes", "Manchester Airport", "EGCC", "MAN", "United Kingdom", "retro", ["historic"]),
    ("99000022", "Douglas DC-3", "N431HM", "Historic Flight", "Nancy Reed",
     "Wittman Regional Airport", "KOSH", "OSH", "United States", "retro", ["historic"]),
    ("99000023", "Boeing 707-330B", "N707JT", "Private", "Greg Turner",
     "Mojave Air and Space Port", "KMHV", "MHV", "United States", "retro", ["historic"]),
    # ── bizjet ───────────────────────────────────────────────────────
    ("99000024", "Gulfstream G700", "N700GD", "Gulfstream", "Brian Cole",
     "Savannah/Hilton Head Airport", "KSAV", "SAV", "United States", "bizjet", ["elegant"]),
    ("99000025", "Bombardier Global 7500", "9H-VITA", "VistaJet", "Sofia Rossi",
     "Geneva Airport", "LSGG", "GVA", "Switzerland", "bizjet", []),
    # ── special_livery ───────────────────────────────────────────────
    ("99000026", "Boeing 777-381ER", "JA789A", "All Nippon Airways", "Kenji Sato",
     "Tokyo Narita Airport", "RJAA", "NRT", "Japan", "special_livery", ["star_wars", "livery"]),
    ("99000027", "Airbus A320-214", "OO-SNF", "Brussels Airlines", "Lucas Peeters",
     "Brussels Airport", "EBBR", "BRU", "Belgium", "special_livery", ["tribute", "livery"]),
    ("99000028", "Boeing 737-8H4", "N922WN", "Southwest Airlines", "Ashley Brooks",
     "Dallas Love Field", "KDAL", "DAL", "United States", "special_livery", ["flag", "livery"]),
    # ── helicopter ───────────────────────────────────────────────────
    ("99000029", "Sikorsky S-92A", "G-MCGY", "Bristow Helicopters", "Iain Ross",
     "Aberdeen Airport", "EGPD", "ABZ", "United Kingdom", "helicopter", ["offshore"]),
    # ── other ────────────────────────────────────────────────────────
    ("99000030", "Cessna 172S Skyhawk", "N172SP", "Private", "Pat Morgan",
     "Palo Alto Airport", "KPAO", "PAO", "United States", "other", ["general_aviation"]),
]

SCRAPED_AT = "2026-06-06T00:00:00Z"


def synth_cdn_url(pid: str) -> str:
    """Deterministic JetPhotos-style CDN URL (synthetic; will not resolve)."""
    series = int(pid[-1]) % 9 + 1
    seq = pid[-6:]
    ts = 1700000000 + int(pid[-4:])
    return f"https://cdn.jetphotos.com/full/{series}/{seq}_{ts}.jpg"


def build_record(row) -> dict:
    (pid, atype, reg, airline, photog, airport, icao, iata, country, category, tags) = row
    sizes = derive_cdn_sizes(synth_cdn_url(pid))
    # Cross-check classifier for non-livery categories (livery is a manual signal).
    auto = classify(atype, tags=tags, airline=airline)
    final_cat = category if category == "special_livery" else (auto if auto != "other" else category)
    return {
        "id": pid,
        "jetphotos_url": f"https://www.jetphotos.com/photo/{pid}",
        "image_url": sizes["image_url"],
        "thumb_url": sizes["thumb_url"],
        "fallback_url": sizes["fallback_url"],
        "aircraft": {"type": atype, "registration": reg, "airline": airline},
        "photographer": {
            "name": photog,
            "profile_url": f"https://www.jetphotos.com/photographer/{(int(pid) % 90000) + 10000}",
        },
        "location": {"airport": airport, "icao": icao, "iata": iata, "country": country},
        "meta": {
            "category": final_cat,
            "tags": tags,
            "cdn_verified": False,
            "scraped_at": SCRAPED_AT,
            "_sample": True,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic demo dataset")
    ap.add_argument("--clean", action="store_true", help="remove existing photos/*.json first")
    args = ap.parse_args(argv)

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for f in PHOTOS_DIR.glob("*.json"):
            f.unlink()

    for row in SAMPLES:
        rec = build_record(row)
        (PHOTOS_DIR / f"{rec['id']}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    generate_indexes()

    marker = OUTPUT_DIR / "_SAMPLE_DATA_README.md"
    marker.write_text(
        "# ⚠️ SAMPLE / PLACEHOLDER DATA\n\n"
        "These JSON files were produced by `make_sample_data.py`, **not** by scraping.\n"
        "The `image_url`s are synthetic JetPhotos-style URLs that do **not** resolve, so\n"
        "the extension falls back to the bundled placeholder image.\n\n"
        "Replace this with real output from `scraper.py` once you have curated,\n"
        "rights-cleared photo URLs. Every record carries `meta._sample: true`.\n",
        encoding="utf-8")

    print(f"Wrote {len(SAMPLES)} sample records to {PHOTOS_DIR}")
    print(f"Marker: {marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
