"""Local page: python -m carfinder.web, then open http://127.0.0.1:8765"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

from carfinder import db, models, scan, valuation

app = FastAPI()
MODEL_BY_KEY = {m["as24"]: m for m in models.MODELS}
# the first generation's name without its code: "Golf 6" -> "Golf", "1er F20" -> "1er"
MODEL_LABELS = [(m["as24"], m["make"].replace("Volkswagen", "VW") + " " + m["generations"][0]["name"].rsplit(" ", 1)[0])
                for m in models.MODELS]
MODEL_LABELS.sort(key=lambda pair: pair[1])   # 138 models: the page's filter lists them A to Z
FUEL_NAMES = {"diesel": "dizel", "petrol": "benzin", "petrol_lpg": "benzin + TNG", "petrol_cng": "benzin + metan (CNG)",
              "hybrid": "hibrid", "electric": "struja"}
FRESH_S = 2 * 24 * 3600   # cars not seen for two days are probably sold
MAX_CARDS = 300
VERDICTS = ("uzeo bih", "onako", "ne")   # Novky's word on a car, as Bane types it in
VERDICT_NOTE_CHARS = 80
SPEED_ORDER = {"brzo": 0, "sporo": 2}   # a passing car that sells fast comes first; normal and unknown sit between
PAGE = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=True).get_template("page.html")


def warnings_label(count):
    """'1 upozorenje', '2 upozorenja', '5 upozorenja', '11 upozorenja', '21 upozorenje': Serbian plural."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} upozorenje"
    return f"{count} upozorenja"


