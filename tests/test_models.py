import re

import pytest

from carfinder import customs, models, scan, valuation

GOLF = models.MODELS[0]
PASSAT = models.MODELS[2]
TIGUAN = models.MODELS[3]
A4 = models.MODELS[7]


# --- four-wheel drive from the seller's words ------------------------------------

@pytest.mark.parametrize("text", ["Volkswagen Tiguan 2.0 TDI DPF 4Motion DSG", "Audi A4 Avant 2.0 TDI QUATTRO",
                                  "Octavia Combi 4x4 2.0 TDI", "4×4 automatik zahnriemen gemacht",
                                  "Superb 2.0 TDI Allrad", "Škoda Octavia Scout", "Passat Alltrack 2.0 TDI",
                                  "Peugeot 3008 Hybrid4", "ABS, Four wheel drive", "All-wheel drive"])
def test_four_wheel_drive_words(text):
    assert models.drive_of(text) == "4x4"


@pytest.mark.parametrize("text", ["Volkswagen Golf 7 1.6 TDI", "Tiguan 2.0 TDI R-Line", "Front wheel drive", "", None])
def test_text_without_a_four_wheel_drive_word(text):
    assert models.drive_of(text) is None


@pytest.mark.parametrize("text", [
    "VW Tiguan 2.0 TDI 4 Motion", "VW Tiguan R-Line 2.0TDI 4 Motion",          # willhaben, live run 24.11.2026
    "Volkswagen Tiguan Sport 1.4 TSI 4-Motion / AHK", "Volkswagen Tiguan TEAM 4Mot 2.0TDI*Tempo Navi",   # AutoScout24
    "Volkswagen Tiguan 2.0 TDI  4 x 4 (može zamena)", "Volkswagen Tiguan 2.0 TDI/4 MOTION/",             # PA
    "Volkswagen Tiguan Allspace TiguanAllspaceHighl4Motion", "Volkswagen Tiguan 2.0TDI4X4 DSG PANO",     # glued
])
def test_four_wheel_drive_in_the_spellings_sellers_use(text):
    assert models.drive_of(text) == "4x4"


@pytest.mark.parametrize("text", ["Inserat auch bei AutoScout24 zu finden", "autoscout24.de", "Pfadfinder (Scouts)",
                                  "Škoda Octavia Scoutline 2.0 TDI"])
def test_scout_counts_only_as_a_whole_word(text):
    assert models.drive_of(text) is None


# --- sub-models ---------------------------------------------------------------------

@pytest.mark.parametrize("title,name", [
    ("Volkswagen Golf Plus 1.6 TDI", "golf plus"), ("VW GolfPlus", "golf plus"),
    ("Volkswagen Golf Sportsvan 1.6 TDI", "sportsvan"),
    ("Škoda Octavia Scout 2.0 TDI", "scout"),
    ("Volkswagen Polo Cross 1.6 TDI", "cross"), ("VW CrossPolo", "cross"), ("Volkswagen Cross Golf", "cross"),
    ("Volkswagen Passat Alltrack 2.0 TDI", "alltrack"),
    ("Volkswagen Tiguan Allspace 2.0 TDI", "allspace"),
    ("Škoda Octavia RS 2.0 TDI", "rs"), ("Skoda Octavia vRS", "rs"),
    ("Volkswagen Golf 7 GTD", "gtd"), ("Volkswagen Golf GTI", "gti"),
])
def test_sub_model_named_in_the_title(title, name):
    assert models.sub_model(title) == name


@pytest.mark.parametrize("title", ["Volkswagen Golf 7 1.6 TDI", "Volkswagen Tiguan R-Line", "Volkswagen Tiguan R line",
                                   "Peugeot 3008 Crossway", "Audi A3 Sportback", "Škoda Octavia Kurs 2.0",
                                   "Volkswagen Golf Comfortline Plus", "", None])
def test_base_model_and_trims_are_no_sub_model(title):
    assert models.sub_model(title) is None


# --- Passat B7 ------------------------------------------------------------------------

def test_passat_b7_starts_in_2011():
    assert [g["name"] for g in models.generations_for(PASSAT, 2010)] == ["Passat B6"]
    assert [g["name"] for g in models.generations_for(PASSAT, 2011)] == ["Passat B7"]
    assert [g["name"] for g in models.generations_for(PASSAT, 2013)] == ["Passat B7"]
    assert valuation.year_window(PASSAT, 2011) == (2011, 2012)   # never compared with 2010 ads


# --- a generation the seller names in the title (Novky 24.11.2026) -----------------------

@pytest.mark.parametrize("model,title,name", [
    (PASSAT, "Volkswagen Passat B6 1.4 TSI EcoFuel", "Passat B6"),
    (PASSAT, "VW Passat Variant b7 2.0 TDI", "Passat B7"),
    (GOLF, "VW Golf 6 1.6 TDI", "Golf 6"), (GOLF, "VW Golf6 GTD", "Golf 6"), (GOLF, "VW Golf Mk6 GTD", "Golf 6"),
    (GOLF, "VW Golf IV 1.9 TDI", "Golf 4"), (GOLF, "VW Golf V GT", "Golf 5"), (GOLF, "VW Golf VI 1.6 TDI", "Golf 6"),
    (GOLF, "VW Golf VII Highline", "Golf 7"), (GOLF, "VW Golf VIII 2.0 TDI", "Golf 8"),
    (GOLF, "VW Golf 4 4Motion 1.9 TDI", "Golf 4"),
    (A4, "Audi A4 B8 Avant 2.0 TDI", "A4 B8"),
])
def test_generation_named_in_the_title_in_the_models_own_naming(model, title, name):
    assert models.named_generation(model, title) == name


@pytest.mark.parametrize("model,title", [
    (PASSAT, "VW Passat 2.0 TDI, Inserat auch bei AutoScout24"), (PASSAT, "Passat 1.4 TSI Delle an der B-Säule"),
    (PASSAT, "VW Passat 2.0 TDI ABS ESP"), (A4, "Audi A4 Avant B-Säule ABS AutoScout24"),
    (GOLF, "VW Golf 1.6 TDI ABS AutoScout24"), (GOLF, "VW Golf Variant 1.6 TDI"),
    (GOLF, "VW Golf 4 Motion 2.0 TDI"), (GOLF, "VW Golf 4-Motion Highline"),   # four-wheel drive, not a Golf 4
    (TIGUAN, "VW Tiguan B6"),                                                  # a model without named generations
    (GOLF, ""), (GOLF, None),
])
def test_title_without_a_generation_name(model, title):
    assert models.named_generation(model, title) is None


