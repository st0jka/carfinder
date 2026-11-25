from datetime import date

import pytest

from carfinder import customs, transport

DEC_2026 = date(2026, 12, 1)


def bill_for(price, border_transport, mass, duty):
    return customs.import_bill(price + border_transport, mass, duty, today=DEC_2026)["total"]


@pytest.mark.parametrize("price", [3000, 4000, 4500])
def test_eu_car_3_to_6k_matches_banes_range(price):
    # Bane: 1200-1600e for EU cars costing 3-6k (Vienna transport 500).
    assert 1200 <= bill_for(price, 500, 1400, 0.0) <= 1700


def test_tesla_s_2015_about_4000():
    rate = customs.duty_rate("Tesla", "Model S", "electric")
    assert rate == customs.DUTY_EV
    assert 3800 <= bill_for(12500, 700, 2150, rate) <= 4300


def test_no_origin_proof_adds_duty_and_vat_on_it():
    with_proof = bill_for(5000, 500, 1400, 0.0)
    without = bill_for(5000, 500, 1400, customs.duty_rate("Volkswagen", "Golf", "diesel", origin_proof=False))
    assert without - with_proof == pytest.approx(5500 * 0.125 * 1.2, abs=2)


def test_promo_test_price_ends_after_2026():
    assert customs.fixed_costs_eur(date(2027, 1, 2)) - customs.fixed_costs_eur(DEC_2026) == pytest.approx(
        10_800 / customs.EUR_RSD)


@pytest.mark.parametrize("make,model,expected", [
    ("Volkswagen", "Golf", True),
    ("Volkswagen", "Tiguan", True),
    ("Volkswagen", "Tiguan Allspace", False),
    ("BMW", "X5", False),
    ("BMW", "X3", False),        # F25 (2010-2017) Spartanburg, US; G01 also Rosslyn, South Africa
    ("BMW", "X1", True),         # E84 Leipzig
    ("BMW", "520", True), ("BMW", "320", True),
    ("Hyundai", "iX35", True),   # Nošovice, Czechia (AutoScout24 writes "iX35")
    ("Hyundai", "Ix35", True),   # willhaben: the path name
    ("Hyundai", "Tucson", True), ("Kia", "Sportage", True),
    ("Mercedes-Benz", "B 180", True), ("Mercedes-Benz", "C 220", True),   # C W205 for Europe: Bremen; a US or ZA VIN decides
    ("Citroën", "Grand C4 Picasso", True), ("Ford", "Kuga", True), ("Opel", "Insignia", True), ("Audi", "A6", True),
    ("Mercedes-Benz", "GLE 350", False),
    ("Audi", "Q5", False),
    ("Audi", "A4", True),
    ("Tesla", "Model S", False),
    ("Tesla", "Model Y", True),
    ("Kia", "Ceed", True),
    ("Kia", "Sorento", False),
    ("Toyota", "RAV4", False),
    ("Mazda", "3", False),
    ("Skoda", "", True),
])
def test_eu_built(make, model, expected):
    assert customs.eu_built(make, model) is expected


@pytest.mark.parametrize("make,model,year,expected", [
    ("Audi", "Q5", 2016, True), ("Audi", "Q5", 2017, False),
    ("BMW", "X3", 2009, True), ("BMW", "X3", 2010, False),
])
def test_suv_origin_changes_when_production_leaves_the_eu(make, model, year, expected):
    assert customs.eu_built(make, model, year) is expected


@pytest.mark.parametrize("make,model,year,expected", [
    ("Opel", "Mokka", 2014, False), ("Opel", "Mokka X", 2015, True), ("Opel", "Mokka", None, False),   # Korea, Zaragoza
    ("Suzuki", "Swift", 2016, True), ("Suzuki", "Swift", 2017, False), ("Suzuki", "Swift", None, False),   # HU, Japan
    ("Nissan", "Micra", 2015, False), ("Nissan", "Micra", 2018, True),     # K13 India, K14 Flins
    ("Ford", "EcoSport", 2017, False), ("Ford", "EcoSport", 2018, True),   # India, then Craiova
    ("Ford", "Focus", None, True),                                          # the table touches only its models
    ("Renault", "Koleos", 2019, False), ("Renault", "Kadjar", 2019, True),   # Busan, Palencia
    ("Suzuki", "SX4 S-Cross", 2016, True), ("Suzuki", "Sx4-s-cross", 2016, True),   # AutoScout24, willhaben
    ("Toyota", "Verso", 2014, True), ("Toyota", "C-hr", 2018, True),       # Turkey: free-trade agreement
    ("Kia", "Rio", 2015, False), ("Honda", "Civic", 2015, False), ("Mitsubishi", "ASX", 2015, False),
    ("Nissan", "Qashqai", 2015, False), ("Seat", "Leon", 2015, True), ("Dacia", "Duster", 2015, True),
])
def test_origin_of_the_daily_models(make, model, year, expected):
    assert customs.eu_built(make, model, year) is expected


