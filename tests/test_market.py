"""Serbian market knowledge: the reputation table, PA ad ages and the sell speed of a variant."""
from datetime import datetime, timedelta

import pytest

from carfinder import db, market, models, scan, valuation
from tests.test_scan_db import foreign, pa_car
from tests.test_scan_phases import GOLF, GOLF7_DIESEL, conn, fetched   # noqa: F401 (fixtures)

NOW = datetime(2026, 11, 25, 12, 0)
B_KLASSE = next(model for model in models.MODELS if model["as24"] == "mercedes-benz/b-klasse")


def day(days_ago):
    """PA's update time of an ad last touched this many days before NOW."""
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


# --- reputation -------------------------------------------------------------------------

@pytest.mark.parametrize("make,model,gearbox,avoided", [
    ("Ford", "Kuga", "automatic", True),
    ("Ford", "B-Max", "automatic", True),
    ("Ford", "Kuga", "manual", False),
    ("Ford", "Kuga", None, False),           # gearbox unknown on a list page: nothing says it is an automatic
    ("Volkswagen", "Golf", "automatic", False),
    (None, "Kuga", "automatic", False),      # no make: an unknown never drops a car
])
def test_only_a_ford_automatic_is_dropped(make, model, gearbox, avoided):
    assert market.avoided({"make": make, "model": model, "gearbox": gearbox, "fuel": "diesel"}) is avoided


@pytest.mark.parametrize("model", ["B 180", "B 200", "B-klasse"])   # mobile.de, AutoScout24 and willhaben names
def test_b_klasse_automatic_stays_without_a_note_because_the_sell_speed_measures_it(model):
    car = {"make": "Mercedes-Benz", "model": model, "gearbox": "automatic", "fuel": "diesel"}
    assert market.notes(car) == []
    assert not market.avoided(car)


@pytest.mark.parametrize("car", [
    {"make": "Mercedes-Benz", "model": "B 180", "gearbox": "manual", "fuel": "diesel"},
    {"make": "Mercedes-Benz", "model": "B 180", "gearbox": None, "fuel": "diesel"},
    {"make": "Mercedes-Benz", "model": "A 180", "gearbox": "automatic", "fuel": "diesel"},
    {"make": "Opel", "model": "Insignia", "gearbox": "manual", "fuel": "diesel"},
    {"make": "Opel", "model": "Insignia", "gearbox": "automatic", "fuel": "diesel"},   # speed and price show it
    {"make": "Volkswagen", "model": "Passat", "gearbox": "automatic", "fuel": "diesel"},
    {"make": None, "model": None, "gearbox": None, "fuel": None},
])
def test_variants_buyers_do_not_hold_anything_against_get_no_note(car):
    assert market.notes(car) == []


@pytest.mark.parametrize("gearbox", ["manual", "automatic", None])
def test_factory_methane_is_dropped_with_any_gearbox(gearbox):   # Novky 25.11.2026: "Vise ne"
    passat = {"make": "Volkswagen", "model": "Passat", "gearbox": gearbox, "fuel": "petrol_cng"}
    assert market.avoided(passat)
    assert not market.avoided(dict(passat, fuel="petrol"))


@pytest.mark.parametrize("make,gearbox,avoided", [
    ("Opel", "automatic", True), ("Opel", "manual", False),
    ("Renault", "automatic", True), ("Renault", "manual", False),
    ("Hyundai", "automatic", True), ("Hyundai", "manual", False),
    ("Kia", "automatic", True), ("Kia", "manual", False),
    ("Mercedes-Benz", "automatic", False),   # Novky 25.11: A and B DCT "Ok"
    ("Opel", None, False),                   # gearbox unknown on a list page: never dropped
])
def test_novkys_automatics_buyers_avoid(make, gearbox, avoided):   # Novky 25.11.2026, question by question
    assert market.avoided({"make": make, "model": "x", "gearbox": gearbox, "fuel": "diesel"}) is avoided


@pytest.mark.parametrize("make,words,avoided", [
    ("Peugeot", "3008 1.6 HDi ETG6", True),
    ("Peugeot", "3008 HDi FAP 110 EGS", True),
    ("Peugeot", "308 1.6 e-HDi BMP6", True),
    ("Peugeot", "2008 PureTech 2-Tronic", True),
    ("Peugeot", "3008 automatisiertes Schaltgetriebe", True),
    ("Peugeot", "3008 Halbautomatik", True),
    ("Citroen", "C4 1.6 HDi EGS6", True),
    ("Peugeot", "3008 1.2 PureTech EAT6", False),   # torque converter: "samo sa automatskim menjacem"
    ("Peugeot", "3008 2.0 BlueHDi EAT8", False),
    ("Peugeot", "3008 2.0 HDi Automatik", False),
    ("Peugeot", "Allegro 3008 Kette", False),       # no robot word inside another word
])
def test_peugeot_and_citroen_robot_gearbox_is_dropped_a_converter_stays(make, words, avoided):
    car = {"make": make, "model": "x", "gearbox": "automatic", "fuel": "diesel", "title": words, "text": ""}
    assert market.avoided(car) is avoided
    assert not market.avoided(dict(car, gearbox="manual"))   # a robot word on a manual car drops nothing


