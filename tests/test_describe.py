import hashlib
import json

import anthropic
import httpx
import pytest

from carfinder import db, describe, models, scan, valuation
from tests.test_scan_db import foreign, pa_car, seed_cache, value_car

GOLF = models.MODELS[0]
REAL_ASK_HAIKU = describe.ask_haiku   # conftest swaps it out in every test; taken here before that
REAL_DOWNLOAD_PHOTO = describe.download_photo   # the same for the photo download


def answer(state, note="", repair="nema"):
    return lambda prompt: '{"stanje": "%s", "popravka": "%s", "napomena": "%s"}' % (state, repair, note)


def test_parse_answer_accepts_json_with_text_around_it():
    reading = describe.parse_answer('Evo: {"stanje": "kvar", "popravka": "velika", "napomena": "udaren napred"} kraj')
    assert reading == {"state": "kvar", "repair": "velika", "note": "udaren napred"}


@pytest.mark.parametrize("repair", ["nema", "mala", "velika"])
def test_parse_answer_keeps_the_repair_size(repair):
    assert describe.parse_answer('{"stanje": "kvar", "popravka": "%s"}' % repair)["repair"] == repair


def test_parse_answer_rejects_a_missing_or_unknown_repair_size():
    assert describe.parse_answer('{"stanje": "kvar", "napomena": "udaren napred"}') is None
    assert describe.parse_answer('{"stanje": "kvar", "popravka": "srednja"}') is None
    assert describe.parse_answer('{"stanje": "ok", "popravka": null}') is None


def test_prompt_asks_for_the_repair_size_and_says_what_is_small_and_big():
    assert '"popravka": "nema" ili "mala" ili "velika"' in describe.PROMPT
    small = describe.PROMPT.split('- "mala":')[1].split('- "nema":')[0]
    big = describe.PROMPT.split('- "velika":')[1].split('- "mala":')[0]
    # Bane 24.11.2026: bodywork and small mechanical faults are cheap in Serbia, so they are small repairs;
    # a bent roof or body structure and a fired airbag are a total loss, not a repair.
    for word in ("farbanje", "ulegnuća", "grad", "potrošni", "ogrebotine", "kvačilo", "turbina", "DPF"):
        assert word in small
    for word in ("udes", "motora", "menjača", "korozija"):
        assert word in big
    wreck = describe.PROMPT.split('- "les":')[1].split('- "kvar":')[0]
    for word in ("krov", "airbag", "šasija", "stubovi"):
        assert word in wreck


def test_parse_answer_rejects_anything_else():
    assert describe.parse_answer("") is None
    assert describe.parse_answer(None) is None
    assert describe.parse_answer("nije json") is None
    assert describe.parse_answer('{"stanje": "super", "popravka": "nema"}') is None
    assert describe.parse_answer('{"stanje": ') is None
    assert describe.parse_answer('["les"]') is None


def test_read_returns_state_note_and_key():
    car = foreign(text="Unfallwagen, Motor ok")
    reading = describe.read(car, ask=answer("kvar", "udes", "velika"))
    assert reading == {"state": "kvar", "repair": "velika", "note": "udes", "photos_unread": False,
                       "key": describe.text_key(car)}


def test_read_none_without_text_or_when_claude_fails():
    assert describe.read(foreign(text=""), ask=answer("ok")) is None
    assert describe.read(foreign(text="  "), ask=answer("ok")) is None
    assert describe.read(foreign(text="Top Zustand")) is None            # conftest: claude unavailable
    assert describe.read(foreign(text="Top Zustand"), ask=lambda p: "bla") is None


def test_long_description_is_cut_and_ad_text_reaches_the_prompt():
    seen = []
    reply = '{"stanje": "ok", "popravka": "nema"}'
    assert describe.read(foreign(title="VW Golf", text="x" * 10000), ask=lambda p: seen.append(p) or reply)["state"] == "ok"
    assert "VW Golf" in seen[0]
    assert len(seen[0]) < describe.MAX_TEXT + len(describe.PROMPT) + 50


def test_text_key_changes_when_the_seller_edits_the_ad():
    assert describe.text_key(foreign(text="a")) != describe.text_key(foreign(text="b"))
    assert describe.text_key(foreign(text="a")) == describe.text_key(foreign(text="a"))


