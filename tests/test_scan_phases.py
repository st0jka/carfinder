"""The scan as a whole: PA snapshots, one thread per site, the five phases. No network: every site is faked."""
import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import date

import pytest

from carfinder import db, describe, models, net, polovni, scan
from tests.test_scan_db import foreign, pa_car

GOLF, POLO, PASSAT, TIGUAN = models.MODELS[0], models.MODELS[1], models.MODELS[2], models.MODELS[3]
GOLF6_DIESEL = ("Volkswagen", "Golf 6", 2009, 2013, "diesel")
GOLF7_DIESEL = ("Volkswagen", "Golf 7", 2012, 2020, "diesel")
GOLF7_LPG = ("Volkswagen", "Golf 7", 2012, 2020, "petrol_lpg")
GOLF7_PETROL = ("Volkswagen", "Golf 7", 2012, 2020, "petrol")
# every Golf generation sells as petrol too, so its petrol snapshot is fetched up front with the diesel one
GOLF_UPFRONT = [GOLF6_DIESEL, ("Volkswagen", "Golf 6", 2009, 2013, "petrol"), GOLF7_DIESEL, GOLF7_PETROL,
                ("Volkswagen", "Golf 8", 2020, 2024, "diesel"), ("Volkswagen", "Golf 8", 2020, 2024, "petrol")]
HOUR = 3600


def pa_cars():
    return [pa_car(str(i), 9000 + i * 100) for i in range(6)]


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


@pytest.fixture
def fetched(monkeypatch):
    """No site is reached: PA has six Golf 7 ads for every snapshot, searches find nothing, a detail page only
    marks the car as read. Returns the list of snapshots asked from PA."""
    asked = []

    def fetch_snapshot(*snapshot):
        asked.append(snapshot)
        return pa_cars()

    monkeypatch.setattr(polovni, "fetch_snapshot", fetch_snapshot)
    for source in scan.SOURCES.values():
        monkeypatch.setattr(source, "search", lambda *a: [])
        monkeypatch.setattr(source, "add_details", lambda car: car.update(detailed=True))
    return asked


def found_on_autoscout24(monkeypatch, *cars):
    """AutoScout24 finds these cars for the Golf and nothing for other models."""
    def search(as24_path, *a):
        return list(cars) if as24_path == GOLF["as24"] else []
    monkeypatch.setattr(scan.autoscout24, "search", search)


def run(conn, scan_models=(GOLF,), overrides=None, blocked_sites=None):
    errors = []
    scan.run(conn, list(scan_models), overrides or {}, errors, set() if blocked_sites is None else blocked_sites)
    return errors


def saved(conn, car_id="as24:1"):
    """The saved row of a car as a dict, or None when the scan did not save it."""
    row = conn.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
    return dict(row) if row else None


def saved_result(conn, car_id="as24:1"):
    return db.json.loads(saved(conn, car_id)["result"])


def age_cache(conn, hours):
    conn.execute("UPDATE pa_cache SET fetched_at = fetched_at - ?", (hours * HOUR,))
    conn.commit()


# --- which snapshot a car needs ---------------------------------------------------

def test_snapshot_starts_one_year_under_year_from_or_with_the_generation():
    golf6, golf7, golf8 = GOLF["generations"]
    assert scan.snapshot_of(GOLF, golf6, "diesel") == GOLF6_DIESEL   # 2008 generation: from 2009
    assert scan.snapshot_of(GOLF, golf7, "diesel") == GOLF7_DIESEL   # 2012 generation: from 2012
    assert scan.snapshot_of(GOLF, golf8, "petrol") == ("Volkswagen", "Golf 8", 2020, 2024, "petrol")
    assert scan.YEAR_FROM == 2010


def test_car_of_the_first_scanned_year_keeps_its_one_year_older_comparables():
    car = foreign(year=2010, kw=77)
    ads = [pa_car(str(year), 5000, model="Golf 6", title="Golf 6 1.6 TDI", year=year, kw=77)
           for year in (2009, 2010, 2011, 2012)]
    assert [c["id"] for c in scan.comparables_for({GOLF6_DIESEL: ads}, car, GOLF)] == ["2009", "2010", "2011"]


@pytest.mark.parametrize("car", [foreign(fuel="petrol", price=500), foreign(price=500), foreign(year=2012),
                                 foreign(year=None),
                                 foreign(year=2030), foreign(text="Motorschaden"), {"id": "odd"}])
def test_car_that_is_not_priced_needs_no_snapshot(car):
    assert scan.snapshot_for(car, GOLF) is None


def test_car_is_priced_against_the_snapshot_of_its_generation_and_fuel():
    assert scan.snapshot_for(foreign(), GOLF) == GOLF7_DIESEL
    assert scan.snapshot_for(foreign(year=2010), GOLF) == GOLF6_DIESEL
    assert scan.snapshot_for(foreign(fuel="petrol_lpg"), GOLF) == GOLF7_LPG
    assert scan.snapshot_for(foreign(fuel="petrol"), GOLF) == GOLF7_PETROL


