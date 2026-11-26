"""Serbian sale price for the exact variant, full cost of one foreign car, profit and max buy price."""
from carfinder import customs, market, models, transport

MIN_ADS = 3                # with fewer clean ads of the exact variant there is no market to read a price from
THIN_MARKET_ADS = 5        # useful context when the exact variant has only three or four clean ads
YEAR_STEP = 0.07           # cached low-end asks move about 7–7.6% per model year
ASK_TO_SALE_CUT = 0.09     # 9% brings the cheapest credible asks, after year and mileage, near Novky's sale estimates
BAIT_SHARE = 0.75          # a cheapest ad under 75% of the next one stands alone: bait or a hidden wreck
MAX_BAIT_ADS = 2           # a third lonely cheap ad in a row is the market itself, not bait
DEFAULT_BUY_DISCOUNT_EUR = 200   # midpoint of the owner's usual €100–€300 reduction abroad
KM_FREE = 250000           # up to this mileage the cheapest Serbian ads already are cars like ours
KM_CUT_PER_10K = 0.011     # within 250–350k km, the median of 52 same-variant groups in the cache was 1.06% per 10k
KM_MAX_CUT = 0.12          # cap the mileage deduction where the high-mileage cache evidence runs out
TARGET_MIN_EUR = 1000
TARGET_CASH_EUR = 6000     # Bane: at least 1000e on up to 5-6k invested, proportionally more above
CC_TOLERANCE = 30
KW_TOLERANCE = 2           # keeps Golf 77 kW and 81 kW apart
DEFAULT_REPAIR_EUR = 300   # Bane 24.11.2026: painting one panel is about 80 EUR, a headlight 150-200 EUR in Serbia
LOW_KM_SHARE = 0.6
DEFAULT_MASS_KG = 1450
SUSPICIOUS_SHARE = 0.5     # under half of AutoScout24's own market median for this car
THIN_MARKET_FLAG = f"malo ovakvih oglasa u Srbiji (manje od {THIN_MARKET_ADS}), prodajna cena je nesigurna"
BIG_REPAIR_FLAG = "veća popravka: unesi cenu popravke"
# shortcut: 90 days is three times the usual PA ad age of 25.11.2026; set it again from pa_seen after a few weeks
STALE_ANCHOR_DAYS = 90
STALE_ANCHOR_FLAG = "najjeftiniji oglas u Srbiji stoji preko 3 meseca, za tu cenu auto se možda ne prodaje"
UNREAD_FLAG = "opis nije pročitan"
PHOTOS_UNREAD_FLAG = "slike nisu pregledane, pogledaj ih u oglasu"
GOLF6_ESTATE_FLAG = "Golf 6 karavan se pravio u Meksiku: carina veća"

# Equipment Bane cares about, as (label, words in German or English listings, words in Serbian titles).
# mobile.de (through Apify) lists equipment in English.
EQUIPMENT = [
    ("MF volan", ("multifunktionslenkrad", "multifunction steering wheel"), ("multifunkc",)),
    ("Koža", ("leder", "vollleder", "teilleder"), ("koža", "koza")),
    ("Navigacija", ("navigationssystem", "navi"), ("navi", "nav")),
    ("LED/Xenon", ("led-scheinwerfer", "xenon", "bi-xenon", "led scheinwerfer", "led headlights"), ("led", "xenon")),
    ("Automatska klima", ("klimaautomatik",), ("automatska klima",)),
    ("Parking senzori", ("einparkhilfe",), ("pdc", "senzor")),
    ("Kamera", ("kamera", "rückfahrkamera", "camera"), ("kamera",)),
    ("Panorama", ("panorama", "panoramic"), ("panoram",)),
    ("Grejanje sedišta", ("sitzheizung", "heated seats"), ("grejanje",)),
    ("Kuka", ("anhängerkupplung", "ahk", "trailer coupling"), ("kuka",)),
]


def equipment_of(car):
    haystack = " ".join([car.get("title") or "", car.get("text") or "", *(car.get("equipment") or [])]).lower()
    return [label for label, german, _ in EQUIPMENT if any(word in haystack for word in german)]


