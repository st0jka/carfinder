import pytest

from carfinder import db, models, scan, valuation

GOLF = models.MODELS[0]


def pa_car(id_, price, **overrides):
    car = {"id": id_, "url": "u", "title": "Golf 7 1.6 TDI", "model": "Golf 7", "year": 2015, "price": price,
           "km": 200000, "cc": 1598, "kw": 81, "fuel": "diesel", "gearbox": "manual", "body": "hatchback",
           "doors": 5, "drive": None, "tags": ["Domaće tablice"], "dealer": False, "city": "BG",
           "updated": "", "image": None}
    car.update(overrides)
    return car


def foreign(**overrides):
    car = {"id": "as24:1", "source": "autoscout24", "url": "u", "title": "VW Golf", "make": "Volkswagen",
           "model": "Golf", "year": 2015, "month": 3, "km": 150000, "kw": 81, "cc": 1598, "fuel": "diesel",
           "gearbox": "manual", "body": None, "doors": None, "drive": None, "price": 4000, "net_price": None,
           "vat_deductible": False, "seller": "dealer", "country": "AT", "zip": "1100", "city": "Wien",
           "damaged": False, "text": "", "equipment": [], "mass": 1350, "market_median": None, "image": None,
           "detailed": True}
    car.update(overrides)
    return car


def seed_cache(car, pa_cars):
    """The PA snapshot of this car's generation and fuel, as the scan holds it in memory."""
    generation = models.generations_for(GOLF, car["year"])[0]
    return {scan.snapshot_of(GOLF, generation, car["fuel"]): pa_cars}


def value_car(conn, snapshots, car, blocked_sites):
    """Phases b to e of the scan for one car: its saved result."""
    with scan.site_threads() as threads:
        return scan.value_and_save(conn, threads, [(car, GOLF)], snapshots, {}, blocked_sites, [])[car["id"]]


def test_comparables_drop_other_model_year_and_engine(tmp_path):
    car = foreign()
    snapshots = seed_cache(car, [pa_car("1", 9000), pa_car("2", 9100, model="Golf 6"), pa_car("3", 9200, year=2013),
                                 pa_car("4", 9300, kw=77), pa_car("5", 9400, title="Golf 7 ostecen")])
    assert [c["id"] for c in scan.comparables_for(snapshots, car, GOLF)] == ["1"]


MODEL = {model["as24"]: model for model in models.MODELS}


def comparables(model, car, pa_cars):
    """Comparables of a car, from the diesel snapshot of the first generation of its year."""
    snapshot = scan.snapshot_of(model, models.generations_for(model, car["year"])[0], "diesel")
    return [c["id"] for c in scan.comparables_for({snapshot: pa_cars}, car, model)]


def test_generation_listed_under_several_pa_names_takes_ads_of_each_name_only():
    bmw = MODEL["bmw/3er"]
    car = foreign(title="BMW 318d", make="BMW", model="318", year=2015, cc=1995, kw=105)
    ad = {"title": "BMW 318d", "year": 2015, "cc": 1995, "kw": 105, "body": "sedan"}
    pa_cars = [pa_car("318", 9000, model="318", **ad), pa_car("320", 9100, model="320", **ad),
               pa_car("316", 9200, model="316", **ad), pa_car("118", 9300, model="118", **ad),
               pa_car("x1", 9400, model="X1", **ad)]
    assert comparables(bmw, car, pa_cars) == ["318", "320", "316"]


def test_mpv_without_a_body_on_its_list_page_is_compared_with_pa_vans():
    b_klasse = MODEL["mercedes-benz/b-klasse"]
    ad = {"title": "Mercedes-Benz B 180 CDI", "model": "B 180", "year": 2015, "cc": 1461, "kw": 80}
    pa_cars = [pa_car("van", 7000, body="van", **ad), pa_car("hatch", 7100, body="hatchback", **ad)]
    car = foreign(title="Mercedes-Benz B 180 CDI Style", make="Mercedes-Benz", model="B 180", cc=1461, kw=80)
    assert comparables(b_klasse, car, pa_cars) == ["van"]
    assert car["body"] is None   # the car itself keeps what its page said
    assert comparables(b_klasse, dict(car, body="hatchback"), pa_cars) == ["hatch"]   # its detail page decides


