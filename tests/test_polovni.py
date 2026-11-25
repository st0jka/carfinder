import pytest

from carfinder import net, polovni
from tests.test_scan_db import pa_car


@pytest.mark.parametrize("title,price,clean", [
    ("Audi A3 Rata 260e Bez Ucesca", 260, False),
    ("Audi A3 Rata od 260 €", 260, False),
    ("Audi A3 Rata 260e Bez Ucesca", 9500, True),
    ("Audi A3 5 vrata", 9500, True),
])
def test_monthly_payment_is_excluded_only_when_it_is_the_listed_price(title, price, clean):
    assert polovni.is_clean({"title": title, "price": price, "tags": []}) is clean


def item(id_, price=5000):
    return {"id": id_, "title": "Golf 7", "price": price}


@pytest.fixture
def pa(monkeypatch):
    """Stands in for polovniautomobili: no network in tests. pa(pages) serves them and returns the requests made."""
    def serve(pages, page_count=None):
        requests = []

        def get(url, params=None, site=None, headers=None):
            requests.append((site, dict(params)))
            return type("Response", (), {"text": str(params["page"])})()

        def next_data(text):
            page = pages[int(text) - 1]
            if isinstance(page, Exception):
                raise page
            count = len(pages) if page_count is None else page_count
            return {"searchResults": {"results": page}, "pagination": {"pageCount": count}}

        monkeypatch.setattr(polovni.net, "get", get)
        monkeypatch.setattr(polovni.net, "next_data", next_data)
        return requests
    return serve


def snapshot():
    return polovni.fetch_snapshot("Volkswagen", "Golf 7", 2012, 2020, "diesel")


# --- the snapshot of one generation ---------------------------------------------

def test_snapshot_reads_every_page_in_price_order(pa):
    requests = pa([[item("1"), item("2")], [item("3")], [item("4")]])
    assert [car["id"] for car in snapshot()] == ["1", "2", "3", "4"]
    assert [params["page"] for _, params in requests] == [1, 2, 3]
    assert {site for site, _ in requests} == {"polovni"}


def test_snapshot_asks_for_the_whole_generation_without_an_engine_filter(pa):
    requests = pa([[item("1")]])
    snapshot()
    assert requests == [("polovni", {"brand": "Volkswagen", "model[]": ["Golf 7"], "yearFrom": 2012, "yearTo": 2020,
                                     "damaged[]": "notDamaged", "sort": "price_asc", "page": 1,
                                     "fuel[]": "diesel"})]


def test_snapshot_of_a_generation_under_several_pa_names_asks_for_all_of_them_at_once(pa):
    requests = pa([[item("1")], [item("2")]])
    cars = polovni.fetch_snapshot("BMW", "316/318/320", 2012, 2018, "diesel")
    assert [car["id"] for car in cars] == ["1", "2"]
    assert [params["model[]"] for _, params in requests] == [["316", "318", "320"], ["316", "318", "320"]]
    assert requests[0][1]["brand"] == "BMW"


def test_snapshot_of_another_fuel_asks_for_that_fuel(pa):
    requests = pa([[item("1")]])
    polovni.fetch_snapshot("Volkswagen", "Golf 7", 2012, 2020, "petrol_lpg")
    assert requests[0][1]["fuel[]"] == "gasolineLpg"


def test_snapshot_without_ads_is_empty_after_one_request(pa):
    requests = pa([[]], page_count=0)
    assert snapshot() == []
    assert len(requests) == 1


def test_ad_repeated_on_the_next_page_is_kept_once_in_its_first_place(pa):
    pa([[item("1"), item("2")], [item("2"), item("3")]])
    assert [car["id"] for car in snapshot()] == ["1", "2", "3"]


def test_row_that_is_not_an_ad_is_skipped_and_the_snapshot_survives(pa):
    pa([[item("1"), "odd", 7, ["odd"], None, {}, item("2")]])
    assert [car["id"] for car in snapshot()] == ["1", "2"]


def test_error_on_a_later_page_fails_the_whole_snapshot(pa):
    pa([[item("1")], RuntimeError("HTTP 500")])
    with pytest.raises(RuntimeError):
        snapshot()


def test_block_on_a_later_page_is_a_block(pa):
    pa([[item("1")], net.Blocked("polovni returned 429")])
    with pytest.raises(net.Blocked):
        snapshot()


def test_page_count_at_the_limit_is_read_and_above_it_is_refused(pa, monkeypatch):
    monkeypatch.setattr(polovni, "MAX_PAGES", 2)
    pa([[item("1")], [item("2")]])
    assert len(snapshot()) == 2
    requests = pa([[item("1")], [item("2")], [item("3")]])
    with pytest.raises(ValueError):
        snapshot()
    assert len(requests) == 1


# --- one variant out of the snapshot ----------------------------------------------

def ids(ads):
    return [ad["id"] for ad in ads]