def test_plain_petrol_needs_a_snapshot_only_for_a_petrol_generation():
    passat = foreign(title="VW Passat 1.4 TSI", model="Passat", year=2017, fuel="petrol", cc=1395, kw=110)
    assert scan.snapshot_for(passat, PASSAT) is None                  # no Passat generation sells as petrol
    assert scan.snapshot_for(dict(passat, fuel="diesel"), PASSAT) == ("Volkswagen", "Passat B8", 2014, 2023, "diesel")
    assert scan.snapshot_for(foreign(fuel="petrol", year=2012), GOLF) is None   # Golf 6 or 7: not told apart


def test_comparables_are_every_clean_exact_match_of_the_snapshot():
    """PA used to be asked per variant for its 75 cheapest ads; that cut stopped the list at same37."""
    car = foreign()   # 2015, 1598 cc, 81 kW, manual: years 2014 to 2016
    ads = []
    for number in range(100):
        price = 5000 + number * 10
        ads.append(pa_car(f"same{number}", price))
        ads.append(pa_car(f"automatic{number}", price, gearbox="automatic"))   # same PA query, dropped locally
        ads.append(pa_car(f"two-litre{number}", price, cc=1968, kw=110))       # another PA query
        ads.append(pa_car(f"old{number}", price, year=2013))                   # outside the year window
    comparables = scan.comparables_for({GOLF7_DIESEL: ads}, car, GOLF)
    assert [c["id"] for c in comparables] == [f"same{number}" for number in range(100)]


def test_sub_model_behind_75_cheaper_base_cars_is_still_priced():
    """A cut at the 75 cheapest ads of the engine came before the exact match and left a dearer variant no ads."""
    alltrack = foreign(title="Volkswagen Golf Alltrack 1.6 TDI 4Motion", drive="4x4")
    ads = [pa_car(f"base{number}", 5000 + number * 10) for number in range(80)]
    ads += [pa_car(f"alltrack{number}", 9000 + number * 100, title="Volkswagen Golf 7 Alltrack", drive="4x4")
            for number in range(5)]
    snapshots = {GOLF7_DIESEL: ads}
    assert [c["id"] for c in scan.comparables_for(snapshots, alltrack, GOLF)] == [f"alltrack{n}" for n in range(5)]
    serbia = scan.estimate(snapshots, alltrack, GOLF, {})["serbia"]
    assert serbia["n"] == 5 and serbia["anchor"] == 9000   # the cheapest Alltrack ad, not a 5,000 base car


def test_named_registration_in_a_split_year_uses_its_generation_and_rejects_conflicting_ad_titles():
    car = foreign(year=2012, title="VW Golf Variant VI")
    assert scan.snapshot_for(car, GOLF) == GOLF6_DIESEL
    right = pa_car("right", 5000, year=2012, model="Golf 6", title="Golf 6 1.6 TDI")
    wrong = dict(right, id="wrong", title="Golf VII")
    from_other_snapshot = dict(right, id="wrong-snapshot", model="Golf 7")
    snapshots = {GOLF6_DIESEL: [right, wrong], GOLF7_DIESEL: [from_other_snapshot]}
    assert [ad["id"] for ad in scan.comparables_for(snapshots, car, GOLF)] == ["right"]
    assert scan.snapshot_for(dict(car, year=2014), GOLF) is None


def test_mixed_year_under_one_pa_name_needs_a_named_generation_on_the_serbian_ad():
    car = foreign(year=2015, title="Tiguan I", model="Tiguan", body="suv")
    key = scan.snapshot_for(car, TIGUAN)
    known = pa_car("known", 9000, year=2016, model="Tiguan", title="Tiguan I", body="suv")
    unknown = dict(known, id="unknown", title="Volkswagen Tiguan")
    other = dict(known, id="other", title="Tiguan II")
    assert [ad["id"] for ad in scan.comparables_for({key: [known, unknown, other]}, car, TIGUAN)] == ["known"]


# --- phase a: PA snapshots ------------------------------------------------------------

def test_diesel_and_petrol_snapshots_of_every_petrol_generation_are_fetched_up_front_and_stored(conn, fetched):
    assert run(conn) == []
    assert fetched == GOLF_UPFRONT
    keys = [row["key"] for row in conn.execute("SELECT key FROM pa_cache ORDER BY key")]
    assert keys == ['[7, "Volkswagen", "Golf 6", 2009, 2013, "diesel"]', '[7, "Volkswagen", "Golf 6", 2009, 2013, "petrol"]',
                    '[7, "Volkswagen", "Golf 7", 2012, 2020, "diesel"]', '[7, "Volkswagen", "Golf 7", 2012, 2020, "petrol"]',
                    '[7, "Volkswagen", "Golf 8", 2020, 2024, "diesel"]', '[7, "Volkswagen", "Golf 8", 2020, 2024, "petrol"]']
    assert conn.execute("SELECT COUNT(*) FROM pa_seen").fetchone()[0] == 6   # sightings are still written


def test_only_the_models_of_this_run_are_fetched(conn, fetched):
    run(conn, [PASSAT])
    assert [snapshot[1] for snapshot in fetched] == ["Passat B6", "Passat B7", "Passat B8"]


