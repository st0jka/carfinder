import pytest

from carfinder import describe


@pytest.fixture(autouse=True)
def no_real_haiku(monkeypatch):
    """Tests never start the real claude program; a test that needs a reading passes its own `ask`."""
    def unavailable(prompt, photos=()):
        raise RuntimeError("claude is not called in tests")
    monkeypatch.setattr(describe, "ask_haiku", unavailable)


@pytest.fixture(autouse=True)
def no_real_photo_download(monkeypatch):
    """Tests never download a photo; every photo 'downloads' as a few bytes of a jpeg."""
    monkeypatch.setattr(describe, "download_photo", lambda url: {"media_type": "image/jpeg", "data": "data-of-" + url})