def test_robot_words_are_read_from_the_description_too():
    car = {"make": "Peugeot", "model": "3008", "gearbox": "automatic", "fuel": "diesel", "title": "Peugeot 3008",
           "text": "Getriebe: ETG6, Klima"}
    assert market.avoided(car)
    assert not market.avoided(dict(car, text=None))   # no words at all: kept


def test_two_notes_of_one_car_are_both_kept(monkeypatch):
    monkeypatch.setattr(market, "REPUTATION", [{"fuel": "petrol_cng", "effect": market.NOTE, "text": "jedan"},
                                               {"make": "opel", "effect": market.NOTE, "text": "drugi"}])
    car = {"make": "Opel", "model": "Zafira", "gearbox": "automatic", "fuel": "petrol_cng"}
    assert market.notes(car) == ["jedan", "drugi"]


def test_reputation_note_is_a_warning_on_the_card(monkeypatch):
    monkeypatch.setattr(market, "REPUTATION", [{"fuel": "diesel", "effect": market.NOTE, "text": "napomena kupaca"}])
    assert "napomena kupaca" in valuation.flags_of(foreign(fuel="diesel"))
    assert "napomena kupaca" not in valuation.flags_of(foreign(fuel="petrol"))


def test_every_avoid_row_names_its_case_and_every_note_has_its_text():
    for row in market.REPUTATION:
        assert row["effect"] in (market.AVOID, market.NOTE)
        assert row["effect"] == market.AVOID or row["text"]


# --- ad ages from PA ids ---------------------------------------------------------------------

def test_an_ad_is_as_old_as_the_earliest_update_of_any_newer_ad():
    old = {"id": "30000000", "updated": day(5)}      # touched 5 days ago, but a newer ad is 40 days old
    newer = {"id": "30000500", "updated": day(40)}
    newest = {"id": "31000000", "updated": day(2)}
    market.add_ages({"a": [old, newest], "b": [newer]}, NOW)
    assert (old["age_days"], newer["age_days"], newest["age_days"]) == (40, 40, 2)


def test_ids_are_compared_as_numbers():
    short = {"id": "9999999", "updated": day(1)}     # older ad: as text it would sort above "30000000"
    long = {"id": "30000000", "updated": day(30)}
    market.add_ages({"a": [short, long]}, NOW)
    assert (short["age_days"], long["age_days"]) == (30, 30)


@pytest.mark.parametrize("updated", ["", None, "yesterday"])
def test_ad_without_a_usable_update_time_still_gets_the_age_of_newer_ads(updated):
    odd = {"id": "100", "updated": updated}
    newer = {"id": "200", "updated": day(12)}
    market.add_ages({"a": [odd, newer]}, NOW)
    assert odd["age_days"] == 12


def test_newest_ad_without_an_update_time_is_counted_as_new_today():
    lone = {"id": "100", "updated": ""}
    market.add_ages({"a": [lone]}, NOW)
    assert lone["age_days"] == 0


def test_ad_with_an_id_that_is_not_a_number_gets_no_age():
    odd = {"id": "fwd1", "updated": day(3)}
    market.add_ages({"a": [odd]}, NOW)
    assert "age_days" not in odd


def test_no_snapshots_is_fine():
    market.add_ages({}, NOW)
    assert market.band_reference({}) == []


def test_band_reference_has_one_entry_per_clean_aged_ad_cheapest_first():
    aged = dict(pa_car("1", 9000), age_days=30)
    again = dict(aged)                                            # the same ad in a second snapshot
    cheaper = dict(pa_car("2", 7000), age_days=10)
    wreck = dict(pa_car("3", 5000, title="Golf 7 za delove"), age_days=5)
    unknown = pa_car("4", 8000)                                   # no age
    assert market.band_reference({"a": [aged, wreck, unknown], "b": [again, cheaper]}) == [(7000, 10, "2"), (9000, 30, "1")]


# --- sell speed -------------------------------------------------------------------------------

def ads_of(count, age, price=9000, cut=False):
    return [{"id": f"own{i}", "price": price, "age_days": age, "cut": cut} for i in range(count)]


def reference_of(count, age, price=9000):
    """Other ads of the scan: their ids are never the variant's own."""
    return [(price, age, f"{price}-{age}-{i}") for i in range(count)]


