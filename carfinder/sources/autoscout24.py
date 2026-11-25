"""AutoScout24 list pages for screening and detail pages for candidates."""
import logging
import re

from carfinder import models, net

BASE = "https://www.autoscout24.de"
PAGES_PER_YEAR = 2   # 20 cars per page, cheapest first
# The site's own "fuel" filter: diesel, LPG, CNG, the two hybrids and electric. Plain petrol sells in Serbia only
# for some generations (models.petrol_years) and was a third of what one search of all fuels returned, so it gets
# its own pages in those years.
WANTED_FUELS = "D,L,C,2,3,E"
PETROL = "B"
MAX_IMAGES = 16   # photos Haiku looks at for damage the seller does not write about
# Models whose cheapest pages are mostly engines over 2.0 l (A6: 25 of 36 cars were 3.0 TDI); the site's own cap
# keeps both pages for cars that sell. Not for every model: the cap also drops ads without an engine size (5% of Golfs).
CC_CAPPED = {"audi/a6"}

log = logging.getLogger("carfinder")

FUEL = {"D": "diesel", "B": "petrol", "E": "electric", "L": "petrol_lpg", "C": "petrol_cng",
        "2": "hybrid", "3": "hybrid", "O": "other"}
# "touring sports" and "sports wagon" are Toyota and Kia, "cw" Hyundai; Seat's "ST" counts only after "Leon" or
# "Ibiza", so Ford's "ST-Line" stays a trim. A V60 needs no word: its model's body is estate.
ESTATE_WORDS = re.compile(r"\b(?:variant|avant|combi|kombi|touring|sports[ -]?tourer|country[ -]tourer|sw|break"
                          r"|grand ?tour|turnier|t-modell|estate|sports ?wagon|cw|c5 tourer|civic tourer"
                          r"|shooting ?brake)\b|\b(?:leon|ibiza) st\b(?!-)", re.I)
GEARBOX = {"Schaltgetriebe": "manual", "Automatik": "automatic", "Halbautomatik": "automatic"}
BODY = {"Kombi": "estate", "Limousine": "sedan", "Kleinwagen": "hatchback", "SUV/Geländewagen/Pickup": "suv",
        "Van/Kleinbus": "van", "Coupé": "coupe", "Cabrio": "cabrio"}
# Words that mean a wreck or a broken engine; such cars are dropped (customs can refuse them too).
WRECK_WORDS = ("motorschaden", "getriebeschaden", "nicht fahrbereit", "totalschaden", "wasserschaden",
               "hochwasser", "flutschaden", "brandschaden", "unfallwagen nicht", "bastler", "teileträger", "teilträger",
               "ersatzteile erhältlich", "ausschlachten", "schlachte", "springt nicht an", "airbag defekt",
               "airbags defekt",
               "rahmenschaden", "airbag ausgelöst", "airbags ausgelöst", "dach eingedrückt", "dach verzogen")
WRECK_READINGS = ("nije u voznom stanju", "auto ne pali", "motor ne pali", "kriv krov", "ulegnut krov",
                  "aktiviran airbag", "aktivirani airbag", "deformisana šasija")


def _number(text):
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits else None


def _detail_value(listing, label):
    for item in listing.get("vehicleDetails") or []:
        if item.get("ariaLabel") == label:
            return item.get("data")
    return None


def parse_list_item(item):
    vehicle = item["vehicle"]
    tracking = item.get("tracking") or {}
    month, _, year = (tracking.get("firstRegistration") or "-").partition("-")
    power = _detail_value(item, "Leistung") or ""
    kw = _number(power.split("kW")[0]) if "kW" in power else None
    variant = vehicle.get("variant") or ""
    model_name = vehicle.get("model")
    text = " ".join(filter(None, [vehicle.get("modelVersionInput"), vehicle.get("subtitle")]))
    title = f"{vehicle.get('make')} {vehicle.get('variant') or vehicle.get('model')} {vehicle.get('modelVersionInput') or ''}".strip()
    return {
        "source": "autoscout24",
        "id": "as24:" + item["id"],
        "url": BASE + item["url"],
        "title": title,
        "make": vehicle.get("make"),
        "model": model_name,
        "year": int(year) if year.isdigit() else None,
        "month": int(month) if month.isdigit() else None,
        "km": _number(tracking.get("mileage")),
        "kw": kw,
        "cc": _number(vehicle.get("engineDisplacementInCCM")),
        "fuel": FUEL.get((tracking.get("fuelType") or "").upper(), "other"),
        "gearbox": GEARBOX.get(vehicle.get("transmission")),
        "body": "estate" if ESTATE_WORDS.search(f"{variant} {vehicle.get('modelVersionInput') or ''}") else None,
        "doors": None,
        "drive": models.drive_of(title + " " + text),
        "price": item["price"]["priceRaw"],
        "net_price": None,
        "vat_deductible": False,
        "seller": "dealer" if (item.get("seller") or {}).get("type") == "Dealer" else "private",
        "country": (item.get("location") or {}).get("countryCode"),
        "zip": (item.get("location") or {}).get("zip"),
        "city": (item.get("location") or {}).get("city"),
        "damaged": bool(vehicle.get("isCurrentlyDamaged")),
        "text": text,
        "equipment": [],
        "mass": None,
        "market_median": None,
        "image": (item.get("images") or [None])[0],
        "images": [],   # the detail page fills them
        "detailed": False,
    }


