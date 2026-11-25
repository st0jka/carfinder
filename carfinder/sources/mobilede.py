"""mobile.de through the official Apify API (actor blackfalcondata/mobile-de-scraper). Same car dict as autoscout24.

Paid per result, so each model is searched at most once a week and every run is capped in USD.
The week's cars are kept and handed to every scan, so a blocked or failed valuation costs nothing to repeat.
"""
import re
import time
from pathlib import Path

from curl_cffi import requests

from carfinder import db, models, net
from carfinder.sources import autoscout24

ACTOR_URL = "https://api.apify.com/v2/acts/blackfalcondata~mobile-de-scraper/run-sync-get-dataset-items"
LIMITS_URL = "https://api.apify.com/v2/users/me/limits"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

WEEK_S = 7 * 24 * 3600
RETRY_S = 24 * 3600        # a failed run may still have been charged, so it is not repeated every scan
# 19 models and the petrol runs of Golf, Polo, Astra and Corsa: 23 runs x 4.3 weeks x 0.0298 USD = 2.95 USD a month.
# 45 results (2.58 USD for the 19 alone) would put the petrol runs over the budget.
RESULTS_PER_RUN = 42
START_USD = 0.005          # Store price on the free plan, 24.11.2026
RESULT_USD = 0.00059
RUN_CAP_USD = START_USD + RESULTS_PER_RUN * RESULT_USD
MONTHLY_BUDGET_USD = 3.0   # free plan gives 5 USD a month; Bane's target is under 3
MAX_CC = models.MAX_CC
RUN_TIMEOUT_S = 300        # Apify's limit for a synchronous run

# mobile.de make and model names for carfinder.models. Only the core models: the 3 USD budget is full, and each
# daily model would add about 0.13 USD a month (0.26 with a petrol run).
MODELS = {
    "volkswagen/golf": ("Volkswagen", "Golf"), "volkswagen/polo": ("Volkswagen", "Polo"),
    "volkswagen/passat": ("Volkswagen", "Passat"), "volkswagen/tiguan": ("Volkswagen", "Tiguan"),
    "skoda/octavia": ("Skoda", "Octavia"), "skoda/superb": ("Skoda", "Superb"),
    "audi/a3": ("Audi", "A3"), "audi/a4": ("Audi", "A4"),
    "opel/astra": ("Opel", "Astra"), "opel/corsa": ("Opel", "Corsa"), "peugeot/3008": ("Peugeot", "3008"),
    # the actor takes a comma-separated list of models; mobile.de lists BMW and Mercedes by engine name
    "bmw/x1": ("BMW", "X1"), "bmw/520": ("BMW", "520"), "bmw/3er": ("BMW", "316,318,320"), "audi/a6": ("Audi", "A6"),
    "opel/insignia": ("Opel", "Insignia"), "mercedes-benz/b-klasse": ("Mercedes-Benz", "B 180,B 200"),
    "ford/kuga": ("Ford", "Kuga"), "hyundai/ix35": ("Hyundai", "ix35"),
}
# Plain petrol is paid for only in its own weekly run, for the years it sells in Serbia (models.petrol_years).
WANTED_FUELS = ["DIESEL", "HYBRID", "HYBRID_DIESEL", "PLUG_IN_HYBRID", "LPG", "CNG"]
PETROL = ["PETROL"]
FUEL = {"DIESEL": "diesel", "PETROL": "petrol", "LPG": "petrol_lpg", "CNG": "petrol_cng", "HYBRID": "hybrid",
        "HYBRID_DIESEL": "hybrid", "PLUG_IN_HYBRID": "hybrid", "ELECTRIC": "electric"}
GEARBOX = {"MANUAL": "manual", "AUTOMATIC": "automatic", "SEMIAUTOMATIC": "automatic"}
# mobile.de's own body classes (bodyTypeRaw); sedan, small car and off-road are one market in valuation.body_group.
BODY = {"EstateCar": "estate", "Cabrio": "cabrio", "SportsCar": "coupe", "Van": "van"}
DOORS = {"2/3": 3, "4/5": 5}
CC_IN_TEXT = re.compile(r"\b(\d[.,]?\d{3}) ?(?:ccm|cm3|cm³)", re.IGNORECASE)   # "1598 ccm", "1.968 cm³"
# The actor gives mobile.de's image proxy, which answers 403 to everyone but the site itself. The CDN behind it
# serves the same photo, but only with a size rule (400 without one); 640 px is enough for Haiku and the card.
PHOTO_PROXY = "https://m.mobile.de/yams-proxy/"
PHOTO_RULE = "?rule=mo-640.jpg"
# "2,5TDI", "3.0 l TDI", "3.0 V6 TDI", "3.0 BiTDI"
LITRES_IN_TEXT = re.compile(r"\b(\d)[.,](\d) ?(?:l )?(?:v6 |v8 |bi-?)?(?:tdi|tfsi|tsi|cdti|tdci|crdi|bluehdi|hdi|cdi)\b",
                            re.IGNORECASE)