def test_text_key_changes_with_the_reading_version(monkeypatch):
    car = foreign(text="a")
    before = describe.text_key(car)
    assert before != hashlib.sha1((car["title"] + "\n" + car["text"]).encode("utf-8")).hexdigest()[:12]   # the old key
    monkeypatch.setattr(describe, "READING_VERSION", describe.READING_VERSION + 1)
    assert describe.text_key(car) != before


def priced(tmp_path, monkeypatch, car, reply):
    conn = db.connect(tmp_path / "t.db")
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    monkeypatch.setattr(scan.autoscout24, "add_details", lambda c: c.update(detailed=True))
    monkeypatch.setattr(describe, "ask_haiku", reply)
    return conn, value_car(conn, snapshots, car, set())


def test_parts_car_found_in_description_is_hidden(tmp_path, monkeypatch):
    asked = []
    car = foreign(text="Motor dreht nicht mehr")   # none of the wreck words: only the reading can hide this car
    assert scan.usable(car)
    _, result = priced(tmp_path, monkeypatch, car,
                       lambda prompt: asked.append(prompt) or answer("les", "motor ne radi")(prompt))
    assert len(asked) == 1 and car["ai"]["state"] == "les"
    assert result is None


def test_fault_in_description_adds_repair_and_warning(tmp_path, monkeypatch):
    car = foreign(text="Kupplung rutscht")
    _, result = priced(tmp_path, monkeypatch, car, answer("kvar", "kvacilo proklizava", "mala"))
    assert car["damaged"] is True
    assert result["cost"]["repair"] == valuation.DEFAULT_REPAIR_EUR
    assert "iz opisa: kvacilo proklizava" in result["flags"]
    assert result["passes"] is True and valuation.BIG_REPAIR_FLAG not in result["flags"]


def test_big_repair_in_description_is_no_deal_until_bane_types_its_cost(tmp_path, monkeypatch):
    car = foreign(price=3000, text="Unfallschaden vorne, Airbags offen aber fahrbereit")
    conn, result = priced(tmp_path, monkeypatch, car, answer("kvar", "udaren napred", "velika"))
    assert car["damaged"] is True
    assert result["profit"] >= result["target"]
    assert result["passes"] is False
    assert valuation.BIG_REPAIR_FLAG in result["flags"] and "iz opisa: udaren napred" in result["flags"]

    again = foreign(price=3000, text="Unfallschaden vorne, Airbags offen aber fahrbereit")
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    with scan.site_threads() as threads:
        results = scan.value_and_save(conn, threads, [(again, GOLF)], snapshots, {"as24:1": {"repair": 1500}}, set(),
                                      [])
    typed = results["as24:1"]
    assert typed["cost"]["repair"] == 1500
    assert typed["passes"] is True and valuation.BIG_REPAIR_FLAG not in typed["flags"]


def test_clean_description_changes_nothing(tmp_path, monkeypatch):
    car = foreign(text="Scheckheftgepflegt")
    _, result = priced(tmp_path, monkeypatch, car, answer("ok"))
    assert car["damaged"] is False and result["cost"]["repair"] == 0
    assert not any(f.startswith("iz opisa") for f in result["flags"])


def test_unread_description_does_not_stop_the_car(tmp_path, monkeypatch):
    car = foreign(text="Scheckheftgepflegt")
    _, result = priced(tmp_path, monkeypatch, car, lambda p: 1 / 0)
    assert result is not None and car["ai"] is None


def test_same_ad_is_read_once_and_reread_after_an_edit(tmp_path, monkeypatch):
    calls = []
    reply = lambda p: calls.append(p) or '{"stanje": "ok", "popravka": "nema", "napomena": ""}'
    car = foreign(text="Scheckheftgepflegt")
    conn, _ = priced(tmp_path, monkeypatch, car, reply)   # the scan saves the car with its reading
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    value_car(conn, snapshots, foreign(text="Scheckheftgepflegt"), set())
    assert len(calls) == 1
    value_car(conn, snapshots, foreign(text="Scheckheftgepflegt, Motorlampe leuchtet"), set())
    assert len(calls) == 2