@pytest.mark.parametrize("hours,fetches", [(0, 6), (19, 6), (21, 12), (24, 12)])
def test_snapshot_is_fetched_again_only_after_20_hours(conn, fetched, hours, fetches):
    run(conn)
    age_cache(conn, hours)
    run(conn)
    assert len(fetched) == fetches


@pytest.mark.parametrize("phase_a_hours", [0.5, 1.5, 3])
def test_daily_model_gets_fresh_pa_prices_at_its_run_the_next_day(conn, fetched, phase_a_hours):
    """The snapshot is stored when phase a ends; with a 23 h cache, one stored 1.5 h into the run was still
    "fresh" at the same hour next day and the model was priced from two-day-old ads."""
    run(conn)
    age_cache(conn, 24 - phase_a_hours)
    run(conn)
    assert len(fetched) == 2 * len(GOLF_UPFRONT)


def test_other_fuel_is_fetched_only_when_a_car_needs_it(conn, fetched, monkeypatch):
    found_on_autoscout24(monkeypatch, foreign(id="as24:lpg", fuel="petrol_lpg"),
                         foreign(id="as24:lpg2", fuel="petrol_lpg"))
    run(conn)
    assert fetched == GOLF_UPFRONT + [GOLF7_LPG]
    assert saved_result(conn, "as24:lpg") is None   # the six Serbian ads are diesels: nothing to compare with


@pytest.mark.parametrize("car", [foreign(fuel="petrol"), foreign(fuel="petrol_lpg", price=500),
                                 foreign(fuel="petrol_lpg", year=2012), foreign(fuel="other")])
def test_petrol_and_cars_that_are_not_priced_fetch_nothing_more(conn, fetched, monkeypatch, car):
    found_on_autoscout24(monkeypatch, car)
    run(conn)
    assert fetched == GOLF_UPFRONT   # the petrol Golf's snapshot came up front
    assert saved_result(conn) is None   # still saved, hidden


def test_empty_snapshot_hides_the_car(conn, fetched, monkeypatch):
    monkeypatch.setattr(polovni, "fetch_snapshot", lambda *snapshot: [])
    found_on_autoscout24(monkeypatch, foreign())
    assert run(conn) == []
    assert saved_result(conn) is None


def failing_pa(monkeypatch, error, only_model=None):
    calls = []

    def fetch_snapshot(*snapshot):
        calls.append(snapshot)
        if only_model is None or snapshot[1] == only_model:
            raise error
        return pa_cars()
    monkeypatch.setattr(polovni, "fetch_snapshot", fetch_snapshot)
    return calls


@pytest.mark.parametrize("error", [RuntimeError("HTTP 500"), net.Blocked("polovni returned 429")])
@pytest.mark.parametrize("hours", [25, 71])
def test_failed_refresh_prices_from_the_previous_snapshot_under_72_hours(conn, fetched, monkeypatch, error, hours):
    db.store_pa(conn, scan.cache_key(GOLF7_DIESEL), pa_cars(), "Golf 7")
    age_cache(conn, hours)
    stamp = conn.execute("SELECT fetched_at FROM pa_cache").fetchone()[0]
    failing_pa(monkeypatch, error)
    found_on_autoscout24(monkeypatch, foreign())
    errors = run(conn)
    assert saved_result(conn)["serbia"]["n"] == 6
    assert errors                                                                      # the failure is in the run's note
    assert conn.execute("SELECT fetched_at FROM pa_cache").fetchone()[0] == stamp     # and the snapshot keeps its age


@pytest.mark.parametrize("error", [RuntimeError("HTTP 500"), net.Blocked("polovni returned 429")])
def test_previous_snapshot_over_72_hours_is_not_used_and_the_last_result_stays(conn, fetched, monkeypatch, error):
    db.store_pa(conn, scan.cache_key(GOLF7_DIESEL), pa_cars(), "Golf 7")
    age_cache(conn, 73)
    db.save_car(conn, foreign(), {"profit": 1234}, GOLF["as24"])
    before = saved(conn)
    failing_pa(monkeypatch, error)
    found_on_autoscout24(monkeypatch, foreign(price=4100), foreign(id="as24:other", fuel="other"))
    run(conn)
    assert saved(conn) == before                      # not priced in this run and not hidden either
    assert saved_result(conn, "as24:other") is None   # a car that needs no Serbian price is saved as always


def test_car_never_seen_before_is_not_saved_without_a_snapshot(conn, fetched, monkeypatch):
    failing_pa(monkeypatch, RuntimeError("HTTP 500"))
    found_on_autoscout24(monkeypatch, foreign())
    run(conn)
    assert saved(conn) is None


def test_error_in_one_snapshot_does_not_stop_the_next(conn, fetched, monkeypatch):
    calls = failing_pa(monkeypatch, ValueError("odd page"), only_model="Golf 6")
    found_on_autoscout24(monkeypatch, foreign())
    errors = run(conn)
    assert calls == GOLF_UPFRONT
    assert errors == ["polovni Golf 6 diesel: ValueError('odd page')", "polovni Golf 6 petrol: ValueError('odd page')"]
    assert saved_result(conn)["serbia"]["n"] == 6


