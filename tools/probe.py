"""One request per site from the cloud runner: does it let us in?"""
from carfinder import net

URLS = {
    "autoscout24.de": "https://www.autoscout24.de/lst/volkswagen/golf",
    "autoscout24.at": "https://www.autoscout24.at/lst/volkswagen/golf",
    "willhaben": "https://www.willhaben.at/iad/gebrauchtwagen/auto/gebrauchtwagenboerse",
    "polovni": "https://www.polovniautomobili.com/auto-oglasi/pretraga?brand=volkswagen&model=golf",
}

for site, url in URLS.items():
    try:
        html = net.get(url, site=site).text
        print(site, "OK", "next_data" if "__NEXT_DATA__" in html else "NO next_data", len(html))
    except Exception as error:
        print(site, "FAIL", error)