def suspicious(car):
    """Far cheaper than the same car abroad. Only a label: a real deal costs about 0.45 x the Serbian price,
    so a test against the Serbian price would hide exactly the deals."""
    return bool(car.get("market_median") and car["price"] < SUSPICIOUS_SHARE * car["market_median"])


def big_repair_unpriced(car, settings):
    """The seller describes a big repair and Bane has not yet typed what it costs."""
    reading = car.get("ai") or {}
    return reading.get("state") == "kvar" and reading.get("repair") == "velika" and settings.get("repair") is None


def photos_unseen(car):
    """The ad has photos and Haiku saw fewer than half of them, or it never read the car."""
    reading = car.get("ai") or {}
    if reading:
        return bool(reading.get("photos_unread"))
    return bool(car.get("detailed") and (car.get("images") or car.get("image")))


def damage_unseen(car, settings):
    """The car is marked damaged, nobody has looked at its photos and Bane has not typed what the repair costs."""
    return bool(car.get("damaged")) and photos_unseen(car) and settings.get("repair") is None


def description_unread(car):
    """The scan asked Haiku for this ad's text and got no reading (no credit, a timeout, an odd answer), so a
    fault the seller describes is not in the price. A car the scan never sent to Haiku has no "ai" at all."""
    return "ai" in car and not car["ai"] and bool((car.get("text") or "").strip())


def flags_of(car):
    """Warnings Bane should read before calling the seller."""
    text = (car.get("text") or "").lower()
    flags = []
    if car.get("damaged"):
        flags.append("oštećen")
    reading = car.get("ai") or {}
    if reading.get("state") == "kvar" and reading.get("note"):
        flags.append("iz opisa: " + reading["note"])
    if description_unread(car):
        flags.append(UNREAD_FLAG)
    if photos_unseen(car):
        flags.append(PHOTOS_UNREAD_FLAG)
    if suspicious(car):
        flags.append("sumnjivo jeftin, možda prevara ili skriven kvar")
    if "whatsapp" in text:
        flags.append("WhatsApp u oglasu, čest znak prevare")
    if "export" in text or "gewerbe" in text:
        flags.append("prodaje se firmama ili za izvoz, bez garancije")
    if car.get("vat_deductible") and not car.get("net_price"):
        flags.append("u ceni je PDV, za izvoz traži cenu bez PDV-a")
    if car.get("seller") == "private":
        flags.append("privatni prodavac")
    if not car.get("detailed"):
        flags.append("nismo otvorili oglas, opis i slike nisu pregledani")
    flags.extend(market.notes(car))   # what Serbian buyers hold against this variant
    return flags


def target_profit(cash_eur):
    """1000e up to 6000e invested, then the same share (1/6) for pricier cars, so there is no jump."""
    return max(TARGET_MIN_EUR, cash_eur * TARGET_MIN_EUR / TARGET_CASH_EUR)


def mixed_year(model, year):
    """A change-over year whose PA ads hold both generations under one model name (Tiguan 2016, Octavia 2013)."""
    names = [generation["pa_model"] for generation in models.generations_for(model, year)]
    return len(names) > 1 and len(set(names)) == 1


def year_window(model, year, generation=None):
    """Comparable years within one year and the resolved generation."""
    if generation is None:
        generation = generation_of({"year": year}, model)
        if generation is None:
            return year, year
    first, last = generation["years"]
    year_from = max(first, year - 1)
    # The previous generation anchored 17 of 47 2017 Tiguans through the mixed 2016 listings.
    # The two Insignias can use explicitly named 2017 ads on either side of the change-over.
    if model["as24"] != "opel/insignia" and mixed_year(model, year_from):
        year_from = year
    return year_from, min(last, year + 1)


def body_group(body):
    """Hatch and sedan of one model sell alike; estate, MPV, coupe and cabrio are separate markets."""
    if body in ("estate", "van", "coupe", "cabrio", "pickup"):
        return body
    return "other"


def a3_body(car):
    # AutoScout24 uses Limousine even on a Sportback.
    title = (car.get("title") or "").lower()
    if "sportback" in title or "spb" in title.split():
        return "hatchback"
    return car.get("body")


