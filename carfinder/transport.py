"""Transport cost from the seller to Pancevo, from Bane's real carrier prices (23.11.2026)."""
import math

SUBOTICA = (46.10, 19.67)
MAX_DISTANCE_KM = 1250
ROAD_FACTOR = 1.25        # road km is roughly 1.25 x straight-line km in this region
DOMESTIC_LEG_EUR = 120    # Subotica -> Pancevo
LARGE_CAR_EXTRA_EUR = 150  # Frankfurt 700 small vs 850 big car

# Bane's quotes to Subotica, without the 120 domestic leg.
FRANKFURT_CITIES = ("frankfurt", "frankfurt am main")
KNOWN_ROUTES = {("AT", "wien"): 500, ("AT", "vienna"): 500, ("DE", "frankfurt"): 700,
                ("DE", "frankfurt am main"): 700, ("CH", "zurich"): 700, ("CH", "zürich"): 700}

# Rough centre of each postcode region (first digit), enough for a transport estimate.
ZIP_REGIONS = {
    "DE": {"0": (51.1, 13.0), "1": (52.5, 13.4), "2": (53.6, 10.0), "3": (52.0, 9.8), "4": (51.5, 7.2),
           "5": (50.8, 7.0), "6": (50.0, 8.5), "7": (48.7, 9.0), "8": (48.1, 11.6), "9": (49.5, 11.0)},
    "AT": {"1": (48.2, 16.4), "2": (48.0, 16.2), "3": (48.2, 15.6), "4": (48.3, 14.3), "5": (47.8, 13.0),
           "6": (47.3, 11.4), "7": (47.4, 16.3), "8": (47.1, 15.4), "9": (46.6, 14.3)},
    "CH": {"1": (46.5, 6.6), "2": (47.0, 7.0), "3": (46.9, 7.4), "4": (47.5, 7.6), "5": (47.4, 8.1),
           "6": (46.9, 8.5), "7": (46.8, 9.5), "8": (47.4, 8.5), "9": (47.4, 9.4)},
}
COUNTRY_CENTRE = {"DE": (50.1, 8.7), "AT": (48.2, 16.4), "CH": (47.4, 8.5), "IT": (45.5, 10.0),
                  "SI": (46.1, 14.5), "HR": (45.8, 16.0), "HU": (47.5, 19.0), "CZ": (49.8, 15.5),
                  "SK": (48.5, 18.5), "NL": (52.1, 5.3), "BE": (50.8, 4.4), "FR": (48.6, 7.7), "PL": (51.0, 19.0)}


def straight_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def location_point(country, zip_code=""):
    region = ZIP_REGIONS.get(country, {}).get(str(zip_code or "")[:1])
    return region or COUNTRY_CENTRE.get(country)


def road_km(country, zip_code=""):
    point = location_point(country, zip_code)
    if point is None:
        return None
    return round(straight_km(SUBOTICA, point) * ROAD_FACTOR)


def transport_eur(country, zip_code="", city="", large_car=False):
    """Seller -> Subotica -> Pancevo. Known cities use Bane's price; others scale with road distance."""
    city = (city or "").lower().strip()
    base = KNOWN_ROUTES.get((country, city))
    if base is None:
        km = road_km(country, zip_code)
        if km is None:
            return None
        # Line through Bane's quotes: Vienna ~530 road km -> 500, Frankfurt ~1150 road km -> 700.
        base = 330 + 0.32 * km
    if large_car and country == "DE" and city in FRANKFURT_CITIES:
        base += LARGE_CAR_EXTRA_EUR
    return round(base + DOMESTIC_LEG_EUR)