def test_too_few_aged_ads_of_the_variant_give_no_speed():
    ads = ads_of(market.MIN_SPEED_ADS - 1, 60) + [{"price": 9000}]   # one more ad, but without an age
    assert market.speed(ads, reference_of(100, 30)) is None


def test_too_few_ads_in_the_price_band_give_no_speed():
    reference = reference_of(market.MIN_SPEED_ADS - 1, 30) + reference_of(100, 30, price=20000)   # cheapest first
    assert market.speed(ads_of(20, 60), reference) is None


def test_no_reference_gives_no_speed():
    assert market.speed(ads_of(20, 60), ()) is None


@pytest.mark.parametrize("age,label", [(45, "sporo"), (44, "normalno"), (24, "brzo"), (25, "normalno"), (30, "normalno")])
def test_label_is_the_variants_age_against_the_usual_age_of_its_price_band(age, label):
    speed = market.speed(ads_of(20, age), reference_of(100, 30))   # slow from 1.5x (45 d), fast up to 0.8x (24 d)
    assert speed["label"] == label
    assert (speed["age_days"], speed["usual_days"], speed["n"]) == (age, 30, 20)


def test_ads_outside_the_price_band_do_not_count_as_usual():
    reference = reference_of(50, 30) + reference_of(500, 200, price=3000) + reference_of(500, 5, price=20000)
    assert market.speed(ads_of(20, 30), sorted(reference))["usual_days"] == 30


def test_band_edges_are_25_percent_of_the_variants_median_ask_both_ways():
    reference = reference_of(10, 100, price=6750) + reference_of(10, 100, price=11250)   # exactly 9000 -/+ 25%
    reference += reference_of(50, 1, price=6749) + reference_of(50, 1, price=11251)      # just outside
    assert market.speed(ads_of(20, 100), sorted(reference))["usual_days"] == 100


def test_the_variants_own_ads_are_not_counted_as_usual():
    ads = ads_of(20, 60)
    reference = sorted([(ad["price"], ad["age_days"], ad["id"]) for ad in ads] + reference_of(20, 30))
    speed = market.speed(ads, reference)
    assert (speed["usual_days"], speed["label"]) == (30, "sporo")


def test_a_band_of_only_the_variants_own_ads_gives_no_speed():
    ads = ads_of(20, 60)
    assert market.speed(ads, sorted((ad["price"], ad["age_days"], ad["id"]) for ad in ads)) is None


def test_usual_age_of_zero_days_does_not_divide_by_zero():
    assert market.speed(ads_of(20, 3), reference_of(100, 0))["label"] == "sporo"


def test_share_of_cut_ads_is_kept_for_the_card():
    ads = ads_of(15, 30) + ads_of(5, 30, cut=True)
    assert market.speed(ads, reference_of(100, 30))["cut_share"] == 0.25


# --- which PA ads a car's speed is read from ------------------------------------------------------

def golf_ad(id_, **overrides):
    return pa_car(id_, 9000, **overrides)


def test_speed_ads_are_the_generation_with_the_same_gearbox_body_and_years_any_engine():
    car = foreign(year=2015, gearbox="manual", body="hatchback")
    keep = [golf_ad("same"), golf_ad("other engine", cc=1968, kw=110), golf_ad("year after", year=2016)]
    drop = [golf_ad("automatic", gearbox="automatic"), golf_ad("estate", body="estate"),
            golf_ad("too old", year=2013), golf_ad("other model", model="Golf 6"),
            golf_ad("wreck", title="Golf 7 za delove")]
    ads = scan.speed_ads({GOLF7_DIESEL: keep + drop}, car, GOLF)
    assert [ad["id"] for ad in ads] == ["same", "other engine", "year after"]


def test_speed_ads_of_a_car_without_a_generation_are_none():
    assert scan.speed_ads({GOLF7_DIESEL: [golf_ad("1")]}, foreign(year=2005), GOLF) == []


def test_mpv_without_a_body_on_its_list_page_is_read_as_a_van():
    car = foreign(make="Mercedes-Benz", model="B 180", title="B 180 CDI", year=2015, cc=1461, kw=80, body=None)
    snapshot = scan.snapshot_of(B_KLASSE, models.generations_for(B_KLASSE, 2015)[0], "diesel")
    van = pa_car("van", 9000, model="B 180", title="B 180", body="van", cc=1461, kw=80)
    hatch = dict(van, id="hatch", body="hatchback")
    assert [ad["id"] for ad in scan.speed_ads({snapshot: [van, hatch]}, car, B_KLASSE)] == ["van"]