# --- models added from the margin screen (24.11.2026) ------------------------------------

MODEL = {model["as24"]: model for model in models.MODELS}
INSIGNIA = MODEL["opel/insignia"]
AS24_PATH = re.compile(r"^[a-z]+(-[a-z]+)*/[a-z0-9]+(-[a-z0-9]+)*$")   # "volkswagen/golf", "mercedes-benz/b-klasse"


def test_every_model_has_a_unique_autoscout24_path_in_the_sites_format():
    paths = [model["as24"] for model in models.MODELS]
    assert len(paths) == len(set(paths)) == 138
    assert (len(models.CORE_MODELS), len(models.DAILY_MODELS)) == (20, 118)
    for path in paths:
        assert AS24_PATH.match(path), path


def test_every_generation_has_what_the_scan_and_the_carina_need():
    for model in models.MODELS:
        assert model["make"] and 900 <= model["mass"] <= 2500   # up!, Twingo and Fiat 500: 950 kg
        for generation in model["generations"]:
            first, last = generation["years"]
            assert 2003 <= first <= last <= 2024, generation["name"]
            assert generation["pa_model"] and all(models.pa_names(generation["pa_model"]))
            # Sandero II and Panda 169 are new under 10,000
            assert 8000 <= generation["new_price"] <= generation.get("new_price_estate", generation["new_price"])
            assert " " in generation["name"]   # model and generation code; the page shows the model part


def test_generations_of_one_model_overlap_only_in_their_change_over_years():
    for model in models.MODELS:
        years = sorted(generation["years"] for generation in model["generations"])
        for (first_old, last_old), (first_new, last_new) in zip(years, years[1:]):
            # the Golf 6 was still registered in 2013 while the Golf 7 started in 2012
            assert last_old - 1 <= first_new and first_old < first_new and last_old < last_new, model["as24"]


@pytest.mark.parametrize("as24,year,names", [
    ("bmw/x1", 2010, ["X1 E84"]), ("bmw/x1", 2015, ["X1 E84", "X1 F48"]), ("bmw/x1", 2016, ["X1 F48"]),
    ("bmw/x1", 2022, ["X1 F48"]), ("bmw/x1", 2023, []),
    ("bmw/520", 2010, ["520d F10"]), ("bmw/520", 2016, ["520d F10"]), ("bmw/520", 2017, ["520d G30"]),
    ("bmw/520", 2023, ["520d G30"]), ("bmw/520", 2024, []),
    ("bmw/3er", 2011, ["3er E90"]), ("bmw/3er", 2012, []), ("bmw/3er", 2013, ["3er F30"]),
    ("bmw/3er", 2018, ["3er F30"]), ("bmw/3er", 2019, ["3er G20"]),
    ("audi/a6", 2010, ["A6 C6"]), ("audi/a6", 2011, ["A6 C6", "A6 C7"]), ("audi/a6", 2017, ["A6 C7"]),
    ("audi/a6", 2018, ["A6 C8"]),
    ("opel/insignia", 2010, ["Insignia A"]), ("opel/insignia", 2016, ["Insignia A"]),
    ("opel/insignia", 2017, ["Insignia A", "Insignia B"]), ("opel/insignia", 2022, ["Insignia B"]),
    ("opel/insignia", 2023, []),
    ("mercedes-benz/b-klasse", 2011, ["B-Klasse W245"]), ("mercedes-benz/b-klasse", 2012, ["B-Klasse W246"]),
    ("mercedes-benz/b-klasse", 2018, ["B-Klasse W246"]), ("mercedes-benz/b-klasse", 2019, ["B-Klasse W247"]),
    ("ford/kuga", 2012, ["Kuga I"]), ("ford/kuga", 2013, ["Kuga II"]), ("ford/kuga", 2019, ["Kuga II"]),
    ("ford/kuga", 2020, ["Kuga III"]),
    ("hyundai/ix35", 2010, ["ix35 LM"]), ("hyundai/ix35", 2015, ["ix35 LM"]), ("hyundai/ix35", 2016, []),
])
def test_generation_lookup_of_the_added_models(as24, year, names):
    assert [generation["name"] for generation in models.generations_for(MODEL[as24], year)] == names


@pytest.mark.parametrize("as24,years", [
    ("bmw/x1", (2010, 2022)), ("bmw/520", (2010, 2023)), ("bmw/3er", (2010, 2024)), ("audi/a6", (2010, 2024)),
    ("opel/insignia", (2010, 2022)), ("mercedes-benz/b-klasse", (2010, 2024)),
    ("ford/kuga", (2010, 2024)), ("hyundai/ix35", (2010, 2015)),
])
def test_added_models_are_searched_only_in_their_priced_years(as24, years):
    assert scan.search_years(MODEL[as24]) == years


@pytest.mark.parametrize("pa_model,names", [
    ("Golf 7", ["Golf 7"]), ("X1", ["X1"]), ("520", ["520"]),
    ("316/318/320", ["316", "318", "320"]), ("B 180/B 200", ["B 180", "B 200"]),
    ("C4 Picasso/C4 Grand Picasso", ["C4 Picasso", "C4 Grand Picasso"]),
])
def test_pa_names_of_one_generation(pa_model, names):
    assert models.pa_names(pa_model) == names


@pytest.mark.parametrize("as24,pa_names", [
    ("bmw/x1", ["X1"]), ("bmw/520", ["520"]), ("bmw/3er", ["316", "318", "320"]), ("audi/a6", ["A6"]),
    ("opel/insignia", ["Insignia"]), ("mercedes-benz/b-klasse", ["B 180", "B 200"]),
    ("ford/kuga", ["Kuga"]), ("hyundai/ix35", ["ix35"]),
])
def test_added_models_use_the_names_pa_lists_them_under(as24, pa_names):
    for generation in MODEL[as24]["generations"]:
        assert models.pa_names(generation["pa_model"]) == pa_names


