import json
from datetime import date
from pathlib import Path

import pytest

from carfinder import customs, market, models, scan, valuation
from carfinder.sources import autoscout24

GOLF = models.MODELS[0]
PASSAT = models.MODELS[2]
TIGUAN = models.MODELS[3]
OCTAVIA = models.MODELS[4]
DEC_2026 = date(2026, 12, 1)
# The three cars of the importer's review (24.11.2026) with every PA ad the scan held for their variant.
EXPERT_CASES = json.loads((Path(__file__).parent / "fixtures" / "expert_cases.json").read_text(encoding="utf-8"))


def comp(price, **overrides):
    car = {"price": price, "year": 2015, "fuel": "diesel", "gearbox": "manual", "body": "hatchback",
           "doors": 5, "drive": None, "cc": 1598, "kw": 81}
    car.update(overrides)
    return car


def foreign(**overrides):
    car = {"make": "Volkswagen", "model": "Golf", "year": 2015, "fuel": "diesel", "gearbox": "manual",
           "body": None, "doors": None, "drive": None, "cc": 1598, "kw": 81, "price": 4000, "net_price": None,
           "vat_deductible": False, "country": "AT", "zip": "1100", "city": "Wien", "damaged": False,
           "mass": 1350, "market_median": None}
    car.update(overrides)
    return car


def comps(*prices, **overrides):
    return [comp(p, **overrides) for p in prices]


def test_catalogue_bill_uses_the_insignia_generation_mass_when_the_listing_has_none():
    insignia = next(model for model in models.MODELS if model["as24"] == "opel/insignia")
    car = foreign(make="Opel", model="Insignia", year=2015, mass=None)
    assert valuation.costs(car, 4000, {}, insignia, DEC_2026)["import"] == customs.catalogue_bill(
        25000, 2015, None, 1650, 0.0, DEC_2026)
    assert valuation.costs(dict(car, mass=1718), 4000, {}, insignia, DEC_2026)["import"] == customs.catalogue_bill(
        25000, 2015, None, 1718, 0.0, DEC_2026)


def test_q5_duty_uses_the_year_and_still_honors_a_non_eu_vin():
    car = foreign(make="Audi", model="Q5", year=2016)
    model = {"as24": "audi/q5", "generations": []}
    assert valuation.costs(car, 4000, {}, model, DEC_2026)["duty_rate"] == 0
    assert valuation.costs(dict(car, year=2017), 4000, {}, model, DEC_2026)["duty_rate"] == customs.DUTY_STANDARD
    assert valuation.costs(dict(car, text="VIN: 3VWZZZ1KZBM123456"), 4000, {}, model, DEC_2026)[
        "duty_rate"] == customs.DUTY_STANDARD


# --- Serbian sale price ------------------------------------------------------

def test_price_is_the_cheapest_clean_ad():
    sr = valuation.serbian_price(foreign(), comps(3000, 7400, 7600, 7800, 8000, 8500, 9000))
    assert sr["skipped_bait"] == 1         # 3000 is under 75% of the next ad
    assert sr["first"]["price"] == 7400
    assert sr["next"][0]["price"] == 7600
    assert sr["anchor"] == 7400            # the cheapest ad left after the bait
    assert sr["price"] == 6734 and sr["sale_cut"] == 666
    assert sr["within_500"] == 3           # 7400, 7600, 7800
    assert sr["n"] == 6
    assert sr["km_factor"] == 1.0


def test_cheap_ads_far_under_the_median_are_kept():
    # the old floor of 0.8 x median (8000 here) deleted exactly these realistic cheap ads
    sr = valuation.serbian_price(foreign(), comps(7000, 7100, 10000, 10000, 10000, 10000, 10000))
    assert sr["skipped_bait"] == 0 and sr["n"] == 7
    assert sr["anchor"] == 7000


def test_price_needs_three_ads():
    assert valuation.serbian_price(foreign(), []) is None
    assert valuation.serbian_price(foreign(), comps(7000)) is None
    assert valuation.serbian_price(foreign(), comps(7000, 7100)) is None
    sr = valuation.serbian_price(foreign(), comps(7000, 7100, 7200))
    assert sr["anchor"] == 7000 and sr["price"] == 6370


def test_no_price_when_bait_leaves_under_three_ads():
    assert valuation.serbian_price(foreign(), comps(1000, 9000, 9100)) is None
    assert valuation.serbian_price(foreign(), comps(1000, 9000, 9100, 9200))["n"] == 3


@pytest.mark.parametrize("cheapest,dropped", [(7499, 1), (7500, 0)])
def test_bait_is_an_ad_under_three_quarters_of_the_next_one(cheapest, dropped):
    sr = valuation.serbian_price(foreign(), comps(cheapest, 10000, 10100, 10200, 10300))
    assert sr["skipped_bait"] == dropped


def test_bait_is_judged_on_the_price_brought_to_our_year():
    # 7,100 of a year older car counts as 7,597, above 75% of 10,000, so it stays; as a same-year ad it is bait
    older = valuation.serbian_price(foreign(), comps(7100, year=2014) + comps(10000, 10100, 10200, 10300))
    assert older["skipped_bait"] == 0 and older["n"] == 5
    assert (older["first"]["price"], older["first"]["adjusted"]) == (7100, 7597)
    same_year = valuation.serbian_price(foreign(), comps(7100, 10000, 10100, 10200, 10300))
    assert same_year["skipped_bait"] == 1 and same_year["first"]["price"] == 10000


def test_at_most_two_bait_ads_are_dropped():
    sr = valuation.serbian_price(foreign(), comps(1000, 2000, 4000, 8000, 8100, 8200))
    assert sr["skipped_bait"] == 2
    assert sr["first"]["price"] == 4000    # the third lonely ad stays: three in a row are the market
    assert sr["anchor"] == 4000 and sr["n"] == 4


def test_two_cheap_ads_close_to_each_other_are_not_bait():
    sr = valuation.serbian_price(foreign(), comps(1000, 1100, 9000, 9100))
    assert sr["skipped_bait"] == 0 and sr["anchor"] == 1000


def test_one_year_older_ad_is_raised_and_one_year_newer_lowered_seven_percent():
    assert valuation.YEAR_STEP == 0.07
    assert valuation.adjusted_price(foreign(), comp(8000, year=2014)) == 8560   # 8000 x 1.07
    assert valuation.adjusted_price(foreign(), comp(8000, year=2015)) == 8000
    assert valuation.adjusted_price(foreign(), comp(8000, year=2016)) == 7440   # 8000 x 0.93
    assert valuation.adjusted_price(foreign(), comp(8000, year=None)) == 8000


def test_neighbouring_years_are_always_pooled():
    # four ads of the car's own year used to shut the other years out
    ads = comps(9000, 9100, 9200, 9300) + comps(8000, 8100, year=2014) + comps(8900, year=2016)
    sr = valuation.serbian_price(foreign(), ads)
    assert sr["n"] == 7
    # the newer ad, lowered to 8,900 x 0.93 = 8,277, is the cheapest; the page shows the ad's own price
    assert (sr["first"]["price"], sr["first"]["adjusted"], sr["first"]["year"]) == (8900, 8277, 2016)
    assert (sr["next"][0]["price"], sr["next"][0]["adjusted"]) == (8000, 8560)
    assert (sr["next"][1]["price"], sr["next"][1]["adjusted"]) == (8100, 8667)
    assert sr["next"][2]["price"] == 9000  # the car's own year comes after them
    assert sr["anchor"] == 8277


@pytest.mark.parametrize("km,factor", [(None, 1.0), (0, 1.0), (150000, 1.0), (250000, 1.0), (260000, 0.989),
                                       (266000, 0.9824), (350000, 0.89), (360000, 0.88), (450000, 0.88),
                                       (600000, 0.88)])
def test_km_factor_takes_1_1_percent_per_10000_km_above_250000_up_to_12_percent(km, factor):
    assert valuation.km_factor(km) == pytest.approx(factor)


def test_only_extra_mileage_against_the_anchor_lowers_the_price():
    base = comps(9000, 9200, 9400, 9600, 9800, km=300000)
    for km in (200000, 300000):
        sr = valuation.serbian_price(foreign(km=km), base)
        assert sr["km_factor"] == 1.0 and sr["price"] == 8190
    high = valuation.serbian_price(foreign(km=350000), base)
    assert high["km_factor"] == pytest.approx(0.89 / 0.945)
    assert high["first"]["comparable_price"] == 8476
    assert high["price"] == 7713 and high["sale_cut"] == 763
    assert high["anchor"] == 9000


