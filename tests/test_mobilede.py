import json
import time
from pathlib import Path

import pytest

from carfinder import db, models, net, polovni, scan, valuation
from carfinder.sources import autoscout24, mobilede

ITEMS = json.loads((Path(__file__).parent / "fixtures" / "mobilede_golf.json").read_text(encoding="utf-8"))
GOLF = models.MODELS[0]


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeApify:
    """Stands in for curl_cffi requests: no network in tests."""

    def __init__(self, items=ITEMS, status_code=201, used_usd=0.0):
        self.items = items
        self.status_code = status_code
        self.used_usd = used_usd
        self.runs = []

    def get(self, url, headers, timeout):
        return FakeResponse(200, {"data": {"current": {"monthlyUsageUsd": self.used_usd}}})

    def post(self, url, params, json, headers, timeout):
        self.runs.append((params, json))
        return FakeResponse(self.status_code, self.items)


@pytest.fixture
def apify(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(mobilede, "_token", lambda: "test-token")
    fake = FakeApify()
    monkeypatch.setattr(mobilede, "requests", fake)
    return fake


def parsed():
    return [mobilede.parse_item(item) for item in ITEMS]


def passat_search():
    """A model without a petrol generation: one paid run a week."""
    return mobilede.search("volkswagen/passat", 2010, 2026, 1500, 15000)


# --- parsing the real actor output -------------------------------------------

def test_fields_from_real_actor_output():
    first = parsed()[0]
    assert first["id"] == "mobilede:56697498882944"
    assert first["source"] == "mobilede"
    assert first["url"].startswith("https://suchen.mobile.de/auto-inserat/")
    assert first["title"] == "Volkswagen Golf VII Variant BMT 1.6TDI *EURO6*LESEN!!!"
    assert (first["year"], first["month"], first["km"], first["kw"], first["cc"]) == (2016, 2, 312133, 81, 1598)
    assert (first["fuel"], first["gearbox"], first["body"], first["doors"]) == ("diesel", "manual", "estate", 5)
    assert (first["country"], first["zip"], first["city"]) == ("DE", "53545", "Linz am Rhein")
    assert first["price"] == 3490 and first["vat_deductible"] is False
    assert first["seller"] == "dealer" and first["damaged"] is False
    assert first["mass"] == 1395
    assert "ABS" in first["equipment"]
    assert first["text"].startswith("+++FAHRZEUG STARTET")
    assert first["image"].startswith("https://")
    assert first["detailed"] is True


def test_private_seller_keeps_zip_and_city_and_cabrio_body():
    cabrio = parsed()[1]
    assert cabrio["seller"] == "private"
    assert (cabrio["zip"], cabrio["city"]) == ("21720", "Steinkirchen")
    assert cabrio["body"] == "cabrio" and cabrio["doors"] is None
    assert cabrio["cc"] == 1598   # cubicCapacityCc is empty, the description says "1598 ccm"


def test_danish_dealer_keeps_its_country():
    danish = parsed()[4]
    assert (danish["country"], danish["zip"], danish["city"]) == ("DK", "8940", "Randers SV")


def test_same_keys_as_autoscout24():
    item = {"id": "x", "url": "/a", "price": {"priceRaw": 1}, "vehicle": {}, "tracking": {}}
    assert set(parsed()[0]) == set(autoscout24.parse_list_item(item))


def test_missing_fields_do_not_crash():
    car = mobilede.parse_item({"listingKey": "1", "canonicalUrl": "u", "price": 4000})
    assert car["year"] is None and car["cc"] is None and car["zip"] is None and car["city"] is None
    assert car["fuel"] == "other" and car["detailed"] is False and car["country"] == "DE"


def test_ad_without_description_is_not_marked_detailed():
    item = dict(ITEMS[0], description=None)
    assert mobilede.parse_item(item)["detailed"] is False


@pytest.mark.parametrize("actor_fuel,ours", [("DIESEL", "diesel"), ("LPG", "petrol_lpg"), ("CNG", "petrol_cng"),
                                             ("HYBRID", "hybrid"), ("HYBRID_DIESEL", "hybrid"),
                                             ("PLUG_IN_HYBRID", "hybrid"), ("PETROL", "petrol"), ("HYDROGEN", "other")])
def test_fuel_mapping(actor_fuel, ours):
    assert mobilede.parse_item(dict(ITEMS[0], fuelType=actor_fuel))["fuel"] == ours


def test_cng_car_is_valued_against_serbian_cng_cars():
    car = mobilede.parse_item(dict(ITEMS[0], fuelType="CNG"))
    params = polovni.search_params("volkswagen", ["golf"], 2015, 2017, car["fuel"], 1)
    assert params["fuel[]"] == "gasolineCng"


def test_coupe_and_van_bodies_are_kept_apart_from_hatchbacks():
    assert mobilede.parse_item(dict(ITEMS[0], bodyTypeRaw="SportsCar"))["body"] == "coupe"
    assert mobilede.parse_item(dict(ITEMS[0], bodyTypeRaw="Van"))["body"] == "van"
    assert mobilede.parse_item(dict(ITEMS[0], bodyTypeRaw="Limousine"))["body"] is None


def test_front_wheel_drive_golf_is_not_4x4():
    assert parsed()[0]["drive"] is None   # features say "Front wheel drive"


@pytest.mark.parametrize("subtitle,features", [("Tiguan 2.0 TDI 4MOTION Highline", []),
                                               ("A4 Avant 2.0 TDI quattro", []),
                                               ("Octavia Combi 4x4 2.0 TDI", []),
                                               ("Octavia Combi Scout 2.0 TDI", []),
                                               ("Passat Variant Alltrack 2.0 TDI", []),
                                               ("Tiguan 2.0 TDI", ["Four wheel drive", "ABS"]),
                                               ("Superb 2.0 TDI", ["All-wheel drive"])])
def test_four_by_four_from_title_or_equipment(subtitle, features):
    car = mobilede.parse_item(dict(ITEMS[0], subTitle=subtitle, features=features))
    assert car["drive"] == "4x4"


@pytest.mark.parametrize("description,drive", [
    ("Tiguan 2.0 Tdi 4 motion dsg automatik Sommerreifen", "4x4"),      # live run 24.11.2026: the title said nothing
    ("Scheckheftgepflegt, 4MOTION, AHK", "4x4"),
    ("Weitere Angebote auf AutoScout24", None),
    ("", None), (None, None),
])
def test_four_by_four_from_the_description_because_there_is_no_detail_page(description, drive):
    car = mobilede.parse_item(dict(ITEMS[0], subTitle="Tiguan 2.0 Diesel Automatica", features=[],
                                   description=description))
    assert car["drive"] == drive


def test_four_by_four_car_only_uses_four_by_four_serbian_ads():
    car = mobilede.parse_item(dict(ITEMS[0], subTitle="VII Variant 1.6 TDI 4MOTION"))
    serbian = {"gearbox": "manual", "fuel": "diesel", "body": "estate", "cc": 1598, "kw": 81, "doors": 5}
    assert not valuation.is_match(car, dict(serbian, drive=None))
    assert valuation.is_match(car, dict(serbian, drive="4x4"))
    front_wheel_drive = parsed()[0]
    assert valuation.is_match(front_wheel_drive, dict(serbian, drive=None))
    assert not valuation.is_match(front_wheel_drive, dict(serbian, drive="4x4"))


def test_automatic_gearbox():
    assert mobilede.parse_item(dict(ITEMS[0], transmission="AUTOMATIC"))["gearbox"] == "automatic"


# --- the 2.0 engine rule when private sellers leave cc empty -----------------

def test_exact_cc_field_wins_over_text():
    assert mobilede.engine_cc({"cubicCapacityCc": 1968}, "3.0 TDI") == 1968


@pytest.mark.parametrize("text,cc", [("Hubraum 1.968 cm³", 1968), ("1598 ccm, 105 PS", 1598),
                                     ("A4 3.0 TDI quattro", 3000), ("Passat 2,5 TDI", 2500),
                                     ("Golf 2.0 TDI Highline", None), ("7 1,6TDI Klima", None),
                                     ("A4 3.0 V6 TDI quattro", 3000), ("A6 3,0 BiTDI", 3000),
                                     ("Passat 3.0 l TDI", 3000), ("Golf 2.0 l TDI", None),
                                     ("golf 7 disel", None), ("", None)])
def test_engine_from_text_when_cc_is_missing(text, cc):
    assert mobilede.engine_cc({"cubicCapacityCc": None}, text) == cc


def test_three_litre_without_cc_is_not_scanned():
    item = dict(ITEMS[3], subTitle="A4 Avant 3.0 TDI quattro", description="Top Zustand")
    car = mobilede.parse_item(item)
    assert car["cc"] == 3000
    assert not scan.usable(car)


def test_private_one_point_six_without_cc_stays_usable():
    car = parsed()[3]   # "7 1,6TDI", cc empty
    assert car["cc"] is None
    assert scan.usable(car)


# --- model mapping and the actor input ----------------------------------------

def test_every_core_model_but_a_trial_one_has_a_mobilede_name():
    assert set(mobilede.MODELS) == {m["as24"] for m in models.CORE_MODELS if not m.get("trial")}
    assert len(mobilede.MODELS) == 19
    assert [m["as24"] for m in models.MODELS if m.get("trial")] == ["bmw/1er"]   # not paid for while on trial


def test_daily_models_cost_no_paid_run(apify):
    for model in models.DAILY_MODELS:
        assert model["as24"] not in mobilede.MODELS   # the 3 USD budget is full
    assert mobilede.search("toyota/yaris", 2010, 2024, 1500, 15000) == []
    assert apify.runs == []


def test_actor_input_filters_at_the_source():
    search_input = mobilede.actor_input("skoda/octavia", 2010, 2026, 1500, 15000)
    assert (search_input["make"], search_input["model"]) == ("Skoda", "Octavia")
    assert "PETROL" not in search_input["fuelType"] and "DIESEL" in search_input["fuelType"]
    assert (search_input["yearMin"], search_input["yearMax"]) == (2010, 2026)
    assert (search_input["priceMin"], search_input["priceMax"]) == (1500, 15000)
    assert search_input["sort"] == "price_asc"
    assert search_input["maxResults"] == mobilede.RESULTS_PER_RUN
    assert search_input["customFilters"] == [{"field": "cubicCapacityCc", "op": "lte", "value": 2000}]
    assert "damageStatus" not in search_input


@pytest.mark.parametrize("as24,make,model", [
    ("bmw/x1", "BMW", "X1"), ("bmw/520", "BMW", "520"), ("bmw/3er", "BMW", "316,318,320"), ("audi/a6", "Audi", "A6"),
    ("opel/insignia", "Opel", "Insignia"), ("mercedes-benz/b-klasse", "Mercedes-Benz", "B 180,B 200"),
    ("ford/kuga", "Ford", "Kuga"), ("hyundai/ix35", "Hyundai", "ix35"),
])
def test_added_models_are_asked_for_by_their_mobilede_names(as24, make, model):
    search_input = mobilede.actor_input(as24, 2012, 2018, 1500, 15000)
    assert (search_input["make"], search_input["model"]) == (make, model)
    assert search_input["customFilters"] == [{"field": "cubicCapacityCc", "op": "lte", "value": 2000}]


def test_bmw_and_mercedes_engine_names_are_the_pa_names_of_the_generation():
    for as24 in ("bmw/3er", "mercedes-benz/b-klasse"):
        generation = next(model for model in models.MODELS if model["as24"] == as24)["generations"][0]
        assert mobilede.MODELS[as24][1].split(",") == models.pa_names(generation["pa_model"])


def weekly_runs():
    """One paid run per model a week, and a second one for a model with a petrol generation."""
    petrol_runs = [as24 for as24 in mobilede.MODELS if models.petrol_years(as24)]
    return len(mobilede.MODELS) + len(petrol_runs)


def test_monthly_cost_stays_under_three_dollars():
    runs_per_month = weekly_runs() * 4.3
    assert mobilede.RUN_CAP_USD == pytest.approx(0.005 + mobilede.RESULTS_PER_RUN * 0.00059)
    assert runs_per_month * mobilede.RUN_CAP_USD < 3.0
    assert runs_per_month * mobilede.RUN_CAP_USD < mobilede.MONTHLY_BUDGET_USD


def test_nineteen_models_and_four_petrol_runs_at_42_results_cost_about_2_95_a_month():
    petrol_runs = sorted(as24 for as24 in mobilede.MODELS if models.petrol_years(as24))
    assert petrol_runs == ["opel/astra", "opel/corsa", "volkswagen/golf", "volkswagen/polo"]
    assert len(mobilede.MODELS) == 19 and weekly_runs() == 23 and mobilede.RESULTS_PER_RUN == 42
    assert weekly_runs() * 4.3 * mobilede.RUN_CAP_USD == pytest.approx(2.95, abs=0.01)
    # 45 results, as before the petrol runs, would go over the budget
    assert weekly_runs() * 4.3 * (0.005 + 45 * 0.00059) > mobilede.MONTHLY_BUDGET_USD


def test_petrol_run_is_a_second_weekly_run_for_the_petrol_years_only(apify):
    cars = mobilede.search("opel/astra", 2010, 2021, 1500, 15000)
    (_, diesel), (_, petrol) = apify.runs
    assert diesel["fuelType"] == mobilede.WANTED_FUELS and (diesel["yearMin"], diesel["yearMax"]) == (2010, 2021)
    assert petrol["fuelType"] == ["PETROL"] and (petrol["yearMin"], petrol["yearMax"]) == (2010, 2016)   # Astra J
    assert (petrol["make"], petrol["model"]) == ("Opel", "Astra")
    assert len(cars) == 20                                     # the fake answers both runs with the same 10 cars
    assert mobilede.search("opel/astra", 2010, 2021, 1500, 15000) == cars   # same week: both runs are stored
    assert len(apify.runs) == 2


def test_petrol_run_is_skipped_when_no_petrol_year_is_searched(apify):
    mobilede.search("opel/astra", 2017, 2021, 1500, 15000)   # only Astra K years, which sell as diesel
    assert [search_input["fuelType"] for _, search_input in apify.runs] == [mobilede.WANTED_FUELS]


def test_failed_petrol_run_keeps_the_cars_of_the_first_run(apify, monkeypatch):
    real_run_actor = mobilede.run_actor

    def run_actor(headers, search_input):
        if search_input["fuelType"] == ["PETROL"]:
            raise RuntimeError("HTTP 500")
        return real_run_actor(headers, search_input)
    monkeypatch.setattr(mobilede, "run_actor", run_actor)
    with pytest.raises(RuntimeError, match="HTTP 500") as failed:
        mobilede.search("volkswagen/golf", 2010, 2024, 1500, 15000)
    assert len(failed.value.cars) == 10
    # next scan: the diesel run is stored for the week and the failed petrol run waits a day
    assert len(mobilede.search("volkswagen/golf", 2010, 2024, 1500, 15000)) == 10
    assert len(apify.runs) == 1


def test_every_run_is_capped(apify):
    passat_search()
    params, search_input = apify.runs[0]
    assert params["maxItems"] == mobilede.RESULTS_PER_RUN
    assert params["maxTotalChargeUsd"] == mobilede.RUN_CAP_USD
    assert search_input["make"] == "Volkswagen" and search_input["model"] == "Passat"


def test_no_run_when_monthly_budget_is_reached(apify):
    apify.used_usd = 2.98
    with pytest.raises(net.Blocked):
        passat_search()
    assert apify.runs == []


def test_used_up_credit_blocks_the_source(apify):
    apify.status_code = 402
    with pytest.raises(net.Blocked):
        passat_search()


# --- weekly cadence ------------------------------------------------------------

def test_search_runs_once_a_week_per_model(apify):
    first = passat_search()
    assert len(first) == 10
    assert passat_search() == first                    # same week: the stored cars again, no paid run
    assert len(apify.runs) == 1
    mobilede.search("skoda/octavia", 2010, 2026, 1500, 15000)
    assert len(apify.runs) == 2                      # another model has its own week


def test_search_runs_again_after_seven_days(apify, monkeypatch):
    passat_search()
    week_later = time.time() + mobilede.WEEK_S + 1
    monkeypatch.setattr(mobilede.time, "time", lambda: week_later)
    passat_search()
    assert len(apify.runs) == 2


def test_failed_run_waits_a_day_before_paying_again(apify, monkeypatch):
    apify.status_code = 500
    with pytest.raises(RuntimeError):
        passat_search()
    apify.status_code = 201
    assert passat_search() == []                       # next scan, 3 hours later: no second paid run
    assert len(apify.runs) == 1
    day_later = time.time() + mobilede.RETRY_S + 1
    monkeypatch.setattr(mobilede.time, "time", lambda: day_later)
    assert len(passat_search()) == 10
    assert len(apify.runs) == 2


def test_run_without_an_answer_counts_as_an_attempt(apify):
    def dropped(*args, **kwargs):
        apify.runs.append(None)
        raise TimeoutError("connection dropped after Apify started the run")
    apify.post = dropped
    with pytest.raises(TimeoutError):
        passat_search()
    assert passat_search() == []
    assert len(apify.runs) == 1


def test_budget_check_alone_is_not_an_attempt(apify):
    apify.used_usd = 2.98
    with pytest.raises(net.Blocked):
        passat_search()
    apify.used_usd = 0.0
    assert len(passat_search()) == 10                  # new month: runs at once, no day of waiting


def test_week_old_cars_are_not_returned_after_a_failed_refresh(apify, monkeypatch):
    passat_search()
    apify.status_code = 500
    week_later = time.time() + mobilede.WEEK_S + 1
    monkeypatch.setattr(mobilede.time, "time", lambda: week_later)
    with pytest.raises(RuntimeError):
        passat_search()
    assert passat_search() == []
    assert len(apify.runs) == 2


def test_malformed_item_is_skipped(apify):
    apify.items = [ITEMS[0], {"listingKey": "no price"}, None, ITEMS[1]]
    assert [c["id"] for c in passat_search()] == ["mobilede:56697498882944", "mobilede:57799724747072"]


def test_unknown_model_returns_nothing_without_request(apify):
    assert mobilede.search("bmw/x5", 2015, 2020, 1500, 9000) == []
    assert apify.runs == []


def test_real_golf_card_shows_its_equipment():
    golf = parsed()[7]   # "VII Kombi 2.0 TDI Allstar", equipment in English
    assert "MF volan" in valuation.equipment_of(golf)


def test_add_details_changes_nothing():
    car = parsed()[0]
    assert mobilede.add_details(dict(car)) == car


# --- failure isolation in the scan ---------------------------------------------

def other_sources_work(monkeypatch):
    monkeypatch.setattr(scan.autoscout24, "search", lambda *a: [{"id": "as24:1"}])
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [{"id": "willhaben:1"}])


