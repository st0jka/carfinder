"""One full scan: foreign listings -> Serbian comparables -> profit. Run: python -m carfinder.scan

Every site has its own worker thread, so the sites are read side by side while each one still gets one request
at a time with its usual pause. The threads only fetch and parse; the main thread does every database write
through the one connection (mobile.de's weekly bookkeeping keeps its own connection inside its own thread).
"""
import json
import logging
import re
import msvcrt
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from carfinder import db, describe, market, models, net, polovni, transport, valuation
from carfinder.sources import autoscout24, mobilede, willhaben

SOURCES = {"autoscout24": autoscout24, "willhaben": willhaben, "mobilede": mobilede}

YEAR_FROM = 2010
MIN_PRICE_EUR = 1500       # cheaper ads are placeholders ("5 EUR", "price on request") or scrap
MAX_PRICE_EUR = 15000
MAX_CC = models.MAX_CC
MAX_KM = 325_000   # Bane 24.11.2026: "trazimo kola do 325.000"
# Bane 24.11.2026: "rekao sam ne iz italije"; his search is Germany, Austria and Switzerland.
COUNTRIES = {"DE", "AT", "CH"}
# Bane 24.11.2026: an ex-taxi B-Klasse was on top; worn taxis are not what he buys.
TAXI = re.compile(r"taxi", re.I)
PA_CACHE_S = 23 * 3600     # under a day: a daily model's snapshot is about 24 h old at its next run
PA_STALE_S = 72 * 3600     # when a refresh fails, the previous snapshot still prices cars up to this age
PA_CACHE_VERSION = 7       # bump when the PA query or parsing changes, so old cache rows are not reused
UPFRONT_FUEL = "diesel"    # nearly every car we scan, plus petrol for "petrol" generations; other fuels are fetched
                           # when a foreign car needs them
HAIKU_WORKERS = 4
DETAIL_MARGIN_EUR = 1000   # fetch the detail page when the rough profit is within this of the target
EMPTY_SITE_MODELS = 5      # a site with no car for this many models in one run has changed, not run dry
LOCK = Path(db.DB_PATH).parent / "scan.lock"
SCAN_EVERY_H = 3           # Task Scheduler "carFinder scan" starts a run every 3 hours
DAILY_GROUPS = 24 // SCAN_EVERY_H

log = logging.getLogger("carfinder")


class Skipped(net.Blocked):
    """A queued job that made no request because its site blocked earlier in this run."""


@contextmanager
def site_threads():
    """One worker thread per site: a site never gets two requests at once and net.get keeps its pause."""
    threads = {site: ThreadPoolExecutor(max_workers=1, thread_name_prefix=site) for site in ("polovni", *SOURCES)}
    try:
        yield threads
    finally:
        for thread in threads.values():
            thread.shutdown(cancel_futures=True)


def on_site(site, blocked_sites, fetch, *args):
    """Runs in the site's thread. The block is recorded here, before the thread takes its next job."""
    if site in blocked_sites:
        raise Skipped(f"{site} is blocked in this run")
    try:
        return fetch(*args)
    except net.Blocked:
        blocked_sites.add(site)
        raise


def submit(threads, site, blocked_sites, fetch, *args):
    return threads[site].submit(on_site, site, blocked_sites, fetch, *args)


def note_failure(errors, site, what, error):
    """One entry in the run's error list per failed job; a skipped job's block is already in the list."""
    if isinstance(error, Skipped):
        return
    if isinstance(error, net.Blocked):
        errors.append(f"{site}: {error}")
        log.warning("blocked for the rest of the run: %s %s", site, error)
        return
    errors.append(f"{site} {what}: {error!r}")
    log.error("failed: %s %s", site, what, exc_info=error)


def snapshot_of(model, generation, fuel):
    """What one PA snapshot covers: (make, PA model, first year, last year, fuel)."""
    first, last = generation["years"]
    # one year under YEAR_FROM, because a YEAR_FROM car is compared with cars a year older (valuation.year_window)
    return model["make"], generation["pa_model"], max(first, YEAR_FROM - 1), generation.get("named_until", last), fuel


def snapshot_for(car, model):
    """The PA snapshot this car is priced against, or None for a car that is not priced at all."""
    try:
        if not usable(car, model):
            return None
        generation = valuation.generation_of(car, model)
    except Exception:   # an odd listing: estimate() logs it and the car is hidden
        return None
    if generation is None:
        return None
    return snapshot_of(model, generation, car["fuel"])


def cache_key(snapshot):
    return json.dumps([PA_CACHE_VERSION, *snapshot])