def is_match(car, comp):
    """Exact variant: same fuel, gearbox, body group, engine (cc and kW), doors when known, drive and sub-model."""
    if not car.get("gearbox") or comp.get("gearbox") != car["gearbox"] or comp.get("fuel") != car["fuel"]:
        return False
    if body_group(comp.get("body")) != body_group(car.get("body")):
        return False
    model_name = (car.get("model") or "").lower()
    if model_name == "a3":
        body = a3_body(car)
        if body and body != a3_body(comp):
            return False
    if model_name in ("tiguan", "3008") and comp.get("body") != "suv":
        return False
    if not comp.get("cc") or not comp.get("kw"):
        return False
    if car.get("cc") and abs(comp["cc"] - car["cc"]) > CC_TOLERANCE:
        return False
    if not car.get("kw") or abs(comp["kw"] - car["kw"]) > KW_TOLERANCE:
        return False
    if car.get("km") and comp.get("km") and comp["km"] < LOW_KM_SHARE * car["km"]:
        return False   # a much lower-mileage Serbian car would overstate what ours sells for
    if car.get("doors") and comp.get("doors") != car["doors"]:
        return False
    if car.get("drive") != comp.get("drive"):
        return False
    if models.sub_model(comp.get("title"), comp.get("model")) != models.sub_model(car.get("title"), car.get("model")):
        return False   # a Scout, RS or GTD and the base model are priced only against their own kind, both ways
    return True


def adjusted_price(car, comp):
    """What a Serbian ad asks, brought to our car's year: an older car is raised, a newer one lowered by YEAR_STEP.

    Both ways (Novky 24.11.2026): a 2010 Golf priced at 2011 asking prices came out 1,600 too high."""
    if comp.get("year") and comp["year"] < car["year"]:
        return round(comp["price"] * (1 + YEAR_STEP))
    if comp.get("year") and comp["year"] > car["year"]:
        return round(comp["price"] * (1 - YEAR_STEP))
    return comp["price"]


def km_factor(km):
    """Share of the price that is left for a car with this mileage; 1.0 up to KM_FREE or when km is unknown."""
    if not km or km <= KM_FREE:
        return 1.0
    cut = KM_CUT_PER_10K * (km - KM_FREE) / 10000
    return 1 - min(cut, KM_MAX_CUT)


def serbian_price(car, comparables):
    """Estimate the sale from the cheapest credible ask adjusted for year and mileage."""
    ads = []
    for comp in comparables:
        adjusted = adjusted_price(car, comp)
        # The Serbian ad already reflects its own mileage. Only charge the extra wear on ours.
        factor = 1.0
        if comp.get("km"):
            factor = min(1.0, km_factor(car.get("km")) / km_factor(comp["km"]))
        ads.append(dict(comp, adjusted=adjusted, km_factor=factor, comparable_price=round(adjusted * factor)))
    ads.sort(key=lambda ad: ad["comparable_price"])
    bait = 0
    while bait < MAX_BAIT_ADS and len(ads) > 1 and ads[0]["comparable_price"] < BAIT_SHARE * ads[1]["comparable_price"]:
        ads.pop(0)
        bait += 1
    if len(ads) < MIN_ADS:
        return None
    first = ads[0]
    asking = first["comparable_price"]
    price = round(asking * (1 - ASK_TO_SALE_CUT))
    return {
        "price": price,
        "sale_cut": asking - price,
        "anchor": first["adjusted"],
        "km_factor": first["km_factor"],
        "first": first,
        "next": ads[1:6],
        "skipped_bait": bait,
        "n": len(ads),
        "within_500": sum(1 for ad in ads if ad["comparable_price"] <= asking + 500),
    }


def transport_of(car, settings, model):
    if settings.get("transport_override") is not None:
        return settings["transport_override"]
    return transport.transport_eur(car["country"], car.get("zip"), car.get("city"),
                                   large_car=model.get("large", False))