def test_unknown_mileage_has_no_adjustment():
    missing_ad_km = valuation.serbian_price(foreign(km=320000), comps(7000, 7100, 7200))
    missing_car_km = valuation.serbian_price(foreign(), comps(7000, 7100, 7200, km=320000))
    assert missing_ad_km["km_factor"] == missing_car_km["km_factor"] == 1.0
    assert missing_ad_km["price"] == missing_car_km["price"] == 6370


# --- variant matching --------------------------------------------------------

@pytest.mark.parametrize("year,expected", [
    (2015, (2014, 2016)),   # Golf 7 only
    (2012, (2011, 2013)),   # Golf 6 / Golf 7 change-over year: without a name the older Golf 6 (to 2013)
    (2020, (2019, 2020)),   # Golf 7 / Golf 8 change-over year: without a name the older Golf 7
    (2024, (2023, 2024)),   # last Golf 8 year: window capped at the generation end
])
def test_year_window(year, expected):
    assert valuation.year_window(GOLF, year) == expected


def test_year_window_of_the_newer_generation_in_a_changeover_year():
    assert valuation.year_window(GOLF, 2012, GOLF["generations"][1]) == (2012, 2013)
    assert valuation.year_window(GOLF, 2020, GOLF["generations"][2]) == (2020, 2021)


def test_year_window_tiguan_changeover():
    assert valuation.year_window(TIGUAN, 2016) == (2015, 2016)   # without a name the older Tiguan I
    assert valuation.year_window(TIGUAN, 2016, TIGUAN["generations"][1]) == (2016, 2017)
    assert valuation.year_window(TIGUAN, 2014) == (2013, 2015)


@pytest.mark.parametrize("model,year,expected", [
    (TIGUAN, 2017, (2017, 2018)),    # PA calls Tiguan I and II "Tiguan": the ads of 2016 hold both
    (TIGUAN, 2018, (2017, 2019)),
    (TIGUAN, 2015, (2014, 2016)),    # the year after ours stays: its cheapest ads are our own generation
    (OCTAVIA, 2014, (2014, 2015)),   # Octavia II and III share 2013
    (OCTAVIA, 2012, (2011, 2013)),
    (GOLF, 2014, (2013, 2015)),      # PA splits "Golf 6" and "Golf 7": the Golf 7 ads of 2013 are all Golf 7
    (PASSAT, 2016, (2015, 2017)),    # the same for Passat B7 and B8 in 2015
])
def test_year_before_ours_is_left_out_when_its_ads_mix_two_generations(model, year, expected):
    assert valuation.year_window(model, year) == expected


def test_mixed_year_needs_two_generations_under_one_pa_name():
    assert valuation.mixed_year(TIGUAN, 2016) is True
    assert valuation.mixed_year(TIGUAN, 2015) is False
    assert valuation.mixed_year(GOLF, 2012) is False      # two generations, two PA names
    assert valuation.mixed_year(PASSAT, 2010) is False    # no generation at all


def test_tiguan_of_2017_is_not_priced_by_the_older_tiguan_of_2016():
    """Live run 24.11.2026: an 11,850 ad of 2016 counted as 12,680 and was the anchor next to a 13,290 ad of 2017."""
    car = foreign(model="Tiguan", year=2017, cc=1968, kw=110, body="suv")
    ads = []
    for price, year in ((11850, 2016), (13290, 2017), (13500, 2017), (13900, 2018), (14200, 2017), (14500, 2018)):
        ads.append(comp(price, year=year, model="Tiguan", title="Volkswagen Tiguan 2.0 TDI", tags=[], cc=1968,
                        kw=110, body="suv"))
    snapshot = scan.snapshot_of(TIGUAN, TIGUAN["generations"][1], "diesel")
    matched = scan.comparables_for({snapshot: ads}, car, TIGUAN)
    assert [ad["price"] for ad in matched] == [13290, 13500, 13900, 14200, 14500]
    serbia = valuation.serbian_price(car, matched)
    # the cheapest is the 13,900 ad of 2018 lowered to 12,927 (13,900 x 0.93), not the older generation's 2016 ad
    assert (serbia["first"]["price"], serbia["first"]["year"]) == (13900, 2018)
    assert serbia["anchor"] == 12927 and serbia["n"] == 5


def test_match_doors_body_gearbox_drive():
    assert not valuation.is_match(foreign(doors=3), comp(7000, doors=5))      # Golf 3 vs 5 doors
    assert valuation.is_match(foreign(doors=3), comp(7000, doors=3))
    assert valuation.is_match(foreign(), comp(7000, doors=3))                 # doors unknown -> any
    assert not valuation.is_match(foreign(doors=5), comp(7000, doors=None))   # unknown PA doors never match known
    assert not valuation.is_match(foreign(), comp(7000, body="estate"))
    assert not valuation.is_match(foreign(body="estate"), comp(7000))
    assert not valuation.is_match(foreign(body="van"), comp(7000))           # Golf Plus vs Golf hatch
    assert not valuation.is_match(foreign(), comp(7000, gearbox="automatic"))
    assert not valuation.is_match(foreign(), comp(7000, gearbox=None))
    assert not valuation.is_match(foreign(gearbox=None), comp(7000))
    assert not valuation.is_match(foreign(drive="4x4"), comp(7000))
    assert valuation.is_match(foreign(drive="4x4"), comp(7000, drive="4x4"))
    assert not valuation.is_match(foreign(detailed=True), comp(7000, drive="4x4"))
    assert not valuation.is_match(foreign(), comp(7000, drive="4x4"))         # the list page reads the drive too


def test_match_engine_kw_and_cc():
    assert not valuation.is_match(foreign(kw=81), comp(7000, kw=77))         # Golf 1.6 TDI 77 vs 81 kW
    assert valuation.is_match(foreign(kw=81), comp(7000, kw=83))
    assert not valuation.is_match(foreign(cc=1598), comp(7000, cc=1968))
    assert valuation.is_match(foreign(cc=None), comp(7000, cc=1598))
    assert not valuation.is_match(foreign(fuel="petrol_lpg"), comp(7000, fuel="petrol_cng"))


def test_a3_saloon_is_a_separate_variant_and_suv_models_use_suv_ads():
    saloon = foreign(model="A3", body="sedan")
    assert valuation.is_match(saloon, comp(7000, body="sedan"))
    assert not valuation.is_match(saloon, comp(7000, body="hatchback"))
    tiguan = foreign(model="Tiguan", body=None)
    assert valuation.is_match(tiguan, comp(9000, body="suv"))
    assert not valuation.is_match(tiguan, comp(9000, body="sedan"))


@pytest.mark.parametrize("title", ["Audi Sportback 1.6 TDI", "Audi A3 SPB 1.6 TDI"])
def test_a3_sportback_title_overrides_a_generic_limousine_category(title):
    sportback = foreign(model="A3", body="sedan", title=title)
    assert valuation.is_match(sportback, comp(9000, body="hatchback"))
    assert not valuation.is_match(sportback, comp(9000, body="sedan"))


def test_conflicting_displacements_without_foreign_cc_cannot_produce_a_final_price():
    ads = comps(9000, 9200, 9400) + comps(8500, 8700, 8900, cc=1968)
    assert valuation.evaluate(foreign(cc=None, detailed=True), ads, {}, GOLF) is None
    provisional = valuation.evaluate(foreign(cc=None, detailed=False), ads, {}, GOLF)
    assert provisional["sale"] == 7735 and not provisional["passes"]
    confirmed = valuation.evaluate(foreign(cc=1598, detailed=True), ads[:3], {}, GOLF)
    assert confirmed["sale"] == 8190 and confirmed["passes"]


def test_displacement_inferred_from_comps_still_has_to_meet_the_engine_limit():
    car = foreign(cc=None, detailed=True)
    assert valuation.evaluate(car, comps(9000, 9200, 9400, cc=2001), {}, GOLF) is None
    assert valuation.evaluate(car, comps(9000, 9200, 9400, cc=2000), {}, GOLF)["passes"]


def test_sub_model_is_matched_only_with_ads_of_the_same_sub_model():
    gtd = foreign(title="Volkswagen Golf GTD 2.0 TDI")
    assert valuation.is_match(gtd, comp(7000, title="Volkswagen Golf 7 GTD"))
    assert not valuation.is_match(gtd, comp(7000, title="Volkswagen Golf 7 2.0 TDI"))
    assert not valuation.is_match(gtd, comp(7000, title="Volkswagen Golf 7 GTI"))
    assert not valuation.is_match(gtd, comp(7000))                            # an ad without a title
    assert not valuation.is_match(foreign(title="VW Tiguan Allspace 2.0 TDI"), comp(7000, title="Volkswagen Tiguan"))
    assert valuation.is_match(foreign(title="VW Tiguan R-Line"), comp(7000, title="Volkswagen Tiguan"))   # a trim
    assert not valuation.is_match(foreign(title="VW Golf"), comp(7000, title="Volkswagen Golf 7 GTD"))   # both ways