def request_snapshots(conn, threads, wanted, snapshots, blocked_sites):
    """Snapshots under 24 h old come from the cache; the others are queued on the PA thread."""
    jobs = []
    for snapshot in wanted:
        cars = db.cached_pa(conn, cache_key(snapshot), PA_CACHE_S)
        if cars is None:
            jobs.append((snapshot, submit(threads, "polovni", blocked_sites, polovni.fetch_snapshot, *snapshot)))
        else:
            snapshots[snapshot] = cars
    return jobs


def collect_snapshots(conn, jobs, snapshots, errors):
    """Stores every fetched snapshot. A failed one falls back on the previous snapshot while that is under 72 h
    old; without it the generation is not priced in this run."""
    for snapshot, job in jobs:
        _, pa_model, _, _, fuel = snapshot
        try:
            cars = job.result()
        except Exception as error:
            note_failure(errors, "polovni", f"{pa_model} {fuel}", error)
            cars = db.cached_pa(conn, cache_key(snapshot), PA_STALE_S)
            if cars is None:
                log.warning("no Serbian prices in this run: %s %s", pa_model, fuel)
                continue
            log.warning("using the previous snapshot: %s %s", pa_model, fuel)
        else:
            db.store_pa(conn, cache_key(snapshot), cars, pa_model)
        snapshots[snapshot] = cars


def comparables_for(snapshots, car, model):
    """Clean PA cars of the exact variant; empty when the generation cannot be told apart."""
    generation = valuation.generation_of(car, model)
    if generation is None:
        return []
    pa_names = models.pa_names(generation["pa_model"])
    body = generation.get("body") or model.get("body")
    if car.get("body") is None and body:
        car = dict(car, body=body)   # a list page gives no body; an MPV's detail page says van
    year_from, year_to = valuation.year_window(model, car["year"], generation)
    snapshot = snapshots.get(snapshot_of(model, generation, car["fuel"]), [])
    cars = polovni.variant_ads(snapshot, year_from, year_to, car["cc"], car["kw"])
    matched = []
    for comp in cars:
        if comp.get("model") not in pa_names or not polovni.is_clean(comp) or not valuation.is_match(car, comp):
            continue
        named = models.named_generation(model, comp.get("title"))
        if named != generation["name"] and (named or valuation.mixed_year(model, comp["year"])):
            continue
        matched.append(comp)
    return matched


def settings_for(car, overrides):
    override = overrides.get(car["id"]) or {}
    settings = {}
    if override.get("transport") is not None:
        settings["transport_override"] = override["transport"]
    if override.get("repair") is not None:
        settings["repair"] = override["repair"]
    if override.get("origin_proof") is not None:
        settings["origin_proof"] = bool(override["origin_proof"])
    if override.get("carina") is not None:
        settings["import_total"] = override["carina"]
    if override.get("buy_discount") is not None:
        settings["buy_discount"] = override["buy_discount"]
    return settings


def usable(car, model=None):
    """A car we can price and would buy. Without its model (one no longer scanned) plain petrol is never usable."""
    if not car["year"] or not car["kw"] or car["fuel"] == "other" or autoscout24.is_wreck(car):
        return False
    if car["country"] not in COUNTRIES or TAXI.search(f"{car['title']} {car['text']}"):
        return False
    if market.avoided(car):   # Ford automatic and the other variants Serbian buyers do not take
        return False
    cc = car.get("cc") or mobilede.engine_cc({}, f"{car['title']} {car['text']}")
    if not valuation.fuel_sells(car, model) or (cc or 0) > MAX_CC or (car.get("km") or 0) > MAX_KM:
        return False
    if (car["price"] or 0) < MIN_PRICE_EUR:
        return False
    km = transport.road_km(car["country"], car.get("zip"))
    return km is not None and km <= transport.MAX_DISTANCE_KM


def search_years(model):
    """First and last registration year to search: a car outside the model's generations is never priced."""
    first = min(generation["years"][0] for generation in model["generations"])
    last = max(generation["years"][1] for generation in model["generations"])
    return max(YEAR_FROM, first), min(date.today().year, last)


def search_all(threads, scan_models, errors, blocked_sites):
    """Every source searches every model in its own thread. Returns [(car, model)]."""
    jobs = []
    for model in scan_models:
        year_from, year_to = search_years(model)
        for name, source in SOURCES.items():
            job = submit(threads, name, blocked_sites, source.search,
                         model["as24"], year_from, year_to, MIN_PRICE_EUR, MAX_PRICE_EUR)
            jobs.append((name, model, job))
    found = []
    seen = set()
    answered = Counter()   # searches per site that came back
    listed = set()         # sites with at least one car
    for name, model, job in jobs:
        try:
            cars = job.result()
        except Exception as error:   # one source failing must not hide the other
            note_failure(errors, name, model["as24"], error)
            cars = getattr(error, "cars", None)   # the years a search read before it failed or was blocked
            if not cars:
                continue
        log.info("%s %s: %d listings", name, model["as24"], len(cars))
        answered[name] += 1
        if cars:
            listed.add(name)
        for car in cars:
            if car["id"] in seen:
                continue   # an ad that moved to the next page while its search was read
            seen.add(car["id"])
            found.append((car, model))
    for name in sorted(answered):
        # a changed site answers every search with an empty page; the run must not look "ok". A scan of one or
        # two models can honestly find nothing.
        if name not in listed and answered[name] >= EMPTY_SITE_MODELS:
            errors.append(f"{name}: 0 oglasa za sve modele")
    return found


