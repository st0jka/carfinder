import json
from pathlib import Path

import pytest

from carfinder import models, net, scan, valuation
from carfinder.sources import willhaben

ADVERTS = json.loads((Path(__file__).parent / "fixtures" / "willhaben_golf.json").read_text(encoding="utf-8"))


def parsed():
    return [willhaben.parse_list_item(advert, "volkswagen/golf") for advert in ADVERTS]


def test_fields_from_real_search_page():
    first = parsed()[0]
    assert first["id"] == "willhaben:1147219773"
    assert first["country"] == "AT"
    assert first["make"] == "Volkswagen"
    assert (first["year"], first["km"], first["kw"]) == (2020, 185000, 66)
    assert (first["fuel"], first["gearbox"], first["doors"]) == ("diesel", "manual", 3)
    assert first["seller"] == "private"
    assert first["url"].startswith("https://www.willhaben.at/iad/gebrauchtwagen/d/auto/")
    assert first["vat_deductible"] is False


def test_dealer_estate_and_damaged_flags():
    cars = parsed()
    assert [c["seller"] for c in cars] == ["private", "private", "dealer", "dealer"]
    assert cars[1]["body"] == "estate" and cars[1]["damaged"] is True
    assert cars[3]["body"] is None and cars[3]["damaged"] is False


def test_same_keys_as_autoscout24():
    from carfinder.sources import autoscout24
    item = {"id": "x", "url": "/a", "price": {"priceRaw": 1}, "vehicle": {}, "tracking": {}}
    assert set(parsed()[0]) == set(autoscout24.parse_list_item(item))


def test_missing_attributes_do_not_crash():
    car = willhaben.parse_list_item({"id": 1, "attributes": {"attribute": []}}, "volkswagen/golf")
    assert car["price"] is None and car["year"] is None and car["doors"] is None


def test_500_euro_golf_is_under_the_scan_minimum_and_gets_no_label_from_the_serbian_price():
    car = parsed()[0]
    assert car["price"] == 500
    assert not scan.usable(car)            # cheaper than scan.MIN_PRICE_EUR: a placeholder or scrap
    assert not any(f.startswith("sumnjivo") for f in valuation.flags_of(car))   # willhaben has no market median


def test_every_model_has_willhaben_ids_and_a_make_name():
    assert set(willhaben.IDS) == {model["as24"] for model in models.MODELS}
    model_ids = []
    for make_id, model_id in willhaben.IDS.values():
        assert make_id.isdigit() and make_id in willhaben.MAKE_NAME
        ids = model_id if isinstance(model_id, list) else [model_id]   # a list: one model filed under several ids
        assert ids and all(one.isdigit() for one in ids)
        model_ids += ids
    assert len(model_ids) == len(set(model_ids)) == 146


@pytest.mark.parametrize("as24,model_ids", [
    ("opel/zafira", ["1503", "2504"]), ("renault/scenic", ["1558", "1940"]), ("opel/grandland", ["2104", "2356"]),
    ("opel/crossland", ["2282", "2090"]), ("fiat/punto", ["1180", "1173"]), ("seat/altea", ["1779", "1808"]),
    ("volkswagen/cc", ["1958", "2007"]), ("suzuki/sx4-s-cross", ["2275", "2237"]),
])
def test_model_filed_under_several_ids_is_asked_for_all_of_them_in_one_search(site, as24, model_ids):
    requests = site({2018: [advert(1, heading="heading 2.0 Diesel")]})
    cars = willhaben.search(as24, 2018, 2018, 1500, 15000)   # a petrol model also has a petrol search
    assert all(request["CAR_MODEL/MODEL"] == model_ids for request in requests)
    assert cars[0]["make"] == willhaben.MAKE_NAME[willhaben.IDS[as24][0]]


def test_petrol_year_gets_its_own_petrol_search_after_the_other_fuels(site):
    requests = site({2015: [advert(1)]})
    willhaben.search("volkswagen/golf", 2015, 2015, 1500, 15000)
    assert [request["ENGINE/FUEL"] for request in requests] == [willhaben.WANTED_FUELS, ["100001"]]
    assert {(request["YEAR_MODEL_FROM"], request["CAR_MODEL/MODEL"]) for request in requests} == {(2015, "1691")}


