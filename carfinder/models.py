"""Start models (top imported used cars in Serbia, PA/CUBE H1 2026) and their generations.

pa_model is the model name polovniautomobili uses; some models are split per generation there, others not.
Years are first-registration years; neighbouring generations overlap in their change-over year.
"""
import re

MAX_CC = 2000

# Words in a title or ad text that mean four-wheel drive; the sites' own drive field is often empty.
# mobile.de (through Apify) lists equipment in English.
# Sellers write 4Motion as "4Mot", "4 Motion" and "4-Motion" too, and 4x4 as "4 x 4". Scout is not in this
# list: it counts only as a whole word (drive_of), because sellers also write "AutoScout24".
FOUR_BY_FOUR_WORDS = ("4mot", "4 motion", "4-motion", "quattro", "4x4", "4 x 4", "4×4", "allrad", "alltrack",
                      "hybrid4", "four wheel drive", "four-wheel drive", "all wheel drive", "all-wheel drive")
FOUR_BY_FOUR_BADGES = re.compile(r"\b(?:x-?drive(?=\b|\d)|4matic\b|awd\b|4wd\b)")

# Sub-models that are their own market in Serbia: never priced against the base model. R-Line is only a trim.
SUB_MODELS = {
    "golf plus": re.compile(r"\bgolf ?plus\b"),
    "sportsvan": re.compile(r"\bsportsvan\b"),
    "scout": re.compile(r"\bscout\b"),
    "cross": re.compile(r"\bcross ?(polo|golf)?\b"),
    "alltrack": re.compile(r"\balltrack\b"),
    "allspace": re.compile(r"\ballspace\b"),
    "rs": re.compile(r"\bv?rs\b"),
    "gtd": re.compile(r"\bgtd\b"),
    "gti": re.compile(r"\bgti\b"),
    # BMW Gran Turismo: "320d Gran Turismo", "318d GT", "520 GT"; a "3008 GT Line" is only a trim
    "gran turismo": re.compile(r"\bgran ?turismo\b|\b(?:31[68]|320|520)(?: ?d)? gt\b(?![ -]?line\b)"
                               r"|\b3er gt\b|\bbmw\b.*\bf(?:07|34)\b"),
    "country tourer": re.compile(r"\bcountry[ -]tourer\b|\binsignia(?: [ab])? country\b"),
    # 25.11.2026. S-Cross and V40 Cross Country fall under "cross" above.
    "passat cc": re.compile(r"\bpassat[ -]?cc\b|\b(?:vw|volkswagen) cc\b"),
    "grand scenic": re.compile(r"\bgrand ?sc[eé]nic\b"),
    "grand c-max": re.compile(r"\bgrand ?c-?max\b"),
    "qashqai+2": re.compile(r"\bqashqai ?\+ ?2\b"),
    "altea xl": re.compile(r"\baltea ?xl\b"),
    "stepway": re.compile(r"\bstepway\b"),
    "maxi": re.compile(r"\b(?:caddy|kangoo) maxi\b"),
    "gran tourer": re.compile(r"\bgran ?tourer\b"),
}