def test_pa_block_stops_the_requests_to_pa_and_is_noted_once(conn, fetched, monkeypatch):
    calls = failing_pa(monkeypatch, net.Blocked("polovni returned 429"))
    found_on_autoscout24(monkeypatch, foreign(fuel="petrol_lpg"))
    blocked_sites = set()
    errors = run(conn, blocked_sites=blocked_sites)
    assert calls == [GOLF6_DIESEL]          # the other snapshots and LPG were queued but never requested
    assert errors == ["polovni: polovni returned 429"]
    assert blocked_sites == {"polovni"}


# --- one thread per site ----------------------------------------------------------------

def test_job_result_block_and_skip():
    blocked_sites = set()
    calls = []

    def fetch(value):
        calls.append(value)
        if value == "block":
            raise net.Blocked("429")
        if value == "error":
            raise RuntimeError("odd page")
        return value

    assert scan.on_site("a", blocked_sites, fetch, "ok") == "ok"
    with pytest.raises(RuntimeError):
        scan.on_site("a", blocked_sites, fetch, "error")
    assert blocked_sites == set()                      # an error is not a block
    with pytest.raises(net.Blocked) as blocked:
        scan.on_site("a", blocked_sites, fetch, "block")
    assert not isinstance(blocked.value, scan.Skipped) and blocked_sites == {"a"}
    with pytest.raises(scan.Skipped):
        scan.on_site("a", blocked_sites, fetch, "ok")
    assert calls == ["ok", "error", "block"]           # the skipped job made no request
    assert scan.on_site("b", blocked_sites, fetch, "ok") == "ok"


def test_every_site_works_in_one_thread_of_its_own(conn, fetched, monkeypatch):
    threads = defaultdict(set)   # site -> names of the threads that made its requests

    def seen(site, result):
        def request(*a):
            threads[site].add(threading.current_thread().name)
            return result() if callable(result) else result
        return request

    monkeypatch.setattr(polovni, "fetch_snapshot", seen("polovni", pa_cars))
    monkeypatch.setattr(scan.autoscout24, "search", seen("autoscout24", lambda: [foreign(detailed=False)]))
    monkeypatch.setattr(scan.autoscout24, "add_details", seen("autoscout24", None))
    monkeypatch.setattr(scan.willhaben, "search", seen("willhaben", []))
    monkeypatch.setattr(scan.mobilede, "search", seen("mobilede", []))
    assert run(conn, [GOLF, POLO]) == []
    assert set(threads) == {"polovni", "autoscout24", "willhaben", "mobilede"}
    names = [name for site_threads in threads.values() for name in site_threads]
    assert len(names) == 4 and len(set(names)) == 4          # one thread per site, never shared
    assert threading.current_thread().name not in names


def test_sites_are_read_side_by_side_but_one_request_at_a_time_each(conn, fetched, monkeypatch):
    together = threading.Barrier(4, timeout=10)   # breaks unless PA and the three sources are mid-request at once
    met = set()
    in_flight, most = Counter(), Counter()
    lock = threading.Lock()

    def request(site, result):
        def fake(*a):
            with lock:
                in_flight[site] += 1
                most[site] = max(most[site], in_flight[site])
                first = site not in met
                met.add(site)
            if first:
                together.wait()
            time.sleep(0.005)
            with lock:
                in_flight[site] -= 1
            return result() if callable(result) else result
        return fake

    monkeypatch.setattr(polovni, "fetch_snapshot", request("polovni", pa_cars))
    for name, source in scan.SOURCES.items():
        monkeypatch.setattr(source, "search", request(name, []))
    assert run(conn, [GOLF, POLO, PASSAT]) == []
    assert not together.broken
    assert most == {"polovni": 1, "autoscout24": 1, "willhaben": 1, "mobilede": 1}


def test_search_error_in_one_thread_does_not_stop_the_other_sites(conn, fetched, monkeypatch):
    found_on_autoscout24(monkeypatch, foreign())

    def broken(*a):
        raise ValueError("odd page")
    monkeypatch.setattr(scan.willhaben, "search", broken)
    errors = run(conn, [GOLF, POLO])
    assert errors == ["willhaben volkswagen/golf: ValueError('odd page')",
                      "willhaben volkswagen/polo: ValueError('odd page')"]   # an error is retried per model
    assert saved_result(conn)["serbia"]["n"] == 6


def test_blocked_source_is_not_searched_again_in_this_run(conn, fetched, monkeypatch):
    calls = []

    def blocked(as24_path, *a):
        calls.append(as24_path)
        raise net.Blocked("willhaben returned 403")
    monkeypatch.setattr(scan.willhaben, "search", blocked)
    found_on_autoscout24(monkeypatch, foreign())
    blocked_sites = set()
    errors = run(conn, [GOLF, POLO, PASSAT], blocked_sites=blocked_sites)
    assert calls == ["volkswagen/golf"]
    assert errors == ["willhaben: willhaben returned 403"]
    assert blocked_sites == {"willhaben"}
    assert saved_result(conn) is not None


