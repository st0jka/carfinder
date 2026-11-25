"""polovniautomobili.com: every ad of one model generation and fuel, cheapest first; variants are matched locally."""
import logging
import re

from carfinder import models, net

SEARCH_URL = "https://www.polovniautomobili.com/auto-oglasi/pretraga"
MAX_PAGES = 300    # 25 ads a page; a page count above this is a broken query or page, not a popular model
CC_WINDOW = 30
KW_WINDOW = 2

log = logging.getLogger("carfinder")

FUEL_PARAM = {"diesel": "diesel", "petrol": "gasoline", "petrol_lpg": "gasolineLpg", "petrol_cng": "gasolineCng",
              "hybrid": "hybridGasoline", "electric": "electric"}
FUEL_TEXT = {"Dizel": "diesel", "Benzin": "petrol", "Benzin + Gas (TNG)": "petrol_lpg",
             "Benzin + Metan (CNG)": "petrol_cng", "Hibridni pogon (Benzin)": "hybrid",
             "Hibridni pogon (Dizel)": "hybrid", "Električni pogon": "electric"}
BODY_TEXT = {"Hečbek": "hatchback", "Karavan": "estate", "Limuzina": "sedan", "Džip/SUV": "suv",
             "Monovolumen (MiniVan)": "van", "Kupe": "coupe", "Kabriolet/Roadster": "cabrio", "Pickup": "pickup"}

# Words in a title that mean the car is not a clean comparable.
BAD_WORDS = ("delovi", "za delove", "neispravan", "u kvaru", "ne radi", "havar", "oštećen", "ostecen",
             "udaren", "ne pali", "bez papira", "uvoz u toku", "na strane", "ocarinjen nije")
MONTHLY_PAYMENT = re.compile(r"\brata(?: od)?\s*(\d+)")


def search_params(pa_brand, pa_models, year_from, year_to, fuel, page):
    params = {"brand": pa_brand, "model[]": pa_models, "yearFrom": year_from, "yearTo": year_to,
              "damaged[]": "notDamaged", "sort": "price_asc", "page": page}
    if fuel in FUEL_PARAM:
        params["fuel[]"] = FUEL_PARAM[fuel]
    return params


def _gearbox(text):
    if text.startswith("Automatski"):
        return "automatic"
    if text.startswith("Manuelni"):
        return "manual"
    return None


def _doors(text):
    if text.startswith("2/3"):
        return 3
    if text.startswith("4/5"):
        return 5
    return None


def parse_result(item):
    drive = (item.get("featuredInfo") or {}).get("drive") or ""
    return {
        "id": item["id"],
        "url": f"https://www.polovniautomobili.com/auto-oglasi/{item['id']}/",
        "title": item.get("title") or "",
        "model": item.get("model"),
        "year": item.get("year"),
        "price": item.get("price"),
        "km": item.get("mileage"),
        "cc": item.get("engineVolume"),
        "kw": item.get("power"),
        "fuel": FUEL_TEXT.get(item.get("fuel"), item.get("fuel")),
        "gearbox": _gearbox(item.get("gearBox") or ""),
        "body": BODY_TEXT.get(item.get("chassis"), item.get("chassis")),
        "doors": _doors(item.get("doors") or ""),
        # the drive field is often empty on a "4Motion" or "quattro" ad
        "drive": "4x4" if "4x4" in drive else models.drive_of(item.get("title")),
        "tags": item.get("tags") or [],
        "dealer": bool(item.get("dealer")),
        "city": item.get("city"),
        "updated": item.get("updatedAt"),
        "image": item.get("imageMain"),
        # the seller lowered the price; base_price is the price before a cut, on an uncut ad just the asking price
        "cut": bool(item.get("discount")),
        "base_price": item.get("basePrice"),
        "owner": item.get("owner"),   # seller id: later tells a repost from a sale
    }


def fetch_snapshot(pa_brand, pa_model, year_from, year_to, fuel):
    """All pages of one model, year range and fuel. An error on any page fails the whole snapshot."""
    cars = {}
    page = 1
    while True:
        params = search_params(pa_brand, models.pa_names(pa_model), year_from, year_to, fuel, page)
        props = net.next_data(net.get(SEARCH_URL, params=params, site="polovni").text)
        page_count = props["pagination"]["pageCount"]
        if page_count > MAX_PAGES:
            raise ValueError(f"{pa_model} {fuel}: {page_count} pages is more than {MAX_PAGES}")
        for item in props["searchResults"]["results"]:
            try:
                if not item or not item.get("id"):
                    continue
                cars[item["id"]] = parse_result(item)   # same ad can repeat across pages
            except (TypeError, ValueError, AttributeError):
                continue   # one malformed ad must not lose the others
        if page >= page_count:
            break
        page += 1
    log.info("polovni %s %s %d-%d: %d ads on %d pages", pa_model, fuel, year_from, year_to, len(cars), page)
    return list(cars.values())


def variant_ads(snapshot, year_from, year_to, cc, kw):
    """Every ad of these years and this engine, in the snapshot's order (cheapest first).

    There is no limit: a Scout or a DSG estate sits behind many cheaper base cars of the same engine, and a
    cut at the cheapest 75 left it without its own ads."""
    ads = []
    for ad in snapshot:
        if not year_from <= (ad.get("year") or 0) <= year_to:
            continue
        if cc and (not ad.get("cc") or abs(ad["cc"] - cc) > CC_WINDOW):
            continue
        if kw and (not ad.get("kw") or abs(ad["kw"] - kw) > KW_WINDOW):
            continue
        ads.append(ad)
    return ads


def is_clean(car):
    title = car["title"].lower()
    if any(word in title for word in BAD_WORDS):
        return False
    if "Strane tablice" in car["tags"] or not car["price"]:
        return False
    payment = MONTHLY_PAYMENT.search(title)
    if payment and car["price"] == int(payment.group(1)):
        return False
    return True
