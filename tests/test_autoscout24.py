"""AutoScout24: one search per registration year, non-petrol fuels, 4x4 from the seller's words. No network."""
import logging

import pytest

from carfinder import net
from carfinder.sources import autoscout24


def item(id_, version="1.6 TDI", subtitle=None):
    return {"id": id_, "url": "/" + id_, "price": {"priceRaw": 5000}, "tracking": {},
            "vehicle": {"make": "Volkswagen", "model": "Golf", "modelVersionInput": version, "subtitle": subtitle}}


@pytest.fixture
def site(monkeypatch):
    """Stands in for the site: site(pages) serves pages[(year, page)] and returns the requests that were made."""
    def serve(pages, page_count=1):
        requests = []

        def get(url, params=None, site=None, headers=None):
            requests.append(dict(params, url=url, site=site))
            return type("Response", (), {"text": (params["fregfrom"], params["page"])})()

        def next_data(key):
            page = pages.get(key, [])
            if isinstance(page, Exception):
                raise page
            return {"listings": page, "numberOfPages": page_count}

        monkeypatch.setattr(autoscout24.net, "get", get)
        monkeypatch.setattr(autoscout24.net, "next_data", next_data)
        return requests
    return serve


def ids(cars):
    return [car["id"] for car in cars]


def passat_search(year_from=2010, year_to=2012):
    """A diesel-only model: the Passat has no petrol generation, so each year is one search."""
    return autoscout24.search("volkswagen/passat", year_from, year_to, 1500, 15000)


# --- one search per year -------------------------------------------------------------

def test_every_year_is_asked_for_its_cheapest_non_petrol_cars(site):
    requests = site({(2010, 1): [item("a")], (2011, 1): [item("b")], (2012, 1): [item("c")]})
    assert ids(passat_search()) == ["as24:a", "as24:b", "as24:c"]
    assert [(r["fregfrom"], r["fregto"], r["page"]) for r in requests] == [(2010, 2010, 1), (2011, 2011, 1), (2012, 2012, 1)]
    for request in requests:
        assert request["url"] == "https://www.autoscout24.de/lst/volkswagen/passat" and request["site"] == "autoscout24"
        assert request["fuel"] == "D,L,C,2,3,E"
        assert (request["sort"], request["desc"]) == ("price", 0)
        assert (request["pricefrom"], request["priceto"], request["cy"]) == (1500, 15000, "D,A")


def test_a6_pages_are_capped_at_two_litres_on_the_site(site):
    requests = site({(2014, 1): [item("a")], (2014, 2): [item("b")]}, page_count=2)
    assert ids(autoscout24.search("audi/a6", 2014, 2014, 1500, 15000)) == ["as24:a", "as24:b"]
    assert [(r["url"], r["page"], r["ccmto"]) for r in requests] == [
        ("https://www.autoscout24.de/lst/audi/a6", 1, 2000), ("https://www.autoscout24.de/lst/audi/a6", 2, 2000)]


def test_other_models_keep_ads_without_an_engine_size(site):
    requests = site({(2014, 1): [item("a")]})
    passat_search(2014, 2014)
    autoscout24.search("bmw/3er", 2014, 2014, 1500, 15000)
    assert len(requests) == 2 and all("ccmto" not in request for request in requests)


@pytest.mark.parametrize("country,currency,accepted", [
    ("CH", "EUR", True), ("CH", "CHF", False), ("CH", None, False),
    ("AT", None, True), ("DE", "EUR", True), ("DE", "CHF", False),
])
def test_list_prices_must_be_in_eur(country, currency, accepted):
    item = {"price": {"currency": currency}, "location": {"countryCode": country}}
    assert autoscout24.has_euro_price(item) is accepted


def test_search_keeps_a_swiss_euro_quote_and_skips_a_franc_quote(site):
    euro = dict(item("eur"), price={"priceRaw": 5000, "currency": "EUR"}, location={"countryCode": "CH"})
    franc = dict(item("chf"), price={"priceRaw": 5000, "currency": "CHF"}, location={"countryCode": "CH"})
    site({(2010, 1): [euro, franc]})
    cars = passat_search(2010, 2010)
    assert ids(cars) == ["as24:eur"]
    assert (cars[0]["country"], cars[0]["price"]) == ("CH", 5000)


def test_wanted_fuels_are_every_fuel_but_plain_petrol():
    codes = autoscout24.WANTED_FUELS.split(",")
    assert "B" not in codes
    assert {autoscout24.FUEL[code] for code in codes} == {"diesel", "petrol_lpg", "petrol_cng", "hybrid", "electric"}


