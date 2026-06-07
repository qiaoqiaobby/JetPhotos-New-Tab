"""
classifier.py — Aircraft auto-classification for the JetPhotos New Tab build pipeline.

Maps a free-text aircraft `type` string (e.g. "Boeing 747-8F", "Lockheed Martin F-35A")
to one of the gallery categories. Pure stdlib, no dependencies.

Category precedence (first match wins) is deliberate:
  special_livery (explicit) > military > helicopter > cargo > retro > bizjet
  > widebody > narrowbody > other

The order matters because some tokens overlap (a "747-8F" is both a 747 and a
freighter — we want it in `cargo`; an "F-16" must not be mistaken for a freighter).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Rule tables. Keys are matched case-insensitively as whole-ish tokens against
# the aircraft type string. Mirrors the spec in the goal doc, extended with
# helicopter (from the static design doc's category table) and a few aliases.
# ---------------------------------------------------------------------------

CLASSIFICATION_RULES: dict[str, list[str]] = {
    # Order here is the evaluation order (see classify()).
    "military": [
        "F-22", "F-35", "F/A-18", "F-18", "F-16", "F-15", "F-14", "F-4",
        "C-17", "C-130", "C-5", "KC-135", "KC-46", "A400M", "B-52", "B-1",
        "B-2", "Eurofighter", "Typhoon", "Rafale", "Gripen", "Tornado",
        "Mirage", "Su-", "MiG", "Tu-95", "Tu-160", "F-5", "A-10", "AV-8",
        "Harrier", "E-3", "P-8", "P-3", "AWACS", "Blue Angels", "Thunderbirds",
        "Red Arrows", "T-38", "T-6", "Hawk", "Alpha Jet",
    ],
    "helicopter": [
        "AH-64", "Apache", "CH-47", "Chinook", "UH-60", "Black Hawk",
        "Blackhawk", "S-92", "S-76", "EC135", "EC145", "EC155", "EC225",
        "H125", "H145", "H160", "H175", "AW139", "AW169", "AW189",
        "Bell 212", "Bell 412", "Bell 407", "Mi-8", "Mi-17", "Mi-24",
        "Helicopter", "Sikorsky",
    ],
    "cargo": [
        "Freighter", "747F", "747-8F", "777F", "767F", "757F", "737F",
        "A330F", "A330-200F", "MD-11F", "Beluga", "BelugaXL", "Dreamlifter",
        "AN-124", "AN-225", "An-12", "Il-76", "Guppy", "SuperGuppy", "BCF",
        "SF", "Cargo",
    ],
    "retro": [
        "DC-3", "DC-6", "DC-7", "Concorde", "707", "720", "727", "DC-8",
        "DC-9", "Caravelle", "Comet", "Tu-144", "Tu-134", "Tu-154", "VC10",
        "Trident", "BAC 1-11", "Constellation", "Convair", "Vickers",
        "Il-62", "Il-18",
    ],
    "bizjet": [
        "Gulfstream", "Global ", "Global7500", "Global 7500", "Falcon",
        "Learjet", "Citation", "Challenger", "Phenom", "Hawker", "Praetor",
        "Legacy", "Pilatus PC-24", "HondaJet", "Embraer Legacy",
    ],
    "widebody": [
        "747", "777", "787", "A330", "A340", "A350", "A380", "DC-10",
        "MD-11", "L-1011", "TriStar", "767", "A300", "A310", "Il-86", "Il-96",
    ],
    "narrowbody": [
        "737", "A320", "A319", "A321", "A318", "A220", "E-Jet", "E170",
        "E175", "E190", "E195", "ERJ", "CRJ", "717", "757", "MD-80", "MD-82",
        "MD-83", "MD-88", "MD-90", "Fokker", "BAe 146", "Avro RJ", "Dash 8",
        "Q400", "ATR", "Saab 340", "Saab 2000", "SSJ", "Superjet", "C919",
        "MC-21", "Tu-204",
    ],
}

# Evaluation order. special_livery is handled separately (explicit signal only).
_EVAL_ORDER = ["military", "helicopter", "cargo", "retro", "bizjet", "widebody", "narrowbody"]

# Keywords that, when found in tags or the airline/type string, force special_livery.
SPECIAL_LIVERY_KEYWORDS = [
    "livery", "special scheme", "special colours", "special colors",
    "star wars", "pixar", "disney", "marvel", "pokemon", "pokémon",
    "retrojet", "retro livery", "anniversary", "flag", "national colours",
    "one world", "oneworld", "star alliance", "skyteam", "tribute",
    "commemorative", "eurowhite", "hello kitty", "shark", "eagle",
    "painted", "artwork", "wrap", "decal", "promo",
]


def _normalize(text: str) -> str:
    """Uppercase + collapse whitespace so 'F/A-18' and 'f a 18' compare sanely."""
    return re.sub(r"\s+", " ", (text or "")).strip().upper()


def _token_present(needle: str, haystack_upper: str) -> bool:
    """
    Match `needle` inside `haystack_upper` with a word-boundary heuristic that
    avoids greedy false positives.

    Two regimes:
    * Designator tokens (contain a digit / hyphen / slash, e.g. "A320", "F-35",
      "747-8F", "Su-"): require the char *before* the match to be a non-letter,
      but allow any suffix — so "A320" hits "A320neo" and "747" hits "747-8".
    * Plain-alphabetic tokens (e.g. "Hawk", "Typhoon", "Beluga"): require a
      leading word boundary AND that the next char is a boundary or a digit — so
      "Hawk" matches "BAE Hawk" and "CRJ" matches "CRJ900", but "Hawk" does NOT
      match "Skyhawk" or "Hawker".
    """
    tok = needle.upper().strip()
    if not tok:
        return False

    if re.search(r"[0-9/\-]", tok):  # designator
        for m in re.finditer(re.escape(tok), haystack_upper):
            prev = haystack_upper[m.start() - 1] if m.start() else " "
            if not prev.isalpha():
                return True
        return False

    # plain alphabetic token: leading \b, trailing boundary-or-digit
    return re.search(rf"\b{re.escape(tok)}(?=$|[^A-Z])", haystack_upper) is not None


def is_special_livery(aircraft_type: str = "", tags=None, airline: str = "", title: str = "") -> bool:
    """Heuristic: detect special/painted liveries from tags, airline, or title text."""
    blob = " ".join(filter(None, [aircraft_type, airline, title, " ".join(tags or [])]))
    blob_l = blob.lower()
    return any(k in blob_l for k in SPECIAL_LIVERY_KEYWORDS)


def classify(aircraft_type: str, tags=None, airline: str = "", title: str = "",
             force_special_livery: bool = False) -> str:
    """
    Return the best-fit category for an aircraft.

    Args:
        aircraft_type: e.g. "Boeing 747-8" / "Airbus A350-1000" / "Lockheed F-22".
        tags:          optional list of tags (used for special_livery detection).
        airline:       optional airline string (livery hints live here too).
        title:         optional photo title (livery hints).
        force_special_livery: set True when a human has flagged the photo.

    Returns one of the category keys, or "other" when nothing matches.
    """
    if force_special_livery or is_special_livery(aircraft_type, tags, airline, title):
        return "special_livery"

    hay = _normalize(aircraft_type)
    if not hay:
        return "other"

    for category in _EVAL_ORDER:
        for keyword in CLASSIFICATION_RULES[category]:
            if _token_present(keyword, hay):
                return category

    return "other"


# All categories the pipeline may emit (used to pre-seed category index files).
ALL_CATEGORIES = ["widebody", "narrowbody", "military", "cargo", "retro",
                  "bizjet", "special_livery", "helicopter", "other"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        t = " ".join(sys.argv[1:])
        print(f"{t!r} -> {classify(t)}")
    else:
        # Smoke test the rule table.
        samples = [
            ("Boeing 747-8", "widebody"),
            ("Boeing 747-8F", "cargo"),
            ("Airbus A380-800", "widebody"),
            ("Airbus A320neo", "narrowbody"),
            ("Boeing 737 MAX 9", "narrowbody"),
            ("Lockheed Martin F-35A Lightning II", "military"),
            ("Boeing F/A-18E Super Hornet", "military"),
            ("Concorde", "retro"),
            ("Douglas DC-3", "retro"),
            ("Gulfstream G700", "bizjet"),
            ("Airbus A330-200F", "cargo"),
            ("Antonov An-225 Mriya", "cargo"),
            ("Boeing CH-47 Chinook", "helicopter"),
            ("Airbus Beluga XL", "cargo"),
            ("Cessna 172", "other"),
            ("Cessna 172S Skyhawk", "other"),      # 'Skyhawk' must NOT hit 'Hawk'
            ("Hawker 800XP", "bizjet"),            # 'Hawker' must NOT hit 'Hawk'
            ("BAE Hawk T2", "military"),           # but a real Hawk should
            ("Bombardier CRJ900", "narrowbody"),   # alpha token + trailing digits
            ("Embraer ERJ-145", "narrowbody"),
        ]
        ok = 0
        for t, expected in samples:
            got = classify(t)
            flag = "OK " if got == expected else "XX "
            ok += got == expected
            print(f"{flag} {t:40s} -> {got:15s} (expected {expected})")
        print(f"\n{ok}/{len(samples)} passed")
