# carFinder: everything the owner asked for (Bane, 23-24.11.2026)

Bane is a Serbian used-car importer from Pančevo. He writes Serbian; his words are quoted where they decide something.
A customs firm imports, owns and invoices the car to the buyer; Bane is the intermediary. Novky is a working importer
who checks the tool's output; his figures are ground truth.

## 1. Goal (top of the pyramid)
- Find used cars abroad that can be bought, brought to Pančevo and sold in Serbia with real profit.
- Profit target: at least 1,000 EUR on 5-6k EUR invested, proportionally more above ("1000e na 5-6k").
- The tool is useless if it shows junk on top or nothing at all. On 24.11 it showed 8 deals out of 6,042 priced cars;
  Bane laughed at that. People import these exact models every day and make money, so a tool that finds almost
  nothing is wrong somewhere, not the market. Every step must use the realistic case, not the worst case.
- Later (not now): the system picks the models with the biggest price gap that still sell fast ("tamo gde ima
  najviše prostora... najveća razlika u ceni, a opet ide prodaja"); customer-order mode (a customer orders a model
  and gets a quote).

## 2. Where to search
- mobile.de, AutoScout24 and similar; up to 1,250 km from Subotica; main focus Austria, Germany, Switzerland.
- Only cars located in Germany, Austria and Switzerland (24.11: "rekao sam ne iz italije"); mobile.de also lists
  Italian, French and Dutch dealers, they are dropped.
- Sources now: AutoScout24 (DE, AT), willhaben (AT), mobile.de through the Apify actor (paid, weekly, budget guard;
  token in .env). Switzerland is not built.
- No bot-protection bypass, no proxies, keep polite pauses. Never touch VPN or network settings.
- Speed: Bane asked for it to be "optimalno i seniorno"; whole-model PA snapshots and one thread per site are built.

## 3. Which cars
- Plain petrol only where it sells: "benzin retko ko kupuje u srbiji... ne u audi benzin kombinaciji". A generation
  marked "petrol" in models.py (25%+ of its PA ads are petrol, mostly small and compact cars) is searched and priced
  as petrol too; mid and large cars and every Audi stay diesel, LPG, CNG and hybrid.