def test_sub_model_with_under_three_ads_of_its_own_has_no_price():
    scout = foreign(title="Skoda Octavia Scout 2.0 TDI", drive="4x4")
    base = [comp(price, title="Škoda Octavia 2.0 TDI") for price in (9000, 9200, 9400, 9600, 9800)]
    two = [comp(price, title="Škoda Octavia Scout", drive="4x4") for price in (11000, 11500)]
    assert valuation.evaluate(scout, [c for c in base + two if valuation.is_match(scout, c)], {}, GOLF) is None
    three = two + [comp(12000, title="Škoda Octavia SCOUT 4x4", drive="4x4")]
    priced = valuation.evaluate(scout, [c for c in base + three if valuation.is_match(scout, c)], {}, GOLF)
    assert priced["serbia"]["anchor"] == 11000 and priced["serbia"]["n"] == 3


# --- target and max buy ------------------------------------------------------

@pytest.mark.parametrize("cash,target", [(4000, 1000), (5999, 1000), (6000, 1000), (6001, 1000.1667), (12000, 2000)])
def test_target_is_1000_up_to_6000_then_proportional(cash, target):
    assert valuation.target_profit(cash) == pytest.approx(target, abs=0.01)


def test_evaluate_profit_and_exact_max_buy():
    result = valuation.evaluate(foreign(), comps(9000, 9200, 9400, 9600, 9800), {}, GOLF, DEC_2026)
    assert result["serbia"]["price"] == result["sale"] == 8190
    assert result["serbia"]["anchor"] == 9000
    assert result["cost"]["transport"] == 620
    assert result["profit"] == 8190 - result["cost"]["cash"]
    best = result["max_buy"]
    assert valuation.passes_at(foreign(), best, 8190, {}, GOLF, DEC_2026)
    assert not valuation.passes_at(foreign(), best + 1, 8190, {}, GOLF, DEC_2026)


def test_max_buy_none_when_even_free_car_misses_target():
    result = valuation.evaluate(foreign(), comps(2000, 2050, 2100, 2150), {}, GOLF, DEC_2026)
    assert result["max_buy"] is None
    assert result["passes"] is False


# --- costs: VAT, repair, transport, origin, worst case -----------------------

def test_vat_deductible_without_net_price_stays_gross_and_is_flagged():
    gross = valuation.evaluate(foreign(vat_deductible=True), comps(9000, 9200, 9400, 9600), {}, GOLF)
    assert (gross["cost"]["asking"], gross["cost"]["buy"]) == (4000, 3800)
    assert "u ceni je PDV, za izvoz traži cenu bez PDV-a" in gross["flags"]
    net = valuation.evaluate(foreign(vat_deductible=True, net_price=3361), comps(9000, 9200, 9400, 9600), {}, GOLF)
    assert (net["cost"]["asking"], net["cost"]["buy"]) == (3361, 3161)


@pytest.mark.parametrize("asking,settings,buy,discount", [
    (4000, {}, 3800, 200), (4000, {"buy_discount": 0}, 4000, 0),
    (4000, {"buy_discount": 300}, 3700, 300), (4000, {"buy_discount": 5000}, 0, 4000),
])
def test_buy_discount_changes_cash_but_not_the_maximum_to_pay(asking, settings, buy, discount):
    car = foreign(price=asking)
    base = comps(9000, 9200, 9400)
    result = valuation.evaluate(car, base, settings, GOLF, DEC_2026)
    assert result["cost"]["buy"] == buy and result["cost"]["buy_discount"] == discount
    full_price = valuation.evaluate(car, base, {"buy_discount": 0}, GOLF, DEC_2026)
    assert result["cost"]["cash"] == full_price["cost"]["cash"] - discount
    assert result["max_buy"] == full_price["max_buy"]


def test_repair_default_only_for_damaged_but_override_always_applies():
    base = comps(9000, 9200, 9400, 9600)
    clean = valuation.evaluate(foreign(), base, {}, GOLF)
    damaged = valuation.evaluate(foreign(damaged=True), base, {}, GOLF)
    assert clean["profit"] - damaged["profit"] == valuation.DEFAULT_REPAIR_EUR
    unflagged_override = valuation.evaluate(foreign(), base, {"repair": 700}, GOLF)
    assert clean["profit"] - unflagged_override["profit"] == 700
    zero_override = valuation.evaluate(foreign(damaged=True), base, {"repair": 0}, GOLF)
    assert zero_override["profit"] == clean["profit"]


def test_small_transport_override_never_makes_negative_border_leg():
    result = valuation.evaluate(foreign(), comps(9000, 9200, 9400, 9600), {"transport_override": 100}, GOLF)
    assert result["cost"]["transport"] == 100
    no_transport = valuation.costs(foreign(), 4000, {"transport_override": 120}, GOLF)
    small = valuation.costs(foreign(), 4000, {"transport_override": 100}, GOLF)
    assert small["import"]["total"] == no_transport["import"]["total"]


def test_no_origin_proof_extra_is_shown_and_applied():
    base = comps(9000, 9200, 9400, 9600)
    with_proof = valuation.evaluate(foreign(), base, {}, GOLF, DEC_2026)
    extra = with_proof["cost"]["no_proof_extra"]
    # duty and the VAT on it are taken from the catalogue value of a 2015 Golf 7, not from the 4,000 paid
    catalogue = customs.catalogue_value(22500, 2015, None, DEC_2026)
    assert extra == pytest.approx(catalogue * customs.DUTY_STANDARD * 1.2, abs=2)
    without = valuation.evaluate(foreign(), base, {"origin_proof": False}, GOLF, DEC_2026)
    assert with_proof["profit"] - without["profit"] == pytest.approx(extra, abs=1)


def test_worst_case_is_the_invoice_bill_only_when_it_is_higher():
    """Rewritten 24.11.2026: the worst case was the AutoScout24 median as a catalogue proxy; now the headline is
    the catalogue and the worst case is customs taking the invoice instead."""
    base = comps(9000, 9200, 9400, 9600)
    # a 2015 Golf 7 is worth about 3,690 in the catalogue in Dec 2026; 3,800 + 500 border transport is more
    dear = valuation.evaluate(foreign(), base, {}, GOLF, DEC_2026)
    invoice = customs.import_bill(3800 + 500, 1350, 0.0, DEC_2026)["total"] + customs.UNLISTED_COSTS_EUR
    assert dear["cost"]["cash_worst"] == dear["cost"]["cash"] - dear["cost"]["import"]["total"] + invoice
    assert dear["profit_worst"] < dear["profit"]
    cheap = valuation.evaluate(foreign(price=2000), base, {}, GOLF, DEC_2026)
    assert cheap["cost"]["cash_worst"] is None and cheap["profit_worst"] is None
    # the AutoScout24 median no longer plays any part
    median = valuation.evaluate(foreign(price=2000, market_median=9000), base, {}, GOLF, DEC_2026)
    assert median["cost"] == cheap["cost"]


# --- import bill from the catalogue (24.11.2026) ---------------------------------

def test_headline_bill_is_the_catalogue_bill_of_the_generation_whatever_was_paid():
    expected = customs.catalogue_bill(22500, 2015, 3, 1350, 0.0, DEC_2026)
    for buy in (2000, 4000, 9000):
        assert valuation.costs(foreign(month=3), buy, {}, GOLF, DEC_2026)["import"] == expected


def test_registration_month_counts_in_the_catalogue_value():
    january = valuation.costs(foreign(month=1), 4000, {}, GOLF, DEC_2026)["import"]["total"]
    december = valuation.costs(foreign(month=12), 4000, {}, GOLF, DEC_2026)["import"]["total"]
    assert december > january


def test_estate_takes_the_estate_new_price_and_a_model_without_one_takes_the_base_price():
    estate = valuation.costs(foreign(body="estate"), 4000, {}, GOLF, DEC_2026)["import"]
    assert estate == customs.catalogue_bill(24000, 2015, None, 1350, 0.0, DEC_2026)
    polo = models.MODELS[1]
    polo_estate = valuation.costs(foreign(model="Polo", body="estate", mass=1150), 4000, {}, polo, DEC_2026)
    assert polo_estate["import"] == customs.catalogue_bill(14400, 2015, None, 1150, 0.0, DEC_2026)