def generation_of(car, model):
    """The generation the title or AutoScout24 names when its years allow it, None when they do not. Without a
    name, a change-over year gives the older generation: Ogi 26.11.2026, a 5k older BMW was priced as our 10k one."""
    named = models.named_generation(model, car.get("title")) or models.as24_generation(model, car.get("url"))
    generations = models.generations_for(model, car["year"])
    if named:
        generations = [generation for generation in generations if generation["name"] == named]
    if not generations:
        return None
    return generations[0]   # the table lists every model's generations oldest first


def fuel_sells(car, model):
    """Plain petrol sells in Serbia only for a generation marked "petrol" (models.py); every other fuel does.
    A car without a model (one no longer scanned) or without a generation is never a petrol deal."""
    if car["fuel"] != "petrol":
        return True
    if model is None:
        return False
    generation = generation_of(car, model)
    return bool(generation and generation.get("petrol"))


def new_price_of(car, model):
    """Serbian new price customs values this variant from, or None when the generation is unknown."""
    generation = generation_of(car, model)
    if generation is None:
        return None
    if car.get("fuel") == "hybrid" and generation.get("new_price_hybrid"):
        return generation["new_price_hybrid"]
    if car.get("body") == "estate" and generation.get("new_price_estate"):
        return generation["new_price_estate"]
    return generation.get("new_price")


def outside_eu(car, model):
    """(built outside the EU, flag for the card). A VIN from a plant outside the EU decides; without one a Golf 6
    estate is from Puebla, Mexico, and any other car is judged by make and model (no flag). A European VIN never
    clears a car: VW's Mexican plant builds European-market cars under WVW and WVG."""
    vin = customs.non_eu_vin((car.get("title") or "") + " " + (car.get("text") or ""))
    if vin:
        return True, f"proizveden van EU (VIN {vin}), carina veća"
    generation = generation_of(car, model)
    if generation and generation["name"] == "Golf 6" and car.get("body") == "estate":
        return True, GOLF6_ESTATE_FLAG
    return not customs.eu_built(car["make"], car["model"], car["year"]), None


def import_bill_of(car, new_price, invoice_eur, mass, duty, today):
    """The catalogue bill for the car's generation; the invoice bill when the generation is unknown."""
    if new_price is None:
        return customs.import_bill(invoice_eur, mass, duty, today)
    return customs.catalogue_bill(new_price, car["year"], car.get("month"), mass, duty, today)


def costs(car, buy_eur, settings, model, today=None):
    """Cash needed to have this car cleared and tested in Pancevo, for a given purchase price."""
    transport_eur = transport_of(car, settings, model)
    border_part = max(0, transport_eur - transport.DOMESTIC_LEG_EUR)
    built_outside, _ = outside_eu(car, model)
    duty = customs.duty_rate(car["make"], car["model"], car["fuel"], settings.get("origin_proof", True),
                             eu=not built_outside)
    generation = generation_of(car, model) or {}
    mass = car.get("mass") or generation.get("mass") or model.get("mass") or DEFAULT_MASS_KG
    new_price = new_price_of(car, model)
    invoice_eur = buy_eur + border_part
    bill = import_bill_of(car, new_price, invoice_eur, mass, duty, today)
    no_proof_rate = customs.duty_rate(car["make"], car["model"], car["fuel"], origin_proof=False)
    no_proof_bill = import_bill_of(car, new_price, invoice_eur, mass, no_proof_rate, today)
    no_proof_extra = no_proof_bill["total"] - bill["total"]
    if settings.get("repair") is not None:
        repair = settings["repair"]
    else:
        repair = DEFAULT_REPAIR_EUR if car.get("damaged") else 0
    worst_cash = None
    if settings.get("import_total") is not None:
        bill = dict(bill, total=settings["import_total"])   # Bane's own figure from the papers is final
        no_proof_extra = 0
    elif new_price is not None:
        # Customs takes the invoice instead when it is higher than the catalogue value; the forwarder's fee,
        # plates and small charges the catalogue bill carries are paid either way.
        invoice_total = customs.import_bill(invoice_eur, mass, duty, today)["total"] + customs.UNLISTED_COSTS_EUR
        if invoice_total > bill["total"]:
            worst_cash = round(buy_eur + transport_eur + invoice_total + repair)
    cash = round(buy_eur + transport_eur + bill["total"] + repair)
    return {
        "buy": round(buy_eur),
        "transport": transport_eur,
        "import": bill,
        "duty_rate": duty,
        "no_proof_extra": no_proof_extra,
        "no_proof_rate": no_proof_rate,
        "repair": repair,
        "cash": cash,
        "cash_worst": worst_cash,
    }