def test_mpvs_are_large_and_taken_as_vans_before_their_details():
    b_klasse = MODEL["mercedes-benz/b-klasse"]
    assert b_klasse["body"] == "van" and b_klasse["large"]
    assert "body" not in GOLF and "body" not in MODEL["bmw/x1"]


@pytest.mark.parametrize("text", ["BMW X1 xDrive 18d", "BMW 320d x-Drive Touring", "Mercedes B 220 CDI 4MATIC",
                                  "Hyundai iX35 2.0 CRDi AWD Premium", "Ford Kuga 2.0 TDCi 4WD Titanium"])
def test_four_wheel_drive_words_of_the_added_makes(text):
    assert models.drive_of(text) == "4x4"


@pytest.mark.parametrize("text", ["BMW X1 sDrive 18d", "Ford Kuga 2.0 TDCi FWD", "Hyundai iX35 1.7 CRDi 2WD"])
def test_two_wheel_drive_words_of_the_added_makes(text):
    assert models.drive_of(text) is None


@pytest.mark.parametrize("text", ["VW Golf mit Anhängevorrichtung", "Passat, Rawdon", "Audi A4, AXDrive",
                                  "Corsa, 4WDemo", "Polo, kein XDriveX"])
def test_new_drive_badges_do_not_match_inside_words(text):
    assert models.drive_of(text) is None


@pytest.mark.parametrize("title,name", [
    ("BMW Gran Turismo 320d xDrive Gran Turismo Aut.", "gran turismo"), ("BMW 318d GT Aut.", "gran turismo"),
    ("BMW 318 D GT*CLIMATIC*BC*NAVI", "gran turismo"), ("BMW 520 GT (može zamena)", "gran turismo"),
    ("BMW 3er GranTurismo", "gran turismo"),
    ("Opel Insignia Country Tourer 2.0 CDTI", "country tourer"), ("Opel Insignia COUNTRY", "country tourer"),
])
def test_sub_models_of_the_added_models(title, name):
    assert models.sub_model(title) == name


@pytest.mark.parametrize("title", ["BMW Touring 320d Touring", "BMW 520d Touring Luxury Line", "BMW X1 sDrive18d",
                                   "Opel Insignia Sports Tourer 2.0 CDTI",
                                   "Peugeot 3008 GT Line 2.0 BlueHDi", "Mercedes-Benz B 180 CDI"])
def test_base_models_and_trims_of_the_added_models(title):
    assert models.sub_model(title) is None


@pytest.mark.parametrize("title", ["VW Golf 150 GT Sport", "Audi A4 Country of origin Germany", "BMW 320d GT-Line"])
def test_new_sub_models_do_not_match_unrelated_title_text(title):
    assert models.sub_model(title) is None


@pytest.mark.parametrize("path,year,title,expected", [
    ("bmw/x1", 2015, "BMW X1 F48 sDrive18d", "X1 F48"),
    ("bmw/x1", 2015, "BMW X1 E84 xDrive18d", "X1 E84"),
    ("bmw/x1", 2014, "BMW X1 F48 sDrive18d", None),          # the F48 was not registered in 2014
    ("bmw/x1", 2022, "BMW X1 U11 sDrive18d", None),          # a generation the table does not hold
    ("bmw/520", 2010, "BMW 520d E60", None),
    ("bmw/520", 2016, "BMW 520d F11 Touring", "520d F10"),
    ("bmw/520", 2016, "BMW 520d F07", "520d F10"),
    ("bmw/3er", 2013, "BMW 318d E91", None),
    ("bmw/3er", 2011, "BMW 318d E91 Touring", "3er E90"),
    ("bmw/3er", 2018, "BMW 320d G20", None),
    ("bmw/3er", 2015, "BMW 320d F31 Touring", "3er F30"),
    ("bmw/3er", 2015, "BMW 320d F34", "3er F30"),
    ("audi/a6", 2011, "Audi A6 C6 2.0 TDI", "A6 C6"),
    ("audi/a6", 2012, "Audi A6 C6 2.0 TDI", None),           # the C6 ends in 2011
    ("audi/a6", 2011, "Audi A6 4G 2.0 TDI", "A6 C7"),
    ("audi/a6", 2011, "Audi A6 Android 4G C6", "A6 C6"),     # the C code is read before the 4G code
    ("audi/a6", 2012, "Audi A6 Android 4G C6", None),
    ("mercedes-benz/b-klasse", 2018, "Mercedes-Benz B 180 W247", None),
    ("mercedes-benz/b-klasse", 2019, "Mercedes-Benz B 180 W247", "B-Klasse W247"),
    ("ford/kuga", 2019, "Ford Kuga III 2.0 EcoBlue", None),
    ("ford/kuga", 2012, "Ford Kuga I 2.0 TDCi", "Kuga I"),
])
def test_explicit_chassis_codes_cannot_be_priced_as_the_wrong_generation(path, year, title, expected):
    generation = valuation.generation_of({"year": year, "title": title}, MODEL[path])
    assert (generation["name"] if generation else None) == expected


@pytest.mark.parametrize("title", ["BMW 320d F34", "BMW 520d F07", "BMW 3er GT"])
def test_bmw_gran_turismo_can_be_identified_by_its_chassis_or_series(title):
    assert models.sub_model(title) == "gran turismo"


@pytest.mark.parametrize("title,name", [("Opel Insignia A 2.0 CDTI", "Insignia A"),
                                        ("Opel Insignia B Sports Tourer", "Insignia B"),
                                        ("Opel Insignia 2.0 CDTI", None), ("Opel Insignia ST Business", None)])
def test_insignia_generation_named_in_the_title(title, name):
    assert models.named_generation(INSIGNIA, title) == name