@pytest.mark.parametrize("model_index,year,new_price", [(2, 2012, 23549), (3, 2018, 33000), (9, 2010, 14200)])
def test_every_generation_has_its_new_price(model_index, year, new_price):
    model = models.MODELS[model_index]
    assert valuation.new_price_of(foreign(year=year), model) == new_price


def test_unknown_generation_falls_back_on_the_invoice_bill():
    car = foreign(year=2014, title="VW Golf VI")   # the title names a Golf 6, which ends in 2013
    cost = valuation.costs(car, 4000, {}, GOLF, DEC_2026)
    assert valuation.new_price_of(car, GOLF) is None
    assert cost["import"] == customs.import_bill(4000 + 500, 1350, 0.0, DEC_2026)
    assert cost["cash_worst"] is None


def test_banes_own_import_figure_replaces_the_bill():
    estimate = valuation.costs(foreign(), 4000, {}, GOLF, DEC_2026)
    typed = valuation.costs(foreign(), 4000, {"import_total": 1700}, GOLF, DEC_2026)
    assert typed["import"]["total"] == 1700
    assert typed["cash"] == estimate["cash"] - estimate["import"]["total"] + 1700
    assert typed["cash_worst"] is None and typed["no_proof_extra"] == 0
    zero = valuation.costs(foreign(), 4000, {"import_total": 0}, GOLF, DEC_2026)   # a typed zero counts too
    assert zero["import"]["total"] == 0


# --- built outside the EU ------------------------------------------------------------

OUTSIDE_FLAG = "proizveden van EU (VIN 3VWZZZ1KZBM123456), carina veća"


@pytest.mark.parametrize("car,duty,flag", [
    (foreign(text="FIN: 3VWZZZ1KZBM123456, Top Zustand"), customs.DUTY_STANDARD, OUTSIDE_FLAG),   # Mexico
    (foreign(title="VW Golf 3vwzzz1kzbm123456"), customs.DUTY_STANDARD, OUTSIDE_FLAG),           # lower case
    (foreign(text="FIN WVWZZZAUZFW123456"), 0.0, None),                                          # Wolfsburg
    (foreign(year=2010, body="estate"), customs.DUTY_STANDARD, valuation.GOLF6_ESTATE_FLAG),       # Puebla
    (foreign(year=2010, body="estate", text="WVWZZZ1KZAM123456"),                                # Puebla for Europe:
     customs.DUTY_STANDARD, valuation.GOLF6_ESTATE_FLAG),                                         # a W VIN clears nothing
    (foreign(text="Erstzulassung2019 Klima"), 0.0, None),                                         # a word and a year
    (foreign(text="https://www.example.de/ad/AB123456789012345"), 0.0, None),                     # an id in a link
    (foreign(text="http://x.de/AB123456789012345 FIN: 3VWZZZ1KZBM123456"),                        # the real VIN after it
     customs.DUTY_STANDARD, OUTSIDE_FLAG),
    (foreign(text="Tel00491701234567 FIN 3VWZZZ1KZBM123456"), customs.DUTY_STANDARD, OUTSIDE_FLAG),   # T.. junk first
    (foreign(year=2010, body=None), 0.0, None),
    (foreign(body="estate"), 0.0, None),                                                         # Golf 7 estate
])
def test_car_built_outside_the_eu_pays_duty_and_says_why(car, duty, flag):
    assert valuation.costs(car, 4000, {}, GOLF, DEC_2026)["duty_rate"] == duty
    flags = valuation.evaluate(car, comps(9000, 9200, 9400, 9600, 9800, year=car["year"]), {}, GOLF, DEC_2026)["flags"]
    outside = [f for f in flags if "carina veća" in f]
    assert outside == ([flag] if flag else [])


def test_eu_vin_never_clears_a_non_eu_model_and_origin_proof_still_counts():
    allspace = foreign(model="Tiguan Allspace")
    assert valuation.costs(allspace, 4000, {}, TIGUAN, DEC_2026)["duty_rate"] == customs.DUTY_STANDARD
    with_vin = foreign(model="Tiguan Allspace", text="WVGZZZ5NZJW123456")   # Puebla builds it under WVG
    assert valuation.costs(with_vin, 4000, {}, TIGUAN, DEC_2026)["duty_rate"] == customs.DUTY_STANDARD
    golf = foreign(text="WVWZZZAUZFW123456")
    assert valuation.costs(golf, 4000, {}, GOLF, DEC_2026)["duty_rate"] == 0.0
    no_proof = valuation.costs(golf, 4000, {"origin_proof": False}, GOLF, DEC_2026)
    assert no_proof["duty_rate"] == customs.DUTY_STANDARD


def test_non_eu_duty_raises_the_bill_by_duty_and_its_vat():
    eu = valuation.costs(foreign(), 4000, {}, GOLF, DEC_2026)["import"]["total"]
    mexico = valuation.costs(foreign(text="3VWZZZ1KZFM123456"), 4000, {}, GOLF, DEC_2026)["import"]["total"]
    catalogue = customs.catalogue_value(22500, 2015, None, DEC_2026)
    assert mexico - eu == pytest.approx(catalogue * customs.DUTY_STANDARD * 1.2, abs=2)


def test_evaluate_none_without_location_or_comparables():
    base = comps(9000, 9200, 9400, 9600)
    assert valuation.evaluate(foreign(country="XX", city=""), base, {}, GOLF) is None
    assert valuation.evaluate(foreign(), base[:2], {}, GOLF) is None


# --- equipment and flags -----------------------------------------------------

def test_equipment_detection():
    car = {"equipment": ["Multifunktionslenkrad", "Navigationssystem", "Sitzheizung"], "text": "Leder, Xenon"}
    assert valuation.equipment_of(car) == ["MF volan", "Koža", "Navigacija", "LED/Xenon", "Grejanje sedišta"]


def test_equipment_named_only_in_the_title_is_shown():
    assert valuation.equipment_of({"title": "Golf mit Leder und Navigationssystem"}) == ["Koža", "Navigacija"]


def test_english_equipment_from_mobilede():
    car = {"equipment": ["Multifunction steering wheel", "Heated seats", "Fixed trailer coupling", "Navigation system",
                         "LED headlights", "Panoramic roof", "Leather steering wheel"], "text": ""}
    assert valuation.equipment_of(car) == ["MF volan", "Navigacija", "LED/Xenon", "Panorama", "Grejanje sedišta",
                                           "Kuka"]


def test_flags():
    car = foreign(damaged=True, market_median=9000, price=4000, seller="private",
                  text="Export Gewerbe, WhatsApp +49", detailed=True)
    flags = valuation.flags_of(car)
    assert "oštećen" in flags
    assert any(f.startswith("sumnjivo") for f in flags)
    assert any(f.startswith("WhatsApp") for f in flags)
    assert "prodaje se firmama ili za izvoz, bez garancije" in flags
    assert "privatni prodavac" in flags
    assert valuation.flags_of(foreign(seller="dealer", detailed=True, market_median=5000)) == []


# --- round-two review fixes --------------------------------------------------

def test_comparable_without_engine_data_never_matches():
    assert not valuation.is_match(foreign(), comp(7000, cc=None))
    assert not valuation.is_match(foreign(), comp(7000, kw=None))
    assert not valuation.is_match(foreign(kw=None), comp(7000))


def test_much_lower_km_serbian_car_is_not_a_comparable():
    assert not valuation.is_match(foreign(km=480000), comp(7000, km=280000))
    assert valuation.is_match(foreign(km=150000), comp(7000, km=230000))   # higher km is fine (conservative)


def test_coupe_and_cabrio_are_separate_bodies():
    assert not valuation.is_match(foreign(body="hatchback"), comp(7000, body="cabrio"))
    assert valuation.is_match(foreign(body="sedan"), comp(7000, body="hatchback"))


def test_only_detailed_car_can_pass():
    base = comps(9000, 9200, 9400, 9600, 9800)
    assert valuation.evaluate(foreign(), base, {}, GOLF)["passes"] is False
    assert valuation.evaluate(foreign(detailed=True), base, {}, GOLF)["passes"] is True


@pytest.mark.parametrize("sale", [12000, 9300, 6000, 1500, 900])
def test_cash_ceiling_is_the_exact_boundary(sale):
    ceiling = valuation.cash_ceiling(sale)
    if sale < 1000:
        assert ceiling == 0
        return
    assert round(sale - ceiling) >= round(valuation.target_profit(ceiling))
    assert round(sale - ceiling - 1) < round(valuation.target_profit(ceiling + 1))