# --- which years are searched, and a search that stops half way ------------------------------

@pytest.mark.parametrize("model,years", [
    (GOLF, (2010, 2024)),      # the Golf 8 runs to 2024
    (PASSAT, (2010, 2023)),    # 2010 Passats are priced as B6
    (TIGUAN, (2010, 2024)),    # Tiguan I began in 2007: the search still starts at YEAR_FROM
])
def test_search_years_are_the_years_the_model_is_priced_in(model, years):
    assert scan.search_years(model) == years


def test_petrol_golf_is_priced_against_serbian_petrol_ads(conn, monkeypatch):
    def fetch_snapshot(*snapshot):
        fuel = snapshot[-1]
        return [pa_car(f"{fuel}{i}", 9000 + i * 100, fuel=fuel) for i in range(6)]
    monkeypatch.setattr(polovni, "fetch_snapshot", fetch_snapshot)
    for source in scan.SOURCES.values():
        monkeypatch.setattr(source, "search", lambda *a: [])
    found_on_autoscout24(monkeypatch, foreign(id="as24:petrol", fuel="petrol"))
    assert run(conn) == []
    serbia = saved_result(conn, "as24:petrol")["serbia"]
    assert serbia["n"] == 6 and serbia["first"]["id"] == "petrol0"   # never a diesel ad


def test_petrol_passat_is_saved_hidden_without_a_petrol_snapshot(conn, fetched, monkeypatch):
    passat = foreign(title="VW Passat 1.4 TSI", model="Passat", year=2017, fuel="petrol", cc=1395, kw=110)
    monkeypatch.setattr(scan.autoscout24, "search", lambda as24_path, *a: [passat] if as24_path == PASSAT["as24"] else [])
    run(conn, [PASSAT])
    assert [snapshot[-1] for snapshot in fetched] == ["diesel", "diesel", "diesel"]
    assert saved_result(conn) is None


@pytest.mark.parametrize("run_number,group", [(0, 0), (1, 1), (4, 4), (7, 7), (8, 0), (13, 5)])
def test_every_run_scans_the_core_models_and_one_eighth_of_the_daily_ones(run_number, group):
    run_models = scan.models_of_run(run_number)
    assert run_models[:20] == models.CORE_MODELS
    assert run_models[20:] == models.DAILY_MODELS[group::8]
    assert 14 <= len(run_models) - 20 <= 15   # 118 daily models in 8 groups


@pytest.mark.parametrize("first_run", [0, 5, 37])
def test_any_eight_runs_in_a_row_scan_every_daily_model_once(first_run):
    # GitHub starts scheduled runs late or drops them (25.11.2026: 2 of 6 ran), so the turn follows runs, not hours
    runs = [scan.models_of_run(number) for number in range(first_run, first_run + 8)]
    daily = [model["as24"] for run_models in runs for model in run_models[20:]]
    assert sorted(daily) == sorted(model["as24"] for model in models.DAILY_MODELS)
    assert len(daily) == len(set(daily)) == 118


def test_search_years_never_pass_this_year(monkeypatch):
    class Date:
        @staticmethod
        def today():
            return date(2022, 5, 1)
    monkeypatch.setattr(scan, "date", Date)
    assert scan.search_years(PASSAT) == (2010, 2022)


def test_every_source_is_asked_for_the_priced_years_only(fetched, monkeypatch):
    asked = []
    for name, source in scan.SOURCES.items():
        monkeypatch.setattr(source, "search", lambda *a, name=name: asked.append((name, *a)) or [])
    with scan.site_threads() as threads:
        assert scan.search_all(threads, [PASSAT], [], set()) == []
    assert sorted(asked) == [(name, "volkswagen/passat", 2010, 2023, scan.MIN_PRICE_EUR, scan.MAX_PRICE_EUR)
                             for name in ("autoscout24", "mobilede", "willhaben")]


def failing_search(monkeypatch, error, cars):
    """AutoScout24 fails every model with this error, which carries the cars of the years read before it."""
    calls = []

    def search(as24_path, *a):
        calls.append(as24_path)
        error.cars = list(cars)
        raise error
    monkeypatch.setattr(scan.autoscout24, "search", search)
    return calls


def test_block_in_the_middle_of_a_model_keeps_the_years_already_read(conn, fetched, monkeypatch):
    calls = failing_search(monkeypatch, net.Blocked("autoscout24 returned 429"), [foreign()])
    blocked_sites = set()
    errors = run(conn, [GOLF, POLO], blocked_sites=blocked_sites)
    assert calls == ["volkswagen/golf"] and blocked_sites == {"autoscout24"}   # the Polo was not searched
    assert errors == ["autoscout24: autoscout24 returned 429"]
    assert saved_result(conn)["serbia"]["n"] == 6      # the car read before the block is priced and saved