@pytest.mark.parametrize("year,title,name", [
    (2017, "Opel Insignia 2.0 CDTI", None),               # change-over year without a name: not priced
    (2017, "Opel Insignia A 2.0 CDTI", "Insignia A"), (2017, "Opel Insignia B 2.0 CDTI", "Insignia B"),
    (2016, "Opel Insignia B 2.0 CDTI", None),             # the B was not registered in 2016
    (2018, "Opel Insignia 1.6 CDTI", "Insignia B"),
])
def test_insignia_generation_of_a_car(year, title, name):
    generation = valuation.generation_of({"year": year, "title": title}, INSIGNIA)
    assert (generation["name"] if generation else None) == name


def test_insignia_body_pillar_is_not_a_generation():
    assert models.named_generation(INSIGNIA, "Opel Insignia B-Säule beschädigt") is None
    assert models.named_generation(INSIGNIA, "Opel Insignia-B 2.0 CDTI") == "Insignia B"


def test_carina_of_an_estimated_estate_uses_its_estate_price():
    touring = {"year": 2014, "title": "BMW 520d Touring", "body": "estate"}
    assert valuation.new_price_of(touring, MODEL["bmw/520"]) == 40500
    assert valuation.new_price_of(dict(touring, body=None), MODEL["bmw/520"]) == 38700
    assert valuation.new_price_of({"year": 2014, "title": "BMW X1 xDrive18d"}, MODEL["bmw/x1"]) == 28000


def test_a6_hybrid_has_its_own_estimated_catalogue_price():
    car = {"year": 2014, "title": "Audi A6 2.0 TFSI hybrid", "fuel": "hybrid"}
    assert valuation.new_price_of(car, MODEL["audi/a6"]) == 48000
    assert valuation.new_price_of(dict(car, fuel="diesel"), MODEL["audi/a6"]) == 36500


# --- 25.11.2026: BMW 1er F20, a four-week trial ------------------------------------------

@pytest.mark.parametrize("year,names", [(2011, []), (2012, ["1er F20"]), (2018, ["1er F20"]), (2019, ["1er F40"])])
def test_1er_f20_covers_its_full_years_only(year, names):
    assert [generation["name"] for generation in models.generations_for(MODEL["bmw/1er"], year)] == names


def test_1er_is_searched_in_its_priced_years_under_its_pa_engine_names():
    assert scan.search_years(MODEL["bmw/1er"]) == (2012, 2024)
    assert models.pa_names(MODEL["bmw/1er"]["generations"][0]["pa_model"]) == ["116", "118", "120"]
    assert MODEL["bmw/1er"]["trial"] and "large" not in MODEL["bmw/1er"]


@pytest.mark.parametrize("year,title,expected", [
    (2015, "BMW 118d F20 Sport Line", "1er F20"),
    (2015, "BMW 116d F21 3-Türer", "1er F20"),
    (2012, "BMW 118d E87", None),
    (2018, "BMW 118d F40", None),
    (2015, "BMW 118d Advantage", "1er F20"),   # no chassis code: the year decides
])
def test_1er_chassis_codes_in_the_title(year, title, expected):
    generation = valuation.generation_of({"year": year, "title": title}, MODEL["bmw/1er"])
    assert (generation["name"] if generation else None) == expected


def test_1er_is_built_in_the_eu_and_valued_from_its_new_price():
    car = {"make": "BMW", "model": "1er", "year": 2015, "title": "BMW 118d", "fuel": "diesel", "body": "hatchback"}
    assert customs.eu_built("BMW", "1er", 2015)
    assert valuation.new_price_of(car, MODEL["bmw/1er"]) == 24500


# --- 25.11.2026: every generation that sells in Serbia (the daily models) -----------------------------------
# Frozen from the list checked on PA, AutoScout24 and willhaben on 25.11.2026: a changed row is a deliberate edit.