def test_petrol_is_asked_for_only_in_the_years_of_a_petrol_generation(site):
    requests = site({})
    willhaben.search("opel/astra", 2016, 2017, 1500, 15000)   # Astra J (petrol) ends in 2016, the K is diesel only
    assert [(request["YEAR_MODEL_FROM"], request["ENGINE/FUEL"]) for request in requests] == [
        (2016, willhaben.WANTED_FUELS), (2016, ["100001"]), (2017, willhaben.WANTED_FUELS)]


def test_model_without_a_petrol_generation_is_never_asked_for_petrol(site):
    requests = site({})
    willhaben.search("volkswagen/passat", 2010, 2023, 1500, 15000)
    assert len(requests) == 14 and all("100001" not in request["ENGINE/FUEL"] for request in requests)


def test_failed_petrol_search_does_not_lose_the_other_years(site, monkeypatch):
    calls = []

    def search_fuels(as24_path, year, min_price, max_price, fuels):
        calls.append((year, fuels))
        if fuels == willhaben.PETROL and year == 2015:
            raise RuntimeError("HTTP 500")
        return [willhaben.parse_list_item(advert(f"{year}{len(fuels)}"), as24_path)]
    monkeypatch.setattr(willhaben, "search_fuels", search_fuels)
    with pytest.raises(RuntimeError, match="HTTP 500") as failed:
        willhaben.search("volkswagen/polo", 2015, 2016, 1500, 15000)
    # the 2015 diesel cars are lost with their year, as with any failed year; 2016 is read in full
    assert [car["id"] for car in failed.value.cars] == ["willhaben:20165", "willhaben:20161"]
    assert len(calls) == 4


@pytest.mark.parametrize("as24,ids,make,model", [
    ("bmw/x1", ("1005", "1843"), "BMW", "X1"), ("bmw/520", ("1005", "1046"), "BMW", "520"),
    ("bmw/3er", ("1005", "1042"), "BMW", "3er"), ("audi/a6", ("1003", "1026"), "Audi", "A6"),
    ("opel/insignia", ("1043", "1833"), "Opel", "Insignia"),
    ("mercedes-benz/b-klasse", ("1036", "1386"), "Mercedes-Benz", "B-klasse"),
    ("ford/kuga", ("1017", "1829"), "Ford", "Kuga"), ("hyundai/ix35", ("1020", "1858"), "Hyundai", "Ix35"),
])
def test_added_models_are_searched_and_named_as_willhaben_lists_them(site, as24, ids, make, model):
    requests = site({2014: [advert(1, heading="heading 2.0 Diesel")]})
    car, = willhaben.search(as24, 2014, 2014, 1500, 15000)
    make_id, model_id = ids
    assert requests[0]["CAR_MODEL/MAKE"] == make_id
    assert requests[0]["CAR_MODEL/MODEL"] == model_id
    assert (car["make"], car["model"]) == (make, model)


def test_unknown_model_returns_nothing_without_request():
    assert willhaben.search("bmw/x5", 2015, 2020, 1500, 9000) == []


# --- one search per year, non-petrol fuels ---------------------------------------

@pytest.fixture
def site(monkeypatch):
    """Stands in for willhaben: site(years) serves years[year] and returns the requests that were made."""
    def serve(years):
        requests = []

        def get(url, params=None, site=None, headers=None):
            requests.append(dict(params, url=url, site=site))
            return type("Response", (), {"text": params["YEAR_MODEL_FROM"]})()

        def next_data(year):
            adverts = years.get(year, [])
            if isinstance(adverts, Exception):
                raise adverts
            return {"searchResult": {"advertSummaryList": {"advertSummary": adverts}, "rowsFound": len(adverts)}}

        monkeypatch.setattr(willhaben.net, "get", get)
        monkeypatch.setattr(willhaben.net, "next_data", next_data)
        return requests
    return serve