def test_reading_from_before_the_repair_size_is_read_again(tmp_path, monkeypatch):
    calls = []
    reply = lambda p: calls.append(p) or '{"stanje": "kvar", "popravka": "velika", "napomena": "udes"}'
    old = foreign(price=3000, text="Unfallwagen, Motor ok")
    old_key = hashlib.sha1((old["title"] + "\n" + old["text"]).encode("utf-8")).hexdigest()[:12]
    old["ai"] = {"state": "kvar", "note": "udes", "key": old_key}     # as the scans before 24.11. saved it
    conn = db.connect(tmp_path / "t.db")
    db.save_car(conn, old, None, GOLF["as24"])
    car = foreign(price=3000, text="Unfallwagen, Motor ok")
    snapshots = seed_cache(car, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    monkeypatch.setattr(describe, "ask_haiku", reply)
    result = value_car(conn, snapshots, car, set())
    assert len(calls) == 1
    assert car["ai"]["repair"] == "velika" and result["passes"] is False


# --- 24.11. second review: a description that could not be read --------------------

def test_description_haiku_could_not_read_is_said_on_the_card(tmp_path, monkeypatch):
    car = foreign(text="Unfallschaden vorne, fahrbereit")
    _, result = priced(tmp_path, monkeypatch, car, lambda prompt: 1 / 0)
    assert car["ai"] is None
    assert valuation.UNREAD_FLAG == "opis nije pročitan"
    assert valuation.UNREAD_FLAG in result["flags"]


def test_answer_that_is_not_the_json_counts_as_unread(tmp_path, monkeypatch):
    _, result = priced(tmp_path, monkeypatch, foreign(text="Top Zustand"), lambda prompt: "ne znam")
    assert valuation.UNREAD_FLAG in result["flags"]


def test_read_description_and_ad_without_text_are_not_called_unread(tmp_path, monkeypatch):
    _, read = priced(tmp_path, monkeypatch, foreign(text="Scheckheftgepflegt"), answer("ok"))
    assert valuation.UNREAD_FLAG not in read["flags"]
    _, no_text = priced(tmp_path, monkeypatch, foreign(id="as24:2", text=""), lambda prompt: 1 / 0)
    assert valuation.UNREAD_FLAG not in no_text["flags"]


# --- 24.11. Haiku looks at the photos ----------------------------------------------

PHOTOS = ["https://img.example/1/800x600.webp", "https://img.example/2/800x600.webp"]


def test_photos_reach_the_request_with_the_text():
    seen = []

    def ask(prompt, photos=()):
        seen.append((prompt, list(photos)))
        return '{"stanje": "ok", "popravka": "nema", "airbag": false}'
    reading = describe.read(foreign(title="VW Tiguan", text="Klima, AHK", images=PHOTOS), ask=ask)
    assert reading["state"] == "ok"
    assert seen == [(seen[0][0], PHOTOS)] and "VW Tiguan" in seen[0][0] and "Klima, AHK" in seen[0][0]


def fake_photo(url):
    return {"media_type": "image/jpeg", "data": "data-of-" + url}


def downloaded(urls):
    """What download_photos gives for these photos when every one downloads."""
    return {url: fake_photo(url) for url in urls}


def fake_client(monkeypatch, create):
    """The SDK client with messages.create replaced; no network."""
    messages = type("Messages", (), {"create": staticmethod(create)})()
    monkeypatch.setattr(describe, "api_key", lambda: "test")
    monkeypatch.setattr(describe.anthropic, "Anthropic", lambda **kwargs: type("Client", (), {"messages": messages})())


def bad_request():
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.BadRequestError("Unable to download the file", response=response, body=None)


def test_ask_haiku_puts_the_photos_before_the_text_as_base64_images(monkeypatch):
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        text = type("Block", (), {"type": "text", "text": '{"stanje": "ok", "popravka": "nema"}'})()
        return type("Response", (), {"stop_reason": "end_turn", "content": [text]})()
    fake_client(monkeypatch, create)
    assert REAL_ASK_HAIKU("PROMPT", downloaded(PHOTOS)) == '{"stanje": "ok", "popravka": "nema"}'
    content = sent["messages"][0]["content"]
    assert content == [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": "data-of-" + PHOTOS[0]}},
                       {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": "data-of-" + PHOTOS[1]}},
                       {"type": "text", "text": "PROMPT"}]
    assert sent["model"] == "claude-haiku-5-5" and sent["max_tokens"] == 300
    assert sent["thinking"] == {"type": "disabled"} and sent["output_config"] == {"effort": "low"}


def test_request_the_api_rejects_is_a_photo_problem_only_when_photos_were_sent(monkeypatch):
    def create(**kwargs):
        raise bad_request()
    fake_client(monkeypatch, create)
    with pytest.raises(describe.PhotoRejected):
        REAL_ASK_HAIKU("PROMPT", downloaded(PHOTOS))
    with pytest.raises(anthropic.BadRequestError):
        REAL_ASK_HAIKU("PROMPT")


def test_refusal_is_still_an_error(monkeypatch):
    fake_client(monkeypatch, lambda **kwargs: type("Response", (), {"stop_reason": "refusal", "content": []})())
    with pytest.raises(RuntimeError):
        REAL_ASK_HAIKU("PROMPT", downloaded(PHOTOS))


def test_photo_the_api_cannot_fetch_is_dropped_and_the_text_is_read_alone():
    calls = []

    def ask(prompt, photos=()):
        calls.append(list(photos))
        if photos:
            raise describe.PhotoRejected("Unable to download the file")
        return '{"stanje": "kvar", "popravka": "mala", "napomena": "ogrebotine"}'
    reading = describe.read(foreign(text="Kratzer hinten", images=PHOTOS), ask=ask)
    assert calls == [PHOTOS, []]
    assert reading["state"] == "kvar" and reading["note"] == "ogrebotine"


def test_rejected_photos_and_no_text_give_no_reading():
    def ask(prompt, photos=()):
        raise describe.PhotoRejected("Unable to download the file")
    assert describe.read(foreign(text="", images=PHOTOS), ask=ask) is None


def test_ad_with_photos_and_no_text_is_read():
    seen = []
    reply = '{"stanje": "kvar", "popravka": "velika", "airbag": false, "napomena": "udaren napred"}'
    reading = describe.read(foreign(text="", images=PHOTOS), ask=lambda prompt, photos=(): seen.append(list(photos)) or reply)
    assert seen == [PHOTOS] and reading["repair"] == "velika"


def test_ad_without_photos_and_text_is_not_read():
    asked = []
    assert describe.read(foreign(text=" ", images=[], image=None), ask=lambda *a: asked.append(a)) is None
    assert asked == []


def test_list_page_photo_is_used_when_the_site_gives_no_list():
    assert describe.photos_of(foreign(images=[], image="https://img.example/main.jpg")) == ["https://img.example/main.jpg"]
    assert describe.photos_of(foreign(images=PHOTOS, image="https://img.example/main.jpg")) == PHOTOS
    assert describe.photos_of(foreign(image=None)) == []


def test_key_changes_when_the_photos_change():
    car = foreign(text="a", images=PHOTOS)
    assert describe.text_key(car) == describe.text_key(foreign(text="a", images=list(PHOTOS)))
    assert describe.text_key(car) != describe.text_key(foreign(text="a", images=PHOTOS[:1]))
    assert describe.text_key(car) != describe.text_key(foreign(text="a"))


@pytest.mark.parametrize("airbag,state", [(True, "les"), (False, "ok"), (None, "ok"), ("true", "ok")])
def test_fired_airbag_makes_the_car_a_parts_car(airbag, state):
    answer = '{"stanje": "ok", "popravka": "nema", "airbag": %s}' % json.dumps(airbag)
    assert describe.parse_answer(answer)["state"] == state


def test_prompt_asks_about_airbags_and_the_photos():
    assert '"airbag": true ili false' in describe.PROMPT
    for word in ("fotografij", "volan", "tabl", "sedišt", "zaves"):
        assert word in describe.PROMPT


def test_airbag_seen_on_the_photos_hides_the_car_in_the_scan(tmp_path, monkeypatch):
    car = foreign(text="Klima, AHK, Navi", images=PHOTOS)
    seen_airbag = '{"stanje": "kvar", "popravka": "velika", "airbag": true, "napomena": "otvoreni airbagovi"}'
    text_only = '{"stanje": "ok", "popravka": "nema", "airbag": false}'   # the text lists equipment only

    def ask(prompt, photos=()):
        return seen_airbag if list(photos) == PHOTOS else text_only
    _, result = priced(tmp_path, monkeypatch, car, ask)
    assert car["ai"]["state"] == "les"
    assert result is None


def test_site_damaged_car_haiku_reads_as_clean_keeps_the_default_repair_in_the_scan(tmp_path, monkeypatch):
    car = foreign(price=3000, damaged=True, text="Klima, Navi, AHK")
    _, result = priced(tmp_path, monkeypatch, car, answer("ok"))
    assert result["cost"]["repair"] == valuation.DEFAULT_REPAIR_EUR


# --- review fixes (24.11.2026) ------------------------------------------------------

def rejects_photos(prompt, photos=()):
    if photos:
        raise describe.PhotoRejected("Unable to download the file")
    return '{"stanje": "ok", "popravka": "nema", "airbag": false}'


def test_text_only_reading_is_keyed_without_the_photos_so_the_next_scan_tries_them():
    car = foreign(text="Klima, AHK", images=PHOTOS)
    reading = describe.read(car, ask=rejects_photos)
    assert reading["key"] == describe.text_key(car, [])
    assert reading["key"] != describe.text_key(car)


def test_reading_with_the_photos_is_keyed_with_them():
    car = foreign(text="Klima, AHK", images=PHOTOS)
    reading = describe.read(car, ask=lambda prompt, photos=(): '{"stanje": "ok", "popravka": "nema"}')
    assert reading["key"] == describe.text_key(car)


def test_scan_reads_the_photos_again_after_a_text_only_reading(tmp_path, monkeypatch):
    car = foreign(text="Klima, AHK", images=PHOTOS)
    conn, result = priced(tmp_path, monkeypatch, car, rejects_photos)
    assert car["ai"]["state"] == "ok"
    asked = []

    def airbag_on_photos(prompt, photos=()):
        asked.append(list(photos))
        return '{"stanje": "ok", "popravka": "nema", "airbag": true}'
    monkeypatch.setattr(describe, "ask_haiku", airbag_on_photos)
    again = foreign(text="Klima, AHK", images=PHOTOS)
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    assert value_car(conn, snapshots, again, set()) is None
    assert asked == [PHOTOS]


def test_title_alone_is_read_when_the_photos_are_rejected():
    prompts = []

    def ask(prompt, photos=()):
        if photos:
            raise describe.PhotoRejected("Unable to download the file")
        prompts.append(prompt)
        return '{"stanje": "les", "popravka": "velika", "napomena": "airbagovi otvoreni"}'
    reading = describe.read(foreign(title="Golf Airbags offen", text="", images=PHOTOS), ask=ask)
    assert reading["state"] == "les" and "Golf Airbags offen" in prompts[0]


def test_rejected_photos_without_title_or_text_give_no_reading():
    asked = []

    def ask(prompt, photos=()):
        asked.append(list(photos))
        raise describe.PhotoRejected("Unable to download the file")
    assert describe.read(foreign(title="", text="", images=PHOTOS), ask=ask) is None
    assert asked == [PHOTOS]   # no second, text-only call with nothing to read


def test_empty_photo_slot_is_left_out_and_does_not_break_the_key():
    car = foreign(text="a", images=[None, PHOTOS[0], ""])
    assert describe.photos_of(car) == [PHOTOS[0]]
    assert describe.text_key(car) == describe.text_key(foreign(text="a", images=[PHOTOS[0]]))
    assert describe.photos_of(foreign(images=[None], image="https://img.example/main.jpg")) == ["https://img.example/main.jpg"]


def test_known_wreck_stays_hidden_when_the_scan_skips_its_details(tmp_path, monkeypatch):
    car = foreign(price=3000, text="Klima, Navi", images=PHOTOS)
    conn, result = priced(tmp_path, monkeypatch, car,
                          lambda prompt, photos=(): answer("les", "airbagovi otvoreni")(prompt))
    assert result is None
    asked = []
    monkeypatch.setattr(describe, "ask_haiku", lambda *args: asked.append(args))
    again = foreign(price=3000, text="Klima, Navi", images=PHOTOS)   # mobile.de: the search brings the whole ad
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    assert value_car(conn, snapshots, again, {"autoscout24"}) is None   # the site blocked: no detail stage
    assert asked == []
    assert db.saved_reading(conn, "as24:1")["state"] == "les"   # kept for the next scan too


def test_known_fault_counts_when_the_scan_skips_the_details(tmp_path, monkeypatch):
    car = foreign(text="Kupplung rutscht", images=PHOTOS)
    conn, _ = priced(tmp_path, monkeypatch, car,
                     lambda prompt, photos=(): answer("kvar", "kvacilo proklizava", "mala")(prompt))
    again = foreign(text="Kupplung rutscht", images=PHOTOS)
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    result = value_car(conn, snapshots, again, {"autoscout24"})
    assert result["cost"]["repair"] == valuation.DEFAULT_REPAIR_EUR
    assert "iz opisa: kvacilo proklizava" in result["flags"]
    assert db.saved_reading(conn, "as24:1")["note"] == "kvacilo proklizava"


def test_changed_ad_does_not_reuse_the_old_reading_at_list_stage(tmp_path, monkeypatch):
    car = foreign(price=3000, text="Klima, Navi", images=PHOTOS)
    conn, _ = priced(tmp_path, monkeypatch, car,
                     lambda prompt, photos=(): answer("les", "airbagovi otvoreni")(prompt))
    assert db.saved_reading(conn, "as24:1")["state"] == "les"
    again = foreign(price=3000, text="Klima, Navi, neu lackiert", images=PHOTOS)
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    result = value_car(conn, snapshots, again, {"autoscout24"})
    assert result is not None and "ai" not in again


# --- 24.11. smashed B-Klasse read as clean: mobile.de photos never reached Haiku ------

class FakeResponse:
    def __init__(self, status=200, content_type="image/jpeg", body=b"\xff\xd8jpeg"):
        self.status_code = status
        self.headers = {"content-type": content_type} if content_type else {}
        self.content = body


def serve(monkeypatch, response):
    """describe's HTTP get answers every photo with this response (or raises it); returns the asked urls."""
    asked = []

    def get(url, **kwargs):
        asked.append((url, kwargs.get("impersonate")))
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(describe.requests, "get", get)
    return asked


def test_photo_is_downloaded_and_sent_as_base64(monkeypatch):
    asked = serve(monkeypatch, FakeResponse(content_type="image/jpeg; charset=binary", body=b"abc"))
    assert REAL_DOWNLOAD_PHOTO(PHOTOS[0]) == {"media_type": "image/jpeg", "data": "YWJj"}
    assert asked == [(PHOTOS[0], "chrome")]


@pytest.mark.parametrize("content_type", ["image/jpeg", "image/png", "image/webp", "image/gif", "IMAGE/WEBP"])
def test_every_image_type_the_api_takes_is_kept(monkeypatch, content_type):
    serve(monkeypatch, FakeResponse(content_type=content_type))
    assert REAL_DOWNLOAD_PHOTO(PHOTOS[0])["media_type"] == content_type.lower()


@pytest.mark.parametrize("response", [
    FakeResponse(status=403),                                    # mobile.de's proxy answers 403 to everyone else
    FakeResponse(status=404),
    FakeResponse(content_type="text/html"),                      # a block or error page
    FakeResponse(content_type="image/svg+xml"),                  # an image the API does not take
    FakeResponse(content_type=None),
    FakeResponse(body=b"x" * (describe.MAX_PHOTO_BYTES + 1)),    # over the API's limit for one image
    FakeResponse(body=b"x" * (describe.MAX_PHOTO_BYTES - 1)),    # under 5 MB, but its base64 is over the limit
    RuntimeError("timeout"),
])
def test_photo_that_cannot_be_used_is_skipped(monkeypatch, response):
    serve(monkeypatch, response)
    assert REAL_DOWNLOAD_PHOTO(PHOTOS[0]) is None


def test_photo_whose_base64_is_exactly_the_size_limit_is_kept(monkeypatch):
    serve(monkeypatch, FakeResponse(body=b"x" * (describe.MAX_PHOTO_BYTES * 3 // 4)))   # base64: 4 chars per 3 bytes
    photo = REAL_DOWNLOAD_PHOTO(PHOTOS[0])
    assert len(photo["data"]) == describe.MAX_PHOTO_BYTES


def ok_response(**kwargs):
    text = type("Block", (), {"type": "text", "text": '{"stanje": "ok", "popravka": "nema"}'})()
    return type("Response", (), {"stop_reason": "end_turn", "content": [text]})()


def test_photo_that_cannot_be_downloaded_is_left_out_and_the_rest_are_sent(monkeypatch):
    sent = {}
    fake_client(monkeypatch, lambda **kwargs: sent.update(kwargs) or ok_response())
    monkeypatch.setattr(describe, "download_photo", lambda url: None if url == PHOTOS[0] else fake_photo(url))
    describe.read(foreign(text="Klima", images=PHOTOS), ask=REAL_ASK_HAIKU)
    content = sent["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "text"]
    assert content[0]["source"]["data"] == "data-of-" + PHOTOS[1]


def test_no_photo_downloaded_sends_the_text_alone_and_says_the_photos_were_not_seen(monkeypatch):
    calls = []
    fake_client(monkeypatch, lambda **kwargs: calls.append(kwargs) or ok_response())
    monkeypatch.setattr(describe, "download_photo", lambda url: None)
    car = foreign(text="Klima", images=PHOTOS)
    reading = describe.read(car, ask=REAL_ASK_HAIKU)
    assert len(calls) == 1
    assert [block["type"] for block in calls[0]["messages"][0]["content"]] == ["text"]
    assert reading["photos_unread"] is True and reading["key"] == describe.text_key(car, [])


def test_no_photo_downloaded_and_no_text_gives_no_reading(monkeypatch):
    asked = []
    monkeypatch.setattr(describe, "download_photo", lambda url: None)
    assert describe.read(foreign(title="", text="", images=PHOTOS), ask=lambda *args: asked.append(args)) is None
    assert asked == []


def test_reading_made_with_some_photos_is_keyed_with_those_photos(monkeypatch):
    monkeypatch.setattr(describe, "download_photo", lambda url: None if url == PHOTOS[0] else fake_photo(url))
    car = foreign(text="Klima", images=PHOTOS)
    reading = describe.read(car, ask=lambda prompt, photos=(): '{"stanje": "ok", "popravka": "nema"}')
    assert reading["key"] == describe.text_key(car, [PHOTOS[1]])
    assert reading["key"] != describe.text_key(car)


def test_scan_reads_the_ad_again_when_a_photo_was_missing_last_time(tmp_path, monkeypatch):
    # 1 of 2 photos downloaded: the missing one could show the smashed front, so the next scan tries again
    monkeypatch.setattr(describe, "download_photo", lambda url: None if url == PHOTOS[0] else fake_photo(url))
    asked = []

    def ask(prompt, photos=()):
        asked.append(list(photos))
        return '{"stanje": "ok", "popravka": "nema"}'
    conn, _ = priced(tmp_path, monkeypatch, foreign(text="Klima", images=PHOTOS), ask)
    monkeypatch.setattr(describe, "download_photo", fake_photo)
    again = foreign(text="Klima", images=PHOTOS)
    snapshots = seed_cache(again, [pa_car(str(i), 9000 + i * 100) for i in range(6)])
    value_car(conn, snapshots, again, set())
    assert asked == [[PHOTOS[1]], PHOTOS]


@pytest.mark.parametrize("seen,total,unread", [(0, 2, True), (1, 2, False), (2, 2, False), (1, 3, True),
                                               (2, 3, False), (0, 1, True), (0, 0, False)])
def test_photos_count_as_unread_when_haiku_saw_fewer_than_half(monkeypatch, seen, total, unread):
    urls = [f"https://img.example/{i}.jpg" for i in range(total)]
    monkeypatch.setattr(describe, "download_photo", lambda url: fake_photo(url) if url in urls[:seen] else None)
    reading = describe.read(foreign(text="Klima", images=urls, image=None),
                            ask=lambda prompt, photos=(): '{"stanje": "ok", "popravka": "nema"}')
    assert reading["photos_unread"] is unread


def test_photo_download_stops_when_the_time_for_the_ad_runs_out(monkeypatch):
    clock = iter([0, 0, describe.PHOTOS_BUDGET_S, describe.PHOTOS_BUDGET_S + 1])
    monkeypatch.setattr(describe.time, "monotonic", lambda: next(clock))
    urls = [f"https://img.example/{i}.jpg" for i in range(5)]
    assert list(describe.download_photos(urls)) == urls[:2]   # the time is checked before each photo


def test_photos_that_could_not_be_downloaded_are_left_out_in_order(monkeypatch):
    monkeypatch.setattr(describe, "download_photo", lambda url: None if url.endswith("1.jpg") else fake_photo(url))
    urls = [f"https://img.example/{i}.jpg" for i in range(3)]
    assert describe.download_photos(urls) == downloaded([urls[0], urls[2]])
    assert describe.download_photos([]) == {}


def test_text_only_reading_of_an_ad_with_photos_says_the_photos_were_not_seen():
    assert describe.read(foreign(text="Klima, AHK", images=PHOTOS), ask=rejects_photos)["photos_unread"] is True


def test_reading_with_photos_or_of_an_ad_without_photos_is_not_marked():
    reply = '{"stanje": "ok", "popravka": "nema"}'
    seen = describe.read(foreign(text="Klima", images=PHOTOS), ask=lambda prompt, photos=(): reply)
    assert seen["photos_unread"] is False
    no_photos = describe.read(foreign(text="Klima", images=[], image=None), ask=answer("ok"))
    assert no_photos["photos_unread"] is False


def test_prompt_calls_a_smashed_front_a_big_repair():
    big = describe.PROMPT.split('- "velika":')[1].split('- "mala":')[0]
    for word in ("smrskan", "prednji", "hauba", "farovi", "hladnjak"):
        assert word in big


def test_reading_saved_by_the_previous_version_is_read_again(tmp_path, monkeypatch):
    # the readings before 24.11. evening were made from the text alone: mobile.de photos never reached Haiku
    car = foreign(text="Klima, AHK", images=PHOTOS)
    with monkeypatch.context() as old:
        old.setattr(describe, "READING_VERSION", describe.READING_VERSION - 1)
        old_key = describe.text_key(car, [])
    car["ai"] = {"state": "ok", "repair": "nema", "note": "", "key": old_key}
    conn = db.connect(tmp_path / "t.db")
    db.save_car(conn, car, None, GOLF["as24"])
    assert scan.known_reading(conn, car) is None
    car["ai"]["key"] = describe.text_key(car)
    db.save_car(conn, car, None, GOLF["as24"])
    assert scan.known_reading(conn, car)["key"] == describe.text_key(car)   # a current reading is reused


@pytest.mark.parametrize("state,repair,kept", [("ok", "mala", "kvar"), ("ok", "velika", "kvar"), ("ok", "nema", "ok"),
                                               ("kvar", "mala", "kvar"), ("les", "nema", "les")])
def test_clean_answer_that_names_a_repair_counts_as_a_fault(state, repair, kept):
    # willhaben:1269497294: "ok" with repair "mala" for rust on the tailgate showed no rust on the card
    assert describe.parse_answer('{"stanje": "%s", "popravka": "%s"}' % (state, repair))["state"] == kept


@pytest.mark.parametrize("damaged,line", [(True, "OZNAČEN KAO OŠTEĆEN: da"),
                                          (False, "OZNAČEN KAO OŠTEĆEN: nije označen")])
def test_prompt_says_whether_the_site_marks_the_car_damaged(damaged, line):
    prompts = []
    describe.read(foreign(text="Klima", damaged=damaged), ask=lambda prompt: prompts.append(prompt) or "{}")
    assert line in prompts[0]


def test_prompt_asks_for_the_note_in_serbian_with_diacritics():
    assert "č, ć, š, ž i đ, bez nemačkih reči" in describe.PROMPT
    assert "motor ne pali" in describe.PROMPT.split('- "les":')[1].split('- "kvar":')[0]


def test_site_damaged_car_whose_photos_haiku_could_not_see_waits_for_bane(tmp_path, monkeypatch):
    # mobilede:54216795530592: smashed front, the text is an equipment list, the photos never reached Haiku
    car = foreign(price=3000, damaged=True, text="Klima, Navi, AHK", images=PHOTOS)
    _, result = priced(tmp_path, monkeypatch, car, rejects_photos)
    assert car["ai"]["state"] == "ok" and car["ai"]["photos_unread"] is True
    assert result["profit"] >= result["target"]
    assert result["passes"] is False
    assert valuation.PHOTOS_UNREAD_FLAG in result["flags"] and "oštećen" in result["flags"]


def test_site_damaged_car_haiku_saw_as_clean_on_the_photos_still_passes(tmp_path, monkeypatch):
    car = foreign(price=3000, damaged=True, text="Klima, Navi, AHK", images=PHOTOS)
    _, result = priced(tmp_path, monkeypatch, car, lambda prompt, photos=(): answer("ok")(prompt))
    assert car["ai"]["photos_unread"] is False
    assert result["passes"] is True and valuation.PHOTOS_UNREAD_FLAG not in result["flags"]


def test_undamaged_car_whose_photos_were_not_seen_passes_with_the_warning(tmp_path, monkeypatch):
    car = foreign(price=3000, text="Klima, Navi, AHK", images=PHOTOS)
    _, result = priced(tmp_path, monkeypatch, car, rejects_photos)
    assert result["passes"] is True and valuation.PHOTOS_UNREAD_FLAG in result["flags"]