DAILY_TABLE = [
    # as24, searched years, [(generation, years, PA names, sells as petrol)]
    ("volkswagen/touran", (2010, 2024), [
        ("Touran I", (2010, 2015), ["Touran"], False),
        ("Touran II", (2015, 2024), ["Touran"], False)]),
    ("volkswagen/sharan", (2010, 2022), [
        ("Sharan II", (2010, 2022), ["Sharan"], False)]),
    ("volkswagen/caddy", (2010, 2020), [
        ("Caddy III", (2010, 2015), ["Caddy"], False),
        ("Caddy IV", (2015, 2020), ["Caddy"], False)]),
    ("volkswagen/t-roc", (2017, 2024), [
        ("T-Roc A1", (2017, 2024), ["T-Roc"], True)]),
    ("volkswagen/up", (2012, 2022), [
        ("up! AA", (2012, 2022), ["up!"], True)]),
    ("volkswagen/cc", (2012, 2017), [
        ("CC 358", (2012, 2017), ["Passat CC"], False)]),
    ("volkswagen/jetta", (2010, 2018), [
        ("Jetta VI", (2010, 2018), ["Jetta"], False)]),
    ("skoda/fabia", (2010, 2021), [
        ("Fabia II", (2007, 2014), ["Fabia"], True),
        ("Fabia III", (2014, 2021), ["Fabia"], True)]),
    ("skoda/rapid", (2012, 2019), [
        ("Rapid NH", (2012, 2019), ["Rapid"], True)]),
    ("skoda/kodiaq", (2016, 2024), [
        ("Kodiaq I", (2016, 2024), ["Kodiaq"], False)]),
    ("skoda/yeti", (2010, 2017), [
        ("Yeti 5L", (2010, 2017), ["Yeti"], True)]),
    ("skoda/karoq", (2017, 2024), [
        ("Karoq NU", (2017, 2024), ["Karoq"], False)]),
    ("skoda/scala", (2019, 2024), [
        ("Scala NW", (2019, 2024), ["Scala"], True)]),
    ("skoda/kamiq", (2019, 2024), [
        ("Kamiq NW4", (2019, 2024), ["Kamiq"], True)]),
    ("seat/leon", (2010, 2024), [
        ("Leon II", (2005, 2012), ["Leon"], True),
        ("Leon III", (2012, 2020), ["Leon"], True),
        ("Leon IV", (2020, 2024), ["Leon"], True)]),
    ("seat/ibiza", (2010, 2024), [
        ("Ibiza IV", (2008, 2017), ["Ibiza"], True),
        ("Ibiza V", (2017, 2024), ["Ibiza"], True)]),
    ("seat/ateca", (2016, 2024), [
        ("Ateca KH", (2016, 2024), ["Ateca"], True)]),
    ("seat/alhambra", (2010, 2020), [
        ("Alhambra II", (2010, 2020), ["Alhambra"], False)]),
    ("seat/arona", (2017, 2024), [
        ("Arona KJ", (2017, 2024), ["Arona"], True)]),
    ("seat/altea", (2010, 2015), [
        ("Altea 5P", (2004, 2015), ["Altea", "Altea XL"], True)]),
    ("audi/a1", (2010, 2018), [
        ("A1 8X", (2010, 2018), ["A1"], False)]),
    ("audi/a5", (2010, 2024), [
        ("A5 8T", (2008, 2016), ["A5"], False),
        ("A5 F5", (2016, 2024), ["A5"], False)]),
    ("audi/q2", (2016, 2024), [
        ("Q2 GA", (2016, 2024), ["Q2"], False)]),
    ("audi/q3", (2011, 2024), [
        ("Q3 8U", (2011, 2018), ["Q3"], False),
        ("Q3 F3", (2018, 2024), ["Q3"], False)]),
    ("audi/q5", (2010, 2024), [
        ("Q5 8R", (2008, 2017), ["Q5"], False),
        ("Q5 FY", (2017, 2024), ["Q5"], False)]),
    ("bmw/x3", (2010, 2024), [
        ("X3 F25", (2010, 2017), ["X3"], False),
        ("X3 G01", (2017, 2024), ["X3"], False)]),
    ("bmw/2er", (2014, 2021), [
        ("2er F45", (2014, 2021), ["216", "218", "220"], False)]),
    ("mercedes-benz/a-klasse", (2010, 2024), [
        ("A-Klasse W169", (2004, 2012), ["A 160", "A 180", "A 200"], True),
        ("A-Klasse W176", (2012, 2018), ["A 160", "A 180", "A 200"], True),
        ("A-Klasse W177", (2018, 2024), ["A 160", "A 180", "A 200"], True)]),
    ("mercedes-benz/c-klasse", (2010, 2021), [
        ("C-Klasse W204", (2007, 2014), ["C 180", "C 200", "C 220"], False),
        ("C-Klasse W205", (2014, 2021), ["C 180", "C 200", "C 220"], False)]),
    ("mercedes-benz/e-klasse", (2010, 2023), [
        ("E-Klasse W212", (2009, 2016), ["E 200", "E 220"], False),
        ("E-Klasse W213", (2016, 2023), ["E 200", "E 220"], False)]),
    ("mercedes-benz/cla", (2013, 2024), [
        ("CLA C117", (2013, 2019), ["CLA 180", "CLA 200", "CLA 220"], True),
        ("CLA C118", (2019, 2024), ["CLA 180", "CLA 200", "CLA 220"], True)]),
    ("mercedes-benz/gla", (2014, 2024), [
        ("GLA X156", (2014, 2019), ["GLA 180", "GLA 200"], True),
        ("GLA H247", (2020, 2024), ["GLA 180", "GLA 200"], True)]),
    ("opel/zafira", (2010, 2019), [
        ("Zafira B", (2005, 2011), ["Zafira"], False),
        ("Zafira C", (2011, 2019), ["Zafira"], False)]),
    ("opel/meriva", (2010, 2017), [
        ("Meriva B", (2010, 2017), ["Meriva"], True)]),
    ("opel/mokka", (2012, 2019), [
        ("Mokka A", (2012, 2019), ["Mokka", "Mokka X"], True)]),
    ("opel/grandland", (2017, 2024), [
        ("Grandland X", (2017, 2024), ["Grandland X", "Grandland"], True)]),
    ("opel/crossland", (2017, 2024), [
        ("Crossland X", (2017, 2024), ["Crossland X"], True)]),
    ("opel/adam", (2013, 2019), [
        ("Adam M13", (2013, 2019), ["Adam"], True)]),
    ("peugeot/207", (2010, 2014), [
        ("207 A7", (2006, 2014), ["207"], True)]),
    ("peugeot/208", (2012, 2024), [
        ("208 I", (2012, 2019), ["208"], True),
        ("208 II", (2019, 2024), ["208"], True)]),
    ("peugeot/308", (2010, 2021), [
        ("308 T7", (2007, 2013), ["308"], False),
        ("308 T9", (2013, 2021), ["308"], False)]),
    ("peugeot/2008", (2013, 2024), [
        ("2008 I", (2013, 2019), ["2008"], True),
        ("2008 II", (2019, 2024), ["2008"], True)]),
    ("peugeot/508", (2010, 2024), [
        ("508 I", (2010, 2018), ["508"], False),
        ("508 II", (2018, 2024), ["508"], False)]),
    ("peugeot/5008", (2010, 2024), [
        ("5008 I", (2009, 2016), ["5008"], False),
        ("5008 II", (2017, 2024), ["5008"], False)]),
    ("renault/clio", (2010, 2024), [
        ("Clio III", (2005, 2012), ["Clio"], True),
        ("Clio IV", (2012, 2019), ["Clio"], True),
        ("Clio V", (2019, 2024), ["Clio"], True)]),
    ("renault/megane", (2010, 2023), [
        ("Megane III", (2008, 2016), ["Megane"], False),
        ("Megane IV", (2016, 2023), ["Megane"], False)]),
    ("renault/scenic", (2010, 2022), [
        ("Scenic III", (2009, 2016), ["Scenic", "Grand Scenic"], False),
        ("Scenic IV", (2016, 2022), ["Scenic", "Grand Scenic"], False)]),
    ("renault/captur", (2013, 2024), [
        ("Captur I", (2013, 2019), ["Captur"], True),
        ("Captur II", (2019, 2024), ["Captur"], True)]),
    ("renault/kadjar", (2015, 2022), [
        ("Kadjar HA", (2015, 2022), ["Kadjar"], False)]),
    ("renault/talisman", (2015, 2022), [
        ("Talisman L2M", (2015, 2022), ["Talisman"], False)]),
    ("renault/laguna", (2010, 2015), [
        ("Laguna III", (2007, 2015), ["Laguna"], False)]),
    ("renault/koleos", (2010, 2024), [
        ("Koleos I", (2008, 2016), ["Koleos"], False),
        ("Koleos II", (2017, 2024), ["Koleos"], False)]),
    ("renault/twingo", (2010, 2022), [
        ("Twingo II", (2007, 2014), ["Twingo"], True),
        ("Twingo III", (2014, 2022), ["Twingo"], True)]),
    ("renault/kangoo", (2010, 2020), [
        ("Kangoo II", (2008, 2020), ["Kangoo"], False)]),
    ("citroen/c3", (2010, 2024), [
        ("C3 II", (2009, 2016), ["C3"], True),
        ("C3 III", (2016, 2024), ["C3"], True)]),
    ("citroen/c4", (2010, 2018), [
        ("C4 II", (2010, 2018), ["C4"], False)]),
    ("citroen/c4-cactus", (2014, 2020), [
        ("C4 Cactus E3", (2014, 2020), ["C4 Cactus"], True)]),
    ("citroen/c5", (2010, 2017), [
        ("C5 III", (2008, 2017), ["C5"], False)]),
    ("citroen/c3-picasso", (2010, 2017), [
        ("C3 Picasso SH", (2009, 2017), ["C3 Picasso"], True)]),
    ("citroen/c3-aircross", (2017, 2024), [
        ("C3 Aircross 2R", (2017, 2024), ["C3 Aircross"], True)]),
    ("citroen/c5-aircross", (2018, 2024), [
        ("C5 Aircross C84", (2018, 2024), ["C5 Aircross"], False)]),
    ("citroen/berlingo", (2010, 2024), [
        ("Berlingo II", (2008, 2018), ["Berlingo"], False),
        ("Berlingo III", (2018, 2024), ["Berlingo"], False)]),
    ("dacia/duster", (2010, 2024), [
        ("Duster I", (2010, 2017), ["Duster"], True),
        ("Duster II", (2018, 2024), ["Duster"], True)]),
    ("dacia/sandero", (2012, 2020), [
        ("Sandero II", (2012, 2020), ["Sandero", "Stepway"], True)]),
    ("fiat/tipo", (2016, 2024), [
        ("Tipo 356", (2016, 2024), ["Tipo"], True)]),
    ("fiat/500x", (2014, 2024), [
        ("500X 334", (2014, 2024), ["500X"], True)]),
    ("fiat/500l", (2012, 2022), [
        ("500L 351", (2012, 2022), ["500L"], True)]),
    ("fiat/doblo", (2010, 2022), [
        ("Doblo 263", (2010, 2022), ["Doblo"], False)]),
    ("fiat/punto", (2010, 2018), [
        ("Punto 199", (2010, 2018), ["Punto", "Grande Punto", "EVO"], True)]),
    ("fiat/500", (2010, 2020), [
        ("500 312", (2010, 2020), ["500"], True)]),
    ("fiat/panda", (2010, 2024), [
        ("Panda 169", (2003, 2012), ["Panda"], True),
        ("Panda 319", (2012, 2024), ["Panda"], True)]),
    ("fiat/bravo", (2010, 2014), [
        ("Bravo 198", (2007, 2014), ["Bravo"], True)]),
    ("ford/focus", (2011, 2024), [
        ("Focus III", (2011, 2018), ["Focus"], True),
        ("Focus IV", (2018, 2024), ["Focus"], True)]),
    ("ford/fiesta", (2010, 2023), [
        ("Fiesta VI", (2008, 2017), ["Fiesta"], True),
        ("Fiesta VII", (2017, 2023), ["Fiesta"], True)]),
    ("ford/mondeo", (2010, 2022), [
        ("Mondeo IV", (2007, 2014), ["Mondeo"], False),
        ("Mondeo V", (2014, 2022), ["Mondeo"], False)]),
    ("ford/c-max", (2010, 2019), [
        ("C-Max II", (2010, 2019), ["C-Max", "Grand C-Max"], False)]),
    ("ford/s-max", (2010, 2022), [
        ("S-Max I", (2006, 2015), ["S-Max"], False),
        ("S-Max II", (2015, 2022), ["S-Max"], False)]),
    ("ford/galaxy", (2010, 2022), [
        ("Galaxy III", (2006, 2015), ["Galaxy"], False),
        ("Galaxy IV", (2015, 2022), ["Galaxy"], False)]),
    ("ford/b-max", (2012, 2017), [
        ("B-Max JK", (2012, 2017), ["B-Max"], True)]),
    ("ford/ecosport", (2014, 2022), [
        ("EcoSport II", (2014, 2022), ["EcoSport"], True)]),
    ("ford/puma", (2019, 2024), [
        ("Puma J2K", (2019, 2024), ["Puma"], True)]),
    ("toyota/auris", (2010, 2018), [
        ("Auris I", (2007, 2012), ["Auris"], True),
        ("Auris II", (2012, 2018), ["Auris"], True)]),
    ("toyota/yaris", (2010, 2024), [
        ("Yaris II", (2005, 2011), ["Yaris"], True),
        ("Yaris III", (2011, 2020), ["Yaris"], True),
        ("Yaris IV", (2020, 2024), ["Yaris"], True)]),
    ("toyota/rav4", (2010, 2018), [
        ("RAV4 III", (2006, 2012), ["RAV 4"], False),
        ("RAV4 IV", (2013, 2018), ["RAV 4"], False)]),
    ("toyota/avensis", (2010, 2018), [
        ("Avensis T27", (2009, 2018), ["Avensis"], False)]),
    ("toyota/verso", (2010, 2018), [
        ("Verso R2", (2009, 2018), ["Verso"], False)]),
    ("toyota/corolla", (2013, 2024), [
        ("Corolla E170", (2013, 2018), ["Corolla"], True),
        ("Corolla E210", (2019, 2024), ["Corolla"], True)]),
    ("toyota/c-hr", (2016, 2024), [
        ("C-HR AX1", (2016, 2024), ["C-HR"], False)]),
    ("kia/sportage", (2010, 2021), [
        ("Sportage III", (2010, 2015), ["Sportage"], False),
        ("Sportage IV", (2015, 2021), ["Sportage"], False)]),
    ("kia/ceed", (2010, 2024), [
        ("Ceed ED", (2006, 2012), ["cee`d"], True),
        ("Ceed JD", (2012, 2018), ["cee`d"], True),
        ("Ceed CD", (2018, 2024), ["cee`d"], True)]),
    ("kia/rio", (2011, 2022), [
        ("Rio III", (2011, 2017), ["Rio"], True),
        ("Rio IV", (2017, 2022), ["Rio"], True)]),
    ("hyundai/i30", (2010, 2024), [
        ("i30 FD", (2007, 2012), ["i30"], True),
        ("i30 GD", (2012, 2017), ["i30"], True),
        ("i30 PD", (2017, 2024), ["i30"], True)]),
    ("hyundai/tucson", (2015, 2020), [
        ("Tucson TL", (2015, 2020), ["Tucson"], True)]),
    ("hyundai/i20", (2010, 2020), [
        ("i20 PB", (2008, 2014), ["i20"], True),
        ("i20 GB", (2014, 2020), ["i20"], True)]),
    ("nissan/qashqai", (2010, 2021), [
        ("Qashqai J10", (2007, 2013), ["Qashqai"], True),
        ("Qashqai J11", (2013, 2021), ["Qashqai"], True)]),
    ("nissan/juke", (2010, 2019), [
        ("Juke F15", (2010, 2019), ["Juke"], True)]),
    ("nissan/x-trail", (2010, 2022), [
        ("X-Trail T31", (2007, 2014), ["X-Trail"], False),
        ("X-Trail T32", (2014, 2022), ["X-Trail"], False)]),
    ("nissan/micra", (2010, 2024), [
        ("Micra K13", (2010, 2017), ["Micra"], True),
        ("Micra K14", (2017, 2024), ["Micra"], True)]),
    ("mazda/mazda3", (2010, 2024), [
        ("Mazda3 BL", (2009, 2013), ["3"], True),
        ("Mazda3 BM", (2013, 2018), ["3"], True),
        ("Mazda3 BP", (2019, 2024), ["3"], True)]),
    ("mazda/mazda6", (2010, 2021), [
        ("Mazda6 GH", (2008, 2012), ["6"], True),
        ("Mazda6 GJ", (2012, 2021), ["6"], True)]),
    ("mazda/cx-5", (2012, 2024), [
        ("CX-5 KE", (2012, 2017), ["CX-5"], True),
        ("CX-5 KF", (2017, 2024), ["CX-5"], True)]),
    ("mazda/cx-3", (2015, 2022), [
        ("CX-3 DK", (2015, 2022), ["CX-3"], True)]),
    ("mazda/mazda2", (2010, 2024), [
        ("Mazda2 DE", (2007, 2014), ["2"], True),
        ("Mazda2 DJ", (2014, 2024), ["2"], True)]),
    ("volvo/v40", (2012, 2019), [
        ("V40 II", (2012, 2019), ["V40"], False)]),
    ("volvo/v60", (2010, 2024), [
        ("V60 I", (2010, 2018), ["V60"], False),
        ("V60 II", (2018, 2024), ["V60"], False)]),
    ("volvo/s60", (2010, 2018), [
        ("S60 II", (2010, 2018), ["S60"], False)]),
    ("volvo/xc60", (2010, 2024), [
        ("XC60 I", (2008, 2017), ["XC60"], False),
        ("XC60 II", (2017, 2024), ["XC60"], False)]),
    ("volvo/xc40", (2017, 2024), [
        ("XC40 536", (2017, 2024), ["XC40"], True)]),
    ("honda/civic", (2012, 2021), [
        ("Civic IX", (2012, 2017), ["Civic"], True),
        ("Civic X", (2017, 2021), ["Civic"], True)]),
    ("honda/cr-v", (2012, 2024), [
        ("CR-V IV", (2012, 2018), ["CR-V"], True),
        ("CR-V V", (2018, 2024), ["CR-V"], True)]),
    ("honda/jazz", (2010, 2020), [
        ("Jazz III", (2008, 2015), ["Jazz"], True),
        ("Jazz IV", (2015, 2020), ["Jazz"], True)]),
    ("mitsubishi/asx", (2010, 2024), [
        ("ASX GA", (2010, 2024), ["ASX"], False)]),
    ("mitsubishi/outlander", (2012, 2021), [
        ("Outlander III", (2012, 2021), ["Outlander"], True)]),
    ("suzuki/swift", (2010, 2024), [
        ("Swift IV", (2010, 2017), ["Swift"], True),
        ("Swift V", (2017, 2024), ["Swift"], True)]),
    ("suzuki/vitara", (2015, 2024), [
        ("Vitara LY", (2015, 2024), ["Vitara"], True)]),
    ("suzuki/sx4-s-cross", (2013, 2021), [
        ("S-Cross JY", (2013, 2021), ["SX4 S-Cross"], True)]),
    ("chevrolet/cruze", (2010, 2016), [
        ("Cruze J300", (2009, 2016), ["Cruze"], True)]),
    ("alfa-romeo/giulietta", (2010, 2020), [
        ("Giulietta 940", (2010, 2020), ["Giulietta"], True)]),
]