def advert(id_, heading="VW Golf 1.6 TDI", price="5000"):
    return {"id": id_, "attributes": {"attribute": [{"name": "HEADING", "values": [heading]},
                                                    {"name": "PRICE", "values": [price]}]}}


def passat_search(year_from=2010, year_to=2012):
    """A diesel-only model: the Passat has no petrol generation, so each year is one search."""
    return willhaben.search("volkswagen/passat", year_from, year_to, 1500, 15000)


def test_every_year_is_asked_once_for_its_90_cheapest_non_petrol_cars(site):
    requests = site({2010: [advert(1)], 2011: [advert(2), advert(3)], 2012: [advert(4)]})
    assert [car["id"] for car in passat_search()] == ["willhaben:1", "willhaben:2", "willhaben:3", "willhaben:4"]
    assert [(r["YEAR_MODEL_FROM"], r["YEAR_MODEL_TO"]) for r in requests] == [(2010, 2010), (2011, 2011), (2012, 2012)]
    for request in requests:
        assert request["url"] == willhaben.SEARCH_URL and request["site"] == "willhaben"
        assert request["ENGINE/FUEL"] == ["100003", "100004", "100011", "100013", "100022"]
        assert (request["rows"], request["page"], request["sort"]) == (90, 1, willhaben.SORT_PRICE_ASC)
        assert (request["CAR_MODEL/MAKE"], request["CAR_MODEL/MODEL"]) == ("1065", "1703")
        assert (request["PRICE_FROM"], request["PRICE_TO"]) == (1500, 15000)


def test_wanted_fuels_are_every_fuel_but_plain_petrol():
    assert "100001" not in willhaben.WANTED_FUELS
    assert {willhaben.FUEL[fuel_id] for fuel_id in willhaben.WANTED_FUELS} == {"diesel", "electric", "petrol_lpg", "hybrid"}
    assert len(willhaben.WANTED_FUELS) == len(willhaben.FUEL) - 1


def test_year_without_adverts_and_adverts_without_a_price(site):
    requests = site({2010: [], 2011: [advert(1, price="")]})
    assert passat_search() == []
    assert len(requests) == 3


def test_failed_year_does_not_lose_the_other_years(site):
    requests = site({2010: [advert(1)], 2011: RuntimeError("HTTP 500"), 2012: [advert(3)]})
    with pytest.raises(RuntimeError, match="HTTP 500") as failed:   # raised after the last year, for the run's note
        passat_search()
    assert [car["id"] for car in failed.value.cars] == ["willhaben:1", "willhaben:3"]
    assert len(requests) == 3


def test_error_is_raised_when_no_year_brought_a_car(site):
    site({2010: RuntimeError("HTTP 500"), 2011: RuntimeError("HTTP 500"), 2012: RuntimeError("HTTP 500")})
    with pytest.raises(RuntimeError):
        passat_search()


def test_block_ends_the_model_without_another_request(site):
    requests = site({2010: [advert(1)], 2011: net.Blocked("willhaben returned 403"), 2012: [advert(3)]})
    with pytest.raises(net.Blocked) as blocked:
        passat_search()
    assert [r["YEAR_MODEL_FROM"] for r in requests] == [2010, 2011]
    assert [car["id"] for car in blocked.value.cars] == ["willhaben:1"]   # handed to the scan with the block


# --- four-wheel drive -----------------------------------------------------------------

@pytest.mark.parametrize("heading,drive", [("VW Tiguan 2.0 TDI 4Motion DSG", "4x4"), ("Audi A4 Avant quattro", "4x4"),
                                           ("Skoda Octavia Scout", "4x4"), ("VW Passat Alltrack", "4x4"),
                                           ("VW Golf 1.6 TDI", None)])
def test_drive_is_read_from_the_heading_on_the_list_page(heading, drive):
    assert willhaben.parse_list_item(advert(1, heading), "volkswagen/golf")["drive"] == drive