- Every model that sells in Serbia is scanned (Bane 25.11: "treba da ubacis sve sto je prodajno... ako ih nema u ovom
  momentu, kakve veze ima? Mozda ce biti sutra, za mesec dana, 6 meseci"): 138 models. The 20 core models run every
  3 hours; the other 118 run once a day, one eighth of them in each 3-hour run. mobile.de stays on the core models
  (budget).
- Engine at most 2.0 litres: "sve preko 2.0 motora je problem u srbiji".
- At most 325,000 km: "stavi limit da trazimo kola do 325.000".
- Estate (karavan) sells for less in Serbia: "mora da je bas jeftin da bi bio karavan". It must be compared only with
  estates.
- Damage: slightly damaged cars are OK if much cheaper; no total wrecks. Sellers hide how bad it is ("alle Airbag OK,
  Motor läuft" on a Tiguan with a bent roof). Fired airbags, bent roof or body structure = total loss, hide. Ideal:
  a small mechanical fault or bodywork scratches/dents, because "u srbiji je vecina stvari jeftino za popravku",
  "kod nas je jeftina limarija". Repair prices: painting one panel about 80 EUR, a headlight 150-200 EUR; a crumpled
  part = paint + a used part. Default small-repair estimate 300 EUR. Do not over-engineer damage rules: "to je
  overengineering... ne seci tako autisticno". Haiku 5.5 reads the description AND the photos (API key in .env,
  project-only key, Haiku 5.5 is the latest).
- No ex-taxis (24.11: an ex-taxi B-Klasse was in the top five); the word "taxi" in the ad drops the car.
- Equipment (MF steering wheel buttons, leather, navigation...) adds value.

## 4. Serbian sale price (the core, the source of most errors so far)
- Compare against polovniautomobili.com, the exact same variant: model, generation, year, doors, engine (cc, kW),
  fuel, gearbox, body (estate separate), 4x4, sub-model (RS, GTD, Scout... only against their own kind).
- Use the cheaper prices: "Moras mu reci da gleda po ceni vozila. Jeftinija. Jer ima budala da traze i 13.000" for a
  Tiguan that is worth at most 9,000. The cheapest ads are often wrecks: take the first clean one and look how many.
- Novky's figures (ground truth): Tiguan 2013 2.0 TDI 130 kW DSG 4Motion, 266,000 km: 8,000-9,000 in Serbia.
  Passat B6 2011 1.4 TSI CNG: "5000 max da ga prodas". Golf 6 GTD 2010: same, about 5,000. Octavia 2014 2.0 TDI
  4x4 DSG L&K: "mozda ima smisla". A colleague bought "the same Skoda" (Octavia) abroad for 2,700.
- Novky on 24.11 (22:51) about two top cars: Mercedes B 200 CDI 2013 "B klasa onako" (so-so seller, weak demand);
  Ford Kuga Titanium automatic "Ford automatik losi" (Ford automatics, PowerShift, are unreliable: they do not
  sell). Ford with an automatic gearbox is dropped; Ford manual stays.
- Bane 24.11: "znas siru sliku kako stvari funkcionisu, a ne od ovog primera za ford automatika da to bude jedina
  pouka". The market layer (carfinder/market.py): sell speed per variant from PA ad ages, the cheapest ad's own age
  and price cut, a reputation table backed by Novky + PA data, and a Novky verdict per car stored as data.
  Research 25.11: a big DE->RS gap often marks a slow seller; French cars from DE/AT are cheaper in Serbia than in
  Germany (margin -45%), so they are not scanned; the money is in older, deep, fast generations bought for 3-7k.
- Novky 25.11 on the top A6 Avant 2017 (priced from 3 Serbian ads): "E to nzm. Ja bih se plasio karavana"; on a
  B 200 2012 automatic at 4,500: "B klasa mi nesto deluje puno. Oko 7 moze da se proda". A car priced from fewer
  than 5 Serbian ads never leads the list. Both verdicts are stored in overrides.
- Novky 25.11, ten questions answered one by one: Opel automatic no; Mercedes A/B DCT ok; Peugeot only with a
  torque-converter automatic, never a robot (ETG/EGS/BMP/2-Tronic); Renault EDC no; Hyundai/Kia automatic no;
  factory CNG "vise ne"; small petrol cars "Daaaa to ide bas bas"; BMW 1er or Mondeo: neither is good, BMW if he
  must; a fast car at +1,000 beats a slow one at +1,900; C4 Picasso "mrtav je za prodaju" (dropped from the scan).
  Plain petrol was skipped everywhere as "does not sell in Serbia": wrong for small cars. Screen 25.11 of 27 small
  petrol generations (Polo, Corsa, Fabia, Ibiza, i20, Rio, Yaris, Clio, 208, C3, Fiesta, up!, Citigo, Swift,
  Sandero, Punto, 500), 1,106 DE/AT cars: 2 at target, both bait or thin; best real car Polo V +529. They sell in
  Serbia for 3-5k and ~1,800 of transport and import bill eat the gap. Bane 25.11 decided to scan them anyway, so a
  good one shows the day it is listed.
- Bane 27.11.2026 on how far under the cheapest PA ask a cash buyer gets the car: "pa zavisi...ali uglavnom bude
  200-300eur". The sale price is the cheapest ask minus 250 e, shown on the card as "minus 250 e za cenkanje u Srbiji".
- A title that names another generation than the year implies (B6 sold as 2011) is not priced against the wrong one.
- Ogi 26.11 (a working importer): "gleda po modelu i restajlingu... Na prelazne godine masi mnogo", an older BMW
  worth 5k was valued at the newer one's 10k. A car is priced only on ads of its own generation and its own side of a
  facelift; in a change-over year that neither the title nor AutoScout24 settles, it counts as the older, cheaper one.

## 5. Costs: there are exactly two, "dovoz" and "carina"
- "kad kazem carina... to se misli na ceo trosak koji trazi carinska firma da se resi sve. troskova su 2 - dovoz i
  carina."
- Transport (dovoz), his real prices to Subotica, +120 EUR Subotica-Pančevo each: Vienna 500, Frankfurt 700-850 by
  car size, Zurich 700. Editable per car.
- Carina: customs values the car from the AMSS catalogue (model, engine, age), not from the invoice. Calibrated on
  Novky's bills: Golf 6 2011 ~1,250; Passat B7 2012 ~1,300; Golf 7 2015 ~1,600. Bane's range: 1,200-1,600 for 3-6k
  cars, up to 10,000; Tesla S 2015 ~4,000. Built outside the EU costs more (Golf 6 from Mexico 1,660 instead of
  1,200; Fiat Freemont 1,700 instead of 1,500); estate vs sedan and fuel matter. "Ali i tu ima mnogo razlika. Zato
  ne treba se voditi time": show it as one rough figure ("oko X"), never split into duty/VAT/fees, and let Bane type
  the real figure per car. Never show anything about EUR.1 ("skloni ovo govno").
- Haggling abroad: the asking price usually comes down 100-300 EUR, sometimes more for export
  ("spusti se obicno 100-300eur al nekad moze i vise za export"). Today the tool uses the full asking price; it must
  count the usual discount (and say so on the card).

## 6. The page
- Local page on his PC, http://127.0.0.1:8765, starts with Windows; scan every 3 hours automatically.
- He reads on a phone and a narrow panel. "Jasno naznaci jednostavno kolika je cena gore, koliko je trosak i koliko
  je ukupno. Ovi dropdowni su bas losi... stavi u prvi plan sta je najbitnije." No dropdowns around the money.
- "'Najviše platiti' nema smisla... jako los ux": the max must say it is the price to pay THE SELLER (now
  "Najviše da daš prodavcu").
- Serbian copy with diacritics, his words (cena, dovoz, carina, ukupno, zarada, prodaja u Srbiji), no jargon.

## 7. Working rules
- Smallest complete change, readable code, no clever one-liners; tests are never weakened, merged or deleted; new
  logic gets edge-case tests. Never print or log anything from .env. Do not touch VPN or network settings.
- Agents run on Opus, not Fable, to save tokens.
