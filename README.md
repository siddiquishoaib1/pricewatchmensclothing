# PK Menswear Price Watcher

Watches 17 Pakistani menswear stores for price drops on **shirts in XL**
and **shoes in size 45**, and ranks the steepest.

It reports two numbers side by side:

| Column | Meaning |
|---|---|
| **REAL** | How far the price actually fell since the last run |
| **CLAIM** | Discount off the store's own crossed-out "original" price |

The REAL column is the one to trust. CLAIM is included so you can spot
inflated originals — an item showing 60% off that has never actually
moved is marketing, not a deal.

## Requirements

Python 3.8 or newer. Nothing to install — standard library only.

Check what you have:

```bash
python3 --version
```

On Windows, use `python` instead of `python3` in every command below.

## Running it

```bash
python3 watcher.py
```

First run takes a few minutes (it pages through every store's full
catalogue at roughly one request per second, deliberately gentle on
small shops). It builds `prices.db` and prints a report.

**The first run cannot show REAL drops** — there is no history to
compare against yet. Everything will be in the CLAIM column. Run it
again the next day and real drops start appearing.

Other options:

```bash
python3 watcher.py --min-drop 20    # only drops of 20% or more
python3 watcher.py --report-only    # reprint last report, no fetching
python3 watcher.py --probe          # check which stores respond
```

Each run also writes `latest_report.csv`.

## Running it automatically

**macOS / Linux** — run daily at 9am. Open your crontab with
`crontab -e` and add:

```
0 9 * * * cd /full/path/to/pricewatch && /usr/bin/python3 watcher.py >> log.txt 2>&1
```

**Windows** — open Task Scheduler → Create Basic Task → Daily →
Start a program:

- Program: `python`
- Arguments: `watcher.py`
- Start in: the folder containing `watcher.py`

Then read `log.txt`, or run `python watcher.py --report-only` whenever
you want to see the latest.

## Stores covered

brandstudio · turbobrandsfactory · boutiquederoyal · dealsexpress ·
designdistrict · gomilaintersole · ismailfarid · silentluxury ·
weebyshoes · aspire · alfatah · saleemfabrics · leftoversden ·
enemmall · justbrands · casualcollection · amazonleftover

## Stores NOT covered, and why

| Store | Reason |
|---|---|
| hopkicks.pk | robots.txt disallows automated access |
| accoutreclothing.com (Accoutre) | blocks non-browser requests |
| ahmedfabricsinternational.com | robots.txt disallows automated access |
| amoosajeesons.com | robots.txt disallows automated access |
| calabria.com.pk | server error on the product feed |
| brandedkicks.pk | server error on the product feed |
| aieopeson (AliExpress) | marketplace seller, no storefront feed |

The robots.txt ones are a deliberate "no" from the site owner, so the
script respects it. The two erroring stores may simply have been down —
try `python3 watcher.py --probe` after moving them from `BLOCKED` into
`SITES` in `sites.py`.

## What counts as a match

**Shirts** means shirts proper — casual, formal, denim, flannel,
oxford. T-shirts, polos, sweatshirts, hoodies, jerseys and vests are
deliberately excluded. To widen it, edit `_SHIRT_EXCLUDE` in
`matching.py`.

**Size XL** matches `XL`, `X-Large`, `Extra Large` — and deliberately
not `XXL`, `2XL` or `3XL`.

**Size 45** matches the various labels these stores use: `45`,
`EU 45`, `PK 11 | EU 45`, `Male Size 45`. Half sizes like `45.5` are
excluded.

Out-of-stock variants never appear in the report.

## Tests

```bash
python3 test_matching.py
python3 test_watcher.py
```

The first checks size parsing and shirt/shoe classification against
label formats taken from the real feeds. The second simulates two runs
a day apart and verifies a genuine drop is told apart from a fake
claimed discount.

## Files

```
watcher.py         main script
matching.py        size parsing and product classification
sites.py           store list
test_matching.py   classification tests
test_watcher.py    end-to-end drop-detection tests
prices.db          price history (created on first run)
latest_report.csv  most recent report (created on first run)
```

## A note on fairness to these shops

The script identifies itself honestly in its User-Agent, waits a second
between requests, and reads only the public product feed every Shopify
store publishes. Please leave those settings alone — it is the
difference between a hobby price tracker and something that gets your
IP banned.
