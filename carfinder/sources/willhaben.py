"""willhaben.at, Austria's main car market (many private sellers). Same car dict as autoscout24."""
import re

from carfinder import models, net
from carfinder.sources import autoscout24

SEARCH_URL = "https://www.willhaben.at/iad/gebrauchtwagen/auto/gebrauchtwagenboerse"
ROWS_PER_YEAR = 90   # one page per registration year, cheapest first
SORT_PRICE_ASC = 3

# willhaben make / model ids for carfinder.models (from the site's own filter list, 24.11.2026).
IDS = {
    "volkswagen/golf": ("1065", "1691"), "volkswagen/polo": ("1065", "1705"),
    "volkswagen/passat": ("1065", "1703"), "volkswagen/tiguan": ("1065", "1812"),
    "skoda/octavia": ("1057", "1600"), "skoda/superb": ("1057", "1605"),
    "audi/a3": ("1003", "1023"), "audi/a4": ("1003", "1024"),
    "opel/astra": ("1043", "1477"), "opel/corsa": ("1043", "1482"), "peugeot/3008": ("1045", "1881"),
    # BMW has no 520 or 318 here, only its series ("5er-Reihe", "3er-Reihe"); a 530d differs by kW anyway.
    "bmw/x1": ("1005", "1843"), "bmw/520": ("1005", "1046"), "bmw/3er": ("1005", "1042"),
    "audi/a6": ("1003", "1026"), "opel/insignia": ("1043", "1833"), "mercedes-benz/b-klasse": ("1036", "1386"),
    "ford/kuga": ("1017", "1829"), "hyundai/ix35": ("1020", "1858"),
    "bmw/1er": ("1005", "1041"),   # "1er-Reihe"
    # 25.11.2026, from the filter list of each make; a list holds the ids one model is filed under
    "volkswagen/touran": ("1065", "1709"),
    "volkswagen/sharan": ("1065", "1706"),
    "volkswagen/caddy": ("1065", "1686"),
    "volkswagen/t-roc": ("1065", "2108"),
    "volkswagen/up": ("1065", "1938"),
    "volkswagen/cc": ("1065", ["1958", "2007"]),
    "volkswagen/jetta": ("1065", "1698"),
    "skoda/fabia": ("1057", "1596"),
    "skoda/rapid": ("1057", "1601"),
    "skoda/kodiaq": ("1057", "2092"),
    "skoda/yeti": ("1057", "1889"),
    "skoda/karoq": ("1057", "2100"),
    "skoda/scala": ("1057", "2183"),
    "skoda/kamiq": ("1057", "2192"),
    "seat/leon": ("1056", "1590"),
    "seat/ibiza": ("1056", "1588"),
    "seat/ateca": ("1056", "2069"),
    "seat/alhambra": ("1056", "1583"),
    "seat/arona": ("1056", "2103"),
    "seat/altea": ("1056", ["1779", "1808"]),
    "audi/a1": ("1003", "1838"),
    "audi/a5": ("1003", "1789"),
    "audi/q2": ("1003", "2082"),
    "audi/q3": ("1003", "1925"),
    "audi/q5": ("1003", "1824"),
    "bmw/x3": ("1005", "1055"),
    "bmw/2er": ("1005", "2044"),
    "mercedes-benz/a-klasse": ("1036", "1384"),
    "mercedes-benz/c-klasse": ("1036", "1387"),
    "mercedes-benz/e-klasse": ("1036", "1393"),
    "mercedes-benz/cla": ("1036", "1973"),
    "mercedes-benz/gla": ("1036", "2043"),
    "opel/zafira": ("1043", ["1503", "2504"]),
    "opel/meriva": ("1043", "1487"),
    "opel/mokka": ("1043", "1965"),
    "opel/grandland": ("1043", ["2104", "2356"]),
    "opel/crossland": ("1043", ["2282", "2090"]),
    "opel/adam": ("1043", "1969"),
    "peugeot/207": ("1045", "1743"),
    "peugeot/208": ("1045", "1948"),
    "peugeot/308": ("1045", "1805"),
    "peugeot/2008": ("1045", "1977"),
    "peugeot/508": ("1045", "1919"),
    "peugeot/5008": ("1045", "1882"),
    "renault/clio": ("1051", "1542"),
    "renault/megane": ("1051", "1548"),
    "renault/scenic": ("1051", ["1558", "1940"]),
    "renault/captur": ("1051", "1978"),
    "renault/kadjar": ("1051", "2062"),
    "renault/talisman": ("1051", "2070"),
    "renault/laguna": ("1051", "1546"),
    "renault/koleos": ("1051", "1834"),
    "renault/twingo": ("1051", "1562"),
    "renault/kangoo": ("1051", "1545"),
    "citroen/c3": ("1010", "1102"),
    "citroen/c4": ("1010", "1103"),
    "citroen/c4-cactus": ("1010", "2057"),
    "citroen/c5": ("1010", "1104"),
    "citroen/c3-picasso": ("1010", "1846"),
    "citroen/c3-aircross": ("1010", "2117"),
    "citroen/c5-aircross": ("1010", "2170"),
    "citroen/berlingo": ("1010", "1096"),
    "dacia/duster": ("1011", "1849"),
    "dacia/sandero": ("1011", "1826"),
    "fiat/tipo": ("1016", "1189"),
    "fiat/500x": ("1016", "2056"),
    "fiat/500l": ("1016", "2041"),
    "fiat/doblo": ("1016", "1168"),
    "fiat/punto": ("1016", ["1180", "1173"]),
    "fiat/500": ("1016", "1795"),
    "fiat/panda": ("1016", "1179"),
    "fiat/bravo": ("1016", "1163"),
    "ford/focus": ("1017", "1197"),
    "ford/fiesta": ("1017", "1195"),
    "ford/mondeo": ("1017", "1203"),
    "ford/c-max": ("1017", "1816"),
    "ford/s-max": ("1017", "1740"),
    "ford/galaxy": ("1017", "1200"),
    "ford/b-max": ("1017", "1961"),
    "ford/ecosport": ("1017", "2028"),
    "ford/puma": ("1017", "1206"),
    "toyota/auris": ("1062", "1785"),
    "toyota/yaris": ("1062", "1657"),
    "toyota/rav4": ("1062", "1654"),
    "toyota/avensis": ("1062", "1637"),
    "toyota/verso": ("1062", "1894"),
    "toyota/corolla": ("1062", "1643"),
    "toyota/c-hr": ("1062", "2081"),
    "kia/sportage": ("1025", "1289"),
    "kia/ceed": ("1025", "1767"),
    "kia/rio": ("1025", "1285"),
    "hyundai/i30": ("1020", "1796"),
    "hyundai/tucson": ("1020", "1256"),
    "hyundai/i20": ("1020", "1857"),
    "nissan/qashqai": ("1042", "1774"),
    "nissan/juke": ("1042", "1878"),
    "nissan/x-trail": ("1042", "1474"),
    "nissan/micra": ("1042", "1460"),
    "mazda/mazda3": ("1035", "1364"),
    "mazda/mazda6": ("1035", "1366"),
    "mazda/cx-5": ("1035", "1945"),
    "mazda/cx-3": ("1035", "2060"),
    "mazda/mazda2": ("1035", "1363"),
    "volvo/v40": ("1064", "1677"),
    "volvo/v60": ("1064", "1924"),
    "volvo/s60": ("1064", "1673"),
    "volvo/xc60": ("1064", "1835"),
    "volvo/xc40": ("1064", "2126"),
    "honda/civic": ("1018", "1222"),
    "honda/cr-v": ("1018", "1225"),
    "honda/jazz": ("1018", "1230"),
    "mitsubishi/asx": ("1040", "1872"),
    "mitsubishi/outlander": ("1040", "1435"),
    "suzuki/swift": ("1061", "1632"),
    "suzuki/vitara": ("1061", "1633"),
    "suzuki/sx4-s-cross": ("1061", ["2275", "2237"]),
    "chevrolet/cruze": ("1008", "1844"),
    "alfa-romeo/giulietta": ("1000", "1837"),
}
MAKE_NAME = {"1065": "Volkswagen", "1057": "Škoda", "1003": "Audi", "1043": "Opel", "1045": "Peugeot", "1005": "BMW",
             "1036": "Mercedes-Benz", "1010": "Citroën", "1017": "Ford", "1020": "Hyundai", "1056": "Seat",
             "1051": "Renault", "1011": "Dacia", "1016": "Fiat", "1062": "Toyota", "1025": "Kia", "1042": "Nissan",
             "1035": "Mazda", "1064": "Volvo", "1018": "Honda", "1040": "Mitsubishi", "1061": "Suzuki",
             "1008": "Chevrolet", "1000": "Alfa Romeo"}