@pytest.mark.parametrize("heading,wheel_drive,description,drive", [
    ("VW Tiguan 2.0 TDI", "Allrad", "Top Zustand", "4x4"),             # the site's own field
    ("VW Tiguan 2.0 TDI 4Motion", None, "Top Zustand", "4x4"),         # empty field: the heading still says it
    ("VW Tiguan 2.0 TDI", None, "<p>Allrad, Pickerl neu</p>", "4x4"),  # only the description says it
    ("VW Tiguan 2.0 TDI", "Vorderrad", "Top Zustand", None),
    ("VW Tiguan 2.0 TDI", None, "", None),
])
def test_detail_page_never_loses_the_four_wheel_drive_of_the_heading(monkeypatch, heading, wheel_drive, description, drive):
    car = willhaben.parse_list_item(advert(1, heading), "volkswagen/tiguan")
    attributes = [{"name": "DESCRIPTION", "values": [description]}]
    if wheel_drive:
        attributes.append({"name": "WHEEL_DRIVE", "values": [wheel_drive]})
    page = {"advertDetails": {"attributes": {"attribute": attributes}}}
    monkeypatch.setattr(willhaben.net, "get", lambda *a, **k: type("Response", (), {"text": ""})())
    monkeypatch.setattr(willhaben.net, "next_data", lambda text: page)
    assert willhaben.add_details(car)["drive"] == drive
    assert car["detailed"] is True


# --- photos for Haiku (24.11.2026) ---------------------------------------------------

def detail_with_images(monkeypatch, images):
    page = {"advertDetails": {"attributes": {"attribute": []}, "advertImageList": images}}
    monkeypatch.setattr(willhaben.net, "get", lambda *a, **k: type("Response", (), {"text": ""})())
    monkeypatch.setattr(willhaben.net, "next_data", lambda text: page)


def test_detail_page_keeps_up_to_16_photos(monkeypatch):
    car = willhaben.parse_list_item(ADVERTS[0], "volkswagen/golf")
    assert car["images"] == []
    photos = [{"id": i, "mainImageUrl": f"https://cache.willhaben.at/mmo/8/{i}_hoved.jpg"} for i in range(20)]
    photos[1]["mainImageUrl"] = None     # a broken entry is skipped
    detail_with_images(monkeypatch, {"advertImage": photos})
    willhaben.add_details(car)
    assert len(car["images"]) == 16
    assert car["images"][:2] == ["https://cache.willhaben.at/mmo/8/0_hoved.jpg", "https://cache.willhaben.at/mmo/8/2_hoved.jpg"]


@pytest.mark.parametrize("images", [None, {}, {"advertImage": []}])
def test_detail_page_without_photos_gives_an_empty_list(monkeypatch, images):
    car = willhaben.parse_list_item(ADVERTS[0], "volkswagen/golf")
    detail_with_images(monkeypatch, images)
    assert willhaben.add_details(car)["images"] == []


# --- 25.11.2026: the daily models ------------------------------------------------------------------------
# Frozen from each make's filter list on willhaben, 25.11.2026.