def test_daily_table_holds_every_daily_model_in_order():
    assert [row[0] for row in DAILY_TABLE] == [model["as24"] for model in models.DAILY_MODELS]


@pytest.mark.parametrize("as24,years,generations", DAILY_TABLE, ids=[row[0] for row in DAILY_TABLE])
def test_daily_model_is_searched_in_its_priced_years_under_its_pa_names(as24, years, generations):
    model = MODEL[as24]
    assert scan.search_years(model) == years
    found = []
    for generation in model["generations"]:
        petrol = bool(generation.get("petrol"))
        found.append((generation["name"], generation["years"], models.pa_names(generation["pa_model"]), petrol))
    assert found == generations


@pytest.mark.parametrize("as24,years,generations", DAILY_TABLE, ids=[row[0] for row in DAILY_TABLE])
def test_generation_lookup_of_the_daily_models(as24, years, generations):
    first_year = min(row[1][0] for row in generations)
    last_year = max(row[1][1] for row in generations)
    for year in range(first_year - 1, last_year + 2):   # a year before and after the table give no generation
        expected = [name for name, (first, last), _, _ in generations if first <= year <= last]
        assert [generation["name"] for generation in models.generations_for(MODEL[as24], year)] == expected, year


@pytest.mark.parametrize("as24,years", [
    ("volkswagen/golf", set(range(2008, 2025))), ("volkswagen/polo", set(range(2009, 2025))),
    ("opel/astra", set(range(2009, 2017))),     # Astra K stays diesel (18% petrol on PA)
    ("opel/corsa", set(range(2006, 2025))), ("kia/ceed", set(range(2006, 2025))),
    ("peugeot/5008", set()), ("volkswagen/passat", set()), ("audi/a1", set()),   # every Audi stays diesel only
    ("bmw/x5", set()),                          # not a model of ours
])
def test_petrol_years_are_the_years_of_the_petrol_generations(as24, years):
    assert models.petrol_years(as24) == years


