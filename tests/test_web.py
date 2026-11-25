import json
import time

import pytest
from fastapi.testclient import TestClient

from carfinder import db, market, models, valuation, web
from tests.test_scan_db import foreign, pa_car

GOLF = models.MODELS[0]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    return TestClient(web.app)


def save(car, prices=(9000, 9100, 9200, 9300, 9400)):
    conn = db.connect()
    result = valuation.evaluate(car, [pa_car(str(i), p) for i, p in enumerate(prices)], {}, GOLF)
    db.save_car(conn, car, result, GOLF["as24"])
    return result


@pytest.mark.parametrize("text,expected", [("5500", 5500), ("5.500", 5500), ("5 500", 5500), ("", None),
                                           ("²", None), ("abc", None), ("-5", None)])
def test_parse_eur(text, expected):
    assert web.parse_eur(text) == expected


def test_empty_page_says_scanner_has_not_run(client):
    page = client.get("/").text
    assert "Skener još nije radio" in page


def test_card_shows_profit_max_buy_and_serbian_proof(client):
    result = save(foreign())
    page = client.get("/").text
    assert "carFinder" in page and "VW Golf" in page
    assert result["passes"]
    assert "Najviše platiti" not in page
    assert "Na polovniautomobili.com najjeftiniji oglas:" in page
    assert "dizel" in page and "manuelni" in page
    assert 'loading="lazy"' in page or "bez slike" in page


def test_filters_budget_and_below_target(client):
    save(foreign())
    cheap = save(foreign(id="as24:2", price=8000), prices=(8500, 8600, 8700, 8800, 8900))
    assert not cheap["passes"]
    assert client.get("/").text.count('class="car') == 1
    assert client.get("/?all=1").text.count('class="car') == 2
    assert client.get("/?max_cash=1.000").text.count('class="car') == 0
    assert client.get("/?country=DE").text.count('class="car') == 0