WILLHABEN_TABLE = [
    ("volkswagen/touran", "1065", "1709", "Volkswagen"),
    ("volkswagen/sharan", "1065", "1706", "Volkswagen"),
    ("volkswagen/caddy", "1065", "1686", "Volkswagen"),
    ("volkswagen/t-roc", "1065", "2108", "Volkswagen"),
    ("volkswagen/up", "1065", "1938", "Volkswagen"),
    ("volkswagen/cc", "1065", ["1958", "2007"], "Volkswagen"),
    ("volkswagen/jetta", "1065", "1698", "Volkswagen"),
    ("skoda/fabia", "1057", "1596", "Škoda"),
    ("skoda/rapid", "1057", "1601", "Škoda"),
    ("skoda/kodiaq", "1057", "2092", "Škoda"),
    ("skoda/yeti", "1057", "1889", "Škoda"),
    ("skoda/karoq", "1057", "2100", "Škoda"),
    ("skoda/scala", "1057", "2183", "Škoda"),
    ("skoda/kamiq", "1057", "2192", "Škoda"),
    ("seat/leon", "1056", "1590", "Seat"),
    ("seat/ibiza", "1056", "1588", "Seat"),
    ("seat/ateca", "1056", "2069", "Seat"),
    ("seat/alhambra", "1056", "1583", "Seat"),
    ("seat/arona", "1056", "2103", "Seat"),
    ("seat/altea", "1056", ["1779", "1808"], "Seat"),
    ("audi/a1", "1003", "1838", "Audi"),
    ("audi/a5", "1003", "1789", "Audi"),
    ("audi/q2", "1003", "2082", "Audi"),
    ("audi/q3", "1003", "1925", "Audi"),
    ("audi/q5", "1003", "1824", "Audi"),
    ("bmw/x3", "1005", "1055", "BMW"),
    ("bmw/2er", "1005", "2044", "BMW"),
    ("mercedes-benz/a-klasse", "1036", "1384", "Mercedes-Benz"),
    ("mercedes-benz/c-klasse", "1036", "1387", "Mercedes-Benz"),
    ("mercedes-benz/e-klasse", "1036", "1393", "Mercedes-Benz"),
    ("mercedes-benz/cla", "1036", "1973", "Mercedes-Benz"),
    ("mercedes-benz/gla", "1036", "2043", "Mercedes-Benz"),
    ("opel/zafira", "1043", ["1503", "2504"], "Opel"),
    ("opel/meriva", "1043", "1487", "Opel"),
    ("opel/mokka", "1043", "1965", "Opel"),
    ("opel/grandland", "1043", ["2104", "2356"], "Opel"),
    ("opel/crossland", "1043", ["2282", "2090"], "Opel"),
    ("opel/adam", "1043", "1969", "Opel"),
    ("peugeot/207", "1045", "1743", "Peugeot"),
    ("peugeot/208", "1045", "1948", "Peugeot"),
    ("peugeot/308", "1045", "1805", "Peugeot"),
    ("peugeot/2008", "1045", "1977", "Peugeot"),
    ("peugeot/508", "1045", "1919", "Peugeot"),
    ("peugeot/5008", "1045", "1882", "Peugeot"),
    ("renault/clio", "1051", "1542", "Renault"),
    ("renault/megane", "1051", "1548", "Renault"),
    ("renault/scenic", "1051", ["1558", "1940"], "Renault"),
    ("renault/captur", "1051", "1978", "Renault"),
    ("renault/kadjar", "1051", "2062", "Renault"),
    ("renault/talisman", "1051", "2070", "Renault"),
    ("renault/laguna", "1051", "1546", "Renault"),
    ("renault/koleos", "1051", "1834", "Renault"),
    ("renault/twingo", "1051", "1562", "Renault"),
    ("renault/kangoo", "1051", "1545", "Renault"),
    ("citroen/c3", "1010", "1102", "Citroën"),
    ("citroen/c4", "1010", "1103", "Citroën"),
    ("citroen/c4-cactus", "1010", "2057", "Citroën"),
    ("citroen/c5", "1010", "1104", "Citroën"),
    ("citroen/c3-picasso", "1010", "1846", "Citroën"),
    ("citroen/c3-aircross", "1010", "2117", "Citroën"),
    ("citroen/c5-aircross", "1010", "2170", "Citroën"),
    ("citroen/berlingo", "1010", "1096", "Citroën"),
    ("dacia/duster", "1011", "1849", "Dacia"),
    ("dacia/sandero", "1011", "1826", "Dacia"),
    ("fiat/tipo", "1016", "1189", "Fiat"),
    ("fiat/500x", "1016", "2056", "Fiat"),
    ("fiat/500l", "1016", "2041", "Fiat"),
    ("fiat/doblo", "1016", "1168", "Fiat"),
    ("fiat/punto", "1016", ["1180", "1173"], "Fiat"),
    ("fiat/500", "1016", "1795", "Fiat"),
    ("fiat/panda", "1016", "1179", "Fiat"),
    ("fiat/bravo", "1016", "1163", "Fiat"),
    ("ford/focus", "1017", "1197", "Ford"),
    ("ford/fiesta", "1017", "1195", "Ford"),
    ("ford/mondeo", "1017", "1203", "Ford"),
    ("ford/c-max", "1017", "1816", "Ford"),
    ("ford/s-max", "1017", "1740", "Ford"),
    ("ford/galaxy", "1017", "1200", "Ford"),
    ("ford/b-max", "1017", "1961", "Ford"),
    ("ford/ecosport", "1017", "2028", "Ford"),
    ("ford/puma", "1017", "1206", "Ford"),
    ("toyota/auris", "1062", "1785", "Toyota"),
    ("toyota/yaris", "1062", "1657", "Toyota"),
    ("toyota/rav4", "1062", "1654", "Toyota"),
    ("toyota/avensis", "1062", "1637", "Toyota"),
    ("toyota/verso", "1062", "1894", "Toyota"),
    ("toyota/corolla", "1062", "1643", "Toyota"),
    ("toyota/c-hr", "1062", "2081", "Toyota"),
    ("kia/sportage", "1025", "1289", "Kia"),
    ("kia/ceed", "1025", "1767", "Kia"),
    ("kia/rio", "1025", "1285", "Kia"),
    ("hyundai/i30", "1020", "1796", "Hyundai"),
    ("hyundai/tucson", "1020", "1256", "Hyundai"),
    ("hyundai/i20", "1020", "1857", "Hyundai"),
    ("nissan/qashqai", "1042", "1774", "Nissan"),
    ("nissan/juke", "1042", "1878", "Nissan"),
    ("nissan/x-trail", "1042", "1474", "Nissan"),
    ("nissan/micra", "1042", "1460", "Nissan"),
    ("mazda/mazda3", "1035", "1364", "Mazda"),
    ("mazda/mazda6", "1035", "1366", "Mazda"),
    ("mazda/cx-5", "1035", "1945", "Mazda"),
    ("mazda/cx-3", "1035", "2060", "Mazda"),
    ("mazda/mazda2", "1035", "1363", "Mazda"),
    ("volvo/v40", "1064", "1677", "Volvo"),
    ("volvo/v60", "1064", "1924", "Volvo"),
    ("volvo/s60", "1064", "1673", "Volvo"),
    ("volvo/xc60", "1064", "1835", "Volvo"),
    ("volvo/xc40", "1064", "2126", "Volvo"),
    ("honda/civic", "1018", "1222", "Honda"),
    ("honda/cr-v", "1018", "1225", "Honda"),
    ("honda/jazz", "1018", "1230", "Honda"),
    ("mitsubishi/asx", "1040", "1872", "Mitsubishi"),
    ("mitsubishi/outlander", "1040", "1435", "Mitsubishi"),
    ("suzuki/swift", "1061", "1632", "Suzuki"),
    ("suzuki/vitara", "1061", "1633", "Suzuki"),
    ("suzuki/sx4-s-cross", "1061", ["2275", "2237"], "Suzuki"),
    ("chevrolet/cruze", "1008", "1844", "Chevrolet"),
    ("alfa-romeo/giulietta", "1000", "1837", "Alfa Romeo"),
]


def test_willhaben_table_holds_every_daily_model():
    assert [row[0] for row in WILLHABEN_TABLE] == [model["as24"] for model in models.DAILY_MODELS]


@pytest.mark.parametrize("as24,make_id,model_id,make", WILLHABEN_TABLE, ids=[row[0] for row in WILLHABEN_TABLE])
def test_daily_models_are_searched_and_named_as_willhaben_lists_them(site, as24, make_id, model_id, make):
    requests = site({2018: [advert(1, heading="heading 2.0 Diesel")]})
    cars = willhaben.search(as24, 2018, 2018, 1500, 15000)
    for request in requests:
        assert (request["CAR_MODEL/MAKE"], request["CAR_MODEL/MODEL"]) == (make_id, model_id)
    if 2018 in models.petrol_years(as24):
        assert [request["ENGINE/FUEL"] for request in requests] == [willhaben.WANTED_FUELS, willhaben.PETROL]
    else:
        assert [request["ENGINE/FUEL"] for request in requests] == [willhaben.WANTED_FUELS]
    assert all(car["make"] == make for car in cars)