def test_apify_failure_does_not_stop_the_scan(apify, monkeypatch):
    other_sources_work(monkeypatch)
    apify.status_code = 500
    errors, blocked = [], set()
    with scan.site_threads() as threads:
        found = scan.search_all(threads, [GOLF], errors, blocked)
    assert [car["id"] for car, model in found] == ["as24:1", "willhaben:1"]
    assert len(errors) == 1 and errors[0].startswith("mobilede volkswagen/golf")
    assert blocked == set()


def test_used_up_credit_skips_mobilede_for_the_rest_of_the_run(apify, monkeypatch):
    other_sources_work(monkeypatch)
    apify.status_code = 402
    errors, blocked = [], set()
    with scan.site_threads() as threads:
        assert len(scan.search_all(threads, [GOLF], errors, blocked)) == 2
        assert blocked == {"mobilede"}
        scan.search_all(threads, [models.MODELS[1]], errors, blocked)
    assert len(apify.runs) == 1


def test_cars_lost_to_a_polovni_block_are_valued_next_scan_without_paying(apify, monkeypatch):
    monkeypatch.setattr(scan.autoscout24, "search", lambda *a: [])
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [])
    conn = db.connect()

    def polovni_blocked(*snapshot):
        raise net.Blocked("polovniautomobili 429")
    monkeypatch.setattr(polovni, "fetch_snapshot", polovni_blocked)
    errors = []
    scan.run(conn, [GOLF], {}, errors, set())
    assert errors == ["polovni: polovniautomobili 429"]
    # the cars that need a Serbian price are not saved, so the block does not hide them
    need_price = {car["id"] for car in parsed() if scan.snapshot_for(car, GOLF)}
    saved = {row["id"] for row in conn.execute("SELECT id FROM cars")}
    assert len(need_price) == 3 and not saved & need_price   # the fixture's 335,000 km car is over the km limit

    monkeypatch.setattr(polovni, "fetch_snapshot", lambda *snapshot: [])
    scan.run(conn, [GOLF], {}, [], set())
    assert conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 10
    assert len(apify.runs) == 2   # the Golf's diesel and petrol runs, each paid once