def test_zero_transport_override_is_used():
    assert valuation.costs(foreign(), 4000, {"transport_override": 0}, GOLF)["transport"] == 0


def test_no_proof_rate_is_ev_rate_for_tesla():
    tesla = foreign(make="Tesla", model="Model S", fuel="electric")
    assert valuation.costs(tesla, 12000, {}, GOLF)["no_proof_rate"] == customs.DUTY_EV


# --- 24.11. importer's review: the buy side ------------------------------------

def test_car_far_under_the_serbian_price_is_a_deal_without_a_label():
    # a real deal costs about 0.45 x the Serbian price; the old "under 0.4 x" rule hid exactly those
    base = comps(17000, 17200, 17400, 17600, 17800)
    cheap = valuation.evaluate(foreign(price=1990, detailed=True), base, {}, GOLF)
    assert cheap["cost"]["buy"] < 0.4 * cheap["serbia"]["price"]
    assert cheap["profit"] >= cheap["target"]
    assert cheap["passes"] is True
    assert not any(f.startswith("sumnjivo") for f in cheap["flags"])


@pytest.mark.parametrize("price,labelled", [(3999, True), (4000, False)])
def test_price_under_half_the_autoscout24_median_is_only_a_label(price, labelled):
    base = comps(17000, 17200, 17400, 17600, 17800)
    car = foreign(price=price, market_median=8000, detailed=True)
    assert valuation.suspicious(car) is labelled
    result = valuation.evaluate(car, base, {}, GOLF)
    assert any(f.startswith("sumnjivo") for f in result["flags"]) is labelled
    assert result["passes"] is True        # the label never hides the car


def test_car_without_an_autoscout24_median_gets_no_label():
    assert valuation.suspicious(foreign(price=500)) is False
    assert valuation.suspicious(foreign(price=500, market_median=None)) is False


# --- thin market ---------------------------------------------------------------

@pytest.mark.parametrize("ads", [3, 4, 5, 6])
def test_three_and_four_ads_raise_a_warning_but_can_pass(ads):
    base = comps(9000, 9200, 9400, 9600, 9800, 10000)[:ads]
    result = valuation.evaluate(foreign(detailed=True), base, {}, GOLF)
    assert result["serbia"]["price"] == 8190 and result["serbia"]["n"] == ads
    assert result["profit"] >= result["target"]
    assert result["passes"] is True
    assert (valuation.THIN_MARKET_FLAG in result["flags"]) is (ads < 5)


def test_thin_market_flag_names_the_limit():
    assert valuation.MIN_ADS == 3 and valuation.THIN_MARKET_ADS == 5
    assert valuation.THIN_MARKET_FLAG == "malo ovakvih oglasa u Srbiji (manje od 5), prodajna cena je nesigurna"


# --- repair size read from the description ---------------------------------------

def read_as(state, repair):
    return {"state": state, "repair": repair, "note": "opis kvara", "key": "k"}


def test_small_repair_keeps_the_default_repair_and_can_be_a_deal():
    base = comps(9000, 9200, 9400, 9600, 9800)
    car = foreign(detailed=True, damaged=True, ai=read_as("kvar", "mala"))
    result = valuation.evaluate(car, base, {}, GOLF)
    assert result["cost"]["repair"] == valuation.DEFAULT_REPAIR_EUR
    assert result["passes"] is True
    assert valuation.BIG_REPAIR_FLAG not in result["flags"]
    assert "iz opisa: opis kvara" in result["flags"]


def test_big_repair_is_not_a_deal_until_its_cost_is_typed_in():
    base = comps(9000, 9200, 9400, 9600, 9800)
    car = foreign(price=3000, detailed=True, damaged=True, ai=read_as("kvar", "velika"))
    unknown = valuation.evaluate(car, base, {}, GOLF)
    assert unknown["profit"] >= unknown["target"]
    assert unknown["passes"] is False
    assert valuation.BIG_REPAIR_FLAG in unknown["flags"]
    assert valuation.BIG_REPAIR_FLAG == "veća popravka: unesi cenu popravke"

    typed = valuation.evaluate(car, base, {"repair": 1500}, GOLF)
    assert typed["cost"]["repair"] == 1500
    assert typed["profit"] == unknown["profit"] + valuation.DEFAULT_REPAIR_EUR - 1500
    assert typed["passes"] is True
    assert valuation.BIG_REPAIR_FLAG not in typed["flags"]

    free = valuation.evaluate(car, base, {"repair": 0}, GOLF)      # a typed zero is a cost too
    assert free["passes"] is True and valuation.BIG_REPAIR_FLAG not in free["flags"]

    dear = valuation.evaluate(car, base, {"repair": 6000}, GOLF)   # with the cost known the profit decides
    assert dear["passes"] is False and valuation.BIG_REPAIR_FLAG not in dear["flags"]


@pytest.mark.parametrize("reading", [None, {}, read_as("ok", "nema"), read_as("ok", "velika"), read_as("kvar", "nema"),
                                     {"state": "kvar", "note": "stari zapis bez popravke", "key": "k"}])
def test_only_a_fault_with_a_big_repair_asks_for_the_cost(reading):
    assert valuation.big_repair_unpriced(foreign(ai=reading), {}) is False


# --- a description Haiku could not read ---------------------------------------------

@pytest.mark.parametrize("car,unread", [
    (foreign(text="Top Zustand"), False),                              # never sent to Haiku: no "ai" at all
    (foreign(text="Top Zustand", ai=None), True),                      # sent, and no reading came back
    (foreign(text="  ", ai=None), False),                              # nothing to read
    (foreign(text=None, ai=None), False),
    (foreign(text="Top Zustand", ai=read_as("ok", "nema")), False),
])
def test_description_is_unread_only_when_haiku_was_asked_and_gave_no_reading(car, unread):
    assert valuation.description_unread(car) is unread
    assert (valuation.UNREAD_FLAG in valuation.flags_of(car)) is unread


def test_unread_description_is_a_warning_and_the_car_can_still_pass():
    base = comps(9000, 9200, 9400, 9600, 9800)
    result = valuation.evaluate(foreign(detailed=True, text="Top Zustand", ai=None), base, {}, GOLF)
    assert valuation.UNREAD_FLAG in result["flags"] and result["passes"] is True


@pytest.mark.parametrize("image,reading,detailed,warn", [
    ("photo", None, True, True), ("photo", None, False, False),
    (None, None, True, False), ("photo", read_as("ok", "nema"), True, False),
])
def test_unchecked_photos_are_disclosed_on_detailed_cars(image, reading, detailed, warn):
    car = foreign(image=image, ai=reading, detailed=detailed)
    assert (valuation.PHOTOS_UNREAD_FLAG in valuation.flags_of(car)) is warn


# --- the importer's three cars, with the real ads of 24.11.2026 -------------------

def expert_case(name, model):
    case = EXPERT_CASES[name]
    car = case["car"]
    snapshot = scan.snapshot_of(model, models.generations_for(model, car["year"])[0], car["fuel"])
    return car, {snapshot: case["ads"]}


def test_tiguan_4motion_is_read_from_the_title_of_the_list_page():
    listed = autoscout24.parse_list_item(EXPERT_CASES["tiguan_2013_dsg_4motion"]["list_item"])
    assert listed["id"] == "as24:8f4ca3a2-f65f-4e39-9a1d-13e70c041236"
    assert listed["title"] == "Volkswagen Tiguan Tiguan 2.0 TDI DPF 4Motion DSG AHK Sport"
    assert (listed["year"], listed["km"], listed["kw"], listed["gearbox"], listed["price"]) == (2013, 266000, 130, "automatic", 5999)
    assert listed["drive"] == "4x4"