@pytest.mark.parametrize("as24,title,name", [
    ("mercedes-benz/a-klasse", "Mercedes-Benz A 180 CDI W176", "A-Klasse W176"),
    ("mercedes-benz/c-klasse", "Mercedes C 220 CDI S204 T-Modell", "C-Klasse W204"),
    ("mercedes-benz/c-klasse", "Mercedes C 200 d W205", "C-Klasse W205"),
    ("mercedes-benz/e-klasse", "Mercedes E 220 d S213", "E-Klasse W213"),
    ("mercedes-benz/cla", "Mercedes CLA 200 d Shooting Brake X117", "CLA C117"),
    ("mercedes-benz/gla", "Mercedes GLA 200 d X156", "GLA X156"),
    ("bmw/x3", "BMW X3 xDrive20d F25", "X3 F25"), ("bmw/x3", "BMW X3 sDrive18d G01", "X3 G01"),
    ("bmw/3er", "BMW 320d E91 Touring", "3er E90"), ("bmw/3er", "BMW 320d G21 Touring", "3er G20"),
    ("bmw/520", "BMW 520d G31 Touring", "520d G30"),
    ("opel/corsa", "Opel Corsa D 1.3 CDTI", "Corsa D"), ("opel/corsa", "Opel Corsa-F 1.2", "Corsa F"),
    ("opel/zafira", "Opel Zafira Tourer 2.0 CDTI", "Zafira C"), ("opel/zafira", "Opel Zafira Family 1.7", "Zafira B"),
    ("opel/zafira", "Opel Zafira C 1.6 CDTI", "Zafira C"),
])
def test_generation_named_in_the_title_of_the_daily_and_extended_models(as24, title, name):
    assert models.named_generation(MODEL[as24], title) == name