def test_override_keeps_filters_and_reprices(client):
    save(foreign())
    before = client.get("/?country=AT").text
    response = client.post("/override", data={"car_id": "as24:1", "transport": "2000", "back": "/?country=AT#car-as24:1"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?country=AT#car-as24:1"
    after = client.get("/?all=1&country=AT").text
    assert "ručno izmenjeno" in after and after != before


def test_override_redirect_cannot_leave_the_site(client):
    response = client.post("/override", data={"car_id": "x", "back": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/"


def test_hidden_car_disappears(client):
    save(foreign())
    client.post("/override", data={"car_id": "as24:1", "hidden": "1"})
    assert client.get("/?all=1").text.count('class="car') == 0


def test_same_car_posted_twice_is_shown_once(client):
    save(foreign())
    save(foreign(id="willhaben:9", source="willhaben"))
    assert client.get("/?all=1").text.count('class="car') == 1


def test_dedupe_keeps_different_models_and_cars_without_km(client):
    from carfinder import web as w
    a = {"model_key": "volkswagen/golf", "data": {"country": "AT", "year": 2015, "km": 1, "price": 1, "city": "Wien"}}
    b = {"model_key": "volkswagen/polo", "data": {"country": "AT", "year": 2015, "km": 1, "price": 1, "city": "Wien"}}
    c = {"model_key": "volkswagen/golf", "data": {"country": "AT", "year": 2015, "km": None, "price": 1, "city": None}}
    assert len(w.without_duplicates([a, b, c, dict(c)])) == 4


def test_backslash_redirect_is_rejected(client):
    response = client.post("/override", data={"car_id": "x", "back": r"/\evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/"


def seen_days_ago(car_id, days):
    conn = db.connect()
    conn.execute("UPDATE cars SET last_seen = ? WHERE id = ?", (time.time() - days * 24 * 3600, car_id))
    conn.commit()


def test_mobilede_cars_follow_the_same_two_day_rule(client):
    # mobile.de's week of stored cars is saved again on every scan, so an ad missing from the weekly run ages out
    save(foreign(id="as24:old", km=150001))
    save(foreign(id="mobilede:recent", source="mobilede", km=150002))
    save(foreign(id="mobilede:gone", source="mobilede", km=150003))
    seen_days_ago("as24:old", 3)
    seen_days_ago("mobilede:recent", 1)
    seen_days_ago("mobilede:gone", 3)
    page = client.get("/?all=1").text
    assert 'id="car-mobilede:recent"' in page
    assert 'id="car-as24:old"' not in page
    assert 'id="car-mobilede:gone"' not in page


def test_mobilede_card_names_its_site(client):
    save(foreign(id="mobilede:1", source="mobilede"))
    assert "mobile.de" in client.get("/").text


# --- 24.11. importer's review: the Serbian line, the new flags -----------------------

def test_serbian_line_names_the_cheapest_ad_the_next_one_and_how_many_there_are(client):
    save(foreign(), prices=(9000, 9100, 9200, 9300, 9400, 9900))
    page = client.get("/").text
    assert "Na polovniautomobili.com najjeftiniji oglas:" in page
    assert "<b>9.000 e</b></a>, sledeći <a" in page and "<b>9.100 e</b></a>." in page
    assert "Oglasa ukupno 6, od toga 5 najviše 500 e iznad najjeftinijeg." in page
    assert "najjeftiniji oglas 9.000 e, minus 810 e za cenkanje u Srbiji</span>" in page
    assert "Tanko tržište" not in page and "godinu stariji" not in page and "mamac" not in page


def test_thin_market_car_can_pass_and_its_card_shows_the_warning(client):
    result = save(foreign(), prices=(9000, 9100, 9200, 9300))
    assert result["profit"] >= result["target"] and result["passes"]
    page = client.get("/").text
    assert page.count('class="car') == 1
    assert "Oglasa ukupno 4" in page
    assert "Malo ovakvih oglasa (manje od 5), prodajna cena je nesigurna." in page
    assert "malo ovakvih oglasa u Srbiji (manje od 5), prodajna cena je nesigurna" in page


def test_older_ad_shows_its_own_price_and_what_it_counts_as(client):
    car = foreign()
    ads = [pa_car("old", 8000, year=2014)] + [pa_car(str(i), 9000 + i * 100) for i in range(4)]
    db.save_car(db.connect(), car, valuation.evaluate(car, ads, {}, GOLF), GOLF["as24"])
    page = client.get("/").text
    assert "<b>8.000 e</b></a> (godinu stariji, računa se kao 8.560 e), sledeći <a" in page


def test_skipped_bait_and_the_mileage_cut_are_named(client):
    save(foreign(km=320000), prices=(3000, 9000, 9100, 9200, 9300, 9400))   # under the 325,000 km limit
    page = client.get("/?all=1").text
    assert "preskočen mamac ispod njih: 1." in page
    assert "<b>9.000 e</b>" in page and "3.000 e" not in page
    assert "manje 7,7% za razliku u kilometraži, minus 748 e za cenkanje u Srbiji</span>" in page


def test_car_priced_by_the_old_rule_waits_for_its_next_scan(client):
    result = save(foreign())
    del result["serbia"]["anchor"]         # as the scans before 24.11. saved it
    db.save_car(db.connect(), foreign(), result, GOLF["as24"])
    assert client.get("/?all=1").text.count('class="car') == 0


def test_suspiciously_cheap_label_neither_hides_the_car_nor_sorts_it_last(client):
    labelled = save(foreign(id="as24:label", price=3900, market_median=8000, km=150001))
    plain = save(foreign(id="as24:plain", price=4500, km=150002))
    assert any(f.startswith("sumnjivo") for f in labelled["flags"]) and labelled["passes"]
    assert labelled["profit"] > plain["profit"]
    for sort in ("profit", "cash"):
        page = client.get("/?sort=" + sort).text
        assert "sumnjivo jeftin" in page
        assert page.index('id="car-as24:label"') < page.index('id="car-as24:plain"')


@pytest.mark.parametrize("sort,expected", [("profit", -1500), ("cash", 5000), ("newest", -77), ("", -1500)])
def test_sort_key_is_the_number_alone(sort, expected):
    entry = {"first_seen": 77, "result": {"profit": 1500, "cost": {"cash": 5000},
                                         "flags": ["sumnjivo jeftin, možda prevara ili skriven kvar"]}}
    assert web.sort_key(sort)(entry) == expected


def test_big_repair_card_asks_for_the_cost_and_is_a_deal_once_it_is_typed(client):
    reading = {"state": "kvar", "repair": "velika", "note": "udaren napred", "key": "k"}
    save(foreign(price=3000, damaged=True, ai=reading))
    assert client.get("/").text.count('class="car') == 0
    assert '<li class="stop"><b>Velika šteta:</b> udaren napred</li>' in client.get("/?all=1").text
    client.post("/override", data={"car_id": "as24:1", "repair": "1500"})
    page = client.get("/").text
    assert page.count('class="car') == 1
    assert "Velika šteta" not in page and "iz opisa: udaren napred" in page


# --- 24.11. second review: the badge of a held-back car, the list under the Serbian line ------

def test_car_held_back_by_a_warning_is_not_shown_as_on_the_edge(client):
    result = save(foreign(detailed=False), prices=(9000, 9100, 9200, 9300))
    assert result["profit"] >= result["target"] and not result["passes"]
    page = client.get("/?all=1").text
    assert '<span class="badge edge">Čeka proveru</span>' in page
    assert "Na granici" not in page and "Dobro" not in page


def test_big_repair_without_its_cost_is_shown_as_big_damage(client):
    reading = {"state": "kvar", "repair": "velika", "note": "udaren napred", "key": "k"}
    save(foreign(price=3000, damaged=True, ai=reading))
    assert '<span class="badge low">Velika šteta</span>' in client.get("/?all=1").text
    client.post("/override", data={"car_id": "as24:1", "repair": "1500"})
    assert "Velika šteta" not in client.get("/?all=1").text


def test_profit_just_under_the_target_is_still_on_the_edge(client):
    ads = [pa_car(str(i), 9000 + i * 100) for i in range(5)]
    for price in range(4000, 9000, 50):
        result = valuation.evaluate(foreign(price=price), ads, {}, GOLF)
        if 0.9 * result["target"] <= result["profit"] < result["target"]:
            break
    else:
        pytest.fail("no price lands just under the target")
    db.save_car(db.connect(), foreign(price=price), result, GOLF["as24"])
    page = client.get("/?all=1").text
    assert '<span class="badge edge">Na granici</span>' in page and "Čeka proveru" not in page


@pytest.mark.parametrize("prices,more", [((9000, 9100, 9200), 1), ((9000, 9100, 9200, 9300, 9400, 9900), 4),
                                         ((9000, 9100, 9200, 9300, 9400, 9500, 9600, 9700), 4)])
def test_list_under_the_serbian_line_goes_on_from_the_third_ad(client, prices, more):
    save(foreign(), prices=prices)
    page = client.get("/?all=1").text
    assert "<div class=\"others\">Ostali oglasi:" in page
    listed = page.split('<ul class="comps">')[1].split("</ul>")[0]
    assert listed.count("<li>") == more
    assert "9.200 e" in listed and "9.100 e" not in listed and "9.000 e" not in listed   # those two are in the line


# --- import bill as one rough figure (24.11.2026) ----------------------------------------

def troskovi(page):
    return page.split('<table class="bill">')[1].split("</table>")[0]


def test_import_is_one_rough_line_with_the_exact_figure(client):
    result = save(foreign())
    rough = round(result["cost"]["import"]["total"])   # exact, so the receipt adds up
    costs = troskovi(client.get("/").text)
    # Bane 24.11.2026: "carina" is the whole cost the customs firm asks; there are two costs, transport and carina.
    assert '<span class="op">+</span>Carina</th>' in costs and "Uvoz (" not in costs
    assert f"<small>oko</small> {rough:,} e".replace(",", ".") in costs
    assert "otpad" not in costs and "PDV" not in costs and "takse" not in costs


def test_card_never_brings_back_the_eur1_sentence(client):
    save(foreign())
    page = client.get("/").text
    assert "Ako firma ne dobije" not in page
    assert "EUR.1" not in page   # the checkbox in the edit form is gone too


def test_banes_own_import_figure_is_shown_as_typed_and_reprices(client):
    before = save(foreign())
    client.post("/override", data={"car_id": "as24:1", "carina": "1.733"})
    page = client.get("/?all=1").text
    assert "1.733 e <small>(tvoj iznos)</small>" in troskovi(page)
    assert "ručno izmenjeno" in page
    assert db.overrides(db.connect())["as24:1"]["carina"] == 1733
    cash = before["cost"]["cash"] - before["cost"]["import"]["total"] + 1733
    assert f"{cash:,} e".replace(",", ".") in page
    client.post("/override", data={"car_id": "as24:1", "carina": ""})
    assert db.overrides(db.connect())["as24:1"]["carina"] is None
    assert "tvoj iznos" not in client.get("/?all=1").text


def test_worst_case_is_labelled_as_customs_counting_the_invoice(client):
    save(foreign(price=7800), prices=(13200, 13300, 13400, 13500, 13600))
    page = client.get("/?all=1").text
    assert "Ako carina računa po fakturi" in page and "Ako carina uzme fakturu" not in page


def test_site_damaged_car_is_shown_with_the_default_repair(client):
    save(foreign(price=3000, damaged=True))
    page = client.get("/").text
    assert page.count('class="car') == 1 and "oštećen" in page


def worst_stat(page):
    return page.split('<th scope="row">Ako carina računa po fakturi</th><td>')[1].split("</td>")[0]


def test_invoice_case_shows_its_profit_when_it_drops_under_the_target(client):
    result = save(foreign(price=7800), prices=(13200, 13300, 13400, 13500, 13600))
    assert result["profit"] >= result["target"] > result["profit_worst"]
    stat = worst_stat(client.get("/?all=1").text)
    assert stat == f"zarada {'{:+,}'.format(result['profit_worst']).replace(',', '.')} e, ispod cilja"


@pytest.mark.parametrize("price", [6000, 9000])   # the invoice still reaches the target; the car misses it anyway
def test_invoice_case_is_left_out_when_it_does_not_change_the_decision(client, price):
    result = save(foreign(price=price), prices=(12000, 12100, 12200, 12300, 12400))
    assert result["profit_worst"] is not None and result["profit_worst"] < result["profit"]
    assert (result["profit_worst"] >= result["target"]) != (result["profit"] < result["target"])
    assert "po fakturi" not in client.get("/?all=1").text


def test_invoice_case_is_left_out_when_the_catalogue_bill_is_higher(client):
    result = save(foreign(price=2000))   # an 11-year-old Golf 7 is worth about 3,600 in the catalogue
    assert result["profit_worst"] is None
    page = client.get("/?all=1").text
    assert "po fakturi" not in page and "isto" not in troskovi(page)


def test_typed_import_figure_drops_the_invoice_comparison(client):
    save(foreign())
    client.post("/override", data={"car_id": "as24:1", "carina": "0"})
    page = client.get("/?all=1").text
    assert "0 e <small>(tvoj iznos)</small>" in troskovi(page)
    assert "po fakturi" not in page


def test_car_saved_with_more_than_325000_km_is_not_shown(client):
    save(foreign(km=380_000))
    assert client.get("/?all=1").text.count('class="car') == 0


def test_car_saved_from_italy_or_as_a_taxi_is_not_shown(client):
    save(foreign(id="as24:it", country="IT"))
    save(foreign(id="as24:taxi", text="Taxiausstattung: Funkantenne"))
    assert client.get("/?all=1").text.count('class="car') == 0
    save(foreign(id="as24:de", country="DE"))
    assert client.get("/?all=1").text.count('class="car') == 1


# --- card as a receipt, money first, nothing important behind a click (24.11.2026) ----------

def eur(x):
    return f"{x:,} e".replace(",", ".")


def test_receipt_adds_price_abroad_transport_and_carina_into_the_total(client):
    result = save(foreign())
    cost = result["cost"]
    bill = troskovi(client.get("/").text)
    rough = round(cost["import"]["total"])
    assert ('<th scope="row">Cena u Austriji<span class="sub">Traži 4.000 e. '
            'Računamo 200 e popusta.</span></th><td>3.800 e</td>') in bill
    assert f'Dovoz do Pančeva</th><td>{eur(cost["transport"])}</td>' in bill
    assert f'Carina</th><td><small>oko</small> {eur(rough)}</td>' in bill
    assert f'<span class="op">=</span>Ukupno uloženo</th><td>{eur(cost["cash"])}</td>' in bill
    assert cost["buy"] + cost["transport"] + cost["import"]["total"] + cost["repair"] == cost["cash"]
    assert "Popravka" not in bill   # no repair, no row
    order = ["Cena u Austriji", "Dovoz do Pančeva", "Carina", "Ukupno uloženo", "Prodaja u Srbiji", "Zarada"]
    assert [bill.index(label) for label in order] == sorted(bill.index(label) for label in order)
    assert f'Zarada</th><td>{"{:+,}".format(result["profit"]).replace(",", ".")} e</td>' in bill


def test_receipt_adds_the_repair_of_a_damaged_car(client):
    save(foreign(price=3000, damaged=True))
    assert 'Popravka (procena)</th><td>300 e</td>' in troskovi(client.get("/").text)


def test_net_price_is_named_with_the_ads_gross_price(client):
    result = save(foreign(price=6000, net_price=5000, vat_deductible=True))
    assert result["cost"]["buy"] == 4800
    page = client.get("/?all=1").text
    assert ('Cena u Austriji<span class="sub">neto, bez PDV-a; u oglasu 6.000 e</span>'
            '<span class="sub">Traži 5.000 e neto. Računamo 200 e popusta.</span></th><td>4.800 e</td>') in page
    assert "EUR.1" not in page


def test_price_under_the_limit_shows_no_max_to_pay_line(client):
    """Bane 24.11.2026: "Najvise da das prodavcu 5.841, a auto je 5.500" made no sense; a deal needs no max line."""
    result = save(foreign())
    assert result["max_buy"] > 3800
    page = client.get("/").text
    assert "Najviše da daš prodavcu" not in page and "Najviše platiti" not in page
    assert "mora da padne" not in page and "ispod granice" not in page


def test_price_over_the_limit_says_how_far_it_must_come_down(client):
    result = save(foreign(price=8000), prices=(8500, 8600, 8700, 8800, 8900))
    assert result["max_buy"] is not None and result["max_buy"] < 7800
    page = client.get("/?all=1").text
    assert f"Da bi se isplatio, cena auta mora da padne na <b>{eur(result['max_buy'])}</b>" in page
    assert f"Sad računamo 7.800 e, znači treba spustiti još {eur(7800 - result['max_buy'])}." in page


def test_no_price_works(client):
    result = save(foreign(), prices=(1000, 1100, 1200, 1300, 1400))
    assert result["max_buy"] is None
    page = client.get("/?all=1").text
    assert "Ne isplati se ni po kojoj ceni." in page and "mora da padne" not in page


def test_only_the_edit_form_is_behind_a_click(client):
    save(foreign(price=3000, damaged=True, ai={"state": "kvar", "repair": "mala", "note": "udaren napred.", "key": "k"}))
    page = client.get("/").text
    assert page.count('class="car') == 1 and page.count("<details") == 1
    folded = page.split("<details")[1]
    assert 'name="car_id"' in folded and 'name="hidden" value="1"' in folded
    for shown in ('<table class="bill">', '<div class="sr">', '<ul class="warn"'):   # a deal has no max line
        assert page.index(shown) < page.index("<details")


def test_warnings_show_one_fact_per_row_with_the_damage_and_its_note_together(client):
    save(foreign(price=3000, damaged=True, seller="private", text="whatsapp",
                 ai={"state": "kvar", "repair": "mala", "note": "udaren napred.", "key": "k"}))
    page = client.get("/?all=1").text
    top, checks = [part.split("</ul>")[0] for part in page.split('<ul class="warn"')[1:3]]
    assert '<li class="stop"><b>Stop:</b> WhatsApp u oglasu, čest znak prevare</li>' in top and "chk" not in top
    assert '<li class="chk">oštećen, iz opisa: udaren napred</li>' in checks   # the note's own period dropped
    assert '<li class="chk">privatni prodavac</li>' in checks


# --- 24.11.2026 review of the receipt card: the sum adds up, big damage and fraud signs lead -----------

def card(page):
    return page.split('<article class="car')[1].split("</article>")[0]


def test_receipt_rows_add_up_to_the_total_when_the_carina_is_not_a_round_figure(client):
    result = save(foreign())
    cost = result["cost"]
    assert round(cost["import"]["total"]) % 50 != 0     # the case the rounded carina got wrong
    rows = [eur(cost["buy"]), eur(cost["transport"]), eur(round(cost["import"]["total"]))]
    bill = troskovi(client.get("/").text)
    assert all(row in bill for row in rows)
    assert cost["buy"] + cost["transport"] + round(cost["import"]["total"]) == cost["cash"]
    assert f"Ukupno uloženo</th><td>{eur(cost['cash'])}</td>" in bill


def test_big_damage_card_asks_for_the_repair_before_any_price_to_pay(client):
    reading = {"state": "kvar", "repair": "velika", "note": "udaren napred.", "key": "k"}
    save(foreign(price=3000, damaged=True, ai=reading))
    page = card(client.get("/?all=1").text)
    assert '<span class="badge low">Velika šteta</span>' in page
    assert '<span class="sub">300 e je za sitnu štetu, upiši pravu cenu</span>' in page
    assert "Prvo upiši cenu popravke, pa vidi da li se isplati." in page
    assert "Najviše da daš prodavcu" not in page and "Zarada još ne računa veliku popravku." in page
    assert page.index("<b>Velika šteta:</b> udaren napred</li>") < page.index('class="profit')
    assert "veća popravka" not in page and '<li class="chk">oštećen</li>' in page


def test_big_damage_without_the_sites_damage_mark_still_shows_the_repair_row(client):
    save(foreign(price=3000, ai={"state": "kvar", "repair": "velika", "note": "", "key": "k"}))
    page = card(client.get("/?all=1").text)
    assert "<b>Velika šteta:</b> prodavac opisuje veći kvar</li>" in page
    assert '<span class="sub">nije uračunata, upiši pravu cenu</span></th><td>0 e</td>' in page
    assert "Bez upozorenja" not in page


def test_fraud_sign_turns_the_verdict_into_risk_and_leads_the_card(client):
    result = save(foreign(text="whatsapp"))
    assert result["passes"]
    page = card(client.get("/").text)
    assert '<span class="badge low">Rizik</span>' in page
    assert "Odlično" not in page and "Dobro" not in page and 'class="pill' not in page
    assert page.index("<b>Stop:</b> WhatsApp") < page.index('class="profit')


def test_model_labels_are_the_model_without_its_generation_code():
    labels = dict(web.MODEL_LABELS)
    assert [labels[path] for path in ("volkswagen/golf", "skoda/octavia", "audi/a4", "peugeot/3008")] == [
        "VW Golf", "Škoda Octavia", "Audi A4", "Peugeot 3008"]
    assert [labels[path] for path in ("bmw/x1", "bmw/520", "bmw/3er", "audi/a6", "opel/insignia",
                                      "mercedes-benz/b-klasse", "ford/kuga", "hyundai/ix35")] == [
        "BMW X1", "BMW 520d", "BMW 3er", "Audi A6", "Opel Insignia", "Mercedes Benz B-Klasse", "Ford Kuga",
        "Hyundai ix35"]


def test_card_names_the_model_above_the_title(client):
    save(foreign(title="Volkswagen Limousine 2.0 TDI"))
    page = card(client.get("/").text)
    label = dict(web.MODEL_LABELS)[GOLF["as24"]]
    assert f'<p class="mk">{label}</p>' in page
    assert page.index('class="mk"') < page.index("Volkswagen Limousine 2.0 TDI")


def test_a3_sportback_body_is_displayed_even_for_a_stored_limousine_category(client):
    car = foreign(model="A3", title="Audi Sportback 1.6 TDI", body="sedan")
    a3 = web.MODEL_BY_KEY["audi/a3"]
    ads = [pa_car(str(i), 9000 + i * 100) for i in range(3)]
    result = valuation.evaluate(car, ads, {}, a3)
    db.save_car(db.connect(), car, result, a3["as24"])
    specs = card(client.get("/?all=1").text).split('<p class="specs">')[1].split("</p>")[0]
    assert "hečbek" in specs and "limuzina" not in specs


def test_max_to_pay_when_the_seller_asks_exactly_the_limit(client):
    ads = (9000, 9100, 9200, 9300, 9400)
    limit = save(foreign(), prices=ads)["max_buy"]
    result = save(foreign(price=limit + valuation.DEFAULT_BUY_DISCOUNT_EUR), prices=ads)
    assert result["max_buy"] == result["cost"]["buy"] == limit
    assert "mora da padne" not in client.get("/?all=1").text   # exactly at the limit is still a deal


def test_buy_discount_can_be_edited_set_to_zero_and_reset(client):
    save(foreign())
    for entered, stored, cost in (("350", 350, "3.650 e"), ("0", 0, "4.000 e"), ("", None, "3.800 e")):
        client.post("/override", data={"car_id": "as24:1", "buy_discount": entered, "transport": "700"})
        override = db.overrides(db.connect())["as24:1"]
        assert override["buy_discount"] == stored and override["transport"] == 700
        page = client.get("/").text
        assert f'</th><td>{cost}</td>' in troskovi(page)
        assert 'name="buy_discount"' in page
        if stored == 0:
            assert "Računamo" not in troskovi(page)


def test_newer_serbian_ad_and_sale_cut_have_separate_labels(client):
    car = foreign(year=2010, title="VW Golf 6 GTD", cc=1968, kw=125)
    ads = [pa_car(str(i), 6200 + i * 100, year=2011, title="Golf 6 GTD", cc=1968, kw=125) for i in range(3)]
    db.save_car(db.connect(), car, valuation.evaluate(car, ads, {}, GOLF), GOLF["as24"])
    page = client.get("/?all=1").text
    assert "godinu noviji, računa se kao 5.766 e" in page
    assert "minus 519 e za cenkanje u Srbiji" in page
    assert "5.247 e</td>" in troskovi(page)


def test_repair_shows_in_the_bill_of_a_damaged_deal(client):
    save(foreign(price=3000, damaged=True))
    page = client.get("/").text
    assert "Popravka" in page and "mora da padne" not in page


def test_profit_under_the_target_is_red_only_when_it_is_a_loss(client):
    small_profit = save(foreign(price=6000))
    loss = save(foreign(id="as24:loss", price=9000, km=150001))
    assert 0 < small_profit["profit"] < small_profit["target"] and loss["profit"] < 0
    page = client.get("/?all=1").text
    small = page.split('id="car-as24:1"')[0].rsplit("<article", 1)[1]
    loss = page.split('id="car-as24:loss"')[0].rsplit("<article", 1)[1]
    assert 'data-v="low"' in small and "data-loss" not in small
    assert "data-loss" in loss


def test_german_export_flag_is_shown_in_serbian(client):
    save(foreign(text="Export"))
    page = client.get("/?all=1").text
    assert '<li class="chk">prodaje se firmama ili za izvoz, bez garancije</li>' in page and "Gewerbe" not in page


def test_typed_repair_and_a_typed_zero_transport_are_marked_as_his(client):
    save(foreign(price=3000, damaged=True))
    client.post("/override", data={"car_id": "as24:1", "repair": "450"})
    assert "Popravka (tvoj iznos)</th><td>450 e</td>" in troskovi(client.get("/?all=1").text)
    client.post("/override", data={"car_id": "as24:1", "transport": "0"})
    assert "ručno izmenjeno" in client.get("/?all=1").text


def test_broken_photo_falls_back_to_the_no_photo_label(client):
    save(foreign(image="https://example.invalid/x.jpg"))
    assert "onerror=\"this.outerHTML='<span>bez slike</span>'\"" in client.get("/").text


# --- 24.11. the pill says what it counts, in Serbian ("Proveri 1" was "jako glup") ----

@pytest.mark.parametrize("count,label", [
    (1, "1 upozorenje"), (2, "2 upozorenja"), (4, "4 upozorenja"), (5, "5 upozorenja"),
    (11, "11 upozorenja"), (12, "12 upozorenja"), (14, "14 upozorenja"), (21, "21 upozorenje"),
    (22, "22 upozorenja"), (101, "101 upozorenje"), (111, "111 upozorenja"),
])
def test_warnings_label_uses_the_serbian_plural(count, label):
    assert web.warnings_label(count) == label


def test_pill_counts_the_warnings_listed_on_the_card(client):
    save(foreign(seller="private"))
    one = card(client.get("/?all=1").text)
    assert '<span class="pill chk">1 upozorenje</span>' in one and "Proveri" not in one
    save(foreign(seller="private", text="Export"))
    two = card(client.get("/?all=1").text)
    assert '<span class="pill chk">2 upozorenja</span>' in two


# --- 25.11.2026: sell speed, the cheapest Serbian ad's own age, Novky's word ----------------

def speed_of(label, age=60, usual=30, cut_share=0.0):
    return {"label": label, "age_days": age, "usual_days": usual, "cut_share": cut_share, "n": 20}


def save_with(car, speed=None, first=None, prices=(9000, 9100, 9200, 9300, 9400)):
    """A saved car whose scan measured this sell speed and found this about the cheapest Serbian ad."""
    conn = db.connect()
    result = valuation.evaluate(car, [pa_car(str(i), p) for i, p in enumerate(prices)], {}, GOLF)
    result["serbia"]["speed"] = speed
    result["serbia"]["first"].update(first or {})
    db.save_car(conn, car, result, GOLF["as24"])
    return result


def test_slow_seller_is_tagged_and_says_how_long_its_ads_stay_and_how_many_were_cut(client):
    save_with(foreign(), speed_of("sporo", 63, 32, 0.17))
    one = card(client.get("/").text)
    assert '<span class="tag slow">Sporo se prodaje</span>' in one
    assert ("Ovakvi auti stoje u oglasu oko 63 dana, a drugi auti iste cene oko 32 dana. "
            "Cenu je spustilo 17% prodavaca.") in one


def test_fast_seller_is_tagged_without_counting_as_a_warning(client):
    save_with(foreign(), speed_of("brzo", 20, 30))
    one = card(client.get("/").text)
    assert '<span class="tag">Brzo se prodaje</span>' in one and "Bez upozorenja" in one
    assert "a drugi auti iste cene oko 30 dana." in one and "Cenu je spustilo" not in one


def test_normal_seller_gets_the_line_but_no_tag(client):
    save_with(foreign(), speed_of("normalno", 33, 30))
    one = card(client.get("/").text)
    assert "Ovakvi auti stoje u oglasu oko 33 dana" in one and "se prodaje</span>" not in one


@pytest.mark.parametrize("saver", [save, lambda car: save_with(car, speed=None)])
def test_car_without_a_measured_speed_shows_neither_tag_nor_line(client, saver):
    saver(foreign())   # saved before speed existed, or too few ads to measure it
    one = card(client.get("/").text)
    assert "Ovakvi auti" not in one and "se prodaje</span>" not in one and 'class="anchor"' not in one


@pytest.mark.parametrize("first,line", [
    ({"age_days": 120, "cut": True, "base_price": 9500},
     "Najjeftiniji oglas stoji najmanje 120 dana, cena mu je spuštena sa 9.500 e."),
    ({"age_days": 40, "cut": True, "base_price": None}, "Najjeftiniji oglas stoji najmanje 40 dana, cena mu je spuštena."),
    # PA sends the asking price as basePrice on an ad that was never cut
    ({"age_days": 40, "cut": False, "base_price": 9000}, "Najjeftiniji oglas stoji najmanje 40 dana."),
    ({"age_days": 21, "cut": False, "base_price": None}, "Najjeftiniji oglas stoji najmanje 21 dan."),
    ({"age_days": 1, "cut": False, "base_price": None}, "Najjeftiniji oglas stoji najmanje 1 dan."),
    ({"age_days": 0, "cut": False, "base_price": None}, "Najjeftiniji oglas je postavljen ovih dana."),
])
def test_cheapest_serbian_ad_shows_how_long_it_stands_and_its_cut(client, first, line):
    save_with(foreign(), first=first)
    one = card(client.get("/").text)
    assert line in one
    assert ("spuštena" in one) is first["cut"]


@pytest.mark.parametrize("count,label", [
    (0, "0 dana"), (1, "1 dan"), (2, "2 dana"), (5, "5 dana"), (11, "11 dana"), (12, "12 dana"), (21, "21 dan"),
    (22, "22 dana"), (101, "101 dan"), (111, "111 dana"), (161, "161 dan"),
])
def test_days_label_uses_the_serbian_plural(count, label):
    assert web.days_label(count) == label


@pytest.mark.parametrize("age,stale", [(None, False), (89, False), (90, True), (161, True)])
def test_cheapest_serbian_ad_listed_three_months_is_a_warning(client, age, stale):
    save_with(foreign(), first={"age_days": age})
    one = card(client.get("/?all=1").text)
    assert ("najjeftiniji oglas u Srbiji stoji preko 3 meseca, za tu cenu auto se možda ne prodaje" in one) is stale


def test_methane_car_is_not_shown_and_its_fuel_still_has_a_serbian_name(client, monkeypatch):
    save(foreign(fuel="petrol_cng"))
    assert 'class="car' not in client.get("/?all=1").text   # Novky 25.11.2026 on factory CNG: "Vise ne"
    monkeypatch.setattr(market, "REPUTATION", [])
    assert "benzin + metan (CNG)" in card(client.get("/?all=1").text)


def test_petrol_car_is_shown_only_for_a_model_whose_generation_sells_as_petrol(client):
    save(foreign(fuel="petrol"))                                         # a Golf 7: petrol sells
    assert "benzin" in card(client.get("/?all=1").text)
    conn = db.connect()
    conn.execute("UPDATE cars SET model_key = ?", ("volkswagen/passat",))   # a Passat: petrol does not sell
    conn.commit()
    assert 'class="car' not in client.get("/?all=1").text
    conn.execute("UPDATE cars SET model_key = ?", ("citroen/c4-picasso",))   # a model no longer scanned
    conn.commit()
    assert 'class="car' not in client.get("/?all=1").text


def test_model_filter_lists_all_138_models_from_a_to_z(client):
    labels = [label for _, label in web.MODEL_LABELS]
    assert len(labels) == len(set(labels)) == 138 and labels == sorted(labels)
    names = dict(web.MODEL_LABELS)
    assert [names[path] for path in ("volkswagen/up", "mercedes-benz/a-klasse", "toyota/c-hr", "suzuki/sx4-s-cross",
                                     "citroen/c4-cactus", "opel/grandland", "fiat/500", "kia/ceed", "mazda/mazda3")] == [
        "VW up!", "Mercedes Benz A-Klasse", "Toyota C-HR", "Suzuki S-Cross", "Citroen C4 Cactus", "Opel Grandland",
        "Fiat 500", "Kia Ceed", "Mazda Mazda3"]
    page = client.get("/?model=toyota/yaris").text
    assert '<option value="toyota/yaris" selected>Toyota Yaris</option>' in page
    assert page.count("<option value=") >= 138


def test_passing_cars_are_sorted_fast_first_and_slow_last_then_the_rest(client):
    save_with(foreign(id="as24:slow", price=3000, km=150001), speed_of("sporo"))       # the biggest profit
    save_with(foreign(id="as24:normal", price=3500, km=150002), speed_of("normalno"))
    save_with(foreign(id="as24:unknown", price=3600, km=150003))
    save_with(foreign(id="as24:fast", price=4000, km=150004), speed_of("brzo"))       # the smallest profit
    save_with(foreign(id="as24:unread", price=2000, km=150005, detailed=False), speed_of("brzo"))   # under check
    page = client.get("/?all=1").text
    order = [page.index(f'id="car-as24:{name}"') for name in ("fast", "normal", "unknown", "slow", "unread")]
    assert order == sorted(order)
    by_cash = client.get("/?all=1&sort=cash").text   # an explicit sort is left alone
    assert by_cash.index('id="car-as24:unread"') < by_cash.index('id="car-as24:slow"') < by_cash.index('id="car-as24:fast"')


@pytest.mark.parametrize("passes,speed,rank", [
    (True, {"label": "brzo"}, 0), (True, {"label": "normalno"}, 1), (True, None, 1), (True, {"label": "sporo"}, 2),
    (False, {"label": "brzo"}, 3),
])
def test_speed_rank(passes, speed, rank):
    assert web.speed_rank({"result": {"passes": passes, "serbia": {"speed": speed}}}) == rank


@pytest.mark.parametrize("n,rank", [(3, 2), (4, 2), (5, 0), (20, 0)])
def test_fast_car_priced_from_under_five_serbian_ads_sits_with_the_slow_ones(n, rank):
    assert web.speed_rank({"result": {"passes": True, "serbia": {"n": n, "speed": {"label": "brzo"}}}}) == rank


def test_speed_rank_of_a_result_saved_before_speed_existed():
    assert web.speed_rank({"result": {"passes": True, "serbia": {}}}) == 1


def test_novkys_word_is_saved_shown_on_the_card_and_kept_in_the_form(client):
    save(foreign())
    client.post("/override", data={"car_id": "as24:1", "verdict": "onako", "verdict_note": "  ide sporo "})
    assert db.overrides(db.connect())["as24:1"]["verdict"] == "onako"
    page = client.get("/").text
    assert '<span class="tag novky">Novky: onako, ide sporo</span>' in page
    assert 'value="onako" checked' in page and 'value="ide sporo"' in page
    assert "ručno izmenjeno" not in page   # his word changes no money


def test_novkys_word_without_a_note_and_its_reset(client):
    save(foreign())
    client.post("/override", data={"car_id": "as24:1", "verdict": "uzeo bih"})
    assert '<span class="tag novky">Novky: uzeo bih</span>' in client.get("/").text
    client.post("/override", data={"car_id": "as24:1", "verdict": ""})
    page = client.get("/").text
    assert 'class="tag novky"' not in page and 'value="" checked' in page


@pytest.mark.parametrize("verdict,note,saved", [
    ("možda", "", (None, None)),                 # only his three words count as a verdict
    ("ne", "   ", ("ne", None)),
    ("ne", "x" * 100, ("ne", "x" * web.VERDICT_NOTE_CHARS)),
])
def test_verdict_outside_the_three_words_is_dropped_and_the_note_is_trimmed(client, verdict, note, saved):
    client.post("/override", data={"car_id": "as24:1", "verdict": verdict, "verdict_note": note})
    row = db.overrides(db.connect())["as24:1"]
    assert (row["verdict"], row["verdict_note"]) == saved


def test_edit_form_has_novkys_three_words_and_no_word(client):
    save(foreign())
    folded = client.get("/").text.split("<details")[1]
    for value in ("uzeo bih", "onako", "ne", ""):
        assert f'name="verdict" value="{value}"' in folded
    assert 'name="verdict_note"' in folded and "Novky kaže" in folded


def verdict_row():
    return db.overrides(db.connect())["as24:1"]


def test_new_verdict_keeps_when_it_was_given_and_what_the_card_showed(client):
    result = save_with(foreign(), speed_of("sporo"))
    client.post("/override", data={"car_id": "as24:1", "verdict": "onako"})
    row = verdict_row()
    assert row["verdict_at"] > 0
    record = json.loads(row["verdict_result"])
    assert record == {"price": 4000, "sale": result["sale"], "profit": result["profit"], "speed": speed_of("sporo")}


def test_same_verdict_with_a_new_note_or_amounts_keeps_its_time_and_record(client):
    save_with(foreign(), speed_of("sporo"))
    client.post("/override", data={"car_id": "as24:1", "verdict": "onako"})
    first = verdict_row()
    save_with(foreign(price=3000), speed_of("brzo"))   # the next scan changes the car's numbers
    client.post("/override", data={"car_id": "as24:1", "verdict": "onako", "verdict_note": "ide sporo", "repair": "500"})
    again = verdict_row()
    assert (again["verdict_at"], again["verdict_result"]) == (first["verdict_at"], first["verdict_result"])


def test_changed_verdict_gets_a_new_time_and_record(client):
    save_with(foreign(), speed_of("sporo"))
    client.post("/override", data={"car_id": "as24:1", "verdict": "onako"})
    first = verdict_row()
    save_with(foreign(price=3000), speed_of("brzo"))
    client.post("/override", data={"car_id": "as24:1", "verdict": "uzeo bih"})
    again = verdict_row()
    assert again["verdict_at"] >= first["verdict_at"]
    assert json.loads(again["verdict_result"])["price"] == 3000


def test_cleared_verdict_clears_its_time_and_record(client):
    save_with(foreign())
    client.post("/override", data={"car_id": "as24:1", "verdict": "ne"})
    client.post("/override", data={"car_id": "as24:1", "verdict": ""})
    assert (verdict_row()["verdict_at"], verdict_row()["verdict_result"]) == (None, None)


def test_verdict_on_a_car_the_database_no_longer_prices_keeps_its_time_only(client):
    client.post("/override", data={"car_id": "as24:1", "verdict": "ne"})
    assert verdict_row()["verdict_at"] > 0 and verdict_row()["verdict_result"] is None