def test_expert_tiguan_is_worth_8000_to_9000_and_is_no_deal_at_5999():
    """2013 2.0 TDI 130 kW DSG 4Motion, 266,000 km, asked 5,999: the importer says 8,000-9,000 in Serbia.
    The tool said 11,975 and 2,990 profit, because the stored drive was empty and the 8,800 ad is a 4x4."""
    stored, snapshots = expert_case("tiguan_2013_dsg_4motion", TIGUAN)
    assert stored["drive"] is None
    car = dict(stored, drive=models.drive_of(stored["title"] + " " + stored["text"]))   # what the parser now sets
    result = valuation.evaluate(car, scan.comparables_for(snapshots, car, TIGUAN), {}, TIGUAN, DEC_2026)
    serbia = result["serbia"]
    assert (serbia["first"]["id"], serbia["first"]["price"]) == ("31034798", 8800)
    assert (serbia["next"][0]["id"], serbia["next"][0]["price"]) == ("30629106", 10500)
    assert serbia["anchor"] == 8800 and serbia["n"] == 10
    assert all(ad["drive"] == "4x4" for ad in [serbia["first"], *serbia["next"]])
    assert serbia["km_factor"] == 1.0 and serbia["sale_cut"] == 792
    assert serbia["price"] == result["sale"] == 8008
    assert 8000 <= result["sale"] <= 9000
    assert result["profit"] == 8008 - result["cost"]["cash"]
    assert result["profit"] < result["target"]     # the tool said +2,990 on a target of 1,498
    assert result["passes"] is False
    assert result["max_buy"] < 5999


def test_expert_tiguan_without_the_4x4_reading_loses_its_cheapest_ad():
    stored, snapshots = expert_case("tiguan_2013_dsg_4motion", TIGUAN)
    matched = scan.comparables_for(snapshots, stored, TIGUAN)
    assert "31034798" not in [ad["id"] for ad in matched]     # the 8,800 ad is a 4x4: not for a car read as 2WD
    assert valuation.serbian_price(stored, matched)["first"]["price"] == 9690


def test_expert_octavia_2017_manual_estate_is_no_deal_at_5700():
    car, snapshots = expert_case("octavia_2017_manual_estate", OCTAVIA)
    result = valuation.evaluate(car, scan.comparables_for(snapshots, car, OCTAVIA), {}, OCTAVIA, DEC_2026)
    serbia = result["serbia"]
    assert (serbia["first"]["price"], serbia["first"]["adjusted"], serbia["first"]["year"]) == (9299, 9950, 2016)
    assert (serbia["next"][0]["price"], serbia["next"][0]["adjusted"], serbia["next"][0]["year"]) == (9300, 9951, 2016)
    assert serbia["anchor"] == 9950 and serbia["n"] == 7     # 9299 x 1.07 = 9949.9
    # the facelift came in 2017: a 2017 car that does not say so is priced without the 2018 facelift ads (9,450 ...)
    assert {ad["year"] for ad in scan.comparables_for(snapshots, car, OCTAVIA)} == {2016, 2017}
    assert serbia["price"] == 9054
    assert result["profit"] == 9054 - result["cost"]["cash"]
    assert result["profit"] < result["target"]
    assert result["passes"] is False


def test_expert_octavia_2015_dsg_estate_at_2790_drops_the_newer_4900_ad_as_bait_and_rests_on_6500():
    """320,000 km, asked 2,790. The 4,900 ad is a 2016 car: lowered 7% it counts as 4,557, 70.1% of the 6,500 ad
    of 2015, under the bait line of 75%, so it is dropped and the 6,500 ad is the anchor."""
    car, snapshots = expert_case("octavia_2015_dsg_estate", OCTAVIA)
    matched = scan.comparables_for(snapshots, car, OCTAVIA)
    result = valuation.evaluate(car, matched, {}, OCTAVIA, DEC_2026)
    serbia = result["serbia"]
    assert (serbia["first"]["price"], serbia["next"][0]["price"]) == (6500, 8650)
    assert serbia["skipped_bait"] == 1 and serbia["n"] == 11
    assert serbia["km_factor"] == 1.0      # the cheapest Serbian car has more kilometres
    assert serbia["anchor"] == 6500 and serbia["price"] == 5915
    assert result["profit"] == 5915 - result["cost"]["cash"]
    assert result["profit"] >= result["target"]
    assert result["passes"] is True
    assert not any(f.startswith("sumnjivo") for f in result["flags"])   # 2,790 is under 0.4 x the old 9,300

    without_4900 = [ad for ad in matched if ad["price"] != 4900]
    other = valuation.evaluate(car, without_4900, {}, OCTAVIA, DEC_2026)
    assert other["serbia"]["skipped_bait"] == 0 and other["serbia"]["n"] == 11
    assert other["serbia"]["anchor"] == 6500 and other["serbia"]["price"] == 5915
    assert other["passes"] is True
    # the facelift came in 2017: every 2016 ad is from before it, so a 2015 car keeps them
    assert {ad["year"] for ad in matched} == {2014, 2015, 2016}


# --- a damaged car is judged by what Haiku reads, not blocked wholesale (Bane 24.11.2026) ---------

@pytest.mark.parametrize("reading", [None, read_as("ok", "nema"), read_as("kvar", "mala")])
def test_site_damaged_car_with_no_big_fault_keeps_the_default_repair_and_can_pass(reading):
    base = comps(9000, 9200, 9400, 9600, 9800)
    car = foreign(price=3000, detailed=True, damaged=True, ai=reading)
    result = valuation.evaluate(car, base, {}, GOLF)
    assert result["cost"]["repair"] == valuation.DEFAULT_REPAIR_EUR
    assert result["passes"] is True


def test_site_damaged_car_with_a_big_fault_is_no_deal_until_the_repair_is_typed():
    base = comps(9000, 9200, 9400, 9600, 9800)
    car = foreign(price=3000, detailed=True, damaged=True, ai=read_as("kvar", "velika"))
    result = valuation.evaluate(car, base, {}, GOLF)
    assert result["passes"] is False and valuation.BIG_REPAIR_FLAG in result["flags"]
    assert valuation.evaluate(car, base, {"repair": 1200}, GOLF)["passes"] is True


# --- Novky 24.11.2026: the cheapest ad, newer ads lowered, sub-models both ways, named generations --------

def test_one_year_newer_ad_is_lowered_seven_percent_and_can_be_the_anchor():
    # our car is of 2015: a 2016 ad at 8,000 counts as 7,440, under the 7,600 ad of our own year
    sr = valuation.serbian_price(foreign(), comps(8000, year=2016) + comps(7600, 7800, 9000))
    assert (sr["first"]["price"], sr["first"]["adjusted"], sr["first"]["year"]) == (8000, 7440, 2016)
    assert sr["anchor"] == 7440 and sr["price"] == 6770


@pytest.mark.parametrize("model", models.MODELS, ids=lambda model: model["as24"])
def test_no_ad_two_years_from_our_car_is_ever_compared(model):
    for year in range(2000, 2027):
        if models.generations_for(model, year):
            year_from, year_to = valuation.year_window(model, year)
            assert year - 1 <= year_from <= year <= year_to <= year + 1


def test_cheapest_ad_is_the_anchor_and_the_second_ad_does_not_move_the_price():
    close = valuation.serbian_price(foreign(), comps(7000, 7050, 9000))
    far = valuation.serbian_price(foreign(), comps(7000, 9300, 9400))   # 7,000 is 75.3% of 9,300: no bait
    assert close["anchor"] == far["anchor"] == 7000
    assert close["price"] == far["price"] == 6370


@pytest.mark.parametrize("base_title,sub_title", [
    ("Skoda Octavia 2.0 TDI", "Škoda Octavia RS 2.0 TDI"),
    ("Skoda Octavia 2.0 TDI", "Škoda Octavia vRS"),
    ("Volkswagen Golf 2.0 TDI", "Volkswagen Golf 6 GTD"),
])
def test_base_car_never_uses_an_rs_vrs_or_gtd_ad(base_title, sub_title):
    car = foreign(title=base_title)
    assert valuation.is_match(car, comp(7000, title=base_title))
    assert not valuation.is_match(car, comp(7000, title=sub_title))
    ads = [comp(6000, title=sub_title)] + [comp(price, title=base_title) for price in (9000, 9200, 9400)]
    matched = [ad for ad in ads if valuation.is_match(car, ad)]
    assert valuation.serbian_price(car, matched)["anchor"] == 9000   # the cheaper sub-model ad is not ours


def test_title_naming_another_generation_than_the_year_gives_has_no_price():
    ads = comps(9000, 9200, 9400, 9600, 9800, year=2011)
    assert valuation.evaluate(foreign(year=2011, title="VW Golf 7 1.6 TDI"), ads, {}, GOLF) is None
    for title in ("VW Golf VI 1.6 TDI", "VW Golf 6 1.6 TDI", "VW Golf 1.6 TDI", None):   # Golf 6, or no name
        priced = valuation.evaluate(foreign(year=2011, title=title), ads, {}, GOLF)
        assert priced["serbia"]["anchor"] == 9000 and priced["serbia"]["price"] == 8190


