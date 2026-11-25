"""One HTTP session per site, with pauses between requests and stop on blocks."""
import json
import random
import re
import time

from curl_cffi import requests

MIN_PAUSE_S = 4
MAX_PAUSE_S = 8
SITE_PAUSE_S = {"polovni": (3, 5)}   # many pages of one search; still slower than a person clicking

_sessions = {}       # per site: the scan gives every site its own thread and a Session must not be shared
_last_request = {}


class Blocked(Exception):
    """The site answered with a block or captcha; the scan skips this site for the run."""


def get(url, params=None, site=None, headers=None):
    site = site or url.split("/")[2]
    low, high = SITE_PAUSE_S.get(site, (MIN_PAUSE_S, MAX_PAUSE_S))
    wait = _last_request.get(site, 0) + random.uniform(low, high) - time.time()
    if wait > 0:
        time.sleep(wait)
    if site not in _sessions:
        _sessions[site] = requests.Session(impersonate="chrome")
    try:
        response = _sessions[site].get(url, params=params, headers=headers, timeout=40)
    finally:
        _last_request[site] = time.time()   # a request that failed counts too: the next one still waits
    if response.status_code in (403, 429) or "Just a moment..." in response.text[:3000]:
        raise Blocked(f"{site} returned {response.status_code}")
    response.raise_for_status()
    return response


def next_data(html):
    """pageProps from a Next.js page (polovniautomobili, autoscout24, willhaben all use it)."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise Blocked("page has no __NEXT_DATA__ (layout change or block page)")
    return json.loads(match.group(1))["props"]["pageProps"]