def speed_ads(snapshots, car, model):
    """The PA ads a car's sell speed is read from: every clean ad of its generation, fuel and years with the same
    gearbox and body group. The engine is left out so a variant has enough ads; the gearbox stays in, because a
    Kuga automatic and a Kuga manual sell differently."""
    generation = valuation.generation_of(car, model)
    if generation is None:
        return []
    body = generation.get("body") or model.get("body")
    if car.get("body") is None and body:
        car = dict(car, body=body)
    year_from, year_to = valuation.year_window(model, car["year"], generation)
    pa_names = models.pa_names(generation["pa_model"])
    ads = []
    for ad in snapshots.get(snapshot_of(model, generation, car["fuel"]), []):
        if ad.get("model") not in pa_names or not polovni.is_clean(ad):
            continue
        if not year_from <= (ad.get("year") or 0) <= year_to or ad.get("gearbox") != car.get("gearbox"):
            continue
        if valuation.body_group(ad.get("body")) == valuation.body_group(car.get("body")):
            ads.append(ad)
    return ads


def estimate(snapshots, car, model, overrides, reference=()):
    """Result for one foreign car, or None when it is not a deal we can price (it is then hidden).

    reference is market.band_reference of this scan; without it the car gets no sell speed."""
    try:
        if not usable(car, model):
            return None
        result = valuation.evaluate(car, comparables_for(snapshots, car, model), settings_for(car, overrides), model)
        if result:
            result["serbia"]["speed"] = market.speed(speed_ads(snapshots, car, model), reference)
        return result
    except Exception:   # one odd listing must not stop the others
        log.exception("valuation failed: %s", car.get("url"))
        return None


def fetch_details(threads, cars, blocked_sites, errors):
    """Detail pages, each site in its own thread. Returns the cars that are read and valued again."""
    jobs = []
    for car, model in cars:
        job = submit(threads, car["source"], blocked_sites, SOURCES[car["source"]].add_details, car)
        jobs.append((car, model, job))
    checked = []
    for car, model, job in jobs:
        try:
            job.result()
        except Skipped:
            continue   # the site blocked on an earlier car: the list-stage estimate stays
        except net.Blocked as blocked:
            note_failure(errors, car["source"], "details", blocked)
        except Exception as error:   # a removed ad (404) or odd page: keep the list-stage estimate, flagged as unchecked
            log.warning("details failed: %s: %r", car["url"], error)
        checked.append((car, model))
    return checked


def known_reading(conn, car):
    """Haiku's reading from an earlier scan when the ad has not changed since, or None."""
    saved = db.saved_reading(conn, car["id"])
    if saved and saved.get("key") == describe.text_key(car):
        return saved
    return None


def read_descriptions(conn, cars):
    """Haiku reads the seller's text once per version of the ad; a named fault counts as damage.

    Returns how many ads were sent to Haiku."""
    unread = []
    for car in cars:
        saved = known_reading(conn, car)
        if saved:
            car["ai"] = saved
        else:
            unread.append(car)
    with ThreadPoolExecutor(max_workers=HAIKU_WORKERS) as pool:
        jobs = [(car, pool.submit(describe.read, car)) for car in unread]
    for car, job in jobs:
        try:
            car["ai"] = job.result()
        except Exception:   # an unread description must not stop the car
            log.exception("description not read: %s", car.get("url"))
            car["ai"] = None
    for car in cars:
        if car["ai"] and car["ai"]["state"] == "kvar":
            car["damaged"] = True   # adds the repair estimate and the warning on the card
    return len(unread)


def log_phase(name, started, note):
    log.info("phase %s: %.1f s, %s", name, time.time() - started, note)