def test_mobilede_is_a_scan_source():
    assert scan.SOURCES["mobilede"] is mobilede


# --- photos for Haiku (24.11.2026) ---------------------------------------------------

def test_photos_come_with_the_search_at_most_16():
    first = parsed()[0]
    assert len(first["images"]) == 16            # the actor gave 18
    assert first["images"][0] == first["image"]
    assert mobilede.parse_item({"listingKey": "1", "canonicalUrl": "u", "price": 4000})["images"] == []


# --- 24.11. mobile.de photos through the CDN: the actor's proxy answers 403 ----------

PROXY = "https://m.mobile.de/yams-proxy/img.classistatic.de/api/v1/mo-prod/images/e2/e286c875-484c-42b2-9f28-f615c9dbd324"
CDN = "https://img.classistatic.de/api/v1/mo-prod/images/e2/e286c875-484c-42b2-9f28-f615c9dbd324?rule=mo-640.jpg"


def test_proxy_photo_becomes_the_cdn_photo():
    assert mobilede.photo_url(PROXY) == CDN


@pytest.mark.parametrize("url", [CDN, "https://img.classistatic.de/x.jpg", "", None])
def test_direct_or_empty_photo_stays_as_it_is(url):
    assert mobilede.photo_url(url) == url


def test_every_photo_of_the_real_actor_output_goes_through_the_cdn():
    for car in parsed():
        for url in car["images"]:
            assert url.startswith("https://img.classistatic.de/api/v1/mo-prod/images/") and url.endswith("?rule=mo-640.jpg")
        assert car["image"] == (car["images"] or [None])[0]


def test_trial_model_costs_no_paid_run(apify):
    assert mobilede.search("bmw/1er", 2012, 2018, 1500, 15000) == []
    assert apify.runs == []
