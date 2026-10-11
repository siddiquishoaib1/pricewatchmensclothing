# Price Watcher

Watches a list of specific products for price drops and reports where
each one stands.

Two numbers per item:

| Column | Meaning |
|---|---|
| **Real** | How far the price actually fell since the last run |
| **Claim** | Discount off the store's own crossed-out "original" price |

**Real** is the one to trust. **Claim** is shown so you can spot
inflated originals — an item claiming 60% off whose price has never
actually moved is marketing, not a deal.

## The watchlist

`watchlist.txt` holds the items. Paste the URL straight from your
browser, keeping the `?variant=...` part to pin one specific size:

```
https://www.brandstudio.pk/products/ami-ri-copy?variant=46794715758788   # my note
```

- Drop the `?variant=` to watch every size of that product.
- Add `@weekly` in the note to check that item weekly instead of daily.
- Tracking junk in the URL (`?_pos=1&_ss=c&...`) is fine and ignored.
- Lines starting with `#` are ignored; text after the URL is your note.

### How often each item is checked

Items are checked **daily** by default. Add `@weekly` to the note to
slow one down:

```
https://narkins.com/products/...?variant=45042560073947   # Narkins fabric @weekly
```

A weekly item is fetched only once its seven days have passed. On the
days in between it still appears in the report, carrying its last known
price and labelled with when it was actually checked — so a slow-moving
item never silently disappears from the table.

Every item appears in the report every run — whether or not the price
moved, and whether or not it is in stock. Out-of-stock items are
labelled, not hidden. If a pinned variant stops existing because the
store deleted or re-created the product, that is reported as a problem
rather than the item quietly vanishing.

## Monitoring a deal page

`pages.txt` holds pages to watch for line-up changes:

```
https://gomilaintersole.pk/pages/deal-of-the-day   # Gomila deal of the day
```

Use this for hand-built deal pages that are **not** a collection and so
have no JSON endpoint. Gomila's deal-of-the-day is exactly that: its
`deal-of-the-day` collection is empty, while the page itself lists
around fifty products.

Each run fetches the page once, pulls out the products linked from it,
and reports what was **added** or **removed** since last time. New
arrivals are then priced individually, up to 15 per run — pricing all
fifty every day would be a crawl, and the new ones are the news.

If a page suddenly yields no product links at all, that is reported as
a problem rather than passing silently as "no change" — it usually
means the store changed its layout.

Watching a page answers "what showed up today". To track one specific
product's price, use `watchlist.txt` instead.

## Running it

```bash
python3 watcher.py
```

Nothing to install — Python 3.8+ and the standard library only. On
Windows use `python` instead of `python3`.

The first run has no history to compare against, so **Real** will be
empty and everything sits in **Claim**. Run it again later and real
drops appear.

```bash
python3 watcher.py --report-only   # reprint last report, no fetching
python3 watcher.py --quiet-ok      # exit 0 even if some items fail
```

Each run writes `data/REPORT.md` (renders as a table on GitHub, works
on a phone) and `data/latest_report.csv`.

## Running it automatically

**macOS / Linux** — daily at 8.40am. `crontab -e` and add:

```
40 8 * * * cd /full/path/to/pricewatch && /usr/bin/python3 watcher.py >> log.txt 2>&1
```

**Windows** — Task Scheduler → Create Basic Task → Daily:

- Program: `python`
- Arguments: `watcher.py`
- Start in: the folder containing `watcher.py`

### Why not GitHub Actions?

It was tried and it does not work. These stores return
`429 Too Many Requests` to GitHub's shared runner IPs **from the very
first request** — all 17 stores, twice, including after backoff was
raised to honour `Retry-After` and wait up to 90 seconds. It is not a
volume problem that patience fixes; the datacentre IP is simply
refused.

The workflow in `.github/workflows/watch.yml` is left in place but its
schedule is commented out. To use it, set up a
[self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners)
on your own machine, change `runs-on: ubuntu-latest` to
`runs-on: self-hosted`, and uncomment the `schedule:` block. You then
keep the daily schedule, the auto-commit and the phone-readable
report, but requests go out from your own connection.

Plain `cron` or Task Scheduler is simpler and does the same job
locally.

## History

This started as a store-wide sweep across 17 Pakistani menswear sites,
filtering whole catalogues by size. That was removed: the rate
limiting above made it unworkable from anywhere but a home connection,
and most of those stores never populate a "compare at" price anyway,
so there was little to detect. Watching named items is cheaper, more
reliable, and reports on exactly what you care about.

The sweep's code is still in git history if it is ever wanted back —
see the commits before "Replace store-wide sweep with watchlist only".

## Files

```
watcher.py          the script
watchlist.py        URL parsing and price helpers
watchlist.txt       your pinned products - edit this
pages.txt           deal pages to monitor - edit this
test_watchlist.py   tests
data/REPORT.md      latest report - this is the one to read
data/latest_report.csv
data/prices.db      price history (SQLite)
```

`data/` is committed on purpose: it is both the published report and
the baseline the next run compares against.

## Tests

```bash
python3 test_watchlist.py
```

## A note on fairness to these shops

The script identifies itself honestly, waits between requests, and
reads only the public product endpoint — a handful of small requests
per run. Please leave those settings alone.