def test_variant_of_an_empty_snapshot_is_empty():
    assert polovni.variant_ads([], 2014, 2016, 1598, 81) == []


def test_variant_keeps_the_years_of_the_window_with_both_ends():
    ads = [pa_car(str(year), 9000, year=year) for year in (2013, 2014, 2015, 2016, 2017)] + [pa_car("x", 9000, year=None)]
    assert ids(polovni.variant_ads(ads, 2014, 2016, 1598, 81)) == ["2014", "2015", "2016"]


def test_variant_engine_size_is_within_30_cc():
    ads = [pa_car(str(cc), 9000, cc=cc) for cc in (1567, 1568, 1598, 1628, 1629)] + [pa_car("none", 9000, cc=None)]
    assert ids(polovni.variant_ads(ads, 2015, 2015, 1598, 81)) == ["1568", "1598", "1628"]


def test_variant_power_is_within_2_kw():
    ads = [pa_car(str(kw), 9000, kw=kw) for kw in (78, 79, 81, 83, 84)] + [pa_car("none", 9000, kw=None)]
    assert ids(polovni.variant_ads(ads, 2015, 2015, 1598, 81)) == ["79", "81", "83"]


def test_car_with_unknown_engine_size_takes_every_size_of_its_power():
    ads = [pa_car("1.6", 9000, cc=1598), pa_car("2.0", 9100, cc=1968), pa_car("none", 9200, cc=None),
           pa_car("other power", 9300, kw=110)]
    assert ids(polovni.variant_ads(ads, 2015, 2015, None, 81)) == ["1.6", "2.0", "none"]


def test_variant_has_no_limit_and_other_engines_do_not_count():
    ads = []
    for number in range(80):
        ads.append(pa_car(f"other{number}", 5000 + number, kw=110))
        ads.append(pa_car(f"same{number}", 5000 + number))
    variant = polovni.variant_ads(ads, 2015, 2015, 1598, 81)
    assert ids(variant) == [f"same{number}" for number in range(80)]   # the old cut at 75 dropped same75..same79
    assert len(polovni.variant_ads(ads[:150], 2015, 2015, 1598, 81)) == 75
    assert len(polovni.variant_ads(ads[:148], 2015, 2015, 1598, 81)) == 74


# --- four-wheel drive of an ad ---------------------------------------------------------

@pytest.mark.parametrize("title,field,drive", [
    ("Volkswagen Tiguan TDI", "4x4", "4x4"),                      # PA's own drive field
    ("Volkswagen Tiguan 2.0 Tdi 4MOTION", None, "4x4"),           # empty field: the title says it
    ("Audi A4 2.0 TDI Quattro", "", "4x4"),
    ("Škoda Octavia Scout", None, "4x4"),
    ("Volkswagen Passat B8 Alltrack", None, "4x4"),
    ("Volkswagen Tiguan R-Line Cup 4x4", "Prednji", "4x4"),
    ("Volkswagen Tiguan 2.0 TDI DSG HIGHLINE", None, None),
    ("Volkswagen Tiguan 2.0 TDI", "Prednji", None),
    (None, None, None),
])
def test_drive_comes_from_the_field_or_the_words_of_the_title(title, field, drive):
    ad = polovni.parse_result({"id": "1", "title": title, "price": 9000, "featuredInfo": {"drive": field}})
    assert ad["drive"] == drive


def test_ad_without_featured_info_reads_the_title():
    assert polovni.parse_result({"id": "1", "title": "Tiguan 4x4", "price": 9000})["drive"] == "4x4"
    assert polovni.parse_result({"id": "1", "title": "Tiguan", "price": 9000})["drive"] is None


def test_drive_abbreviation_inside_a_word_is_not_four_wheel_drive():
    assert polovni.parse_result({"id": "1", "title": "Audi A4 Rawdon", "price": 9000})["drive"] is None


# --- 25.11.2026: what PA says about the seller and a lowered price --------------------

def test_price_cut_keeps_the_price_before_it_and_the_seller():
    ad = polovni.parse_result({"id": "30352054", "title": "Kuga", "price": 8000, "basePrice": 8900, "discount": True,
                               "discountPercentage": 10, "owner": 1663491})
    assert (ad["cut"], ad["base_price"], ad["owner"]) == (True, 8900, 1663491)


@pytest.mark.parametrize("fields,base_price", [
    ({"discount": False, "basePrice": 9000}, 9000),   # what PA sends on an uncut ad: the asking price again
    ({"discount": False, "basePrice": None}, None),
    ({}, None),
])
def test_ad_never_cut_or_without_the_field_counts_as_not_cut(fields, base_price):
    ad = polovni.parse_result({"id": "1", "title": "Golf 7", "price": 9000, **fields})
    assert (ad["cut"], ad["base_price"], ad["owner"]) == (False, base_price, None)