def _token():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("APIFY_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("APIFY_TOKEN is missing in .env")


def engine_cc(item, text):
    """Exact cc when mobile.de has it; private sellers often leave it empty, then the ad's own words."""
    if item.get("cubicCapacityCc"):
        return item["cubicCapacityCc"]
    exact = CC_IN_TEXT.search(text)
    if exact:
        return int(re.sub(r"[.,]", "", exact.group(1)))
    litres = LITRES_IN_TEXT.search(text)
    if litres:
        cc = int(litres.group(1)) * 1000 + int(litres.group(2)) * 100
        # "2.0 TDI" is 1968 cc, too rough to match Serbian cars by, but "3.0 TDI" is surely above the limit
        if cc > MAX_CC:
            return cc
    return None


def photo_url(url):
    """The CDN address of a photo the actor gives through mobile.de's proxy; any other address stays as it is."""
    if not url or not url.startswith(PHOTO_PROXY):
        return url
    return "https://" + url[len(PHOTO_PROXY):] + PHOTO_RULE


def drive(title, features, description):
    """The actor has no drive field: 4x4 shows in the model name (4MOTION, quattro, 4x4), the equipment list or
    the seller's text. There is no detail page that could add it later."""
    return models.drive_of(title + " " + " ".join(features) + " " + description)


def parse_item(item):
    title = f"{item.get('title') or ''} {item.get('subTitle') or ''}".strip()
    description = item.get("description") or ""
    month, _, year = (item.get("firstRegistration") or "").partition("/")
    photos = [photo_url(url) for url in (item.get("imageUrls") or [])]
    zip_part, _, city = (item.get("sellerZipCity") or "").partition("\xa0")   # "DE-53545\xa0Linz am Rhein"
    return {
        "source": "mobilede",
        "id": "mobilede:" + item["listingKey"],
        "url": item["canonicalUrl"],
        "title": title,
        "make": item.get("make"),
        "model": item.get("model"),
        "year": int(year) if year.isdigit() else None,
        "month": int(month) if month.isdigit() else None,
        "km": item.get("mileageKm"),
        "kw": item.get("powerKw"),
        "cc": engine_cc(item, title + " " + description),
        "fuel": FUEL.get(item.get("fuelType"), "other"),
        "gearbox": GEARBOX.get(item.get("transmission")),
        "body": BODY.get(item.get("bodyTypeRaw")),
        "doors": DOORS.get(item.get("doors")),
        "drive": drive(title, item.get("features") or [], description),
        "price": item["price"],
        "net_price": item.get("netPrice"),
        "vat_deductible": bool(item.get("vatDeductible")),
        "seller": "dealer" if item.get("sellerType") == "Dealer" else "private",
        "country": item.get("country") or "DE",
        "zip": zip_part.partition("-")[2] or None,
        "city": city or item.get("location"),
        "damaged": bool(item.get("isCurrentlyDamaged")),
        "text": description[:4000],
        "equipment": item.get("features") or [],
        "mass": autoscout24._number(item.get("weight")),
        "market_median": None,
        "image": (photos or [None])[0],
        "images": photos[:autoscout24.MAX_IMAGES],   # no detail page: the search has them
        "detailed": bool(description),   # the description came with the search, no detail page to read
    }


def actor_input(as24_path, year_from, year_to, min_price, max_price, fuels=WANTED_FUELS):
    make, model = MODELS[as24_path]
    return {"make": make, "model": model, "category": "CAR", "fuelType": fuels,
            "yearMin": year_from, "yearMax": year_to, "priceMin": min_price, "priceMax": max_price,
            "sort": "price_asc", "maxResults": RESULTS_PER_RUN,
            "includeDetails": True, "descriptionFormat": "text",
            "customFilters": [{"field": "cubicCapacityCc", "op": "lte", "value": MAX_CC}]}


def check_budget(headers):
    response = requests.get(LIMITS_URL, headers=headers, timeout=40)
    response.raise_for_status()
    used = response.json()["data"]["current"]["monthlyUsageUsd"]
    if used + RUN_CAP_USD > MONTHLY_BUDGET_USD:
        raise net.Blocked(f"Apify budget reached: {used:.2f} of {MONTHLY_BUDGET_USD} USD used this month")


def run_actor(headers, search_input):
    params = {"maxItems": RESULTS_PER_RUN, "maxTotalChargeUsd": RUN_CAP_USD, "timeout": RUN_TIMEOUT_S}
    response = requests.post(ACTOR_URL, params=params, json=search_input, headers=headers, timeout=RUN_TIMEOUT_S + 30)
    if response.status_code == 402:
        raise net.Blocked("Apify credit is used up for this month")
    response.raise_for_status()
    return response.json()


def search(as24_path, year_from, year_to, min_price, max_price):
    if as24_path not in MODELS:
        return []
    cars = paid_search(as24_path, as24_path, WANTED_FUELS, year_from, year_to, min_price, max_price)
    petrol_years = [year for year in models.petrol_years(as24_path) if year_from <= year <= year_to]
    if not petrol_years:
        return cars
    # its own run: in one run the cheap petrol cars would push the diesels out of the results
    try:
        cars += paid_search(as24_path + " petrol", as24_path, PETROL, min(petrol_years), max(petrol_years),
                            min_price, max_price)
    except Exception as error:
        error.cars = cars   # the scan still gets the cars of the first run
        raise
    return cars


def paid_search(run_key, as24_path, fuels, year_from, year_to, min_price, max_price):
    """One weekly paid run; run_key keeps its own week in the database (a model's petrol run has its own)."""
    conn = db.connect()
    last = db.paid_run(conn, "mobilede", run_key)
    now = time.time()
    if last and last["finished"] and now - last["finished"] < WEEK_S:
        return last["cars"]   # valued again every scan for free
    if last and now - last["attempted"] < RETRY_S:
        return []
    headers = {"Authorization": "Bearer " + _token()}
    check_budget(headers)
    # Recorded before the POST: Apify can charge a run whose answer never arrives (timeout, dropped connection).
    db.mark_attempt(conn, "mobilede", run_key)
    cars = []
    for item in run_actor(headers, actor_input(as24_path, year_from, year_to, min_price, max_price, fuels)):
        try:
            cars.append(parse_item(item))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue   # one malformed ad must not lose the others
    db.store_run(conn, "mobilede", run_key, cars)
    return cars


def add_details(car):
    """Nothing to add: the search already brought the description, equipment and engine."""
    return car