def test_net_price_only_for_vat_deductible_dealer():
    assert customs.net_price(11900, "DE", True) == pytest.approx(10000)
    assert customs.net_price(11900, "DE", False) == 11900
    assert customs.net_price(10810, "CH", True) == pytest.approx(10000)
    assert customs.net_price(5000, "XX", True) == 5000


def test_known_routes_use_banes_prices():
    assert transport.transport_eur("AT", "1100", "Wien") == 620
    assert transport.transport_eur("DE", "60311", "Frankfurt") == 820
    assert transport.transport_eur("DE", "60311", "Frankfurt", large_car=True) == 970
    assert transport.transport_eur("CH", "8001", "Zürich") == 820


def test_size_surcharge_only_applies_to_the_quoted_frankfurt_route():
    assert transport.transport_eur("DE", "60311", "Frankfurt am Main", large_car=True) == 970
    assert transport.transport_eur("AT", "1100", "Wien", large_car=True) == 620
    assert transport.transport_eur("CH", "8001", "Zürich", large_car=True) == 820
    assert transport.transport_eur("AT", "4200", "Linz", large_car=True) == transport.transport_eur("AT", "4200", "Linz")


def test_distance_estimate_is_close_to_known_routes():
    # Unknown city in the Frankfurt and Vienna postcode regions should land near Bane's quotes.
    assert 750 <= transport.transport_eur("DE", "65000", "Wiesbaden") <= 900
    assert 560 <= transport.transport_eur("AT", "1230", "Liesing") <= 680


def test_unknown_country_gives_none():
    assert transport.transport_eur("XX") is None
    assert transport.road_km("XX") is None


def test_1250_km_limit_keeps_south_and_cuts_far_north():
    for country, zip_code in [("DE", "6"), ("DE", "8"), ("AT", "6"), ("CH", "8")]:
        assert transport.road_km(country, zip_code) <= transport.MAX_DISTANCE_KM
    assert transport.road_km("DE", "2") > transport.MAX_DISTANCE_KM  # Hamburg region


# --- catalogue value (24.11.2026: customs works from the AMSS catalogue, not the invoice) ----------------------

@pytest.mark.parametrize("months,share", [
    (0, 1.00), (12, 0.80), (18, 0.73), (60, 0.41), (120, 0.20), (125, 0.19), (170, 0.10), (300, 0.10), (-5, 1.00)])
def test_remaining_share_by_age(months, share):
    assert customs.remaining_share(months) == pytest.approx(share, abs=0.001)


def test_catalogue_value_depends_on_model_and_age_not_on_price_paid():
    nov_2026 = date(2026, 11, 24)
    old_golf = customs.catalogue_value(21066, 2011, 6, nov_2026)       # Golf 6 1.6 TDI, at the 10% floor
    assert old_golf == pytest.approx(21066 * 0.10 * customs.CATALOGUE_FACTOR, abs=1)
    newer = customs.catalogue_value(22500, 2015, 6, nov_2026)          # Golf 7: 11 years 5 months -> 16.6%
    assert newer == pytest.approx(22500 * 0.166 * customs.CATALOGUE_FACTOR, abs=15)
    assert customs.catalogue_value(22500, 2015, None, nov_2026) == newer   # unknown month counts as June


@pytest.mark.parametrize("name,new_price,year,mass,novky", [
    ("Golf 6 2011", 21066, 2011, 1320, 1250), ("Passat B7 2012", 23549, 2012, 1550, 1300),
    ("Golf 7 2015", 22500, 2015, 1300, 1600)])
def test_catalogue_bill_matches_novkys_real_bills(name, new_price, year, mass, novky):
    """Three bills a working importer gave on 24.11.2026; the model has to land within 60 EUR of each."""
    bill = customs.catalogue_bill(new_price, year, 6, mass, 0.0, date(2026, 11, 24))
    assert abs(bill["total"] - novky) <= 60, (name, bill)