def test_novkys_passat_b6_and_golf_6_gtd_use_their_own_ads_and_sell_near_5000(monkeypatch):
    """Novky 24.11.2026: a 2011 Passat B6 on CNG sells for at most 5,000 (we said 6,311), a 2010 Golf 6 GTD the
    same (we said 6,680). Ads as the live scan held them."""
    passat = foreign(model="Passat", year=2011, fuel="petrol_cng", cc=1390, kw=110, km=304000, mass=1550,
                     price=4700, detailed=True, title="Volkswagen Passat B6 1.4 TSI EcoFuel Comfortline")
    assert scan.snapshot_for(dict(passat, text=""), PASSAT) is None   # since 25.11 a CNG car is dropped before pricing
    monkeypatch.setattr(market, "REPUTATION", [])   # the sale rule on Novky's figure is still checked below
    b7_ads = [comp(price, year=2011, fuel="petrol_cng", cc=1390, kw=110, km=220000, title="Volkswagen Passat B7",
                   model="Passat B7", tags=[])
              for price in (6400, 6950, 7450, 8300, 8500)]
    matched = [ad for ad in b7_ads if valuation.is_match(passat, ad)]
    assert len(matched) == 5
    unnamed = dict(passat, title="Volkswagen Passat 1.4 TSI EcoFuel Comfortline")
    # without a name a 2011 Passat is a B6 too (Ogi 26.11.2026); AutoScout24's own B7 id makes it a B7
    assert scan.snapshot_for(dict(unnamed, text=""), PASSAT) == ("Volkswagen", "Passat B6", 2009, 2011, "petrol_cng")
    b7_car = dict(unnamed, url="https://www.autoscout24.de/angebote/vw-passat-cat_ma74gr100039ge216va1-1")
    b7_snapshot = scan.snapshot_for(dict(b7_car, text=""), PASSAT)
    snapshots = {b7_snapshot: b7_ads}
    assert scan.comparables_for(snapshots, passat, PASSAT) == []
    assert len(scan.comparables_for(snapshots, b7_car, PASSAT)) == 5
    b6_snapshot = scan.snapshot_for(dict(passat, text=""), PASSAT)
    assert b6_snapshot == ("Volkswagen", "Passat B6", 2009, 2011, "petrol_cng")
    assert valuation.evaluate(passat, scan.comparables_for(snapshots, passat, PASSAT), {}, PASSAT, DEC_2026) is None
    # No B6 CNG cache. Reuse these asking prices as a synthetic B6 snapshot to exercise the sale rule.
    snapshots[b6_snapshot] = [dict(ad, title="Volkswagen Passat B6", model="Passat B6") for ad in b7_ads[:3]]
    b6 = valuation.evaluate(passat, scan.comparables_for(snapshots, passat, PASSAT), {}, PASSAT, DEC_2026)
    assert b6["serbia"]["anchor"] == 6400 and b6["serbia"]["km_factor"] == pytest.approx(0.9406)
    assert b6["serbia"]["price"] == b6["sale"] == 5478
    assert b6["sale"] == pytest.approx(5000, rel=0.10)
    assert not b6["passes"]

    gtd = foreign(year=2010, km=265000, cc=1968, kw=125, body="sedan", price=2800,
                  title="Volkswagen Golf GTD 2.0 TDI 170 GTD")
    ads = []
    for price, year, km, title in ((6200, 2011, 204277, "Volkswagen Golf 6 2.0TDI GTD"),
                                   (7990, 2011, 260000, "Volkswagen Golf 6 GTD  CH"),
                                   (8000, 2011, 281000, "Volkswagen Golf 6 2.0 GTD"),
                                   (8250, 2011, 238440, "Volkswagen Golf 6 Gtd"),
                                   (8300, 2011, 253754, "Volkswagen Golf 6 GTD"),
                                   (8000, 2010, 220000, "Volkswagen Golf 6 GTD (može zamena)"),
                                   (5900, 2010, 230000, "Volkswagen Golf 6 2.0 TDI")):   # a base Golf
        ads.append(comp(price, year=year, km=km, cc=1968, kw=125, title=title))
    matched = [ad for ad in ads if valuation.is_match(gtd, ad)]
    assert [ad["price"] for ad in matched] == [6200, 7990, 8000, 8250, 8300, 8000]
    serbia = valuation.evaluate(gtd, matched, {}, GOLF, DEC_2026)["serbia"]
    assert (serbia["first"]["price"], serbia["first"]["adjusted"]) == (6200, 5766)   # 6,200 x 0.93
    assert serbia["anchor"] == 5766 and serbia["n"] == 6
    assert serbia["km_factor"] == pytest.approx(0.9835)
    assert serbia["price"] == 5161
    assert serbia["price"] == pytest.approx(5000, rel=0.10)
    assert serbia["price"] < 6680         # the old rule: mean of 6,200 and 7,990 as they ask, x 0.95 x 0.991
    named = valuation.evaluate(dict(gtd, title="VW Golf 6 GTD"), matched, {}, GOLF, DEC_2026)
    assert named["sale"] == serbia["price"]   # naming its own generation changes nothing


def test_same_sale_cut_applies_to_cheaper_ads_and_other_variants():
    gtd = foreign(year=2010, title="Golf 6 GTD")
    cheap = valuation.evaluate(gtd, comps(4900, 5000, 5100, year=2010), {}, GOLF)
    assert cheap["sale"] == 4459 and cheap["serbia"]["sale_cut"] == 441
    base = valuation.evaluate(dict(gtd, title="Golf 6"), comps(6400, 6500, 6600, year=2010), {}, GOLF)
    assert base["sale"] == 5824 and base["serbia"]["sale_cut"] == 576
    diesel = foreign(year=2011, title="Passat B6", fuel="diesel", kw=110, cc=1968)
    diesel_ads = comps(6400, 6500, 6600, year=2011, fuel="diesel", kw=110, cc=1968)
    assert valuation.evaluate(diesel, diesel_ads, {}, PASSAT)["sale"] == 5824
    cng = dict(diesel, fuel="petrol_cng", cc=None, detailed=True)
    cng_ads = comps(6400, 6500, 6600, year=2011, fuel="petrol_cng", kw=110, cc=1390)
    assert all(valuation.is_match(cng, ad) for ad in cng_ads)
    assert valuation.evaluate(cng, cng_ads, {}, PASSAT)["sale"] == 5824
    mislabelled = dict(cng, cc=1598)
    matched = [ad for ad in cng_ads if valuation.is_match(mislabelled, ad)]
    assert valuation.evaluate(mislabelled, matched, {}, PASSAT) is None


# --- 24.11. photos Haiku did not see: said on the card, a damaged car waits for Bane ----

@pytest.mark.parametrize("reading,warn", [
    ({"state": "ok", "repair": "nema", "note": "", "photos_unread": True}, True),
    ({"state": "ok", "repair": "nema", "note": "", "photos_unread": False}, False),
    ({"state": "ok", "repair": "nema", "note": ""}, False),   # read before the field existed
])
def test_text_only_reading_of_an_ad_with_photos_is_disclosed(reading, warn):
    car = foreign(image="photo", ai=reading, detailed=True)
    assert valuation.photos_unseen(car) is warn
    assert (valuation.PHOTOS_UNREAD_FLAG in valuation.flags_of(car)) is warn


@pytest.mark.parametrize("damaged,photos_unread,settings,waits", [
    (True, True, {}, True),
    (True, True, {"repair": 800}, False),    # Bane looked and typed the repair
    (True, True, {"repair": 0}, False),      # a typed zero is his answer too
    (True, False, {}, False),
    (False, True, {}, False),
])
def test_damaged_car_with_unseen_photos_waits_for_bane(damaged, photos_unread, settings, waits):
    reading = {"state": "ok", "repair": "nema", "note": "", "photos_unread": photos_unread}
    car = foreign(price=3000, damaged=damaged, image="photo", ai=reading, detailed=True)
    assert valuation.damage_unseen(car, settings) is waits
    result = valuation.evaluate(car, comps(9000, 9200, 9400, 9600, 9800), settings, GOLF)
    assert result["profit"] >= result["target"]
    assert result["passes"] is not waits


def test_damaged_car_haiku_never_read_waits_when_it_has_photos():
    base = comps(9000, 9200, 9400, 9600, 9800)
    unread = valuation.evaluate(foreign(price=3000, damaged=True, image="photo", ai=None, detailed=True), base, {}, GOLF)
    assert unread["passes"] is False and valuation.PHOTOS_UNREAD_FLAG in unread["flags"]
    no_photos = valuation.evaluate(foreign(price=3000, damaged=True, image=None, ai=None, detailed=True), base, {}, GOLF)
    assert no_photos["passes"] is True