def days_label(count):
    """'1 dan', '2 dana', '11 dana', '21 dan': Serbian plural."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} dan"
    return f"{count} dana"


def parse_eur(text):
    """'5500', '5.500' or '5 500' -> 5500; anything else -> None."""
    cleaned = re.sub(r"[.\s]", "", text or "")
    return int(cleaned) if re.fullmatch(r"[0-9]{1,7}", cleaned) else None


def current_result(entry, override):
    """Costs and profit with today's customs rules and Bane's edits; the Serbian price comes from the scan."""
    model = MODEL_BY_KEY.get(entry["model_key"])
    if model is None:
        return entry["result"]
    settings = scan.settings_for(entry["data"], {entry["data"]["id"]: override})
    return {**entry["result"], **valuation.reprice(entry["data"], entry["result"]["serbia"], settings, model)}


def sort_key(sort):
    def key(entry):
        if sort == "cash":
            return entry["result"]["cost"]["cash"]
        if sort == "newest":
            return -entry["first_seen"]
        return -entry["result"]["profit"]
    return key


def speed_rank(entry):
    """Order of a car on the profit sort: passing cars by sell speed, then the cars under the target."""
    if not entry["result"]["passes"]:
        return 3
    # Novky 25.11.2026 on the top A6, priced from 3 Serbian ads: "E to nzm". An unsure sale price never leads.
    if entry["result"]["serbia"].get("n", valuation.THIN_MARKET_ADS) < valuation.THIN_MARKET_ADS:
        return 2
    speed = entry["result"]["serbia"].get("speed") or {}
    return SPEED_ORDER.get(speed.get("label"), 1)


def verdict_record(conn, car_id, override):
    """What the card showed when Novky judged the car, as JSON: the asking price, sale in Serbia, profit and speed.

    cars.result changes on every scan, so this copy is what his verdict can later be checked against."""
    entry = db.car(conn, car_id)
    if entry is None or "anchor" not in entry["result"]["serbia"]:
        return None
    result = current_result(entry, override)
    return json.dumps({"price": entry["data"]["price"], "sale": result["sale"], "profit": result["profit"],
                       "speed": result["serbia"].get("speed")})


def without_duplicates(cars):
    """Dealers often post the same car twice (or on both sites): same year, km, price and city."""
    seen, unique = set(), []
    for entry in cars:
        data = entry["data"]
        if not data.get("km") or not data.get("city"):
            unique.append(entry)   # too little to tell two ads apart safely
            continue
        key = (entry["model_key"], data["country"], data["year"], data["km"], data["price"], data["city"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


@app.get("/", response_class=HTMLResponse)
def index(country: str = "", model: str = "", max_cash: str = "", all: str = "", sort: str = "profit"):
    conn = db.connect()
    overrides = db.overrides(conn)
    budget = parse_eur(max_cash)
    cars = []
    now = time.time()
    for entry in db.cars(conn, now - FRESH_S):
        data = entry["data"]
        override = overrides.get(data["id"]) or {}
        if override.get("hidden") or not scan.usable(data, MODEL_BY_KEY.get(entry["model_key"])):
            continue   # hidden, or saved before a scan rule existed
        if country and data["country"] != country or model and entry["model_key"] != model:
            continue
        if "anchor" not in entry["result"]["serbia"]:
            continue   # priced by the old rule (2nd and 3rd ad, median floor); its next scan prices it again
        if entry["model_key"] == "audi/a3":
            data["body"] = valuation.a3_body(data)
        entry["result"] = current_result(entry, override)
        entry["override"] = override
        if budget is not None and entry["result"]["cost"]["cash"] > budget:
            continue
        if not all and not entry["result"]["passes"]:
            continue
        cars.append(entry)
    cars.sort(key=sort_key(sort))
    if sort not in ("cash", "newest"):
        cars.sort(key=speed_rank)   # stable: the profit order stays inside each speed group
    cars = without_duplicates(cars)
    runs = db.last_runs(conn, 1)
    if runs:
        last_run = datetime.fromtimestamp(runs[0]["finished"]).strftime("%d.%m. u %H:%M")
        if runs[0]["status"] != "ok":
            last_run += " (delimično)"
    else:
        last_run = "još nije"
    return PAGE.render(cars=cars[:MAX_CARDS], country=country, model=model, max_cash=max_cash, show_all=bool(all),
                       sort=sort, now=time.time(), model_keys=MODEL_LABELS, fuel_names=FUEL_NAMES, last_run=last_run,
                       min_ads=valuation.THIN_MARKET_ADS, big_flag=valuation.BIG_REPAIR_FLAG,
                       warnings_label=warnings_label, days_label=days_label, verdicts=VERDICTS)


@app.post("/override")
def override(car_id: str = Form(...), transport: str = Form(""), repair: str = Form(""),
             no_origin: str = Form(""), carina: str = Form(""), buy_discount: str = Form(""),
             hidden: str = Form(""), verdict: str = Form(""), verdict_note: str = Form(""), back: str = Form("/")):
    conn = db.connect()
    old = db.overrides(conn).get(car_id) or {}
    verdict = verdict if verdict in VERDICTS else None
    verdict_at, verdict_result = old.get("verdict_at"), old.get("verdict_result")
    if verdict is None:
        verdict_at, verdict_result = None, None
    elif verdict != old.get("verdict"):   # a new word: when he said it and what the card showed then
        verdict_at, verdict_result = time.time(), verdict_record(conn, car_id, old)
    db.set_override(conn, car_id,
                    transport=parse_eur(transport),
                    repair=parse_eur(repair),
                    origin_proof=0 if no_origin else None,
                    hidden=1 if hidden else 0,
                    carina=parse_eur(carina),
                    buy_discount=parse_eur(buy_discount),
                    verdict=verdict,
                    verdict_note=verdict_note.strip()[:VERDICT_NOTE_CHARS] or None,
                    verdict_at=verdict_at,
                    verdict_result=verdict_result)
    # Only local paths, so a crafted form cannot redirect elsewhere.
    local = back.startswith("/") and not back.startswith("//") and "\\" not in back
    target = back if local else "/"
    return RedirectResponse(target, status_code=303)


if __name__ == "__main__":
    if sys.stdout is None:   # started hidden by pythonw (Windows autostart): no console to log to
        log_file = open(Path(db.DB_PATH).parent / "web.log", "a", encoding="utf-8")
        sys.stdout = sys.stderr = log_file
    uvicorn.run(app, host="127.0.0.1", port=8765)