FUEL = {"100001": "petrol", "100003": "diesel", "100004": "electric", "100011": "petrol_lpg",
        "100013": "hybrid", "100022": "hybrid"}
# The search asks for every fuel but plain petrol (the site's ENGINE/FUEL filter); petrol gets its own search in
# the years it sells in Serbia (models.petrol_years).
WANTED_FUELS = [fuel_id for fuel_id, fuel in FUEL.items() if fuel != "petrol"]
PETROL = ["100001"]
GEARBOX = {"180001": "manual", "180004": "automatic"}
ESTATE_WORDS = autoscout24.ESTATE_WORDS


def _attributes(advert):
    return {a["name"]: a["values"] for a in advert["attributes"]["attribute"]}


def _first(attrs, name):
    values = attrs.get(name) or [None]
    return values[0]


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_list_item(advert, as24_path):
    attrs = _attributes(advert)
    make_id, _ = IDS[as24_path]
    heading = _first(attrs, "HEADING") or advert.get("description") or ""
    model_name = as24_path.split("/")[1].capitalize()
    doors = _int(_first(attrs, "NO_OF_DOORS"))
    condition = (_first(attrs, "CONDITION_RESOLVED") or "").lower()
    image = _first(attrs, "MMO")
    return {
        "source": "willhaben",
        "id": "willhaben:" + str(advert["id"]),
        "url": "https://www.willhaben.at/iad/" + (_first(attrs, "SEO_URL") or ""),
        "title": heading,
        "make": MAKE_NAME[make_id],
        "model": model_name,
        "year": _int(_first(attrs, "YEAR_MODEL")),
        "month": None,
        "km": _int(_first(attrs, "MILEAGE")),
        "kw": _int(_first(attrs, "ENGINE/EFFECT")),
        "cc": None,
        "fuel": FUEL.get(_first(attrs, "ENGINE/FUEL"), "other"),
        "gearbox": GEARBOX.get(_first(attrs, "TRANSMISSION")),
        "body": "estate" if ESTATE_WORDS.search(heading) else None,
        "doors": None if doors is None else (3 if doors <= 3 else 5),
        "drive": models.drive_of(heading),
        "price": _int(_first(attrs, "PRICE")),
        "net_price": None,
        "vat_deductible": False,   # Austrian ads are gross; a net export price must be confirmed by phone
        "seller": "private" if _first(attrs, "ISPRIVATE") == "1" else "dealer",
        "country": "AT",
        "zip": _first(attrs, "POSTCODE"),
        "city": _first(attrs, "LOCATION"),
        "damaged": "unfall" in condition or "defekt" in condition,
        "text": heading,
        "equipment": [],
        "mass": None,
        "market_median": None,
        "image": image,
        "images": [],   # the detail page fills them
        "detailed": False,
    }


