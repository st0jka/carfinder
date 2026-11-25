"""Serbian import bill for a used passenger car (rules checked 24.11.2026).

In practice customs values the car from the AMSS catalogue: the Serbian new price of that model times a share
that falls with age, not what was paid (Kurir 04.02.2026, forwarders, paid cases 2021-2026). That is why the
bill depends on model and year. The invoice counts only when it is higher, so callers show that as a second number.
"""
import re
from datetime import date

EUR_RSD = 117.64          # Uprava carina weekly rate, 23-29.11.2026
WASTE_FEE_RSD_PER_KG = 14.58   # posebni tokovi otpada, from 1.1.2026
VAT = 0.20
DUTY_STANDARD = 0.125     # used petrol, diesel, hybrid, PHEV without preferential origin
DUTY_EV = 0.05            # used battery EV without preference
DOMESTIC_LEG_EUR = 120    # Subotica -> Pancevo, enters the VAT base

# Fixed paperwork in RSD; AMSS-CMV test is 21,000 until 31.12.2026, 31,800 after.
AMSS_TEST_PROMO_RSD = 21_000
AMSS_TEST_RSD = 31_800
AMSS_PROMO_UNTIL = date(2026, 12, 31)
ABS_CERTIFICATE_RSD = 4_000 + 430
AMSS_STICKER_RSD = 2_600
DATA_EXTRACT_RSD = 8_600  # needed when there is no COC; counted by default to stay on the safe side
BROKER_EUR = 100

# Share of the new price left after 0..10 full years (insurers' table used with the AMSS catalogue, class
# "diesel or over 1600 cc"); after year 10 it loses 0.2 points a month down to the 10% floor.
REMAINING_SHARE = (1.00, 0.80, 0.66, 0.56, 0.48, 0.41, 0.35, 0.30, 0.26, 0.23, 0.20)
SHARE_FLOOR = 0.10
SHARE_MONTHLY_AFTER_10 = 0.002
# Calibrated 24.11.2026 on three bills from Novky, a working importer: Golf 6 2011 about 1,250, Passat B7 2012
# about 1,300, Golf 7 2015 about 1,600 EUR. They fit the full catalogue value plus about 215 EUR of costs the
# listed fees do not cover (forwarder's real fee, plates, small charges).
CATALOGUE_FACTOR = 1.0
UNLISTED_COSTS_EUR = 215

# Seller-country VAT, used to get the net price from a VAT-deductible dealer.
SELLER_VAT = {"DE": 0.19, "AT": 0.20, "CH": 0.081, "IT": 0.22, "SI": 0.22, "HR": 0.25,
              "HU": 0.27, "CZ": 0.21, "SK": 0.23, "PL": 0.23, "NL": 0.21, "BE": 0.21, "FR": 0.20}

# Built outside EU/EFTA even though the brand is European (or the reverse). Lower-case model prefixes.
NON_EU_BUILT = {
    "bmw": ["x3", "x5", "x6", "x7"],   # X3 from 2010 (F25) Spartanburg US, G01 also Rosslyn ZA
    "mercedes-benz": ["ml", "m-klasse", "gle", "gls", "gl"],
    "volkswagen": ["tiguan allspace", "jetta", "atlas", "touareg"],  # Jetta MX; Touareg is SK (EU) from 2010
    "renault": ["koleos"],   # Busan, Korea
}
# Built in the EU only in some years: (make, model prefix): (first EU year, last EU year), None for open.
# A car without a year counts as built outside.
EU_BUILT_YEARS = {
    ("audi", "q5"): (None, 2016),        # Ingolstadt through 2016, then San José Chiapa, Mexico
    ("opel", "mokka"): (2015, None),     # Korea until 2014, then Zaragoza
    ("suzuki", "swift"): (None, 2016),   # Swift IV Esztergom HU; the Swift V of 2017 comes from Japan
    ("nissan", "micra"): (2018, None),   # K13 from India; K14 Flins FR from 2017
    ("ford", "ecosport"): (2018, None),  # India until 2017, then Craiova RO
}
EU_BUILT_ASIAN = {
    "hyundai": ["i30", "ix20", "ix35", "i20", "kona", "tucson"],  # ix35: Žilina/Nošovice, plus Korean imports
    "kia": ["ceed", "cee'd", "xceed", "proceed", "sportage", "venga"],  # Zilina SK
    "toyota": ["yaris", "aygo", "c-hr", "corolla", "auris", "avensis", "verso"],   # Verso: Adapazari TR
    "suzuki": ["vitara", "sx4 s-cross", "sx4-s-cross", "s-cross"],  # Esztergom HU; willhaben's "Sx4-s-cross"
    "nissan": ["micra"],  # Flins FR; Qashqai/Juke are UK-built (not EU)
}
NON_EU_BRANDS = {"tesla", "jeep", "chevrolet", "dodge", "chrysler", "cadillac", "lexus", "subaru",
                 "mitsubishi", "infiniti", "ssangyong", "isuzu", "mg", "byd", "lada", "mazda", "honda"}
ASIAN_BRANDS = set(EU_BUILT_ASIAN)