def test_failed_year_keeps_the_other_years_and_reaches_the_run_note(conn, fetched, monkeypatch):
    calls = failing_search(monkeypatch, RuntimeError("HTTP 500"), [foreign()])
    blocked_sites = set()
    errors = run(conn, blocked_sites=blocked_sites)
    assert calls == ["volkswagen/golf"] and blocked_sites == set()
    assert errors == ["autoscout24 volkswagen/golf: RuntimeError('HTTP 500')"]
    assert saved_result(conn)["passes"] is True


def test_real_autoscout24_search_blocked_in_its_second_year_keeps_the_first(conn, monkeypatch):
    """The real autoscout24.search and each_year; only the site itself and the other sites are faked."""
    listing = {"id": "1", "url": "/1", "price": {"priceRaw": 4000}, "location": {"countryCode": "AT", "zip": "1100"},
               "vehicle": {"make": "Volkswagen", "model": "Golf", "transmission": "Schaltgetriebe",
                           "engineDisplacementInCCM": "1.598 cm³"},
               "tracking": {"firstRegistration": "03-2015", "fuelType": "d", "mileage": "150000"},
               "vehicleDetails": [{"ariaLabel": "Leistung", "data": "81 kW (110 PS)"}]}
    years = []

    def get(url, params=None, site=None, headers=None):
        years.append(params["fregfrom"])
        if len(years) == 3:   # 2010 has a diesel and a petrol search: the third request is 2011
            raise net.Blocked("autoscout24 returned 429")
        return type("Response", (), {"text": ""})()
    monkeypatch.setattr(polovni, "fetch_snapshot", lambda *snapshot: pa_cars())
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [])
    monkeypatch.setattr(scan.mobilede, "search", lambda *a: [])
    monkeypatch.setattr(scan.autoscout24.net, "get", get)
    monkeypatch.setattr(scan.autoscout24.net, "next_data", lambda text: {"listings": [listing], "numberOfPages": 1})
    errors = run(conn)
    assert years == [2010, 2010, 2011]
    assert errors == ["autoscout24: autoscout24 returned 429"]
    assert saved_result(conn)["serbia"]["n"] == 6      # the 2010 search brought this car before the block


# --- phases b to e -------------------------------------------------------------------------

def test_detail_page_is_read_only_for_cars_near_the_target(conn, fetched, monkeypatch):
    read = []
    monkeypatch.setattr(scan.autoscout24, "add_details", lambda car: read.append(car["id"]) or car.update(detailed=True))
    found_on_autoscout24(monkeypatch, foreign(detailed=False), foreign(id="as24:dear", price=9000, detailed=False),
                         foreign(id="as24:petrol", fuel="petrol", detailed=False))
    run(conn)
    assert read == ["as24:1"]
    assert saved_result(conn)["passes"] is True
    assert saved_result(conn, "as24:dear")["passes"] is False    # valued from the list page alone
    assert saved_result(conn, "as24:petrol") is None


def test_source_blocked_on_a_detail_page_keeps_the_list_estimates(conn, fetched, monkeypatch):
    read, asked = [], []

    def blocked(car):
        read.append(car["id"])
        raise net.Blocked("autoscout24 returned 429")
    monkeypatch.setattr(scan.autoscout24, "add_details", blocked)
    monkeypatch.setattr(describe, "ask_haiku", lambda prompt: asked.append(prompt) or '{"stanje": "ok", "popravka": "nema"}')
    cars = [foreign(id=f"as24:{number}", text="Top Zustand", detailed=False) for number in (1, 2, 3)]
    found_on_autoscout24(monkeypatch, *cars)
    blocked_sites = set()
    errors = run(conn, blocked_sites=blocked_sites)
    assert read == ["as24:1"]                         # the two queued detail pages were never requested
    assert blocked_sites == {"autoscout24"}
    assert errors == ["autoscout24: autoscout24 returned 429"]   # once, so the run is logged as partial
    for car in cars:
        result = saved_result(conn, car["id"])
        assert result["passes"] is False and "nismo otvorili oglas, opis i slike nisu pregledani" in result["flags"]
    assert len(asked) == 1                            # only the car whose page was tried is read, as before


def test_missing_detail_page_keeps_the_estimate_and_the_site(conn, fetched, monkeypatch):
    read = []

    def gone(car):
        read.append(car["id"])
        raise RuntimeError("HTTP 404")
    monkeypatch.setattr(scan.autoscout24, "add_details", gone)
    found_on_autoscout24(monkeypatch, foreign(detailed=False), foreign(id="as24:2", detailed=False))
    blocked_sites = set()
    assert run(conn, blocked_sites=blocked_sites) == []
    assert read == ["as24:1", "as24:2"] and blocked_sites == set()
    assert "nismo otvorili oglas, opis i slike nisu pregledani" in saved_result(conn)["flags"]


def test_failed_detail_page_is_logged_with_its_cause(conn, fetched, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="carfinder")

    def changed(car):
        raise KeyError("listingDetails")
    monkeypatch.setattr(scan.autoscout24, "add_details", changed)
    found_on_autoscout24(monkeypatch, foreign(detailed=False))
    assert run(conn) == []
    assert "details failed: u: KeyError('listingDetails')" in caplog.text