def search(as24_path, year_from, year_to, min_price, max_price):
    if as24_path not in IDS:
        return []

    def search_year(year):
        return search_one_year(as24_path, year, min_price, max_price)
    return autoscout24.each_year("willhaben " + as24_path, search_year, year_from, year_to)


def search_one_year(as24_path, year, min_price, max_price):
    cars = search_fuels(as24_path, year, min_price, max_price, WANTED_FUELS)
    if year in models.petrol_years(as24_path):
        # in one search the cheap petrol cars would push the diesels out of the 90 rows
        cars += search_fuels(as24_path, year, min_price, max_price, PETROL)
    return cars


def search_fuels(as24_path, year, min_price, max_price, fuels):
    # a model id or a list of them: willhaben files the Zafira Tourer apart from the Zafira, and the search adds them
    make_id, model_id = IDS[as24_path]
    params = {"CAR_MODEL/MAKE": make_id, "CAR_MODEL/MODEL": model_id, "YEAR_MODEL_FROM": year, "YEAR_MODEL_TO": year,
              "PRICE_FROM": min_price, "PRICE_TO": max_price, "ENGINE/FUEL": fuels, "sort": SORT_PRICE_ASC,
              "rows": ROWS_PER_YEAR, "page": 1}
    result = net.next_data(net.get(SEARCH_URL, params=params, site="willhaben").text)["searchResult"]
    cars = []
    for advert in result["advertSummaryList"]["advertSummary"]:
        try:
            cars.append(parse_list_item(advert, as24_path))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue   # one malformed ad must not lose the others
    return [car for car in cars if car["price"]]


def add_details(car):
    details = net.next_data(net.get(car["url"], site="willhaben").text)["advertDetails"]
    attrs = _attributes(details)
    car["cc"] = _int(_first(attrs, "ENGINE/VOLUME")) or car["cc"]
    car["kw"] = _int(_first(attrs, "ENGINE/EFFECT")) or car["kw"]
    if "Kombi" in (_first(attrs, "CAR_TYPE") or ""):
        car["body"] = "estate"
    car["equipment"] = attrs.get("EQUIPMENT") or []
    description = re.sub(r"<[^>]+>", " ", _first(attrs, "DESCRIPTION") or "")
    car["text"] = (car["text"] + " " + description)[:4000]
    # the drive field is often empty while the heading or the description says 4Motion or 4x4
    car["drive"] = "4x4" if _first(attrs, "WHEEL_DRIVE") == "Allrad" else models.drive_of(car["text"])
    images = (details.get("advertImageList") or {}).get("advertImage") or []
    car["images"] = [image["mainImageUrl"] for image in images if image.get("mainImageUrl")][:autoscout24.MAX_IMAGES]
    car["detailed"] = True
    return car