def test_model_without_a_body_of_its_own_keeps_an_unknown_body():
    van = pa_car("van", 9000, body="van")
    assert scan.comparables_for(seed_cache(foreign(), [van]), foreign(), GOLF) == []


def test_insignia_b_can_use_explicitly_named_2017_ads_in_2018():
    insignia = MODEL["opel/insignia"]
    car = foreign(title="Opel Insignia 2.0 CDTI", make="Opel", model="Insignia", year=2018, cc=1956, kw=125)
    snapshot = scan.snapshot_of(insignia, insignia["generations"][1], car["fuel"])
    ads = {"model": "Insignia", "year": 2017, "cc": 1956, "kw": 125}
    pa_cars = [pa_car("b", 8000, title="Opel Insignia B", **ads),
               pa_car("a", 7000, title="Opel Insignia A", **ads),
               pa_car("unknown", 7100, title="Opel Insignia 2.0 CDTI", **ads)]
    assert [c["id"] for c in scan.comparables_for({snapshot: pa_cars}, car, insignia)] == ["b"]


def test_xdrive_car_is_compared_with_four_by_four_pa_ads_only():
    x1 = MODEL["bmw/x1"]
    ad = {"model": "X1", "year": 2012, "cc": 1995, "kw": 105, "body": "suv"}
    pa_cars = [pa_car("x", 9000, title="BMW X1 xDrive 18d", drive=models.drive_of("BMW X1 xDrive 18d"), **ad),
               pa_car("s", 8000, title="BMW X1 sDrive 18d", drive=models.drive_of("BMW X1 sDrive 18d"), **ad)]
    car = foreign(title="BMW X1 xDrive18d", make="BMW", model="X1", year=2012, cc=1995, kw=105,
                  drive=models.drive_of("BMW X1 xDrive18d"))
    assert comparables(x1, car, pa_cars) == ["x"]
    assert comparables(x1, dict(car, title="BMW X1 sDrive18d", drive=None), pa_cars) == ["s"]


def test_changeover_year_with_split_pa_models_is_not_priced(tmp_path):
    assert scan.comparables_for({}, foreign(year=2012), GOLF) == []


def test_ad_that_becomes_wreck_is_hidden(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    car = foreign()
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    result = value_car(conn, snapshots, car, {"autoscout24"})
    assert result is not None
    assert len(db.cars(conn, 0)) == 1
    wreck = foreign(text="Motorschaden")
    assert value_car(conn, snapshots, wreck, {"autoscout24"}) is None
    assert db.cars(conn, 0) == []


def test_settings_from_overrides():
    overrides = {"x": {"transport": 900, "repair": 0, "origin_proof": 0}}
    settings = scan.settings_for({"id": "x"}, overrides)
    assert settings == {"transport_override": 900, "repair": 0, "origin_proof": False}
    assert scan.settings_for({"id": "y"}, overrides) == {}


def test_lock_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "LOCK", tmp_path / "scan.lock")
    first = scan.acquire_lock()
    assert first is not None
    assert scan.acquire_lock() is None
    first.close()
    second = scan.acquire_lock()
    assert second is not None
    second.close()


def test_tiguan_changeover_year_is_not_priced(tmp_path):
    tiguan = models.MODELS[3]
    assert scan.comparables_for({}, foreign(model="Tiguan", year=2016), tiguan) == []


def test_zero_transport_override_reaches_settings():
    assert scan.settings_for({"id": "x"}, {"x": {"transport": 0}}) == {"transport_override": 0}