def test_odd_detail_page_hides_that_car_and_the_others_are_saved(conn, fetched, monkeypatch):
    """An engine size that once arrives as text broke the check after the details, and with it every save."""
    def add_details(car):
        car.update(detailed=True)
        if car["id"] == "as24:odd":
            car.update(cc="1598")
    monkeypatch.setattr(scan.autoscout24, "add_details", add_details)
    found_on_autoscout24(monkeypatch, foreign(id="as24:odd", detailed=False), foreign(detailed=False))
    assert run(conn) == []
    assert saved_result(conn, "as24:odd") is None
    assert saved_result(conn)["passes"] is True


def test_car_of_a_source_blocked_earlier_gets_no_detail_page(conn, fetched, monkeypatch):
    read = []
    monkeypatch.setattr(scan.autoscout24, "add_details", lambda car: read.append(car["id"]))
    found_on_autoscout24(monkeypatch, foreign(detailed=False))
    with scan.site_threads() as threads:
        results = scan.value_and_save(conn, threads, [(foreign(detailed=False), GOLF)], {GOLF7_DIESEL: pa_cars()}, {},
                                      {"autoscout24"}, [])
    assert read == [] and results["as24:1"]["passes"] is False


def test_descriptions_are_read_at_most_four_at_a_time(conn, fetched, monkeypatch):
    reading, most = [0], [0]
    lock = threading.Lock()

    def ask(prompt):
        with lock:
            reading[0] += 1
            most[0] = max(most[0], reading[0])
        time.sleep(0.05)
        with lock:
            reading[0] -= 1
        return '{"stanje": "ok", "popravka": "nema", "napomena": ""}'
    monkeypatch.setattr(describe, "ask_haiku", ask)
    found_on_autoscout24(monkeypatch, *[foreign(id=f"as24:{number}", text=f"Top Zustand {number}") for number in range(12)])
    run(conn)
    assert 2 <= most[0] <= scan.HAIKU_WORKERS == 4
    assert all(saved_result(conn, f"as24:{number}")["passes"] for number in range(12))


def test_error_while_reading_one_description_does_not_stop_the_cars(conn, fetched, monkeypatch):
    def read(car):
        if car["id"] == "as24:1":
            raise RuntimeError("thread error")
        return {"state": "kvar", "note": "kvacilo", "key": describe.text_key(car)}
    monkeypatch.setattr(describe, "read", read)
    found_on_autoscout24(monkeypatch, foreign(text="a"), foreign(id="as24:2", text="b"))
    assert run(conn) == []
    assert saved_result(conn)["passes"] is True
    assert "iz opisa: kvacilo" in saved_result(conn, "as24:2")["flags"]


def test_odd_listing_is_hidden_and_the_others_are_saved(conn, fetched, monkeypatch):
    found_on_autoscout24(monkeypatch, {"id": "as24:odd", "source": "autoscout24", "price": 4000}, foreign())
    assert run(conn) == []
    assert saved_result(conn, "as24:odd") is None
    assert saved_result(conn)["passes"] is True


def test_ad_listed_twice_by_one_search_is_read_and_saved_once(conn, fetched, monkeypatch, caplog):
    """Live Tiguan run 24.11.2026: an ad moved to the next page between two requests and came back twice."""
    caplog.set_level(logging.INFO, logger="carfinder")
    read, asked = [], []
    monkeypatch.setattr(scan.autoscout24, "add_details", lambda car: read.append(car["id"]) or car.update(detailed=True))
    monkeypatch.setattr(describe, "ask_haiku",
                        lambda prompt: asked.append(prompt) or '{"stanje": "ok", "popravka": "nema"}')
    found_on_autoscout24(monkeypatch, foreign(text="Top Zustand", detailed=False),
                         foreign(text="Top Zustand", detailed=False), foreign(id="as24:2", price=9000))
    run(conn)
    assert read == ["as24:1"] and len(asked) == 1
    assert conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 2
    assert "2 cars saved, 1 pass" in caplog.text


def test_same_ad_on_two_sites_is_kept_per_site(fetched, monkeypatch):
    monkeypatch.setattr(scan.autoscout24, "search", lambda *a: [foreign()])
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [foreign(id="willhaben:1", source="willhaben")])
    with scan.site_threads() as threads:
        found = scan.search_all(threads, [GOLF], [], set())
    assert [car["id"] for car, model in found] == ["as24:1", "willhaben:1"]


def test_a_site_that_lists_nothing_for_every_model_is_reported(fetched, monkeypatch):
    # 24.11.2026: autoscout24.de answered every search with an empty page and the run still said "ok"
    monkeypatch.setattr(scan.autoscout24, "search", lambda *a: [])
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [foreign(id="willhaben:1", source="willhaben")])
    monkeypatch.setattr(scan.mobilede, "search", lambda *a: [])
    errors = []
    with scan.site_threads() as threads:
        scan.search_all(threads, [GOLF, PASSAT] * 3, errors, set())   # 6 searches per site
    assert errors == ["autoscout24: 0 oglasa za sve modele", "mobilede: 0 oglasa za sve modele"]