@pytest.mark.parametrize("as24,year,title,expected", [
    ("opel/corsa", 2021, "Opel Corsa-e Elegance", None),   # the electric Corsa F reads as "Corsa E": left out
    ("opel/corsa", 2014, "Opel Corsa E 1.3 CDTI", "Corsa E"),   # change-over year: the title decides
    ("opel/corsa", 2014, "Opel Corsa 1.3 CDTI", None),
    ("opel/zafira", 2011, "Opel Zafira Tourer 2.0 CDTI", "Zafira C"),
    ("opel/zafira", 2020, "Opel Zafira Tourer 2.0 CDTI", None),   # the C ends in 2019
    ("mercedes-benz/c-klasse", 2014, "Mercedes C 220 W204", "C-Klasse W204"),
    ("mercedes-benz/c-klasse", 2015, "Mercedes C 220 W204", None),
    ("bmw/3er", 2012, "BMW 318d E90", None),   # 2012 is never priced
])
def test_named_generation_of_a_car_must_fit_its_year(as24, year, title, expected):
    generation = valuation.generation_of({"year": year, "title": title}, MODEL[as24])
    assert (generation["name"] if generation else None) == expected


@pytest.mark.parametrize("title,name", [
    ("Volkswagen Passat CC 2.0 TDI", "passat cc"), ("VW PassatCC 2.0 TDI", "passat cc"),
    ("Volkswagen CC 2.0 TDI BMT", "passat cc"),
    ("Renault Grand Scénic 1.5 dCi", "grand scenic"), ("Renault GrandScenic", "grand scenic"),
    ("Ford Grand C-Max 1.6 TDCi", "grand c-max"), ("Ford Grand CMax", "grand c-max"),
    ("Nissan Qashqai+2 1.5 dCi", "qashqai+2"), ("Nissan Qashqai + 2", "qashqai+2"),
    ("Seat Altea XL 1.6 TDI", "altea xl"), ("Dacia Sandero Stepway 1.5 dCi", "stepway"),
    ("VW Caddy Maxi 2.0 TDI", "maxi"), ("Renault Kangoo Maxi", "maxi"),
    ("BMW 218d Gran Tourer", "gran tourer"),
    ("Suzuki SX4 S-Cross 1.6 DDiS", "cross"), ("Volvo V40 Cross Country D2", "cross"),
])
def test_sub_models_of_the_daily_models(title, name):
    assert models.sub_model(title) == name


@pytest.mark.parametrize("title", ["Volkswagen Passat 2.0 TDI", "VW Golf 1968 cc", "Renault Scenic 1.5 dCi",
                                   "Ford C-Max 1.6 TDCi", "Nissan Qashqai 1.5 dCi", "Seat Altea 1.9 TDI",
                                   "Dacia Sandero 1.5 dCi", "VW Caddy 2.0 TDI", "BMW 218d Active Tourer",
                                   "Opel Crossland X 1.2", "Citroen C3 Aircross 1.5 BlueHDi", "Suzuki SX4 1.6"])
def test_base_models_of_the_daily_models_are_no_sub_model(title):
    assert models.sub_model(title) is None


def test_5008_takes_the_body_of_its_generation():
    peugeot_5008 = MODEL["peugeot/5008"]
    assert [generation.get("body") for generation in peugeot_5008["generations"]] == ["van", "suv"]
    assert "body" not in peugeot_5008   # an MPV first, an SUV after 2017
    assert MODEL["volvo/v60"]["body"] == "estate"   # every V60 is an estate