def test_catalogue_bill_total_is_the_sum_of_its_parts():
    bill = customs.catalogue_bill(22500, 2015, 6, 1300, 0.125, date(2026, 11, 24))
    assert bill["total"] == pytest.approx(bill["duty"] + bill["waste_fee"] + bill["vat"] + bill["fixed"], abs=2)
    assert bill["duty"] > 0


def test_tesla_model_s_2015_is_near_banes_4000():
    bill = customs.catalogue_bill(80000, 2015, 6, 2100, customs.DUTY_EV, date(2026, 11, 24))
    assert 3600 <= bill["total"] <= 4700


# --- VIN: where the car was built (24.11.2026) ----------------------------------------

@pytest.mark.parametrize("text,vin", [
    ("FIN: WVWZZZ1KZBW123456 Scheckheft", "WVWZZZ1KZBW123456"),
    ("fin wvwzzz1kzbw123456", "WVWZZZ1KZBW123456"),                 # lower case
    ("WVWZZZ1KZBW12345", None),                                     # 16 characters
    ("WVWZZZ1KZBW1234567", None),                                   # 18 characters
    ("WVWZZZ1KZIW123456", None),                                    # I, O and Q never appear in a VIN
    ("WVWZZZ1KZOW123456", None),
    ("WVWZZZ1KZQW123456", None),
    ("Ausstattungspaket", None),                                    # a 17-letter word
    ("Tel 00491701234567890", None),                                # 17 digits
    ("", None),
    (None, None),
])
def test_find_vin(text, vin):
    assert customs.find_vin(text) == vin


@pytest.mark.parametrize("vin,eu", [
    ("WVWZZZ1KZBW123456", True),     # Germany
    ("TMBJJ7NE5F0123456", True),     # Czech Republic (Skoda)
    ("VF3MCYHZRHS123456", True),     # France
    ("ZFA31200000123456", True),     # Italy
    ("SUPERB12345678901", True),     # SU: Poland
    ("SNTU123456789A123", True),     # SN: Germany (former GDR plants)
    ("SALGA2BE7HA123456", False),    # SA: UK
    ("SMT123456789A1234", False),    # SM: still UK
    ("3VWZZZ1KZBM123456", False),    # Mexico (Puebla)
    ("1G1BE5SM0H7123456", False),    # USA
    ("JTDKB20U793123456", False),    # Japan
    ("KMHD841CBJU123456", False),    # Korea
    ("LVSHCAMB0EE123456", False),    # China
])
def test_vin_eu_built(vin, eu):
    assert customs.vin_eu_built(vin) is eu


@pytest.mark.parametrize("text,vin", [
    ("FIN: 3VWZZZ1KZBM123456", "3VWZZZ1KZBM123456"),              # Mexico for Europe: Z where the check digit goes
    ("vin 1hgcm82633a004352", "1HGCM82633A004352"),               # USA, valid check digit, lower case
    ("1HGCM82643A004352", None),                                  # USA with a wrong check digit
    ("WVWZZZ1KZBW123456", None),                                  # Germany: not outside the EU
    ("SALGA2BE7HA123456", None),                                  # UK without a check digit: make and model decide
    ("ausstattungen2019", None),                                  # a word run into a year
    ("Erstzulassung2019", None),
    ("https://www.example.de/ad/AB123456789012345", None),         # an id in a link
    ("www.example.de/AB123456789012345", None),
    ("AB123456789012345", "AB123456789012345"),                   # the same id outside a link passes its digit
    ("Tel00491701234567 FIN 3VWZZZ1KZBM123456", "3VWZZZ1KZBM123456"),   # a European-looking token first
    ("", None),
    (None, None),
])
def test_non_eu_vin(text, vin):
    assert customs.non_eu_vin(text) == vin


def test_check_digit():
    assert customs.check_digit("1HGCM82633A004352") == "3"
    assert customs.check_digit("1M8GDM9AXKP042788") == "X"   # remainder 10 is written X


def test_duty_rate_takes_what_the_car_itself_shows():
    assert customs.duty_rate("Volkswagen", "Golf", "diesel", eu=False) == customs.DUTY_STANDARD
    assert customs.duty_rate("Volkswagen", "Tiguan Allspace", "diesel", eu=True) == 0.0
    assert customs.duty_rate("Volkswagen", "Golf", "diesel", origin_proof=False, eu=True) == customs.DUTY_STANDARD
    assert customs.duty_rate("Volkswagen", "Golf", "diesel") == 0.0          # no VIN: make and model decide