def test_petrol_year_gets_its_own_two_pages_after_the_other_fuels(site):
    requests = site({}, page_count=7)
    autoscout24.search("volkswagen/golf", 2015, 2015, 1500, 15000)
    assert [(r["fuel"], r["page"]) for r in requests] == [("D,L,C,2,3,E", 1), ("D,L,C,2,3,E", 2), ("B", 1), ("B", 2)]
    assert {(r["fregfrom"], r["url"]) for r in requests} == {(2015, "https://www.autoscout24.de/lst/volkswagen/golf")}


def test_petrol_is_asked_for_only_in_the_years_of_a_petrol_generation(site):
    requests = site({})
    autoscout24.search("opel/astra", 2016, 2017, 1500, 15000)   # Astra J (petrol) ends in 2016, the K is diesel only
    assert [(r["fregfrom"], r["fuel"]) for r in requests] == [(2016, "D,L,C,2,3,E"), (2016, "B"), (2017, "D,L,C,2,3,E")]


def test_model_without_a_petrol_generation_is_never_asked_for_petrol(site):
    requests = site({})
    autoscout24.search("audi/a4", 2010, 2024, 1500, 15000)   # Bane 24.11.2026: Audi petrol does not sell at all
    assert len(requests) == 15 and all(r["fuel"] == autoscout24.WANTED_FUELS for r in requests)


def test_petrol_pages_keep_their_cars_and_the_a6_cap_stays_on_the_other_fuels(site, monkeypatch):
    monkeypatch.setattr(autoscout24.models, "petrol_years", lambda path: {2014})
    requests = site({(2014, 1): [item("a")]})
    assert ids(autoscout24.search("audi/a6", 2014, 2014, 1500, 15000)) == ["as24:a", "as24:a"]   # the fake serves both
    assert [(r["fuel"], r["ccmto"]) for r in requests] == [("D,L,C,2,3,E", 2000), ("B", 2000)]


def test_two_pages_per_year_at_most(site):
    requests = site({(2010, 1): [item("a")], (2010, 2): [item("b")], (2010, 3): [item("never")]}, page_count=7)
    assert ids(passat_search(2010, 2010)) == ["as24:a", "as24:b"]
    assert [r["page"] for r in requests] == [1, 2]
    assert autoscout24.PAGES_PER_YEAR == 2


def test_year_with_one_page_gets_one_request(site):
    requests = site({(2010, 1): [item("a")]}, page_count=1)
    passat_search(2010, 2010)
    assert len(requests) == 1


def test_years_without_cars_give_an_empty_list(site):
    requests = site({}, page_count=0)
    assert passat_search() == []
    assert len(requests) == 3


def test_one_year_range_is_one_search(site):
    requests = site({(2015, 1): [item("a")]})
    assert ids(passat_search(2015, 2015)) == ["as24:a"]
    assert len(requests) == 1


# --- a failed year ---------------------------------------------------------------------

def test_failed_year_does_not_lose_the_other_years(site, caplog):
    caplog.set_level(logging.WARNING, logger="carfinder")
    requests = site({(2010, 1): [item("a")], (2011, 1): RuntimeError("HTTP 500"), (2012, 1): [item("c")]})
    with pytest.raises(RuntimeError, match="HTTP 500") as failed:   # raised after the last year, for the run's note
        passat_search()
    assert ids(failed.value.cars) == ["as24:a", "as24:c"]
    assert len(requests) == 3
    assert "autoscout24 volkswagen/passat 2011" in caplog.text


def test_error_is_raised_when_no_year_brought_a_car(site):
    site({(2010, 1): RuntimeError("HTTP 500"), (2011, 1): RuntimeError("HTTP 500"), (2012, 1): RuntimeError("HTTP 502")})
    with pytest.raises(RuntimeError, match="HTTP 502") as failed:
        passat_search()
    assert failed.value.cars == []


def test_block_ends_the_model_without_another_request(site):
    requests = site({(2010, 1): [item("a")], (2011, 1): net.Blocked("autoscout24 returned 429"), (2012, 1): [item("c")]})
    with pytest.raises(net.Blocked) as blocked:
        passat_search()
    assert [r["fregfrom"] for r in requests] == [2010, 2011]
    assert ids(blocked.value.cars) == ["as24:a"]      # the year read before the block is handed to the scan


def test_block_in_the_first_year_hands_over_no_cars(site):
    site({(2010, 1): net.Blocked("autoscout24 returned 429")})
    with pytest.raises(net.Blocked) as blocked:
        passat_search()
    assert blocked.value.cars == []


# --- four-wheel drive ------------------------------------------------------------------