def test_a_scan_of_few_models_that_finds_nothing_stays_quiet(fetched, monkeypatch):
    for source in scan.SOURCES.values():
        monkeypatch.setattr(source, "search", lambda *a: [])
    errors = []
    with scan.site_threads() as threads:
        scan.search_all(threads, [GOLF, PASSAT], errors, set())
    assert errors == []


def test_a_site_with_cars_for_one_model_is_not_reported(fetched, monkeypatch):
    monkeypatch.setattr(scan.autoscout24, "search", lambda path, *a: [foreign()] if path == GOLF["as24"] else [])
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [foreign(id="willhaben:1", source="willhaben")])
    monkeypatch.setattr(scan.mobilede, "search", lambda *a: [foreign(id="mobilede:1", source="mobilede")])
    errors = []
    with scan.site_threads() as threads:
        scan.search_all(threads, [GOLF, PASSAT] * 3, errors, set())
    assert errors == []


def test_a_failed_site_is_not_also_reported_as_empty(fetched, monkeypatch):
    def broken(*a):
        raise RuntimeError("timeout")
    monkeypatch.setattr(scan.autoscout24, "search", broken)
    monkeypatch.setattr(scan.willhaben, "search", lambda *a: [foreign(id="willhaben:1", source="willhaben")])
    monkeypatch.setattr(scan.mobilede, "search", lambda *a: [foreign(id="mobilede:1", source="mobilede")])
    errors = []
    with scan.site_threads() as threads:
        scan.search_all(threads, [GOLF], errors, set())
    assert len(errors) == 1 and errors[0].startswith("autoscout24 volkswagen/golf: RuntimeError")


def test_overrides_reach_the_final_valuation(conn, fetched, monkeypatch):
    found_on_autoscout24(monkeypatch, foreign())
    run(conn, overrides={"as24:1": {"transport": 0, "repair": 300, "origin_proof": None}})
    cost = saved_result(conn)["cost"]
    assert (cost["transport"], cost["repair"]) == (0, 300)


def test_no_listings_is_a_quiet_run(conn, fetched):
    assert run(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 0


def test_one_timing_line_per_phase(conn, fetched, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="carfinder")
    found_on_autoscout24(monkeypatch, foreign())
    run(conn)
    phases = [record.getMessage() for record in caplog.records if record.getMessage().startswith("phase ")]
    assert [line[:7] for line in phases] == ["phase a", "phase b", "phase c", "phase d", "phase e"]
    assert "1 cars saved, 1 pass" in phases[4]


# --- main: lock, old cache rows, the run log ----------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """main() works in a temporary data folder."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(scan, "LOCK", tmp_path / "scan.lock")
    return db.connect()


def test_main_scans_one_model_drops_old_cache_rows_and_logs_the_run(home, fetched):
    db.store_pa(home, '[2, "Volkswagen", ["Golf 7"], 2014, 2016, "diesel", 1598, 81]', pa_cars(), "Golf 7")
    # a snapshot parsed before "4 Motion" and "4 x 4" in a title were read as four-wheel drive
    db.store_pa(home, '[3, "Volkswagen", "Tiguan", 2009, 2016, "diesel"]', pa_cars(), "Tiguan")
    # a snapshot parsed before the new drive badges were checked at word boundaries
    db.store_pa(home, '[5, "Volkswagen", "Tiguan", 2009, 2016, "diesel"]', pa_cars(), "Tiguan")
    scan.main("Passat")
    assert [snapshot[1] for snapshot in fetched] == ["Passat B6", "Passat B7", "Passat B8"]
    assert scan.PA_CACHE_VERSION == 7
    assert [row["key"][:2] for row in home.execute("SELECT key FROM pa_cache")] == ["[7", "[7", "[7"]
    assert [(run["status"], run["note"]) for run in db.last_runs(home)] == [("ok", "")]
    lock = scan.acquire_lock()   # released at the end
    assert lock is not None
    lock.close()


def test_main_logs_a_partial_run_with_its_errors(home, fetched, monkeypatch):
    def broken(*a):
        raise ValueError("odd page")
    monkeypatch.setattr(scan.willhaben, "search", broken)
    scan.main("golf")
    assert [(run["status"], run["note"]) for run in db.last_runs(home)] == [
        ("partial", "willhaben volkswagen/golf: ValueError('odd page')")]


def test_main_logs_the_run_even_when_the_scan_itself_breaks(home, fetched, monkeypatch):
    def broken(*a):
        raise RuntimeError("bug")
    monkeypatch.setattr(scan, "run", broken)
    scan.main()
    assert [(run["status"], run["note"]) for run in db.last_runs(home)] == [("partial", "scan: RuntimeError('bug')")]


def test_main_does_nothing_while_another_scan_holds_the_lock(home, fetched):
    lock = scan.acquire_lock()
    scan.main()
    lock.close()
    assert fetched == [] and db.last_runs(home) == []


def test_run_count_counts_every_logged_run_partial_ones_too(conn):
    assert db.run_count(conn) == 0
    db.log_run(conn, 1.0, "ok", "")
    db.log_run(conn, 2.0, "partial", "willhaben blocked")
    assert db.run_count(conn) == 2