def test_malformed_rows_are_skipped_not_fatal(monkeypatch):
    from carfinder import polovni
    from carfinder.sources import autoscout24

    good = {"id": "a", "url": "/a", "price": {"priceRaw": 5000}, "vehicle": {}, "tracking": {}}
    page = {"listings": [good, {"id": "b"}, good | {"id": "c"}], "numberOfPages": 1}
    monkeypatch.setattr(autoscout24.net, "get", lambda *a, **k: type("R", (), {"text": ""})())
    monkeypatch.setattr(autoscout24.net, "next_data", lambda text: page)
    assert [c["id"] for c in autoscout24.search("volkswagen/passat", 2015, 2015, 1500, 9000)] == ["as24:a", "as24:c"]

    pa_page = {"searchResults": {"results": [{"id": "1", "title": None, "price": 5000},
                                              {"id": "2", "featuredInfo": {"drive": None}, "price": 5100}, None]},
               "pagination": {"pageCount": 1}}
    monkeypatch.setattr(polovni.net, "next_data", lambda text: pa_page)
    cars = polovni.fetch_snapshot("Volkswagen", "Golf 7", 2015, 2015, "diesel")
    assert [c["id"] for c in cars] == ["1", "2"]
    assert polovni.is_clean(cars[0])


# --- 24.11. review of the live top list -------------------------------------

def test_plain_petrol_is_not_scanned_but_lpg_and_diesel_are():
    assert not scan.usable(foreign(fuel="petrol"))
    assert scan.usable(foreign(fuel="diesel"))
    assert scan.usable(foreign(fuel="petrol_lpg"))


# --- 25.11.2026: plain petrol where its generation sells as petrol --------------------------------

PASSAT_B8 = {"title": "VW Passat 1.4 TSI", "model": "Passat", "year": 2017, "cc": 1395, "kw": 110}


@pytest.mark.parametrize("car,model,sells", [
    (foreign(fuel="petrol"), GOLF, True),                              # Golf 7: 30% of PA ads are petrol
    (foreign(fuel="petrol", year=2021), GOLF, True),                   # Golf 8
    (foreign(fuel="petrol", **PASSAT_B8), MODEL["volkswagen/passat"], False),
    (foreign(fuel="petrol", year=2014, title="Opel Astra 1.4", make="Opel"), MODEL["opel/astra"], True),    # Astra J
    (foreign(fuel="petrol", year=2018, title="Opel Astra 1.4", make="Opel"), MODEL["opel/astra"], False),   # Astra K
    (foreign(fuel="petrol", year=2016, title="Opel Astra 1.4", make="Opel"), MODEL["opel/astra"], False),   # J or K?
    (foreign(fuel="petrol", year=2012), GOLF, False),                  # Golf 6 or 7: no generation, no price
    (foreign(fuel="petrol", year=2030), GOLF, False),
    (foreign(fuel="petrol"), None, False),                             # a model no longer scanned
    (foreign(fuel="diesel", **PASSAT_B8), MODEL["volkswagen/passat"], True),
    (foreign(fuel="hybrid"), None, True),
])
def test_plain_petrol_sells_only_in_a_petrol_generation(car, model, sells):
    assert valuation.fuel_sells(car, model) is sells
    assert scan.usable(car, model) is (sells and car["year"] != 2030)


def test_petrol_car_still_obeys_the_other_rules():
    assert scan.usable(foreign(fuel="petrol"), GOLF)
    assert not scan.usable(foreign(fuel="petrol", cc=2984), GOLF)
    assert not scan.usable(foreign(fuel="petrol", km=400_000), GOLF)
    assert not scan.usable(foreign(fuel="petrol", price=900), GOLF)
    assert not scan.usable(foreign(fuel="petrol", text="Motorschaden"), GOLF)


@pytest.mark.parametrize("generation,body,ad_bodies", [(0, "van", ["van"]), (1, "suv", ["hatch", "suv"])])
def test_list_page_car_takes_the_body_of_its_generation(generation, body, ad_bodies):
    peugeot = MODEL["peugeot/5008"]
    year = (2012, 2020)[generation]
    car = foreign(title="Peugeot 5008 1.6 BlueHDi", make="Peugeot", model="5008", year=year, cc=1560, kw=88)
    ad = {"title": "Peugeot 5008", "model": "5008", "year": year, "cc": 1560, "kw": 88}
    pa_cars = [pa_car("van", 7000, body="van", **ad), pa_car("hatch", 7100, body="hatchback", **ad),
               pa_car("suv", 7200, body="suv", **ad)]
    assert peugeot["generations"][generation]["body"] == body
    assert comparables(peugeot, car, pa_cars) == ad_bodies   # an SUV sells like a hatch: one body group
    assert car["body"] is None
    assert comparables(peugeot, dict(car, body="van"), pa_cars) == ["van"]   # the detail page decides