@pytest.mark.parametrize("version,subtitle,drive", [
    ("2.0 TDI DPF 4Motion DSG AHK Sport", None, "4x4"),
    ("2.0 TDI quattro S tronic", None, "4x4"),
    ("Scout 2.0 TDI", None, "4x4"),
    ("2.0 TDI", "Alltrack ALLRAD Navi", "4x4"),
    ("2.0 TDI 4x4", None, "4x4"),
    ("1.6 TDI Comfortline", "Navi Klima", None),
    (None, None, None),
])
def test_drive_is_read_from_the_title_on_the_list_page(version, subtitle, drive):
    assert autoscout24.parse_list_item(item("a", version, subtitle))["drive"] == drive


@pytest.mark.parametrize("version,body", [
    ("520d Touring", "estate"), ("Insignia Country Tourer 2.0 CDTI", "estate"),
    ("B 180 CDI Avantgarde", None),
    # 25.11.2026: the estate names of the daily models' makes
    ("308 SW 1.6 BlueHDi", "estate"), ("C5 Break 2.0 HDi", "estate"), ("Megane Grandtour dCi 110", "estate"),
    ("Clio Grand Tour 1.5 dCi", "estate"), ("Focus Turnier 1.5 TDCi", "estate"), ("C 220 T-Modell", "estate"),
    ("Mondeo Estate 2.0 TDCi", "estate"), ("Ceed Sportswagon 1.6 CRDi", "estate"), ("cee'd SW 1.6", "estate"),
    ("Auris Touring Sports Hybrid", "estate"), ("i30 CW 1.6 CRDi", "estate"), ("Civic Tourer 1.6 i-DTEC", "estate"),
    ("Leon ST 1.6 TDI", "estate"), ("Mazda6 Sport Kombi 2.2", "estate"),
    ("Focus 1.5 EcoBlue ST-Line", None), ("Leon 1.5 TSI FR", None), ("Swift 1.2 Dualjet", None),
    ("Leon ST-Line 1.6", None), ("Corolla 1.8 Hybrid", None),
])
def test_list_body_uses_estate_badges_in_the_sellers_version(version, body):
    listing = item("a", version)
    listing["vehicle"]["variant"] = None
    assert autoscout24.parse_list_item(listing)["body"] == body


def details_page(monkeypatch, drive_train, description):
    vehicle = {"numberOfDoors": 5, "bodyType": "SUV/Geländewagen/Pickup", "driveTrain": drive_train, "weight": None,
               "rawDisplacementInCCM": 1968, "rawPowerInKw": 130, "equipment": {}}
    page = {"listingDetails": {"vehicle": vehicle, "prices": {"public": {}}, "description": description}}
    monkeypatch.setattr(autoscout24.net, "get", lambda *a, **k: type("Response", (), {"text": ""})())
    monkeypatch.setattr(autoscout24.net, "next_data", lambda text: page)


@pytest.mark.parametrize("version,drive_train,description,drive", [
    ("2.0 TDI", "Allrad", "Top Zustand", "4x4"),                       # the site's own field
    ("2.0 TDI 4Motion", None, "Top Zustand", "4x4"),                   # empty field: the title still says it
    ("2.0 TDI", None, "<b>4×4</b> automatik zahnriemen gemacht", "4x4"),   # only the description says it
    ("2.0 TDI", "Front", "Top Zustand", None),
    ("2.0 TDI", None, "", None),
])
def test_detail_page_never_loses_the_four_wheel_drive_of_the_title(monkeypatch, version, drive_train, description, drive):
    car = autoscout24.parse_list_item(item("a", version))
    details_page(monkeypatch, drive_train, description)
    assert autoscout24.add_details(car)["drive"] == drive
    assert car["detailed"] is True and car["body"] == "suv"


# --- photos for Haiku (24.11.2026) ---------------------------------------------------

def test_detail_page_keeps_up_to_16_photos_at_800x600(monkeypatch):
    car = autoscout24.parse_list_item(item("a", "2.0 TDI"))
    assert car["images"] == []
    details_page(monkeypatch, None, "")
    photos = [f"https://prod.pictures.autoscout24.net/listing-images/{i}.jpg/1280x960.webp" for i in range(20)]
    autoscout24.net.next_data("")["listingDetails"]["images"] = photos
    autoscout24.add_details(car)
    assert len(car["images"]) == 16
    assert car["images"][0] == "https://prod.pictures.autoscout24.net/listing-images/0.jpg/800x600.webp"


def test_detail_page_without_photos_gives_an_empty_list(monkeypatch):
    car = autoscout24.parse_list_item(item("a", "2.0 TDI"))
    details_page(monkeypatch, None, "")
    assert autoscout24.add_details(car)["images"] == []