# new_price is the Serbian new price in EUR (hatch or sedan, diesel) that customs values a used car from;
# new_price_estate the same for the estate. Values of generations sold up to 2013 come from the AMSS catalogue
# 1/2013 (public tool on registracija-vozila.rs); later generations are estimates (German list price x 0.90).
# Golf 6, Passat B7 and Golf 7 are the ones checked against real bills (customs.CATALOGUE_FACTOR).
# "petrol": plain petrol sells in Serbia for this generation (25%+ of its PA ads; Novky 25.11.2026 on small petrol
# cars: "bas bas"), so the sites are asked for it too. Every other generation is scanned without plain petrol.
# CORE_MODELS are scanned every run (and on mobile.de); DAILY_MODELS once a day, one eighth of them per run.
CORE_MODELS = [
    {"make": "Volkswagen", "as24": "volkswagen/golf", "mass": 1350, "generations": [
        {"name": "Golf 6", "pa_model": "Golf 6", "years": (2008, 2013), "new_price": 21066, "new_price_estate": 22500,
         "petrol": True},
        {"name": "Golf 7", "pa_model": "Golf 7", "years": (2012, 2020), "new_price": 22500, "new_price_estate": 24000,
         "petrol": True},
        {"name": "Golf 8", "pa_model": "Golf 8", "years": (2020, 2024), "new_price": 27000, "new_price_estate": 28000,
         "petrol": True},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/polo", "mass": 1150, "generations": [
        {"name": "Polo V", "pa_model": "Polo", "years": (2009, 2017), "new_price": 14400, "petrol": True},
        {"name": "Polo VI", "pa_model": "Polo", "years": (2017, 2024), "new_price": 17500, "petrol": True},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/passat", "mass": 1550, "generations": [
        # The B6 was still registered in 2011. An explicit B6 title is needed that year.
        {"name": "Passat B6", "pa_model": "Passat B6", "years": (2005, 2010), "named_until": 2011,
         "new_price": 23549, "new_price_estate": 25500},
        {"name": "Passat B7", "pa_model": "Passat B7", "years": (2011, 2015), "new_price": 23549,
         "new_price_estate": 25500},
        {"name": "Passat B8", "pa_model": "Passat B8", "years": (2014, 2023), "new_price": 33000,
         "new_price_estate": 35000},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/tiguan", "mass": 1650, "large": True, "generations": [
        {"name": "Tiguan I", "pa_model": "Tiguan", "years": (2007, 2016), "new_price": 26500},
        {"name": "Tiguan II", "pa_model": "Tiguan", "years": (2016, 2024), "new_price": 33000},
    ]},
    {"make": "Škoda", "as24": "skoda/octavia", "mass": 1400, "generations": [
        {"name": "Octavia II", "pa_model": "Octavia", "years": (2004, 2013), "new_price": 18450,
         "new_price_estate": 20000},
        {"name": "Octavia III", "pa_model": "Octavia", "years": (2013, 2020), "new_price": 23000,
         "new_price_estate": 24500},
    ]},
    {"make": "Škoda", "as24": "skoda/superb", "mass": 1550, "generations": [
        {"name": "Superb II", "pa_model": "Superb", "years": (2008, 2015), "new_price": 25050,
         "new_price_estate": 26000},
        {"name": "Superb III", "pa_model": "Superb", "years": (2015, 2023), "new_price": 30000,
         "new_price_estate": 31500},
    ]},
    {"make": "Audi", "as24": "audi/a3", "mass": 1350, "generations": [
        {"name": "A3 8P", "pa_model": "A3", "years": (2003, 2013), "new_price": 24900},
        {"name": "A3 8V", "pa_model": "A3", "years": (2012, 2020), "new_price": 27000},
    ]},
    {"make": "Audi", "as24": "audi/a4", "mass": 1550, "generations": [
        {"name": "A4 B8", "pa_model": "A4", "years": (2008, 2015), "new_price": 34650, "new_price_estate": 36250},
        {"name": "A4 B9", "pa_model": "A4", "years": (2015, 2024), "new_price": 38000, "new_price_estate": 40000},
    ]},
    {"make": "Opel", "as24": "opel/astra", "mass": 1400, "generations": [
        {"name": "Astra J", "pa_model": "Astra J", "years": (2009, 2016), "new_price": 19550,
         "new_price_estate": 20800, "petrol": True},
        {"name": "Astra K", "pa_model": "Astra K", "years": (2015, 2021), "new_price": 21000,
         "new_price_estate": 22500},
    ]},
    {"make": "Opel", "as24": "opel/corsa", "mass": 1150, "generations": [
        {"name": "Corsa D", "pa_model": "Corsa D", "years": (2006, 2014), "new_price": 14200, "petrol": True},
        {"name": "Corsa E", "pa_model": "Corsa E", "years": (2014, 2019), "new_price": 15000, "petrol": True},
        {"name": "Corsa F", "pa_model": "Corsa F", "years": (2019, 2024), "new_price": 15300, "petrol": True},
    ]},
    {"make": "Peugeot", "as24": "peugeot/3008", "mass": 1450, "large": True, "generations": [
        {"name": "3008 I", "pa_model": "3008", "years": (2009, 2016), "new_price": 22950},
        {"name": "3008 II", "pa_model": "3008", "years": (2016, 2024), "new_price": 30000},
    ]},
    # Added 24.11.2026 from the margin screen of 65 generations: the ones that cleared 700 EUR on clean cars about as
    # often as Golf 7, Octavia III and Passat B7 and have many PA ads. Only the screened generation of each model.
    # Every new_price below is an estimate (German list price x 0.90), not an AMSS catalogue figure.
    # pa_model "316/318/320": PA lists BMW and Mercedes under engine names (see pa_names).
    # "body": what a list-page car without a body is taken as; PA lists these MPVs as vans.
    {"make": "BMW", "as24": "bmw/x1", "mass": 1550, "large": True, "generations": [
        {"name": "X1 E84", "pa_model": "X1", "years": (2009, 2015), "new_price": 28000},
        {"name": "X1 F48", "pa_model": "X1", "years": (2015, 2022), "new_price": 31000},
    ]},
    {"make": "BMW", "as24": "bmw/520", "mass": 1650, "generations": [
        {"name": "520d F10", "pa_model": "520", "years": (2010, 2016), "new_price": 38700, "new_price_estate": 40500},
        {"name": "520d G30", "pa_model": "520", "years": (2017, 2023), "new_price": 44000, "new_price_estate": 46000},
    ]},
    {"make": "BMW", "as24": "bmw/3er", "mass": 1500, "generations": [
        # 2012 is left out: the E90 and the F30 share the PA names and the 318d's 105 kW
        {"name": "3er E90", "pa_model": "316/318/320", "years": (2008, 2011), "new_price": 29500,
         "new_price_estate": 31000},
        {"name": "3er F30", "pa_model": "316/318/320", "years": (2013, 2018), "new_price": 30000,
         "new_price_estate": 31500},
        {"name": "3er G20", "pa_model": "316/318/320", "years": (2019, 2024), "new_price": 34000,
         "new_price_estate": 35500},
    ]},
    {"make": "Audi", "as24": "audi/a6", "mass": 1650, "generations": [
        {"name": "A6 C6", "pa_model": "A6", "years": (2008, 2011), "new_price": 34000, "new_price_estate": 36000},
        {"name": "A6 C7", "pa_model": "A6", "years": (2011, 2017), "new_price": 36500, "new_price_estate": 38750,
         "new_price_hybrid": 48000},
        {"name": "A6 C8", "pa_model": "A6", "years": (2018, 2024), "new_price": 44000, "new_price_estate": 46000},
    ]},
    {"make": "Opel", "as24": "opel/insignia", "mass": 1550, "generations": [
        {"name": "Insignia A", "pa_model": "Insignia", "years": (2008, 2017), "mass": 1650, "new_price": 25000,
         "new_price_estate": 26000},
        {"name": "Insignia B", "pa_model": "Insignia", "years": (2017, 2022), "new_price": 28000,
         "new_price_estate": 29000},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/b-klasse", "mass": 1450, "large": True, "body": "van",
     "generations": [
        {"name": "B-Klasse W245", "pa_model": "B 180/B 200", "years": (2005, 2011), "new_price": 22500},
        {"name": "B-Klasse W246", "pa_model": "B 180/B 200", "years": (2012, 2018), "new_price": 25000},
        {"name": "B-Klasse W247", "pa_model": "B 180/B 200", "years": (2019, 2024), "new_price": 29000},
    ]},
    # Citroen C4 Picasso II left 25.11.2026: Novky "Da mrtav je za prodaju".
    {"make": "Ford", "as24": "ford/kuga", "mass": 1650, "large": True, "generations": [
        # 2012 is the Kuga I's: the Kuga II of 2012 has the same PA name and the same 2.0 TDCi engines
        {"name": "Kuga I", "pa_model": "Kuga", "years": (2008, 2012), "new_price": 25000},
        {"name": "Kuga II", "pa_model": "Kuga", "years": (2013, 2019), "new_price": 26000},
        {"name": "Kuga III", "pa_model": "Kuga", "years": (2020, 2024), "new_price": 28000},
    ]},
    {"make": "Hyundai", "as24": "hyundai/ix35", "mass": 1600, "large": True, "generations": [
        {"name": "ix35 LM", "pa_model": "ix35", "years": (2010, 2015), "new_price": 21500},
    ]},
    # 25.11.2026, a 4-week trial to about 23.12.2026 on AutoScout24 and willhaben only ("trial": not in the paid
    # mobile.de runs). Screen of 25.11: median profit 458 EUR under the Golf 7/Passat B7/Octavia III baseline, 1 of 66
    # cars at +700, ads listed 1.3x as long. Kept only if its cars pass in the live scan; otherwise it goes.
    {"make": "BMW", "as24": "bmw/1er", "mass": 1400, "trial": True, "generations": [
        # first full year: the E87 of 2011 has the same PA names and engines
        {"name": "1er F20", "pa_model": "116/118/120", "years": (2012, 2018), "new_price": 24500},
        {"name": "1er F40", "pa_model": "116/118/120", "years": (2019, 2024), "new_price": 27000},
    ]},
]
DAILY_MODELS = [
    # 25.11.2026, Bane: "treba da ubacis sve sto je prodajno". Every generation with ~30+ clean PA ads;
    # "petrol": plain petrol is 25%+ of that generation's PA ads. new_price: German list x 0.90, estimated.
    {"make": "Volkswagen", "as24": "volkswagen/touran", "mass": 1550, "large": True, "body": "van", "generations": [
        {"name": "Touran I", "pa_model": "Touran", "years": (2010, 2015), "new_price": 22500},
        {"name": "Touran II", "pa_model": "Touran", "years": (2015, 2024), "new_price": 25000},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/sharan", "mass": 1750, "large": True, "body": "van", "generations": [
        {"name": "Sharan II", "pa_model": "Sharan", "years": (2010, 2022), "new_price": 30000},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/caddy", "mass": 1500, "large": True, "body": "van", "generations": [
        {"name": "Caddy III", "pa_model": "Caddy", "years": (2010, 2015), "new_price": 20000},
        {"name": "Caddy IV", "pa_model": "Caddy", "years": (2015, 2020), "new_price": 21500},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/t-roc", "mass": 1350, "generations": [
        {"name": "T-Roc A1", "pa_model": "T-Roc", "years": (2017, 2024), "new_price": 24300, "petrol": True},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/up", "mass": 950, "generations": [
        {"name": "up! AA", "pa_model": "up!", "years": (2012, 2022), "new_price": 9450, "petrol": True},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/cc", "mass": 1500, "generations": [
        {"name": "CC 358", "pa_model": "Passat CC", "years": (2012, 2017), "new_price": 29700},
    ]},
    {"make": "Volkswagen", "as24": "volkswagen/jetta", "mass": 1400, "generations": [
        {"name": "Jetta VI", "pa_model": "Jetta", "years": (2010, 2018), "new_price": 22000},
    ]},
    {"make": "Škoda", "as24": "skoda/fabia", "mass": 1100, "generations": [
        {"name": "Fabia II", "pa_model": "Fabia", "years": (2007, 2014), "new_price": 11250, "new_price_estate": 11950, "petrol": True},
        {"name": "Fabia III", "pa_model": "Fabia", "years": (2014, 2021), "new_price": 12600, "new_price_estate": 13300, "petrol": True},
    ]},
    {"make": "Škoda", "as24": "skoda/rapid", "mass": 1200, "generations": [
        {"name": "Rapid NH", "pa_model": "Rapid", "years": (2012, 2019), "new_price": 16000, "petrol": True},
    ]},
    {"make": "Škoda", "as24": "skoda/kodiaq", "mass": 1650, "large": True, "generations": [
        {"name": "Kodiaq I", "pa_model": "Kodiaq", "years": (2016, 2024), "new_price": 30000},
    ]},
    {"make": "Škoda", "as24": "skoda/yeti", "mass": 1450, "large": True, "generations": [
        {"name": "Yeti 5L", "pa_model": "Yeti", "years": (2010, 2017), "new_price": 21600, "petrol": True},
    ]},
    {"make": "Škoda", "as24": "skoda/karoq", "mass": 1450, "large": True, "generations": [
        {"name": "Karoq NU", "pa_model": "Karoq", "years": (2017, 2024), "new_price": 24500},
    ]},
    {"make": "Škoda", "as24": "skoda/scala", "mass": 1250, "generations": [
        {"name": "Scala NW", "pa_model": "Scala", "years": (2019, 2024), "new_price": 18900, "petrol": True},
    ]},
    {"make": "Škoda", "as24": "skoda/kamiq", "mass": 1250, "generations": [
        {"name": "Kamiq NW4", "pa_model": "Kamiq", "years": (2019, 2024), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Seat", "as24": "seat/leon", "mass": 1300, "generations": [
        {"name": "Leon II", "pa_model": "Leon", "years": (2005, 2012), "new_price": 18000, "petrol": True},
        {"name": "Leon III", "pa_model": "Leon", "years": (2012, 2020), "new_price": 19500, "new_price_estate": 20300, "petrol": True},
        {"name": "Leon IV", "pa_model": "Leon", "years": (2020, 2024), "new_price": 24000, "new_price_estate": 25000, "petrol": True},
    ]},
    {"make": "Seat", "as24": "seat/ibiza", "mass": 1100, "generations": [
        {"name": "Ibiza IV", "pa_model": "Ibiza", "years": (2008, 2017), "new_price": 13950, "new_price_estate": 14600, "petrol": True},
        {"name": "Ibiza V", "pa_model": "Ibiza", "years": (2017, 2024), "new_price": 13500, "petrol": True},
    ]},
    {"make": "Seat", "as24": "seat/ateca", "mass": 1400, "large": True, "generations": [
        {"name": "Ateca KH", "pa_model": "Ateca", "years": (2016, 2024), "new_price": 23400, "petrol": True},
    ]},
    {"make": "Seat", "as24": "seat/alhambra", "mass": 1750, "large": True, "body": "van", "generations": [
        {"name": "Alhambra II", "pa_model": "Alhambra", "years": (2010, 2020), "new_price": 29700},
    ]},
    {"make": "Seat", "as24": "seat/arona", "mass": 1200, "generations": [
        {"name": "Arona KJ", "pa_model": "Arona", "years": (2017, 2024), "new_price": 17100, "petrol": True},
    ]},
    {"make": "Seat", "as24": "seat/altea", "mass": 1400, "body": "van", "generations": [
        {"name": "Altea 5P", "pa_model": "Altea/Altea XL", "years": (2004, 2015), "new_price": 18900, "petrol": True},
    ]},
    {"make": "Audi", "as24": "audi/a1", "mass": 1200, "generations": [
        {"name": "A1 8X", "pa_model": "A1", "years": (2010, 2018), "new_price": 17550},
    ]},
    {"make": "Audi", "as24": "audi/a5", "mass": 1550, "generations": [
        {"name": "A5 8T", "pa_model": "A5", "years": (2008, 2016), "new_price": 36000},
        {"name": "A5 F5", "pa_model": "A5", "years": (2016, 2024), "new_price": 38700},
    ]},
    {"make": "Audi", "as24": "audi/q2", "mass": 1350, "generations": [
        {"name": "Q2 GA", "pa_model": "Q2", "years": (2016, 2024), "new_price": 23400},
    ]},
    {"make": "Audi", "as24": "audi/q3", "mass": 1550, "large": True, "generations": [
        {"name": "Q3 8U", "pa_model": "Q3", "years": (2011, 2018), "new_price": 29000},
        {"name": "Q3 F3", "pa_model": "Q3", "years": (2018, 2024), "new_price": 32500},
    ]},
    {"make": "Audi", "as24": "audi/q5", "mass": 1800, "large": True, "generations": [
        {"name": "Q5 8R", "pa_model": "Q5", "years": (2008, 2017), "new_price": 36000},
        {"name": "Q5 FY", "pa_model": "Q5", "years": (2017, 2024), "new_price": 41500},
    ]},
    {"make": "BMW", "as24": "bmw/x3", "mass": 1800, "large": True, "generations": [
        {"name": "X3 F25", "pa_model": "X3", "years": (2010, 2017), "new_price": 38000},
        {"name": "X3 G01", "pa_model": "X3", "years": (2017, 2024), "new_price": 43000},
    ]},
    {"make": "BMW", "as24": "bmw/2er", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "2er F45", "pa_model": "216/218/220", "years": (2014, 2021), "new_price": 27000},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/a-klasse", "mass": 1400, "generations": [
        {"name": "A-Klasse W169", "pa_model": "A 160/A 180/A 200", "years": (2004, 2012), "new_price": 21600, "petrol": True},
        {"name": "A-Klasse W176", "pa_model": "A 160/A 180/A 200", "years": (2012, 2018), "new_price": 23500, "petrol": True},
        {"name": "A-Klasse W177", "pa_model": "A 160/A 180/A 200", "years": (2018, 2024), "new_price": 27000, "petrol": True},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/c-klasse", "mass": 1550, "generations": [
        {"name": "C-Klasse W204", "pa_model": "C 180/C 200/C 220", "years": (2007, 2014), "new_price": 32400, "new_price_estate": 34000},
        {"name": "C-Klasse W205", "pa_model": "C 180/C 200/C 220", "years": (2014, 2021), "new_price": 33000, "new_price_estate": 34500},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/e-klasse", "mass": 1700, "generations": [
        {"name": "E-Klasse W212", "pa_model": "E 200/E 220", "years": (2009, 2016), "new_price": 38700, "new_price_estate": 41000},
        {"name": "E-Klasse W213", "pa_model": "E 200/E 220", "years": (2016, 2023), "new_price": 42000, "new_price_estate": 44500},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/cla", "mass": 1450, "generations": [
        {"name": "CLA C117", "pa_model": "CLA 180/CLA 200/CLA 220", "years": (2013, 2019), "new_price": 29700, "new_price_estate": 30600, "petrol": True},
        {"name": "CLA C118", "pa_model": "CLA 180/CLA 200/CLA 220", "years": (2019, 2024), "new_price": 32000, "new_price_estate": 33000, "petrol": True},
    ]},
    {"make": "Mercedes Benz", "as24": "mercedes-benz/gla", "mass": 1500, "large": True, "generations": [
        {"name": "GLA X156", "pa_model": "GLA 180/GLA 200", "years": (2014, 2019), "new_price": 29700, "petrol": True},
        {"name": "GLA H247", "pa_model": "GLA 180/GLA 200", "years": (2020, 2024), "new_price": 33300, "petrol": True},
    ]},
    {"make": "Opel", "as24": "opel/zafira", "mass": 1650, "large": True, "body": "van", "generations": [
        {"name": "Zafira B", "pa_model": "Zafira", "years": (2005, 2011), "new_price": 22000},
        {"name": "Zafira C", "pa_model": "Zafira", "years": (2011, 2019), "new_price": 25000},
    ]},
    {"make": "Opel", "as24": "opel/meriva", "mass": 1400, "body": "van", "generations": [
        {"name": "Meriva B", "pa_model": "Meriva", "years": (2010, 2017), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Opel", "as24": "opel/mokka", "mass": 1400, "generations": [
        {"name": "Mokka A", "pa_model": "Mokka/Mokka X", "years": (2012, 2019), "new_price": 21500, "petrol": True},
    ]},
    {"make": "Opel", "as24": "opel/grandland", "mass": 1450, "large": True, "generations": [
        {"name": "Grandland X", "pa_model": "Grandland X/Grandland", "years": (2017, 2024), "new_price": 27000, "petrol": True},
    ]},
    {"make": "Opel", "as24": "opel/crossland", "mass": 1250, "generations": [
        {"name": "Crossland X", "pa_model": "Crossland X", "years": (2017, 2024), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Opel", "as24": "opel/adam", "mass": 1050, "generations": [
        {"name": "Adam M13", "pa_model": "Adam", "years": (2013, 2019), "new_price": 13500, "petrol": True},
    ]},
    {"make": "Peugeot", "as24": "peugeot/207", "mass": 1150, "generations": [
        {"name": "207 A7", "pa_model": "207", "years": (2006, 2014), "new_price": 13500, "new_price_estate": 14200, "petrol": True},
    ]},
    {"make": "Peugeot", "as24": "peugeot/208", "mass": 1100, "generations": [
        {"name": "208 I", "pa_model": "208", "years": (2012, 2019), "new_price": 12600, "petrol": True},
        {"name": "208 II", "pa_model": "208", "years": (2019, 2024), "new_price": 15750, "petrol": True},
    ]},
    {"make": "Peugeot", "as24": "peugeot/308", "mass": 1300, "generations": [
        {"name": "308 T7", "pa_model": "308", "years": (2007, 2013), "new_price": 18000, "new_price_estate": 19000},
        {"name": "308 T9", "pa_model": "308", "years": (2013, 2021), "new_price": 20250, "new_price_estate": 21000},
    ]},
    {"make": "Peugeot", "as24": "peugeot/2008", "mass": 1200, "generations": [
        {"name": "2008 I", "pa_model": "2008", "years": (2013, 2019), "new_price": 17500, "petrol": True},
        {"name": "2008 II", "pa_model": "2008", "years": (2019, 2024), "new_price": 22500, "petrol": True},
    ]},
    {"make": "Peugeot", "as24": "peugeot/508", "mass": 1500, "generations": [
        {"name": "508 I", "pa_model": "508", "years": (2010, 2018), "new_price": 25000, "new_price_estate": 26000},
        {"name": "508 II", "pa_model": "508", "years": (2018, 2024), "new_price": 30000, "new_price_estate": 31000},
    ]},
    {"make": "Peugeot", "as24": "peugeot/5008", "mass": 1550, "large": True, "generations": [
        {"name": "5008 I", "pa_model": "5008", "years": (2009, 2016), "new_price": 23400, "body": "van"},
        {"name": "5008 II", "pa_model": "5008", "years": (2017, 2024), "new_price": 27000, "body": "suv"},
    ]},
    {"make": "Renault", "as24": "renault/clio", "mass": 1100, "generations": [
        {"name": "Clio III", "pa_model": "Clio", "years": (2005, 2012), "new_price": 14000, "new_price_estate": 14700, "petrol": True},
        {"name": "Clio IV", "pa_model": "Clio", "years": (2012, 2019), "new_price": 15750, "new_price_estate": 16500, "petrol": True},
        {"name": "Clio V", "pa_model": "Clio", "years": (2019, 2024), "new_price": 18000, "petrol": True},
    ]},
    {"make": "Renault", "as24": "renault/megane", "mass": 1300, "generations": [
        {"name": "Megane III", "pa_model": "Megane", "years": (2008, 2016), "new_price": 18000, "new_price_estate": 19000},
        {"name": "Megane IV", "pa_model": "Megane", "years": (2016, 2023), "new_price": 20700, "new_price_estate": 21600},
    ]},
    {"make": "Renault", "as24": "renault/scenic", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "Scenic III", "pa_model": "Scenic/Grand Scenic", "years": (2009, 2016), "new_price": 20700},
        {"name": "Scenic IV", "pa_model": "Scenic/Grand Scenic", "years": (2016, 2022), "new_price": 24300},
    ]},
    {"make": "Renault", "as24": "renault/captur", "mass": 1200, "generations": [
        {"name": "Captur I", "pa_model": "Captur", "years": (2013, 2019), "new_price": 18000, "petrol": True},
        {"name": "Captur II", "pa_model": "Captur", "years": (2019, 2024), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Renault", "as24": "renault/kadjar", "mass": 1450, "large": True, "generations": [
        {"name": "Kadjar HA", "pa_model": "Kadjar", "years": (2015, 2022), "new_price": 22500},
    ]},
    {"make": "Renault", "as24": "renault/talisman", "mass": 1500, "generations": [
        {"name": "Talisman L2M", "pa_model": "Talisman", "years": (2015, 2022), "new_price": 28800, "new_price_estate": 30000},
    ]},
    {"make": "Renault", "as24": "renault/laguna", "mass": 1450, "generations": [
        {"name": "Laguna III", "pa_model": "Laguna", "years": (2007, 2015), "new_price": 25200, "new_price_estate": 26500},
    ]},
    {"make": "Renault", "as24": "renault/koleos", "mass": 1650, "large": True, "generations": [
        {"name": "Koleos I", "pa_model": "Koleos", "years": (2008, 2016), "new_price": 27000},
        {"name": "Koleos II", "pa_model": "Koleos", "years": (2017, 2024), "new_price": 31500},
    ]},
    {"make": "Renault", "as24": "renault/twingo", "mass": 950, "generations": [
        {"name": "Twingo II", "pa_model": "Twingo", "years": (2007, 2014), "new_price": 10500, "petrol": True},
        {"name": "Twingo III", "pa_model": "Twingo", "years": (2014, 2022), "new_price": 11000, "petrol": True},
    ]},
    {"make": "Renault", "as24": "renault/kangoo", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "Kangoo II", "pa_model": "Kangoo", "years": (2008, 2020), "new_price": 18000},
    ]},
    {"make": "Citroen", "as24": "citroen/c3", "mass": 1100, "generations": [
        {"name": "C3 II", "pa_model": "C3", "years": (2009, 2016), "new_price": 12150, "petrol": True},
        {"name": "C3 III", "pa_model": "C3", "years": (2016, 2024), "new_price": 13950, "petrol": True},
    ]},
    {"make": "Citroen", "as24": "citroen/c4", "mass": 1300, "generations": [
        {"name": "C4 II", "pa_model": "C4", "years": (2010, 2018), "new_price": 19000},
    ]},
    {"make": "Citroen", "as24": "citroen/c4-cactus", "mass": 1150, "generations": [
        {"name": "C4 Cactus E3", "pa_model": "C4 Cactus", "years": (2014, 2020), "new_price": 18000, "petrol": True},
    ]},
    {"make": "Citroen", "as24": "citroen/c5", "mass": 1550, "generations": [
        {"name": "C5 III", "pa_model": "C5", "years": (2008, 2017), "new_price": 27000, "new_price_estate": 28500},
    ]},
    {"make": "Citroen", "as24": "citroen/c3-picasso", "mass": 1300, "body": "van", "generations": [
        {"name": "C3 Picasso SH", "pa_model": "C3 Picasso", "years": (2009, 2017), "new_price": 16500, "petrol": True},
    ]},
    {"make": "Citroen", "as24": "citroen/c3-aircross", "mass": 1200, "generations": [
        {"name": "C3 Aircross 2R", "pa_model": "C3 Aircross", "years": (2017, 2024), "new_price": 17500, "petrol": True},
    ]},
    {"make": "Citroen", "as24": "citroen/c5-aircross", "mass": 1500, "large": True, "generations": [
        {"name": "C5 Aircross C84", "pa_model": "C5 Aircross", "years": (2018, 2024), "new_price": 27000},
    ]},
    {"make": "Citroen", "as24": "citroen/berlingo", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "Berlingo II", "pa_model": "Berlingo", "years": (2008, 2018), "new_price": 18000},
        {"name": "Berlingo III", "pa_model": "Berlingo", "years": (2018, 2024), "new_price": 22500},
    ]},
    {"make": "Dacia", "as24": "dacia/duster", "mass": 1300, "large": True, "generations": [
        {"name": "Duster I", "pa_model": "Duster", "years": (2010, 2017), "new_price": 13500, "petrol": True},
        {"name": "Duster II", "pa_model": "Duster", "years": (2018, 2024), "new_price": 15300, "petrol": True},
    ]},
    {"make": "Dacia", "as24": "dacia/sandero", "mass": 1050, "generations": [
        {"name": "Sandero II", "pa_model": "Sandero/Stepway", "years": (2012, 2020), "new_price": 9000, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/tipo", "mass": 1300, "generations": [
        {"name": "Tipo 356", "pa_model": "Tipo", "years": (2016, 2024), "new_price": 18900, "new_price_estate": 19800, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/500x", "mass": 1350, "generations": [
        {"name": "500X 334", "pa_model": "500X", "years": (2014, 2024), "new_price": 21600, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/500l", "mass": 1350, "body": "van", "generations": [
        {"name": "500L 351", "pa_model": "500L", "years": (2012, 2022), "new_price": 18000, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/doblo", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "Doblo 263", "pa_model": "Doblo", "years": (2010, 2022), "new_price": 18900},
    ]},
    {"make": "Fiat", "as24": "fiat/punto", "mass": 1100, "generations": [
        {"name": "Punto 199", "pa_model": "Punto/Grande Punto/EVO", "years": (2010, 2018), "new_price": 11700, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/500", "mass": 950, "generations": [
        {"name": "500 312", "pa_model": "500", "years": (2010, 2020), "new_price": 11700, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/panda", "mass": 1000, "generations": [
        {"name": "Panda 169", "pa_model": "Panda", "years": (2003, 2012), "new_price": 9900, "petrol": True},
        {"name": "Panda 319", "pa_model": "Panda", "years": (2012, 2024), "new_price": 10800, "petrol": True},
    ]},
    {"make": "Fiat", "as24": "fiat/bravo", "mass": 1300, "generations": [
        {"name": "Bravo 198", "pa_model": "Bravo", "years": (2007, 2014), "new_price": 17000, "petrol": True},
    ]},
    {"make": "Ford", "as24": "ford/focus", "mass": 1350, "generations": [
        {"name": "Focus III", "pa_model": "Focus", "years": (2011, 2018), "new_price": 20000, "new_price_estate": 21000, "petrol": True},
        {"name": "Focus IV", "pa_model": "Focus", "years": (2018, 2024), "new_price": 22500, "new_price_estate": 23500, "petrol": True},
    ]},
    {"make": "Ford", "as24": "ford/fiesta", "mass": 1100, "generations": [
        {"name": "Fiesta VI", "pa_model": "Fiesta", "years": (2008, 2017), "new_price": 13950, "petrol": True},
        {"name": "Fiesta VII", "pa_model": "Fiesta", "years": (2017, 2023), "new_price": 16650, "petrol": True},
    ]},
    {"make": "Ford", "as24": "ford/mondeo", "mass": 1550, "generations": [
        {"name": "Mondeo IV", "pa_model": "Mondeo", "years": (2007, 2014), "new_price": 26000, "new_price_estate": 27000},
        {"name": "Mondeo V", "pa_model": "Mondeo", "years": (2014, 2022), "new_price": 29700, "new_price_estate": 30700},
    ]},
    {"make": "Ford", "as24": "ford/c-max", "mass": 1450, "large": True, "body": "van", "generations": [
        {"name": "C-Max II", "pa_model": "C-Max/Grand C-Max", "years": (2010, 2019), "new_price": 20700},
    ]},
    {"make": "Ford", "as24": "ford/s-max", "mass": 1700, "large": True, "body": "van", "generations": [
        {"name": "S-Max I", "pa_model": "S-Max", "years": (2006, 2015), "new_price": 29000},
        {"name": "S-Max II", "pa_model": "S-Max", "years": (2015, 2022), "new_price": 32000},
    ]},
    {"make": "Ford", "as24": "ford/galaxy", "mass": 1750, "large": True, "body": "van", "generations": [
        {"name": "Galaxy III", "pa_model": "Galaxy", "years": (2006, 2015), "new_price": 30000},
        {"name": "Galaxy IV", "pa_model": "Galaxy", "years": (2015, 2022), "new_price": 33000},
    ]},
    {"make": "Ford", "as24": "ford/b-max", "mass": 1250, "body": "van", "generations": [
        {"name": "B-Max JK", "pa_model": "B-Max", "years": (2012, 2017), "new_price": 15300, "petrol": True},
    ]},
    {"make": "Ford", "as24": "ford/ecosport", "mass": 1300, "generations": [
        {"name": "EcoSport II", "pa_model": "EcoSport", "years": (2014, 2022), "new_price": 18000, "petrol": True},
    ]},
    {"make": "Ford", "as24": "ford/puma", "mass": 1250, "generations": [
        {"name": "Puma J2K", "pa_model": "Puma", "years": (2019, 2024), "new_price": 21600, "petrol": True},
    ]},
    {"make": "Toyota", "as24": "toyota/auris", "mass": 1350, "generations": [
        {"name": "Auris I", "pa_model": "Auris", "years": (2007, 2012), "new_price": 17100, "new_price_hybrid": 20700, "petrol": True},
        {"name": "Auris II", "pa_model": "Auris", "years": (2012, 2018), "new_price": 18000, "new_price_estate": 19000, "new_price_hybrid": 21500, "petrol": True},
    ]},
    {"make": "Toyota", "as24": "toyota/yaris", "mass": 1050, "generations": [
        {"name": "Yaris II", "pa_model": "Yaris", "years": (2005, 2011), "new_price": 11700, "petrol": True},
        {"name": "Yaris III", "pa_model": "Yaris", "years": (2011, 2020), "new_price": 13000, "new_price_hybrid": 15750, "petrol": True},
        {"name": "Yaris IV", "pa_model": "Yaris", "years": (2020, 2024), "new_price": 15300, "new_price_hybrid": 18900, "petrol": True},
    ]},
    {"make": "Toyota", "as24": "toyota/rav4", "mass": 1650, "large": True, "generations": [
        {"name": "RAV4 III", "pa_model": "RAV 4", "years": (2006, 2012), "new_price": 27000},
        {"name": "RAV4 IV", "pa_model": "RAV 4", "years": (2013, 2018), "new_price": 27000},
    ]},
    {"make": "Toyota", "as24": "toyota/avensis", "mass": 1450, "generations": [
        {"name": "Avensis T27", "pa_model": "Avensis", "years": (2009, 2018), "new_price": 25000, "new_price_estate": 26000},
    ]},
    {"make": "Toyota", "as24": "toyota/verso", "mass": 1500, "large": True, "body": "van", "generations": [
        {"name": "Verso R2", "pa_model": "Verso", "years": (2009, 2018), "new_price": 22500},
    ]},
    {"make": "Toyota", "as24": "toyota/corolla", "mass": 1350, "generations": [
        {"name": "Corolla E170", "pa_model": "Corolla", "years": (2013, 2018), "new_price": 18000, "petrol": True},
        {"name": "Corolla E210", "pa_model": "Corolla", "years": (2019, 2024), "new_price": 21600, "new_price_estate": 22500, "new_price_hybrid": 24000, "petrol": True},
    ]},
    {"make": "Toyota", "as24": "toyota/c-hr", "mass": 1450, "large": True, "generations": [
        {"name": "C-HR AX1", "pa_model": "C-HR", "years": (2016, 2024), "new_price": 22500, "new_price_hybrid": 25000},
    ]},
    {"make": "Kia", "as24": "kia/sportage", "mass": 1600, "large": True, "generations": [
        {"name": "Sportage III", "pa_model": "Sportage", "years": (2010, 2015), "new_price": 22500},
        {"name": "Sportage IV", "pa_model": "Sportage", "years": (2015, 2021), "new_price": 24500},
    ]},
    {"make": "Kia", "as24": "kia/ceed", "mass": 1300, "generations": [
        {"name": "Ceed ED", "pa_model": "cee`d", "years": (2006, 2012), "new_price": 17000, "new_price_estate": 17800, "petrol": True},
        {"name": "Ceed JD", "pa_model": "cee`d", "years": (2012, 2018), "new_price": 18000, "new_price_estate": 18900, "petrol": True},
        {"name": "Ceed CD", "pa_model": "cee`d", "years": (2018, 2024), "new_price": 20700, "new_price_estate": 21600, "petrol": True},
    ]},
    {"make": "Kia", "as24": "kia/rio", "mass": 1150, "generations": [
        {"name": "Rio III", "pa_model": "Rio", "years": (2011, 2017), "new_price": 13000, "petrol": True},
        {"name": "Rio IV", "pa_model": "Rio", "years": (2017, 2022), "new_price": 14400, "petrol": True},
    ]},
    {"make": "Hyundai", "as24": "hyundai/i30", "mass": 1300, "generations": [
        {"name": "i30 FD", "pa_model": "i30", "years": (2007, 2012), "new_price": 17000, "new_price_estate": 17800, "petrol": True},
        {"name": "i30 GD", "pa_model": "i30", "years": (2012, 2017), "new_price": 18000, "new_price_estate": 18900, "petrol": True},
        {"name": "i30 PD", "pa_model": "i30", "years": (2017, 2024), "new_price": 20700, "new_price_estate": 21600, "petrol": True},
    ]},
    {"make": "Hyundai", "as24": "hyundai/tucson", "mass": 1600, "large": True, "generations": [
        {"name": "Tucson TL", "pa_model": "Tucson", "years": (2015, 2020), "new_price": 23500, "petrol": True},
    ]},
    {"make": "Hyundai", "as24": "hyundai/i20", "mass": 1100, "generations": [
        {"name": "i20 PB", "pa_model": "i20", "years": (2008, 2014), "new_price": 12600, "petrol": True},
        {"name": "i20 GB", "pa_model": "i20", "years": (2014, 2020), "new_price": 13500, "petrol": True},
    ]},
    {"make": "Nissan", "as24": "nissan/qashqai", "mass": 1450, "large": True, "generations": [
        {"name": "Qashqai J10", "pa_model": "Qashqai", "years": (2007, 2013), "new_price": 20700, "petrol": True},
        {"name": "Qashqai J11", "pa_model": "Qashqai", "years": (2013, 2021), "new_price": 22500, "petrol": True},
    ]},
    {"make": "Nissan", "as24": "nissan/juke", "mass": 1250, "generations": [
        {"name": "Juke F15", "pa_model": "Juke", "years": (2010, 2019), "new_price": 17550, "petrol": True},
    ]},
    {"make": "Nissan", "as24": "nissan/x-trail", "mass": 1650, "large": True, "generations": [
        {"name": "X-Trail T31", "pa_model": "X-Trail", "years": (2007, 2014), "new_price": 27000},
        {"name": "X-Trail T32", "pa_model": "X-Trail", "years": (2014, 2022), "new_price": 28800},
    ]},
    {"make": "Nissan", "as24": "nissan/micra", "mass": 1000, "generations": [
        {"name": "Micra K13", "pa_model": "Micra", "years": (2010, 2017), "new_price": 11000, "petrol": True},
        {"name": "Micra K14", "pa_model": "Micra", "years": (2017, 2024), "new_price": 14400, "petrol": True},
    ]},
    {"make": "Mazda", "as24": "mazda/mazda3", "mass": 1300, "generations": [
        {"name": "Mazda3 BL", "pa_model": "3", "years": (2009, 2013), "new_price": 18000, "petrol": True},
        {"name": "Mazda3 BM", "pa_model": "3", "years": (2013, 2018), "new_price": 18900, "petrol": True},
        {"name": "Mazda3 BP", "pa_model": "3", "years": (2019, 2024), "new_price": 21600, "petrol": True},
    ]},
    {"make": "Mazda", "as24": "mazda/mazda6", "mass": 1450, "generations": [
        {"name": "Mazda6 GH", "pa_model": "6", "years": (2008, 2012), "new_price": 23400, "new_price_estate": 24300, "petrol": True},
        {"name": "Mazda6 GJ", "pa_model": "6", "years": (2012, 2021), "new_price": 25200, "new_price_estate": 26100, "petrol": True},
    ]},
    {"make": "Mazda", "as24": "mazda/cx-5", "mass": 1550, "large": True, "generations": [
        {"name": "CX-5 KE", "pa_model": "CX-5", "years": (2012, 2017), "new_price": 24300, "petrol": True},
        {"name": "CX-5 KF", "pa_model": "CX-5", "years": (2017, 2024), "new_price": 27000, "petrol": True},
    ]},
    {"make": "Mazda", "as24": "mazda/cx-3", "mass": 1300, "generations": [
        {"name": "CX-3 DK", "pa_model": "CX-3", "years": (2015, 2022), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Mazda", "as24": "mazda/mazda2", "mass": 1050, "generations": [
        {"name": "Mazda2 DE", "pa_model": "2", "years": (2007, 2014), "new_price": 12600, "petrol": True},
        {"name": "Mazda2 DJ", "pa_model": "2", "years": (2014, 2024), "new_price": 14400, "petrol": True},
    ]},
    {"make": "Volvo", "as24": "volvo/v40", "mass": 1450, "generations": [
        {"name": "V40 II", "pa_model": "V40", "years": (2012, 2019), "new_price": 24500},
    ]},
    {"make": "Volvo", "as24": "volvo/v60", "mass": 1650, "body": "estate", "generations": [
        {"name": "V60 I", "pa_model": "V60", "years": (2010, 2018), "new_price": 32400},
        {"name": "V60 II", "pa_model": "V60", "years": (2018, 2024), "new_price": 37800},
    ]},
    {"make": "Volvo", "as24": "volvo/s60", "mass": 1600, "generations": [
        {"name": "S60 II", "pa_model": "S60", "years": (2010, 2018), "new_price": 31500},
    ]},
    {"make": "Volvo", "as24": "volvo/xc60", "mass": 1800, "large": True, "generations": [
        {"name": "XC60 I", "pa_model": "XC60", "years": (2008, 2017), "new_price": 39500},
        {"name": "XC60 II", "pa_model": "XC60", "years": (2017, 2024), "new_price": 45000},
    ]},
    {"make": "Volvo", "as24": "volvo/xc40", "mass": 1550, "large": True, "generations": [
        {"name": "XC40 536", "pa_model": "XC40", "years": (2017, 2024), "new_price": 32400, "petrol": True},
    ]},
    {"make": "Honda", "as24": "honda/civic", "mass": 1300, "generations": [
        {"name": "Civic IX", "pa_model": "Civic", "years": (2012, 2017), "new_price": 18900, "petrol": True},
        {"name": "Civic X", "pa_model": "Civic", "years": (2017, 2021), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Honda", "as24": "honda/cr-v", "mass": 1650, "large": True, "generations": [
        {"name": "CR-V IV", "pa_model": "CR-V", "years": (2012, 2018), "new_price": 27000, "petrol": True},
        {"name": "CR-V V", "pa_model": "CR-V", "years": (2018, 2024), "new_price": 30600, "petrol": True},
    ]},
    {"make": "Honda", "as24": "honda/jazz", "mass": 1100, "generations": [
        {"name": "Jazz III", "pa_model": "Jazz", "years": (2008, 2015), "new_price": 13500, "petrol": True},
        {"name": "Jazz IV", "pa_model": "Jazz", "years": (2015, 2020), "new_price": 15300, "petrol": True},
    ]},
    {"make": "Mitsubishi", "as24": "mitsubishi/asx", "mass": 1400, "large": True, "generations": [
        {"name": "ASX GA", "pa_model": "ASX", "years": (2010, 2024), "new_price": 21600},
    ]},
    {"make": "Mitsubishi", "as24": "mitsubishi/outlander", "mass": 1650, "large": True, "generations": [
        {"name": "Outlander III", "pa_model": "Outlander", "years": (2012, 2021), "new_price": 28000, "petrol": True},
    ]},
    {"make": "Suzuki", "as24": "suzuki/swift", "mass": 1000, "generations": [
        {"name": "Swift IV", "pa_model": "Swift", "years": (2010, 2017), "new_price": 11250, "petrol": True},
        {"name": "Swift V", "pa_model": "Swift", "years": (2017, 2024), "new_price": 12600, "petrol": True},
    ]},
    {"make": "Suzuki", "as24": "suzuki/vitara", "mass": 1200, "generations": [
        {"name": "Vitara LY", "pa_model": "Vitara", "years": (2015, 2024), "new_price": 18000, "petrol": True},
    ]},
    {"make": "Suzuki", "as24": "suzuki/sx4-s-cross", "mass": 1250, "generations": [
        {"name": "S-Cross JY", "pa_model": "SX4 S-Cross", "years": (2013, 2021), "new_price": 18900, "petrol": True},
    ]},
    {"make": "Chevrolet", "as24": "chevrolet/cruze", "mass": 1400, "generations": [
        {"name": "Cruze J300", "pa_model": "Cruze", "years": (2009, 2016), "new_price": 19800, "petrol": True},
    ]},
    {"make": "Alfa Romeo", "as24": "alfa-romeo/giulietta", "mass": 1350, "generations": [
        {"name": "Giulietta 940", "pa_model": "Giulietta", "years": (2010, 2020), "new_price": 22500, "petrol": True},
    ]},
]
MODELS = CORE_MODELS + DAILY_MODELS


def pa_names(pa_model):
    """The PA model names one generation is listed under ("316/318/320" -> three names)."""
    return pa_model.split("/")


def petrol_years(as24_path):
    """Registration years in which plain petrol sells for this model: the years of its "petrol" generations."""
    years = set()
    for model in MODELS:
        if model["as24"] != as24_path:
            continue
        for generation in model["generations"]:
            if generation.get("petrol"):
                first, last = generation["years"]
                years.update(range(first, last + 1))
    return years


def generations_for(model, year):
    """All generations a car of this first-registration year can belong to (two in a change-over year)."""
    return [g for g in model["generations"] if g["years"][0] <= year <= g["years"][1]]


def drive_of(text):
    """'4x4' when the title or ad text names four-wheel drive, else None."""
    text = (text or "").lower()
    for word in FOUR_BY_FOUR_WORDS:
        if word in text:
            return "4x4"
    if FOUR_BY_FOUR_BADGES.search(text) or SUB_MODELS["scout"].search(text):
        return "4x4"
    return None


# A generation the seller names in the title ("Passat B6", "Golf VI"). The year alone can mislead: VW sold the
# B6 into 2011, when our table already starts the B7 (Novky 24.11.2026: a 2011 "B6" priced as a B7 was 1,300 high).
NAMED_GENERATIONS = {
    "volkswagen/passat": [(re.compile(r"\bb([5-9])\b"), "Passat B{}")],
    # "Golf 4 Motion" and "Golf 4-Motion" are four-wheel drive (see FOUR_BY_FOUR_WORDS), not a Golf 4
    "volkswagen/golf": [(re.compile(r"\bgolf ?([4-8])\b(?![ -]?mot)"), "Golf {}"),
                        (re.compile(r"\bmk ?([4-8])\b"), "Golf {}"),
                        (re.compile(r"\b(?:golf|variant) (iv|v|vi|vii|viii)\b"), "Golf {}")],
    "volkswagen/tiguan": [(re.compile(r"\btiguan (i|ii)\b"), "Tiguan {}")],
    "skoda/octavia": [(re.compile(r"\boctavia (ii|iii)\b"), "Octavia {}")],
    "audi/a4": [(re.compile(r"\bb([6-9])\b"), "A4 B{}")],
    "bmw/x1": [(re.compile(r"\b(e84|f48|u11)\b"), "X1 {}")],
    "bmw/520": [(re.compile(r"\b(e6[01]|f07|f1[01]|g3[01]|g6[01])\b"), "520d {}")],
    "bmw/3er": [(re.compile(r"\b(e9[0-3]|f3[014]|g2[01])\b"), "3er {}")],
    "bmw/1er": [(re.compile(r"\b(e8[1278]|f2[01]|f40)\b"), "1er {}")],
    "audi/a6": [(re.compile(r"\b(c[5-9])\b"), "A6 {}"),
                (re.compile(r"\ba6 (?:avant )?(4[fgk])\b"), "A6 {}")],
    "opel/insignia": [(re.compile(r"\binsignia[ -]+([ab])\b(?!-\w)"), "Insignia {}")],
    "mercedes-benz/b-klasse": [(re.compile(r"\b(w24[567])\b"), "B-Klasse {}")],
    "ford/kuga": [(re.compile(r"\bkuga (iii|ii|i)\b"), "Kuga {}")],
    "mercedes-benz/a-klasse": [(re.compile(r"\b(w1(?:69|76|77))\b"), "A-Klasse {}")],
    "mercedes-benz/c-klasse": [(re.compile(r"\b([ws]20[45])\b"), "C-Klasse {}")],
    "mercedes-benz/e-klasse": [(re.compile(r"\b([ws]21[23])\b"), "E-Klasse {}")],
    "mercedes-benz/cla": [(re.compile(r"\b([cx]11[78])\b"), "CLA {}")],
    "mercedes-benz/gla": [(re.compile(r"\b(x156|h247)\b"), "GLA {}")],
    "bmw/x3": [(re.compile(r"\b(f25|g01)\b"), "X3 {}")],
    # "Corsa-e" is the electric Corsa F: named "Corsa E", it is left out rather than priced as a Corsa E
    "opel/corsa": [(re.compile(r"\bcorsa[ -]([d-f])\b"), "Corsa {}")],
    "opel/zafira": [(re.compile(r"\bzafira[ -](tourer|family|b|c)\b"), "Zafira {}")],
}
ROMAN = {"iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8"}
GENERATION_ALIASES = {"520d F07": "520d F10", "520d F11": "520d F10", "520d G31": "520d G30",
                      "3er E91": "3er E90", "3er E92": "3er E90", "3er E93": "3er E90",
                      "3er F31": "3er F30", "3er F34": "3er F30", "3er G21": "3er G20", "1er F21": "1er F20",
                      "A6 4F": "A6 C6", "A6 4G": "A6 C7", "A6 4K": "A6 C8",
                      "C-Klasse S204": "C-Klasse W204", "C-Klasse S205": "C-Klasse W205",
                      "E-Klasse S212": "E-Klasse W212", "E-Klasse S213": "E-Klasse W213",
                      "CLA X117": "CLA C117", "CLA X118": "CLA C118",
                      "Zafira TOURER": "Zafira C", "Zafira FAMILY": "Zafira B"}


def named_generation(model, title):
    """The generation the title names, in MODELS' own naming ("Passat B6"), or None when it names none."""
    title = (title or "").lower()
    for pattern, name in NAMED_GENERATIONS.get(model["as24"], []):
        found = pattern.search(title)
        if found:
            part = found.group(1)
            generation = name.format(ROMAN.get(part, part.upper()))
            return GENERATION_ALIASES.get(generation, generation)
    return None


def sub_model(title, model=None):
    """The sub-model a title names (Scout, GTD, Golf Plus ...), or None for the base model."""
    text = f"{title or ''} {model or ''}".lower()
    for name, pattern in SUB_MODELS.items():
        if pattern.search(text):
            return name
    return None