def test_autoscout24_cng_is_not_lpg():
    from carfinder.sources import autoscout24
    item = {"id": "x", "url": "/a", "price": {"priceRaw": 5000}, "vehicle": {}, "tracking": {"fuelType": "c"}}
    assert autoscout24.parse_list_item(item)["fuel"] == "petrol_cng"
    assert autoscout24.parse_list_item(dict(item, tracking={"fuelType": "l"}))["fuel"] == "petrol_lpg"


def test_parts_car_words_are_wrecks():
    for text in ("ERSATZTEILTRÄGER ERSATZTEILE ERHÄLTLICH", "Unfall auto zum ausschlachten",
                 "Schlachte dieses Auto", "Motor springt nicht an!!!", "Motor Getriebe ok  Airbags defekt"):
        assert scan.autoscout24.is_wreck(foreign(text=text)), text
    assert not scan.autoscout24.is_wreck(foreign(text="Unfallfahrzeug, fahrbereit, Airbag ist noch gut"))


def test_engine_above_two_litres_is_not_scanned():
    assert scan.usable(foreign(cc=1968))          # 2.0 TDI stays
    assert scan.usable(foreign(cc=2000))
    assert not scan.usable(foreign(cc=2967))      # 3.0 TDI
    assert scan.usable(foreign(cc=None))          # unknown on the list page: decided after details


