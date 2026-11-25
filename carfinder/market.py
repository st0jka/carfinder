"""What the Serbian market thinks of a car: variants buyers avoid, and how fast a variant sells.

Reputation is a short table backed by Novky or by PA data. Sell speed is measured in every scan from the PA ads
it holds: the age of the ads still listed, compared with every other PA ad of the scan in the same price band.
"""
import bisect
import re
import statistics
from datetime import datetime

from carfinder import polovni

AVOID, NOTE = "izbaci", "napomena"

# A key a row leaves out matches any car. A key the row sets and the car lacks (no gearbox on a list page) is no
# match, so an unknown never drops a car. "make" is the lower-case start of the site's own make name.
REPUTATION = [
    # Novky 24.11.2026 "Ford automatik losi" (PowerShift). PA 24.11: a Kuga II automatic asks 0.99 of the same
    # manual (VW automatics 1.03-1.10), 13% of them have a cut price against 2% of manuals, and 6 of the 8 Kugas
    # at +700 in the 24.11 scan were automatics: the gap of a car that does not sell.
    {"make": "ford", "gearbox": "automatic", "effect": AVOID},
    # Novky 25.11.2026, asked one by one: Opel automatik "Ne" (PA 25.11 also lists an Insignia B automatic 64 days
    # against 34), Renault EDC "Ne", Hyundai and Kia automatik "Ne". Mercedes A and B DCT "Ok": no row.
    {"make": "opel", "gearbox": "automatic", "effect": AVOID},
    {"make": "renault", "gearbox": "automatic", "effect": AVOID},
    {"make": "hyundai", "gearbox": "automatic", "effect": AVOID},
    {"make": "kia", "gearbox": "automatic", "effect": AVOID},
    # Novky 25.11: Peugeot "samo sa automatskim menjacem nikako robot". The sites file a robot (ETG, EGS, BMP, 2-Tronic)
    # under automatic like a torque converter (AT6, EAT6, EAT8), so only the ad's own words tell them apart.
    {"make": "peugeot", "gearbox": "automatic", "words": re.compile(r"\b(?:etg ?\d?|egs ?\d?|bmp ?\d?|2-?tronic)\b|"
                                                                    r"halbautomati|automatisiert", re.I),
     "effect": AVOID},
    {"make": "citro", "gearbox": "automatic", "words": re.compile(r"\b(?:etg ?\d?|egs ?\d?|bmp ?\d?)\b|"
                                                                  r"halbautomati|automatisiert", re.I),
     "effect": AVOID},
    # Novky 24.11: Passat B6 1.4 TSI CNG "5000 max da ga prodas"; 25.11 on factory CNG: "Vise ne".
    {"fuel": "petrol_cng", "effect": AVOID},
]

MIN_SPEED_ADS = 15     # fewer ads of known age, in the variant or in its price band, give no speed
BAND_SHARE = 0.25      # the same price band: asks within 25% of the variant's median ask
# shortcut: both ratios were guessed on 25.11.2026 between B-Klasse (x2.0), C4 Picasso II (x1.8), Octavia III (x1.3) and
# X1 (x1.2) for slow, 520d F10 (x0.7) and Golf 7 (x0.9) for fast; set them again from pa_seen after 3-4 weeks of scans.
SLOW_RATIO = 1.5
FAST_RATIO = 0.8


def matches(row, car):
    if "make" in row and not (car.get("make") or "").lower().startswith(row["make"]):
        return False
    for key in ("gearbox", "fuel"):
        if key in row and car.get(key) != row[key]:
            return False
    if "words" in row and not row["words"].search(f"{car.get('title') or ''} {car.get('text') or ''}"):
        return False
    return True


def avoided(car):
    """Serbian buyers do not take this variant: the car is not shown."""
    return any(row["effect"] == AVOID and matches(row, car) for row in REPUTATION)


def notes(car):
    """Lines for the card about what Serbian buyers hold against this variant."""
    return [row["text"] for row in REPUTATION if row["effect"] == NOTE and matches(row, car)]


def add_ages(snapshots, now=None):
    """Sets ad["age_days"] on the PA ads of this scan. PA ad ids only grow and an ad is updated no earlier than it
    was created, so an ad is at least as old as the earliest last update of any ad with an id at or above its own.
    The age is a lower bound: a variant can only look faster than it is, never slower."""
    now = now or datetime.now()
    ads = []
    for cars in snapshots.values():
        for ad in cars:
            if str(ad.get("id")).isdigit():
                ads.append(ad)
    ads.sort(key=lambda ad: int(ad["id"]), reverse=True)
    created_by = now
    for ad in ads:   # newest id first
        try:
            updated = datetime.strptime(ad.get("updated") or "", "%Y-%m-%d %H:%M:%S")
        except ValueError:   # no or odd update time: the newer ads still bound this one
            updated = now
        created_by = min(created_by, updated)
        ad["age_days"] = (now - created_by).days


def band_reference(snapshots):
    """(ask, age, id) of every clean PA ad of this scan with a known age, cheapest first, one entry per ad."""
    by_id = {}
    for cars in snapshots.values():
        for ad in cars:
            if "age_days" in ad and polovni.is_clean(ad):
                by_id[str(ad["id"])] = (ad["price"], ad["age_days"], str(ad["id"]))
    return sorted(by_id.values())


def speed(ads, reference):
    """How long this variant's ads stay listed against the other PA ads of the scan in the same price band.

    Returns {"label": "brzo" | "normalno" | "sporo", "age_days", "usual_days", "cut_share", "n"}, or None when the
    variant or its band has too few ads of known age."""
    aged = [ad for ad in ads if "age_days" in ad]
    if len(aged) < MIN_SPEED_ADS:
        return None
    price = statistics.median(ad["price"] for ad in aged)
    low = bisect.bisect_left(reference, (price * (1 - BAND_SHARE),))
    high = bisect.bisect_right(reference, (price * (1 + BAND_SHARE), float("inf")))
    # the variant's own ads are left out, or a big variant (Golf 7, Octavia) is mostly measured against itself
    own = {str(ad.get("id")) for ad in aged}
    band = [age for _, age, ad_id in reference[low:high] if ad_id not in own]
    if len(band) < MIN_SPEED_ADS:
        return None
    age = statistics.median(ad["age_days"] for ad in aged)
    usual = statistics.median(band)
    ratio = age / max(usual, 1)
    if ratio >= SLOW_RATIO:
        label = "sporo"
    elif ratio <= FAST_RATIO:
        label = "brzo"
    else:
        label = "normalno"
    cut = sum(1 for ad in aged if ad.get("cut"))
    return {"label": label, "age_days": round(age), "usual_days": round(usual), "cut_share": round(cut / len(aged), 2),
            "n": len(aged)}