def is_wreck(car):
    text = (car["title"] + " " + car["text"]).lower()
    reading = car.get("ai") or {}
    note = (reading.get("note") or "").lower()
    return reading.get("state") == "les" or any(word in note for word in WRECK_READINGS) or any(
        word in text for word in WRECK_WORDS)


def each_year(what, search_year, year_from, year_to):
    """One search per registration year: one search of all years only ever reached the cheapest, oldest cars.

    A year that fails is logged and skipped, so the other years are still read. A block is raised at once,
    because the site is then left alone for the rest of the run. Either error carries the cars of the years
    that were read in its `cars`: the scan keeps them and the failure still reaches the run's note."""
    cars = []
    failure = None
    for year in range(year_from, year_to + 1):
        try:
            cars += search_year(year)
        except net.Blocked as blocked:
            blocked.cars = cars
            raise
        except Exception as error:
            log.warning("search failed: %s %d: %r", what, year, error)
            failure = error
    if failure:
        failure.cars = cars
        raise failure
    return cars


# autoscout24.de stopped answering a search that includes CH (24.11.2026: 0 results for every model, Golf too);
# Swiss ads live on autoscout24.ch, which is not built.
def search(as24_path, year_from, year_to, min_price, max_price, countries="D,A"):
    def search_year(year):
        return search_one_year(as24_path, year, min_price, max_price, countries)
    return each_year("autoscout24 " + as24_path, search_year, year_from, year_to)


def has_euro_price(item):
    price = item["price"]
    currency = price.get("currency")
    if currency:
        return currency == "EUR"
    # Swiss listings need an explicit EUR quote before a numeric price can enter the receipt.
    return (item.get("location") or {}).get("countryCode") != "CH"


def search_one_year(as24_path, year, min_price, max_price, countries):
    cars = search_pages(as24_path, year, min_price, max_price, countries, WANTED_FUELS)
    if year in models.petrol_years(as24_path):
        # in one search the cheap petrol cars would push the diesels out of the two pages
        cars += search_pages(as24_path, year, min_price, max_price, countries, PETROL)
    return cars


def search_pages(as24_path, year, min_price, max_price, countries, fuels):
    cars = []
    for page in range(1, PAGES_PER_YEAR + 1):
        params = {"fregfrom": year, "fregto": year, "pricefrom": min_price, "priceto": max_price, "cy": countries,
                  "fuel": fuels, "atype": "C", "sort": "price", "desc": 0, "damaged_listing": "include",
                  "page": page}
        if as24_path in CC_CAPPED:
            params["ccmto"] = models.MAX_CC
        props = net.next_data(net.get(f"{BASE}/lst/{as24_path}", params=params, site="autoscout24").text)
        for item in props.get("listings") or []:
            try:
                if has_euro_price(item):
                    cars.append(parse_list_item(item))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue   # one malformed ad must not lose the others
        if page >= (props.get("numberOfPages") or 0):
            break
    return cars


def add_details(car):
    """Fills doors, body, drive, mass, net price, equipment and AutoScout24's own market median."""
    details = net.next_data(net.get(car["url"], site="autoscout24").text)["listingDetails"]
    vehicle = details["vehicle"]
    price = (details.get("prices") or {}).get("public") or {}
    car["doors"] = 3 if vehicle.get("numberOfDoors") in (2, 3) else 5 if vehicle.get("numberOfDoors") else None
    car["body"] = BODY.get(vehicle.get("bodyType"), car["body"])
    car["mass"] = _number(vehicle.get("weight"))
    car["cc"] = vehicle.get("rawDisplacementInCCM") or car["cc"]
    car["kw"] = vehicle.get("rawPowerInKw") or car["kw"]
    car["vat_deductible"] = bool(price.get("taxDeductible"))
    car["net_price"] = price.get("netPriceRaw")
    car["market_median"] = price.get("median")
    car["equipment"] = [entry["id"] for group in (vehicle.get("equipment") or {}).values() for entry in group]
    description = re.sub(r"<[^>]+>", " ", details.get("description") or "")
    car["text"] = (car["text"] + " " + description)[:4000]
    # sellers often leave the drive field empty and write 4Motion or 4x4 in the title or the description
    car["drive"] = "4x4" if vehicle.get("driveTrain") == "Allrad" else models.drive_of(car["title"] + " " + car["text"])
    # 800x600 is enough for Haiku to see a smashed front and costs a quarter of the 1280x960 tokens
    images = [url.replace("/1280x960.webp", "/800x600.webp") for url in details.get("images") or []]
    car["images"] = images[:MAX_IMAGES]
    car["detailed"] = True
    return car