# 17 characters without I, O and Q. Volume makers end every VIN with serial digits, so a 17-letter German word
# ("Ausstattungspaket") is not taken for a VIN.
VIN_PATTERN = re.compile(r"\b[A-HJ-NPR-Z0-9]{13}[0-9]{4}\b")
LINK_PATTERN = re.compile(r"(https?://|www\.)\S+")   # an id in a link can look like a VIN
# ISO 3779 check digit: value of each character times the weight of its position, sum modulo 11 (10 is X).
VIN_VALUES = dict(zip("ABCDEFGHJKLMNPRSTUVWXYZ", (1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 7, 9, 2, 3, 4, 5, 6, 7, 8, 9)))
VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def eu_built(make, model, year=None):
    """Best guess whether the car was built in the EU/EFTA, so it can get 0% duty with an origin proof."""
    make = make.lower().strip()
    model = (model or "").lower().strip()
    if make == "tesla" and model.startswith("model y"):
        return True  # Model Y for Europe is built in Grünheide (DE) since 2022; older ones are Shanghai
    if make in NON_EU_BRANDS:
        return False
    for (table_make, prefix), (first, last) in EU_BUILT_YEARS.items():
        if make == table_make and model.startswith(prefix):
            if not year:
                return False
            return (first is None or year >= first) and (last is None or year <= last)
    if make in ASIAN_BRANDS:
        return any(model.startswith(m) for m in EU_BUILT_ASIAN[make])
    if make == "bmw" and model.startswith("x3") and year and year < 2010:
        return True  # E83 was built in Graz, Austria
    for prefix in NON_EU_BUILT.get(make, []):
        if model.startswith(prefix):
            return False
    return True


def vins_in(text):
    """Every VIN written in the ad (any case, links left out), in order."""
    text = LINK_PATTERN.sub(" ", text or "")
    for found in VIN_PATTERN.finditer(text.upper()):
        vin = found.group(0)
        if any(char.isalpha() for char in vin[:3]):   # a maker code always holds a letter; 17 digits is a phone
            yield vin


def find_vin(text):
    """The first VIN written in the ad, or None."""
    return next(vins_in(text), None)


def check_digit(vin):
    total = 0
    for char, weight in zip(vin, VIN_WEIGHTS):
        value = int(char) if char.isdigit() else VIN_VALUES[char]
        total += value * weight
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def non_eu_vin(text):
    """The first VIN in the ad from a plant outside the EU, or None. Its 9th character must be the check digit
    (compulsory in North America and China) or the Z European-market VINs carry there, so a run-together word
    and year ("Erstzulassung2019") or a code in a link is not taken for a VIN that adds duty.
    shortcut: a Japanese, Korean or UK VIN without a check digit is missed and make and model decide."""
    for vin in vins_in(text):
        if not vin_eu_built(vin) and vin[8] in ("Z", check_digit(vin)):
            return vin
    return None


def vin_eu_built(vin):
    """The VIN's first characters name the region the maker registered its code in, usually the plant's: T to Z
    is Europe; under S only SN to SZ, because SA to SM is the UK. Everything else (1-5 North America, 3 is
    Mexico, J, K, L, M ...) is outside."""
    first, second = vin[0], vin[1]
    if "T" <= first <= "Z":
        return True
    return first == "S" and "N" <= second <= "Z"


def duty_rate(make, model, fuel, origin_proof=True, eu=None):
    """origin_proof=False means the customs firm cannot get EUR.1 / invoice declaration, so duty is paid.
    eu is what the car itself shows (its VIN); None leaves it to the make and model."""
    if eu is None:
        eu = eu_built(make, model)
    if origin_proof and eu:
        return 0.0
    if fuel == "electric":
        return DUTY_EV
    return DUTY_STANDARD


def net_price(gross_eur, country, vat_deductible):
    """A dealer that shows deductible VAT sells for export without it; private and margin-scheme cars stay gross."""
    if not vat_deductible:
        return gross_eur
    return gross_eur / (1 + SELLER_VAT.get(country, 0.0))


def fixed_costs_eur(today=None):
    today = today or date.today()
    test = AMSS_TEST_PROMO_RSD if today <= AMSS_PROMO_UNTIL else AMSS_TEST_RSD
    rsd = test + ABS_CERTIFICATE_RSD + AMSS_STICKER_RSD + DATA_EXTRACT_RSD
    return rsd / EUR_RSD + BROKER_EUR


def remaining_share(months_old):
    """Part of the new price a car still has in the catalogue at this age."""
    months_old = max(0, months_old)
    years, extra_months = divmod(months_old, 12)
    if years >= 10:
        return max(SHARE_FLOOR, REMAINING_SHARE[10] - SHARE_MONTHLY_AFTER_10 * (months_old - 120))
    step = REMAINING_SHARE[years] - REMAINING_SHARE[years + 1]
    return REMAINING_SHARE[years] - step * extra_months / 12


def catalogue_value(new_price_eur, year, month=None, today=None):
    """What customs takes as the car's value: new price x age share x factor. Month unknown counts as June."""
    today = today or date.today()
    months_old = (today.year - year) * 12 + today.month - (month or 6)
    return new_price_eur * remaining_share(months_old) * CATALOGUE_FACTOR


def catalogue_bill(new_price_eur, year, month, mass_kg, duty, today=None):
    """The bill an importer really pays for this model and age (what Bane calls "carina")."""
    bill = import_bill(catalogue_value(new_price_eur, year, month, today), mass_kg, duty, today)
    bill["fixed"] += UNLISTED_COSTS_EUR
    bill["total"] += UNLISTED_COSTS_EUR
    return bill


def import_bill(customs_value_eur, mass_kg, duty, today=None):
    """Everything paid to clear, test and paper the car, for the value customs works from."""
    duty_eur = customs_value_eur * duty
    waste_eur = mass_kg * WASTE_FEE_RSD_PER_KG / EUR_RSD
    vat_eur = VAT * (customs_value_eur + duty_eur + waste_eur + DOMESTIC_LEG_EUR)
    fixed_eur = fixed_costs_eur(today)
    return {
        "duty": round(duty_eur),
        "waste_fee": round(waste_eur),
        "vat": round(vat_eur),
        "fixed": round(fixed_eur),
        "total": round(duty_eur + waste_eur + vat_eur + fixed_eur),
    }