def value_and_save(conn, threads, found, snapshots, overrides, blocked_sites, errors, all_models=True):
    """Phases b to e for the found cars. Returns {car id: result}; a result of None hides the car.

    A car whose PA snapshot is missing is left out and not saved, so the result of its last priced scan stays.
    A scan of some models only gives no sell speed: their price bands would hold no other model's ads."""
    started = time.time()
    market.add_ages(snapshots)
    reference = market.band_reference(snapshots) if all_models else ()
    results = {}       # list-stage result first, replaced by the final one for cars near the target
    near_target = []
    for car, model in found:
        snapshot = snapshot_for(car, model)
        if snapshot and snapshot not in snapshots:
            continue
        # mobile.de brings the whole ad in the search, so its earlier reading still counts (and is saved again)
        # when this scan skips the car's details: a known wreck must not come back as a deal.
        reading = known_reading(conn, car)
        if reading:
            car["ai"] = reading
            if reading["state"] == "kvar":
                car["damaged"] = True
        if reading and reading["state"] == "les":
            results[car["id"]] = None
            continue
        result = estimate(snapshots, car, model, overrides, reference)
        results[car["id"]] = result
        if result and result["profit"] >= result["target"] - DETAIL_MARGIN_EUR and car["source"] not in blocked_sites:
            near_target.append((car, model))
    log_phase("b list valuation", started, f"{len(results)} cars, {len(near_target)} near the target")

    started = time.time()
    checked = fetch_details(threads, near_target, blocked_sites, errors)
    log_phase("c detail pages", started, f"{len(checked)} of {len(near_target)} cars")

    started = time.time()
    readable = []
    for car, model in checked:
        try:
            still_usable = usable(car, model)   # details can reveal wreck words or an engine above 2.0
        except Exception:   # an odd detail page hides this car; it must not lose every save of the run
            log.exception("odd details: %s", car.get("url"))
            still_usable = False
        if still_usable:
            readable.append((car, model))
        else:
            results[car["id"]] = None
    sent = read_descriptions(conn, [car for car, _ in readable])
    log_phase("d descriptions", started, f"{sent} read by Haiku, {len(readable) - sent} known from before")

    started = time.time()
    for car, model in readable:
        if car["ai"] and car["ai"]["state"] == "les":
            results[car["id"]] = None
        else:
            results[car["id"]] = estimate(snapshots, car, model, overrides, reference)
    saved, passed = 0, 0
    for car, model in found:
        if car["id"] not in results:
            continue
        result = results[car["id"]]
        db.save_car(conn, car, result, model["as24"])   # saving None hides an ad that stopped being a deal
        saved += 1
        if result and result["passes"]:
            passed += 1
    log_phase("e final valuation and save", started, f"{saved} cars saved, {passed} pass")
    return results


def run(conn, scan_models, overrides, errors, blocked_sites, all_models=True):
    """The whole scan. Phase a runs the sites side by side; b to e are in value_and_save."""
    with site_threads() as threads:
        started = time.time()
        snapshots = {}
        upfront = []
        for model in scan_models:
            for generation in model["generations"]:
                upfront.append(snapshot_of(model, generation, UPFRONT_FUEL))
                if generation.get("petrol"):
                    upfront.append(snapshot_of(model, generation, "petrol"))
        jobs = request_snapshots(conn, threads, upfront, snapshots, blocked_sites)
        found = search_all(threads, scan_models, errors, blocked_sites)
        other_fuels = {snapshot_for(car, model) for car, model in found} - {None} - set(upfront)
        jobs += request_snapshots(conn, threads, sorted(other_fuels), snapshots, blocked_sites)
        collect_snapshots(conn, jobs, snapshots, errors)
        log_phase("a searches and PA snapshots", started,
                  f"{len(found)} listings, {len(jobs)} snapshots requested from PA, {len(snapshots)} ready")
        value_and_save(conn, threads, found, snapshots, overrides, blocked_sites, errors, all_models)


def acquire_lock():
    """Windows file lock held for the whole scan; the OS releases it when the process ends."""
    handle = open(LOCK, "a+")
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def models_of_run(hour):
    """The core models every run, plus the daily models' group of this hour, so each daily model is read once a day.
    shortcut: a run that does not start (PC off, the last run still going) skips its group until the next day."""
    group = hour // SCAN_EVERY_H
    return models.CORE_MODELS + models.DAILY_MODELS[group::DAILY_GROUPS]


def main(only=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(Path(db.DB_PATH).parent / "scan.log", encoding="utf-8")])
    Path(db.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock()
    if lock is None:
        log.info("another scan is running, skipping")
        return
    conn = db.connect()
    db.drop_old_pa_cache(conn, PA_CACHE_VERSION)
    started = time.time()
    errors, blocked_sites = [], set()
    if only:
        scan_models = [model for model in models.MODELS if only.lower() in model["as24"]]
    else:
        scan_models = models_of_run(datetime.now().hour)
    try:
        all_models = not only
        run(conn, scan_models, db.overrides(conn), errors, blocked_sites, all_models)
    except Exception as error:   # the run is still logged, with what stopped it
        errors.append(f"scan: {error!r}")
        log.exception("scan failed")
    log.info("scan done in %.0f s", time.time() - started)
    db.log_run(conn, started, "ok" if not errors else "partial", "; ".join(errors)[:2000])
    lock.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