def test_warnings_are_plain_serbian():
    car = foreign(text="Export, WhatsApp", vat_deductible=True, seller="private", detailed=False, market_median=20000)
    assert valuation.flags_of(car) == [
        "sumnjivo jeftin, možda prevara ili skriven kvar",
        "WhatsApp u oglasu, čest znak prevare",
        "prodaje se firmama ili za izvoz, bez garancije",
        "u ceni je PDV, za izvoz traži cenu bez PDV-a",
        "privatni prodavac",
        "nismo otvorili oglas, opis i slike nisu pregledani",
    ]
    assert valuation.PHOTOS_UNREAD_FLAG == "slike nisu pregledane, pogledaj ih u oglasu"


# --- 26.11.2026, Ogi: an older generation and the side before a facelift are priced on their own ads -------------

X3 = next(model for model in models.MODELS if model["as24"] == "bmw/x3")


def x3_ad(price, year, title="BMW X3 xDrive18d"):
    return comp(price, year=year, model="X3", title=title, tags=[], cc=1995, kw=105, body="suv", drive="4x4")


# The xDrive18d has 105 kW in both generations, so only the generation keeps the ads apart.
X3_ADS = [x3_ad(5500, 2009), x3_ad(5800, 2009), x3_ad(6000, 2009),
          x3_ad(6300, 2010, "BMW X3 E83 xDrive18d"), x3_ad(9900, 2010, "BMW X3 F25 xDrive18d"),
          x3_ad(9800, 2010),                                        # 2010 without a code: E83 or F25
          x3_ad(10000, 2011), x3_ad(10500, 2011), x3_ad(11000, 2011)]


def x3(year):
    return foreign(make="BMW", model="X3", year=year, cc=1995, kw=105, body="suv", drive="4x4",
                   title="BMW X3 xDrive18d", url="u")


def test_ogis_older_x3_e83_of_2010_is_priced_on_e83_ads_not_as_the_newer_f25():
    """Ogi 26.11.2026: "kad bi nam naso onog bmwa sto je stariji model od naseg, onaj do 2010 ... taj bmw tipa 5k
    eura a nas 10k, i ovaj ga upise u 10k value". The table had only the F25 from 2010; most 2010 X3 are E83."""
    car = x3(2010)
    generation = valuation.generation_of(car, X3)
    assert generation["name"] == "X3 E83"
    snapshot = scan.snapshot_of(X3, generation, "diesel")
    assert snapshot == ("BMW", "X3", 2009, 2010, "diesel")
    matched = scan.comparables_for({snapshot: X3_ADS}, car, X3)
    assert sorted(ad["price"] for ad in matched) == [5500, 5800, 6000, 6300]
    serbia = valuation.serbian_price(car, matched)
    assert serbia["anchor"] == 5885 and serbia["price"] == 5355   # 5,500 of 2009 raised 7%, then the 9% cut
    assert valuation.new_price_of(car, X3) == 34000               # the carina of an E83, not of an F25


def test_x3_f25_of_2011_leaves_out_the_2010_ads_that_mix_both_generations():
    car = x3(2011)
    generation = valuation.generation_of(car, X3)
    assert generation["name"] == "X3 F25"
    assert valuation.year_window(X3, 2011, generation) == (2011, 2012)
    matched = scan.comparables_for({scan.snapshot_of(X3, generation, "diesel"): X3_ADS}, car, X3)
    assert sorted(ad["price"] for ad in matched) == [10000, 10500, 11000]


def test_x3_f25_of_2010_named_in_the_title_uses_only_named_f25_ads_of_2010():
    car = dict(x3(2010), title="BMW X3 F25 xDrive18d")
    generation = valuation.generation_of(car, X3)
    matched = scan.comparables_for({scan.snapshot_of(X3, generation, "diesel"): X3_ADS}, car, X3)
    assert sorted(ad["price"] for ad in matched) == [9900, 10000, 10500, 11000]


def golf7_ad(price, year, title="Volkswagen Golf 7 2.0 TDI"):
    return comp(price, year=year, model="Golf 7", title=title, tags=[], cc=1968, kw=110)


# The Golf 7.5 was registered from 2017 (PA: no 2016 Golf 7 ad says 7.5). The 2.0 TDI kept its 110 kW, so only the
# facelift keeps these ads apart.
GOLF7_ADS = [golf7_ad(7500, 2016, "Volkswagen Golf 7.5 look 2.0 TDI"),   # a look-alike: a 2016 car is no 7.5
             golf7_ad(8000, 2016), golf7_ad(8300, 2017), golf7_ad(9600, 2017, "Volkswagen Golf 7.5 2.0 TDI"),
             golf7_ad(10000, 2018), golf7_ad(10400, 2019)]


@pytest.mark.parametrize("year,title,prices", [
    (2016, "VW Golf 2.0 TDI", [7500, 8000, 8300]),      # before: the unsaid 2017 ad stays, its cheapest decides
    (2016, "VW Golf 7.5 Look 2.0 TDI", [7500, 8000, 8300]),   # a facelift word before the facelift is a look-alike
    (2017, "VW Golf 2.0 TDI", [7500, 8000, 8300]),      # the facelift year without a word: the older, cheaper side
    (2017, "VW Golf 7.5 2.0 TDI", [9600, 10000]),        # the facelift year, named: the 7.5 ads only
    (2018, "VW Golf 2.0 TDI", [9600, 10000, 10400]),     # after: the unsaid 2017 ad may be from before the facelift
])
def test_golf_7_is_priced_on_ads_from_its_own_side_of_the_facelift(year, title, prices):
    car = foreign(year=year, title=title, cc=1968, kw=110)
    snapshot = scan.snapshot_of(GOLF, GOLF["generations"][1], "diesel")
    matched = scan.comparables_for({snapshot: GOLF7_ADS}, car, GOLF)
    assert sorted(ad["price"] for ad in matched) == prices


def test_golf_7_5_look_of_2016_is_not_priced_at_facelift_money():
    """Review 26.11.2026: a 2016 Golf titled "7.5 Look" was matched with the real 7.5 ads and priced too high."""
    snapshot = scan.snapshot_of(GOLF, GOLF["generations"][1], "diesel")
    plain = foreign(year=2016, title="VW Golf 2.0 TDI", cc=1968, kw=110)
    look = dict(plain, title="VW Golf 7.5 Look 2.0 TDI")
    look_ads = scan.comparables_for({snapshot: GOLF7_ADS}, look, GOLF)
    assert sorted(ad["price"] for ad in look_ads) == [7500, 8000, 8300]   # not the 9,600 and 10,000 of the real 7.5
    assert valuation.serbian_price(look, look_ads)["price"] == 6825      # 7,500 less the 9% sale cut
    plain_ads = scan.comparables_for({snapshot: GOLF7_ADS}, plain, GOLF)
    assert valuation.serbian_price(plain, plain_ads)["price"] == 6825


def test_speed_of_an_x3_e83_is_read_without_the_f25_and_unnamed_2010_ads():
    car = x3(2010)
    generation = valuation.generation_of(car, X3)
    ads = scan.speed_ads({scan.snapshot_of(X3, generation, "diesel"): X3_ADS}, car, X3)
    assert sorted(ad["price"] for ad in ads) == [5500, 5800, 6000, 6300]


def test_speed_of_a_golf_7_5_is_read_from_facelift_ads_only():
    car = foreign(year=2018, title="VW Golf 2.0 TDI", cc=1968, kw=110)
    snapshot = scan.snapshot_of(GOLF, GOLF["generations"][1], "diesel")
    assert sorted(ad["price"] for ad in scan.speed_ads({snapshot: GOLF7_ADS}, car, GOLF)) == [9600, 10000, 10400]


def test_generation_without_a_facelift_keeps_every_ad_of_its_years():
    car = foreign(model="Tiguan", year=2012, cc=1968, kw=103, body="suv", title="VW Tiguan 2.0 TDI")
    ads = [comp(price, year=year, model="Tiguan", title=title, tags=[], cc=1968, kw=103, body="suv")
           for price, year, title in ((9000, 2011, "VW Tiguan"), (9500, 2012, "VW Tiguan Facelift"),
                                      (9900, 2013, "VW Tiguan"))]
    snapshot = scan.snapshot_of(TIGUAN, TIGUAN["generations"][0], "diesel")
    assert [ad["price"] for ad in scan.comparables_for({snapshot: ads}, car, TIGUAN)] == [9000, 9500, 9900]