def buy_price(car):
    """Net only when the ad states a net price; 'VAT deductible' alone must still be confirmed by the seller."""
    if car.get("vat_deductible") and car.get("net_price"):
        return car["net_price"]
    return car["price"]


def evaluate(car, matched, settings, model, today=None):
    if generation_of(car, model) is None:
        return None
    if not car.get("cc") and car.get("detailed") and matched:
        displacements = [comp["cc"] for comp in matched if comp.get("cc")]
        if displacements:
            largest = max(displacements)
            if largest > models.MAX_CC or largest - min(displacements) > CC_TOLERANCE:
                return None
    serbia = serbian_price(car, matched)
    if serbia is None or transport_of(car, settings, model) is None:
        return None
    return {"serbia": serbia, **reprice(car, serbia, settings, model, today)}


def reprice(car, serbia, settings, model, today=None):
    """Costs and profit for a known Serbian price; the page calls this on every view with current rules."""
    sale = serbia["price"] * (1 - settings.get("sale_discount", 0.0))
    asking = round(buy_price(car))
    discount = min(asking, settings.get("buy_discount", DEFAULT_BUY_DISCOUNT_EUR))
    cost = costs(car, asking - discount, settings, model, today)
    cost.update(asking=asking, buy_discount=discount)
    profit = round(sale - cost["cash"])
    target = round(target_profit(cost["cash"]))
    thin_market = serbia["n"] < THIN_MARKET_ADS
    repair_unknown = big_repair_unpriced(car, settings)
    # a damaged car whose photos nobody saw waits for Bane's look, like a big repair without a price
    waits_for_check = repair_unknown or damage_unseen(car, settings)
    flags = flags_of(car)
    if thin_market:
        flags.append(THIN_MARKET_FLAG)
    if repair_unknown:
        flags.append(BIG_REPAIR_FLAG)
    _, outside_flag = outside_eu(car, model)
    if outside_flag:
        flags.append(outside_flag)
    # an anchor that sat this long is a price nobody has paid yet
    anchor_age = (serbia.get("first") or {}).get("age_days")
    if anchor_age is not None and anchor_age >= STALE_ANCHOR_DAYS:
        flags.append(STALE_ANCHOR_FLAG)
    return {
        "sale": round(sale),
        "cost": cost,
        "profit": profit,
        "profit_worst": None if cost["cash_worst"] is None else round(sale - cost["cash_worst"]),
        "target": target,
        "passes": profit >= target and bool(car.get("detailed")) and not waits_for_check,
        "cash_ceiling": cash_ceiling(sale),
        "max_buy": max_buy_price(car, sale, settings, model, today),
        "equipment": equipment_of(car),
        "flags": flags,
    }


def cash_ceiling(sale_eur):
    """Most cash that can go in and still leave the target profit (same rounding as passes_at)."""
    if round(sale_eur) < round(target_profit(0)):
        return 0
    low, high = 0, int(sale_eur)
    while high - low > 1:
        middle = (low + high) // 2
        if round(sale_eur - middle) >= round(target_profit(middle)):
            low = middle
        else:
            high = middle
    return low


def passes_at(car, buy_eur, sale_eur, settings, model, today=None):
    cash = costs(car, buy_eur, settings, model, today)["cash"]
    return round(sale_eur - cash) >= round(target_profit(cash))


def max_buy_price(car, sale_eur, settings, model, today=None):
    """Highest whole-euro purchase price that still reaches the target; None when no price does."""
    if not passes_at(car, 0, sale_eur, settings, model, today):
        return None
    low, high = 0, int(sale_eur)   # low always passes, high never does (cost exceeds sale)
    while high - low > 1:
        middle = (low + high) // 2
        if passes_at(car, middle, sale_eur, settings, model, today):
            low = middle
        else:
            high = middle
    return low
