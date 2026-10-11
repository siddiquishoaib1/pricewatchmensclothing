# PK Menswear Price Watcher

Watches 17 Pakistani menswear stores for price drops on
t-shirts, polos, shirts, belts and shoes in your sizes, and ranks the steepest.

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

## Automatic weekly runs (already set up)

A GitHub Action runs this every **Monday at 09:10 Pakistan time**,
with no need for your computer to be on, and commits the result back
to this repo.

**To read today's drops, open [`data/REPORT.md`](data/REPORT.md).**
It renders as a table on github.com, so it works fine on a phone.

To run it immediately instead of waiting: repo → **Actions** tab →
*Weekly price check* → **Run workflow**.

To change the time, edit the `cron` line in
`.github/workflows/watch.yml`. It is in UTC, so Pakistan time minus
five hours. GitHub also queues scheduled jobs, so the actual run can
be 5-30 minutes later than scheduled.

If you want an email when prices move, go to your GitHub
**Settings → Notifications** and enable notifications for your own
repository activity — you will then get a mail per commit the watcher
makes, and it only commits on days something actually changed.

## Running it yourself instead

**macOS / Linux** — run weekly on Monday at 9am. Open your crontab with
`crontab -e` and add:

```
0 9 * * 1 cd /full/path/to/pricewatch && /usr/bin/python3 watcher.py >> log.txt 2>&1
```

**Windows** — open Task Scheduler → Create Basic Task → Weekly →
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

Five categories, each with its own sizing rule:

| Category | What it catches | Size matched |
|---|---|---|
| T-shirts & polos | tees, polo shirts | XL |
| Casual shirts | casual button-downs, oxford, flannel, denim | XL **or** collar 17 |
| Formal shirts | formal / dress shirts | collar 17 |
| Belts | belts (not buckles or belt bags) | waist 34 or 36 |
| Shoes | all footwear incl. sneakers, slides, sandals | 45 |

**XL** matches `XL`, `X-Large`, `Extra Large` — deliberately not
`XXL`, `2XL` or `3XL`.

**Collar 17** matches `17`, `17"`, `17 inch` and the metric `43`.
`17.5` is a different collar and is excluded. `43` is only read as a
collar on a shirt, so it never collides with shoe size 43.

**Waist 34/36** matches those numbers, plus the metric `85 cm` and
`90 cm`.

**Size 45** matches `45`, `EU 45`, `PK 11 | EU 45`, `Male Size 45`.
Half sizes like `45.5` are excluded.

Sweatshirts, hoodies, jerseys, tanks, nightshirts and shirt-dresses
are excluded from every category. To change any of this, edit the
patterns at the top of `matching.py`.

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
watcher.py                    main script
matching.py                   size parsing and product classification
sites.py                      store list
test_matching.py              classification tests
test_watcher.py               end-to-end drop-detection tests
.github/workflows/watch.yml   the weekly automatic run
data/REPORT.md                today's drops - this is the one to read
data/latest_report.csv        same thing as a spreadsheet
data/prices.db                price history (SQLite)
```

`data/` is committed on purpose — that is how the weekly run publishes
its results and remembers yesterday's prices.

## A note on fairness to these shops

The script identifies itself honestly in its User-Agent, waits a second
between requests, and reads only the public product feed every Shopify
store publishes. Please leave those settings alone — it is the
difference between a hobby price tracker and something that gets your
IP banned.
