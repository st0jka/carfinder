"""Writes the page as one static file for GitHub Pages: python -m tools.export_page site/index.html"""
import sys
from pathlib import Path

from carfinder import web


def export(path):
    web.PAGE.globals["static"] = True   # no filters or edit forms: nothing answers them online
    try:
        html = web.index(country="", model="", max_cash="", all="", sort="profit")
    finally:
        web.PAGE.globals.pop("static")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    export(sys.argv[1])