def test_big_engine_found_on_detail_page_is_hidden(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    car = foreign(cc=None, detailed=False)
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    monkeypatch.setattr(scan.autoscout24, "add_details", lambda c: c.update(cc=2967, detailed=True))
    assert value_car(conn, snapshots, car, set()) is None


# --- 24.11. importer's review ---------------------------------------------------

def test_2010_passat_uses_its_own_b6_snapshot():
    passat = models.MODELS[2]
    b6 = foreign(model="Passat", year=2010)
    assert scan.snapshot_for(b6, passat) == ("Volkswagen", "Passat B6", 2009, 2011, "diesel")
    assert scan.estimate({}, b6, passat, {}) is None
    assert scan.snapshot_for(foreign(model="Passat", year=2011), passat) == ("Volkswagen", "Passat B7", 2011, 2015, "diesel")


def test_golf_plus_is_not_priced_against_the_golf():
    car = foreign(title="Volkswagen Golf Plus 1.6 TDI")
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    assert scan.comparables_for(snapshots, car, GOLF) == []
    assert scan.estimate(snapshots, car, GOLF, {}) is None
    assert len(scan.comparables_for(snapshots, foreign(), GOLF)) == 6


def test_two_wheel_drive_and_four_wheel_drive_use_separate_comparables(tmp_path):
    ads = [pa_car("fwd1", 9000), pa_car("fwd2", 9100), pa_car("4motion", 8000, title="Golf 7 2.0 TDI 4Motion", drive="4x4")]
    car = foreign()
    assert [c["id"] for c in scan.comparables_for(seed_cache(car, ads), car, GOLF)] == ["fwd1", "fwd2"]
    four = foreign(title="VW Golf 4Motion", drive="4x4")
    assert [c["id"] for c in scan.comparables_for(seed_cache(four, ads), four, GOLF)] == ["4motion"]


def test_banes_import_figure_reaches_settings():
    settings = scan.settings_for({"id": "x"}, {"x": {"carina": 1500}})
    assert settings == {"import_total": 1500}
    assert scan.settings_for({"id": "x"}, {"x": {"carina": 0}}) == {"import_total": 0}
    assert scan.settings_for({"id": "x"}, {"x": {"carina": None}}) == {}


def test_old_database_gets_the_carina_column_without_losing_rows(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE overrides (id TEXT PRIMARY KEY, transport INTEGER, repair INTEGER, "
                "origin_proof INTEGER, hidden INTEGER DEFAULT 0)")
    old.execute("INSERT INTO overrides VALUES ('as24:1', 900, 300, 0, 1)")
    old.commit()
    old.close()
    conn = db.connect(path)
    assert db.overrides(conn) == {"as24:1": {"id": "as24:1", "transport": 900, "repair": 300, "origin_proof": 0,
                                             "hidden": 1, "carina": None, "buy_discount": None, "verdict": None,
                                             "verdict_note": None, "verdict_at": None, "verdict_result": None}}
    db.set_override(conn, "as24:2", carina=1400)
    assert db.overrides(db.connect(path))["as24:2"]["carina"] == 1400   # a second connect leaves the column alone


def test_database_with_carina_gets_discount_column_and_keeps_existing_override(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as old:
        old.execute("CREATE TABLE overrides (id TEXT PRIMARY KEY, transport INTEGER, repair INTEGER, "
                    "origin_proof INTEGER, hidden INTEGER, carina INTEGER)")
        old.execute("INSERT INTO overrides VALUES ('as24:1', 900, 300, 0, 1, 1400)")
    conn = db.connect(path)
    assert db.overrides(conn)["as24:1"]["carina"] == 1400
    assert db.overrides(conn)["as24:1"]["buy_discount"] is None


@pytest.mark.parametrize("discount,settings", [(None, {}), (0, {"buy_discount": 0}), (250, {"buy_discount": 250})])
def test_buy_discount_reaches_settings(discount, settings):
    assert scan.settings_for({"id": "x"}, {"x": {"buy_discount": discount}}) == settings


@pytest.mark.parametrize("note,usable", [
    ("Auto nije u voznom stanju, kvačilo je defektno.", False),
    ("Kriv krov, motor radi.", False),
    ("Aktivirani airbag posle sudara.", False),
    ("Ogrebotine na braniku, auto je vozan.", True),
])
def test_wreck_facts_in_the_ai_note_win_over_a_small_repair_label(note, usable):
    car = foreign(ai={"state": "kvar", "repair": "mala", "note": note})
    assert scan.usable(car) is usable


def test_engine_limit_uses_ad_text_when_numeric_field_is_empty():
    assert not scan.usable(foreign(cc=None, title="Audi 3.0 TDI"))
    assert scan.usable(foreign(cc=None, title="Audi 2.0 TDI"))


def test_second_opener_of_an_old_database_does_not_fail_on_the_carina_column(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE overrides (id TEXT PRIMARY KEY, transport INTEGER, repair INTEGER, "
                "origin_proof INTEGER, hidden INTEGER DEFAULT 0)")
    old.execute("INSERT INTO overrides VALUES ('as24:1', 900, 300, 0, 1)")
    old.commit()
    old.close()

    real_connect = sqlite3.connect

    class RacedConnection(sqlite3.Connection):
        """Sees the old columns, then the other process adds the column just before this one does."""
        def execute(self, sql, *args):
            if sql.startswith("ALTER TABLE"):
                other = real_connect(path)
                other.execute(sql)
                other.commit()
                other.close()
            return super().execute(sql, *args)
    monkeypatch.setattr(db.sqlite3, "connect", lambda p: real_connect(p, factory=RacedConnection))
    conn = db.connect(path)
    assert db.overrides(conn)["as24:1"]["carina"] is None and db.overrides(conn)["as24:1"]["repair"] == 300


def test_other_schema_errors_still_raise(tmp_path, monkeypatch):
    import sqlite3

    class LockedConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql.startswith("ALTER TABLE"):
                raise sqlite3.OperationalError("database is locked")
            return super().execute(sql, *args)
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE overrides (id TEXT PRIMARY KEY, transport INTEGER, repair INTEGER, "
                "origin_proof INTEGER, hidden INTEGER DEFAULT 0)")
    old.commit()
    old.close()
    real_connect = sqlite3.connect
    monkeypatch.setattr(db.sqlite3, "connect", lambda p: real_connect(p, factory=LockedConnection))
    with pytest.raises(sqlite3.OperationalError):
        db.connect(path)


def test_cars_above_325000_km_are_not_scanned():
    assert scan.usable(foreign(km=325_000))
    assert not scan.usable(foreign(km=325_001))
    assert scan.usable(foreign(km=None))   # unknown km is not a reason to drop the car


@pytest.mark.parametrize("country,usable", [("DE", True), ("AT", True), ("CH", True), ("IT", False),
                                            ("FR", False), ("NL", False), (None, False)])
def test_only_cars_from_germany_austria_and_switzerland_are_scanned(country, usable):
    assert scan.usable(foreign(country=country, zip="8000")) is usable   # 8000: Zurich in CH, Graz in AT


@pytest.mark.parametrize("title,text", [
    ("Mercedes-Benz B 180 Taxi", ""),
    ("Mercedes-Benz B 180 CDI", "Sitzheizung vorn, Taxiausstattung: Dachzeichen einarmig"),
    ("Skoda Superb Ambition", "Export. EX Taxi/Mietwagen"),
    ("VW Golf", "TAXI-DACHZEICHEN"),
])
def test_ex_taxi_is_not_scanned(title, text):
    assert not scan.usable(foreign(title=title, text=text))


@pytest.mark.parametrize("make,gearbox,kept", [
    ("Ford", "automatic", False),     # mobilede:53181455186272, a Kuga PowerShift, was second on the page
    ("Ford", "manual", True),
    ("Ford", None, True),             # gearbox unknown: nothing says it is an automatic
    ("Volkswagen", "automatic", True),
])
def test_ford_with_an_automatic_gearbox_is_not_scanned(make, gearbox, kept):
    assert scan.usable(foreign(title=f"{make} Kuga", make=make, gearbox=gearbox)) is kept


# --- 25.11.2026: pa_seen keeps what a later days-to-sell count needs -------------------------

def test_old_pa_seen_gets_the_new_columns_without_losing_rows_and_its_price_as_the_first(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as old:
        old.execute("CREATE TABLE pa_seen (id TEXT PRIMARY KEY, pa_model TEXT, year INTEGER, price INTEGER, "
                    "first_seen REAL, last_seen REAL)")
        old.execute("INSERT INTO pa_seen VALUES ('30000001', 'Golf 7', 2015, 9000, 1.0, 2.0)")
    conn = db.connect(path)
    row = dict(conn.execute("SELECT * FROM pa_seen").fetchone())
    assert row == {"id": "30000001", "pa_model": "Golf 7", "year": 2015, "price": 9000, "first_seen": 1.0,
                   "last_seen": 2.0, "fuel": None, "gearbox": None, "kw": None, "body": None, "first_price": 9000,
                   "owner": None}
    db.connect(path)   # a second connect adds nothing and changes nothing
    assert dict(conn.execute("SELECT * FROM pa_seen").fetchone()) == row


def test_sighting_stores_the_variant_and_seller_and_keeps_the_first_price(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.store_pa(conn, "k", [pa_car("30000001", 9000, owner=1663491)], "Golf 7")
    db.store_pa(conn, "k", [pa_car("30000001", 8500, owner=1663491, gearbox="automatic")], "Golf 7")
    row = dict(conn.execute("SELECT * FROM pa_seen").fetchone())
    assert (row["price"], row["first_price"]) == (8500, 9000)
    assert (row["fuel"], row["gearbox"], row["kw"], row["body"], row["owner"]) == (
        "diesel", "automatic", 81, "hatchback", 1663491)


def test_first_price_comes_from_the_first_sighting_that_has_a_price(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.store_pa(conn, "k", [pa_car("30000001", None)], "Golf 7")    # PA showed the ad without a price first
    db.store_pa(conn, "k", [pa_car("30000001", 9000)], "Golf 7")
    db.store_pa(conn, "k", [pa_car("30000001", 8500)], "Golf 7")
    assert conn.execute("SELECT price, first_price FROM pa_seen").fetchone()[:] == (8500, 9000)


def test_sighting_of_an_ad_without_a_seller_id(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.store_pa(conn, "k", [pa_car("30000001", 9000)], "Golf 7")
    assert conn.execute("SELECT owner, first_price FROM pa_seen").fetchone()[:] == (None, 9000)
