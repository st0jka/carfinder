import pytest

from carfinder import net


class FakeSession:
    """Stands in for a curl_cffi Session: no network in tests."""
    created = []

    def __init__(self, impersonate=None):
        self.impersonate = impersonate
        self.urls = []
        self.status_code = 200
        self.text = "<html></html>"
        FakeSession.created.append(self)

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append(url)
        return self

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def web(monkeypatch):
    """A fake clock and fake sessions; returns the list of pauses net.get slept."""
    FakeSession.created = []
    clock = {"now": 1000.0}
    pauses = []

    def sleep(seconds):
        pauses.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(net.requests, "Session", FakeSession)
    monkeypatch.setattr(net, "_sessions", {})
    monkeypatch.setattr(net, "_last_request", {})
    monkeypatch.setattr(net.time, "time", lambda: clock["now"])
    monkeypatch.setattr(net.time, "sleep", sleep)
    monkeypatch.setattr(net.random, "uniform", lambda low, high: low)
    return pauses


def test_every_site_has_its_own_session_and_keeps_it(web):
    net.get("https://a.example/1", site="a")
    net.get("https://a.example/2", site="a")
    net.get("https://b.example/1", site="b")
    assert len(FakeSession.created) == 2
    assert FakeSession.created[0].urls == ["https://a.example/1", "https://a.example/2"]
    assert FakeSession.created[1].urls == ["https://b.example/1"]
    assert {session.impersonate for session in FakeSession.created} == {"chrome"}


def test_site_name_comes_from_the_url_when_it_is_not_given(web):
    net.get("https://www.willhaben.at/iad/x")
    net.get("https://www.willhaben.at/iad/y")
    assert len(FakeSession.created) == 1


def test_pause_is_kept_between_two_requests_to_one_site_only(web):
    net.get("https://a.example/1", site="a")
    net.get("https://b.example/1", site="b")      # another site does not wait for the first
    assert web == []
    net.get("https://a.example/2", site="a")
    assert web == [net.MIN_PAUSE_S]
    net.get("https://www.polovniautomobili.com/1", site="polovni")
    net.get("https://www.polovniautomobili.com/2", site="polovni")
    assert web == [net.MIN_PAUSE_S, net.SITE_PAUSE_S["polovni"][0]]


def test_pause_lengths_are_the_agreed_ones():
    assert (net.MIN_PAUSE_S, net.MAX_PAUSE_S) == (4, 8)
    assert net.SITE_PAUSE_S == {"polovni": (3, 5)}


@pytest.mark.parametrize("status,text", [(403, ""), (429, ""), (200, "<title>Just a moment...</title>")])
def test_block_answers_raise_blocked(web, status, text):
    net.get("https://a.example/1", site="a")
    FakeSession.created[0].status_code = status
    FakeSession.created[0].text = text
    with pytest.raises(net.Blocked):
        net.get("https://a.example/2", site="a")


def failing_session(error):
    """The site's session from now on fails every request with this error."""
    def get(url, params=None, headers=None, timeout=None):
        raise error
    FakeSession.created[0].get = get


def test_failed_request_is_paced_like_any_other(web):
    """One search per year means a dropped connection is followed by many more requests to the same site."""
    net.get("https://a.example/1", site="a")
    failing_session(ConnectionError("connection reset"))
    for attempt in range(3):
        with pytest.raises(ConnectionError):
            net.get("https://a.example/2", site="a")
    assert web == [net.MIN_PAUSE_S] * 3


def test_request_after_a_failed_first_request_waits_too(web, monkeypatch):
    class Refusing(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            if not self.urls:
                self.urls.append(url)
                raise ConnectionError("connection refused")
            return super().get(url, params, headers, timeout)
    monkeypatch.setattr(net.requests, "Session", Refusing)
    with pytest.raises(ConnectionError):
        net.get("https://a.example/1", site="a")
    assert web == []
    net.get("https://a.example/2", site="a")
    assert web == [net.MIN_PAUSE_S]