def slow_and_fast_golfs():
    """20 manual Golf 7 ads listed about 60 days and 20 automatics of the same price listed about 10 days."""
    manuals = [pa_car(str(30000000 + i), 9000 + i * 10, updated=day(60)) for i in range(20)]
    automatics = [pa_car(str(31000000 + i), 9000 + i * 10, gearbox="automatic", updated=day(10)) for i in range(20)]
    return {GOLF7_DIESEL: manuals + automatics}


def test_estimate_without_a_reference_has_no_speed():
    snapshots = slow_and_fast_golfs()
    assert scan.estimate(snapshots, foreign(), GOLF, {})["serbia"]["speed"] is None


def test_estimate_adds_the_speed_of_the_cars_gearbox_against_its_price_band():
    snapshots = slow_and_fast_golfs()
    market.add_ages(snapshots, NOW)
    reference = market.band_reference(snapshots)
    manual = scan.estimate(snapshots, foreign(), GOLF, {}, reference)["serbia"]["speed"]
    automatic = scan.estimate(snapshots, foreign(id="as24:2", gearbox="automatic"), GOLF, {}, reference)
    assert (manual["label"], manual["age_days"], manual["usual_days"]) == ("sporo", 60, 10)
    assert automatic["serbia"]["speed"]["label"] == "brzo"
    assert automatic["serbia"]["first"]["age_days"] == 10   # the anchor ad carries its own age


def test_scan_measures_ages_and_speed_before_it_saves(conn, fetched):   # noqa: F811
    with scan.site_threads() as threads:
        results = scan.value_and_save(conn, threads, [(foreign(), GOLF)], slow_and_fast_golfs(), {}, set(), [])
    speed = results["as24:1"]["serbia"]["speed"]
    assert speed["label"] == "sporo" and speed["n"] == 20
    assert results["as24:1"]["serbia"]["first"]["age_days"] > 40   # ages count from the real clock here


def test_scan_of_some_models_dates_the_ads_but_gives_no_speed(conn, fetched):   # noqa: F811
    with scan.site_threads() as threads:
        results = scan.value_and_save(conn, threads, [(foreign(), GOLF)], slow_and_fast_golfs(), {}, set(), [],
                                      all_models=False)
    assert results["as24:1"]["serbia"]["speed"] is None
    assert results["as24:1"]["serbia"]["first"]["age_days"] > 40


def other_model_ads(days_listed):
    """20 ads of another model in the Golf's price band, as a cached snapshot from an earlier run."""
    return [pa_car(str(32000000 + i), 9000 + i * 10, model="Octavia", updated=day(days_listed)) for i in range(20)]


def manual_golfs():
    """Only the 20 manual Golfs of slow_and_fast_golfs: without other ads their price band is empty."""
    return {GOLF7_DIESEL: [ad for ad in slow_and_fast_golfs()[GOLF7_DIESEL] if ad["gearbox"] == "manual"]}


def scan_speed(conn, snapshots, all_models=True):
    with scan.site_threads() as threads:
        results = scan.value_and_save(conn, threads, [(foreign(), GOLF)], snapshots, {}, set(), [],
                                      all_models=all_models)
    return results["as24:1"]["serbia"]["speed"]


def test_price_band_holds_the_cached_snapshots_of_the_models_outside_this_run(conn, fetched):   # noqa: F811
    """A run reads the core models and one eighth of the daily ones; the band must not change with that eighth."""
    assert scan_speed(conn, manual_golfs()) is None   # the Golf's own ads are left out of its band
    db.store_pa(conn, "octavia", other_model_ads(10), "Octavia")
    speed = scan_speed(conn, manual_golfs())
    assert speed["label"] == "sporo" and speed["usual_days"] >= 10


def test_price_band_leaves_out_a_snapshot_over_72_hours_old(conn, fetched):   # noqa: F811
    db.store_pa(conn, "octavia", other_model_ads(10), "Octavia")
    conn.execute("UPDATE pa_cache SET fetched_at = fetched_at - ?", (scan.PA_STALE_S + 60,))
    assert scan_speed(conn, manual_golfs()) is None


def test_scan_of_some_models_takes_no_band_from_the_cache(conn, fetched):   # noqa: F811
    db.store_pa(conn, "octavia", other_model_ads(10), "Octavia")
    assert scan_speed(conn, manual_golfs(), all_models=False) is None


@pytest.mark.parametrize("only,all_models", [(None, True), ("golf", False)])
def test_main_measures_speed_only_on_a_scan_of_every_model(tmp_path, monkeypatch, only, all_models):
    monkeypatch.setattr(scan.db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(scan, "LOCK", tmp_path / "scan.lock")
    calls = []
    monkeypatch.setattr(scan, "run", lambda *args: calls.append(args[-1]))
    scan.main(only)
    assert calls == [all_models]
