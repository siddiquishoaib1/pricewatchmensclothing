#!/usr/bin/env python3
"""Price watcher for a list of specific products.

Checks each item in watchlist.txt, keeps a price history in SQLite,
and reports where each one stands - moved or not, in stock or not.

Two numbers per item:

  REAL    - how far the price fell since the last time this script ran
  CLAIMED - discount off the store's own crossed-out original price

REAL is the honest one. CLAIMED is shown so you can spot stores
inflating their "original" - a big claimed discount on an item whose
price has never actually moved is marketing, not a deal.

The store-wide catalogue sweep was removed (see README). Each item here
costs one small request against the storefront .js endpoint.

Usage:
    python watcher.py                 # check, store, report
    python watcher.py --report-only   # reprint last report, no fetching
    python watcher.py --quiet-ok      # exit 0 even if some items fail

Standard library only - nothing to install.
"""

import argparse
import json
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import watchlist as W

HERE = Path(__file__).resolve().parent
WATCHLIST_PATH = HERE / "watchlist.txt"
PAGES_PATH = HERE / "pages.txt"
DATA_DIR = HERE / "data"
DB_PATH = DATA_DIR / "prices.db"
CSV_PATH = DATA_DIR / "latest_report.csv"
MD_PATH = DATA_DIR / "REPORT.md"

REQUEST_PAUSE = 1.5      # be polite to small shops
TIMEOUT = 30
RETRIES = 5
# Rate limits need real waiting, not a couple of seconds.
BACKOFF = (15, 30, 60, 90)

UA = ("Mozilla/5.0 (compatible; personal-price-watcher/1.0; "
      "single user, a few requests per run)")


# ----------------------------------------------------------- fetching

def fetch_text(url):
    """GET a URL and return its body as text. Retries like fetch_json."""
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
            })
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT,
                                        context=ctx) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429 and attempt < RETRIES - 1:
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = int(retry_after)
                except (TypeError, ValueError):
                    wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                time.sleep(min(wait, 120))
                continue
            break
        except Exception as exc:          # noqa: BLE001
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
    raise RuntimeError(f"{type(last).__name__}: {last}")


def fetch_json(url):
    """GET a URL and parse JSON. Raises on failure after retries.

    Honours Retry-After on 429. A shared/datacentre IP (a CI runner, a
    VPN exit) can be throttled from the very first request, in which
    case no amount of backoff helps - that is why this runs from your
    own machine.
    """
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json",
            })
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT,
                                        context=ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429 and attempt < RETRIES - 1:
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = int(retry_after)
                except (TypeError, ValueError):
                    wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                time.sleep(min(wait, 120))
                continue
            if attempt < RETRIES - 1 and 500 <= exc.code < 600:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
            break
        except Exception as exc:          # noqa: BLE001
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
    raise RuntimeError(f"{type(last).__name__}: {last}")


# ------------------------------------------------------------ storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL,
    site        TEXT    NOT NULL,
    variant_id  TEXT    NOT NULL,
    handle      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    size        TEXT    NOT NULL,
    price       REAL,
    compare_at  REAL,
    available   INTEGER,
    url         TEXT,
    seen_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_variant ON observations(site, variant_id, id);
CREATE TABLE IF NOT EXISTS page_items (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL,
    page        TEXT    NOT NULL,
    handle      TEXT    NOT NULL,
    seen_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_page ON page_items(page, run_id);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    notes       TEXT
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def previous_prices(conn, run_id):
    """Latest price per variant from BEFORE this run.

    Returns {(site, variant_id): (price, seen_at)}.
    """
    rows = conn.execute(
        """
        SELECT site, variant_id, price, seen_at
        FROM observations o
        WHERE run_id < ?
          AND id = (SELECT MAX(id) FROM observations
                    WHERE site = o.site
                      AND variant_id = o.variant_id
                      AND run_id < ?)
        """,
        (run_id, run_id),
    ).fetchall()
    return {(r["site"], r["variant_id"]): (r["price"], r["seen_at"])
            for r in rows}


def last_observation(conn, site, handle):
    """Most recent stored observation for an item, or None."""
    row = conn.execute(
        """SELECT * FROM observations
           WHERE site = ? AND handle = ?
           ORDER BY id DESC LIMIT 1""",
        (site, handle)).fetchone()
    return dict(row) if row else None


def days_since(iso_stamp):
    """Whole days between an ISO stamp and now. None if unparseable."""
    if not iso_stamp:
        return None
    try:
        then = datetime.fromisoformat(iso_stamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).days


def store_rows(conn, rows):
    if not rows:
        return
    conn.executemany(
        """INSERT INTO observations
           (run_id, site, variant_id, handle, title, category, size,
            price, compare_at, available, url, seen_at)
           VALUES (:run_id, :site, :variant_id, :handle, :title,
                   :category, :size, :price, :compare_at, :available,
                   :url, :seen_at)""",
        rows,
    )
    conn.commit()


# ------------------------------------------------------------ collect

def collect(conn, run_id):
    """Check each watchlist item. Returns (rows, errors)."""
    if not WATCHLIST_PATH.exists():
        return [], [("watchlist", f"{WATCHLIST_PATH.name} not found")]

    entries, problems = W.parse_file(
        WATCHLIST_PATH.read_text(encoding="utf-8"))
    rows = []
    errors = [(f"line {n}", msg) for n, msg in problems]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not entries:
        errors.append(("watchlist", "no items - add product URLs to "
                                    f"{WATCHLIST_PATH.name}"))

    carried = []
    for e in entries:
        label = e["note"] or e["handle"]

        # A non-daily item is only fetched once its interval has passed.
        # On the days it is skipped we carry its last known state into
        # the report, so it does not silently vanish from the table.
        wait_days = W.CADENCE_DAYS.get(e.get("every", "daily"), 0)
        if wait_days:
            previous = last_observation(conn, e["site"], e["handle"])
            age = days_since(previous["seen_at"]) if previous else None
            if previous and age is not None and age < wait_days:
                stale = dict(previous)
                stale["stale_days"] = age
                carried.append(stale)
                print(f"  {label[:40]:42s} not due ({e['every']}, "
                      f"checked {age}d ago)")
                continue

        try:
            data = fetch_json(W.js_url(e["base"], e["handle"]))
        except Exception as exc:               # noqa: BLE001
            errors.append((label, str(exc)))
            print(f"  {label[:40]:42s} FAILED  {exc}", file=sys.stderr)
            continue

        title = data.get("title") or e["handle"]
        wanted = e["variant"]
        found = False

        for v in data.get("variants") or []:
            vid = str(v.get("id"))
            if wanted and vid != wanted:
                continue
            found = True
            vlabel = v.get("title") or ""
            # "Default Title" is Shopify's placeholder for a product
            # with no options at all - showing it would be noise.
            if vlabel.strip().lower() == "default title":
                vlabel = ""
            rows.append({
                "run_id": run_id,
                "site": e["site"],
                "variant_id": vid,
                "handle": e["handle"],
                "title": f"{title} ({vlabel})" if vlabel else title,
                "category": "watchlist",
                "size": W.normalise(vlabel),
                "price": W.to_rupees(v.get("price")),
                "compare_at": W.to_rupees(v.get("compare_at_price")),
                "available": 1 if v.get("available") else 0,
                "url": e["url"],
                "seen_at": now,
            })

        if wanted and not found:
            errors.append((label, f"variant {wanted} no longer exists"))
            print(f"  {label[:40]:42s} variant gone", file=sys.stderr)
        else:
            print(f"  {label[:40]:42s} ok")
        time.sleep(REQUEST_PAUSE)

    store_rows(conn, rows)
    return rows, carried, errors


# ------------------------------------------------------- page watches

# A deal page can list dozens of products. Pricing every one of them on
# every run would be a crawl; pricing only the new arrivals keeps a
# daily check down to roughly one request plus a handful.
MAX_NEW_PRICED = 15


def collect_pages(conn, run_id):
    """Diff each monitored page's product line-up against last run.

    Returns (changes, rows, errors) where changes is a list of dicts
    describing what was added or removed, and rows are observations for
    newly added products so their prices enter the history.
    """
    if not PAGES_PATH.exists():
        return [], [], []

    entries, problems = W.parse_pages_file(
        PAGES_PATH.read_text(encoding="utf-8"))
    changes, rows = [], []
    errors = [(f"pages.txt line {n}", msg) for n, msg in problems]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for e in entries:
        label = e["note"] or e["url"]
        try:
            html = fetch_text(e["url"])
        except Exception as exc:               # noqa: BLE001
            errors.append((label, str(exc)))
            print(f"  {label[:40]:42s} FAILED  {exc}", file=sys.stderr)
            continue

        handles = W.extract_product_handles(html)
        if not handles:
            errors.append((label, "no product links found - page layout "
                                  "may have changed"))
            print(f"  {label[:40]:42s} no products found", file=sys.stderr)
            continue

        prior = {r["handle"] for r in conn.execute(
            """SELECT DISTINCT handle FROM page_items
               WHERE page = ? AND run_id = (
                   SELECT MAX(run_id) FROM page_items
                   WHERE page = ? AND run_id < ?)""",
            (e["url"], e["url"], run_id))}

        conn.executemany(
            "INSERT INTO page_items (run_id, page, handle, seen_at) "
            "VALUES (?, ?, ?, ?)",
            [(run_id, e["url"], h, now) for h in handles],
        )
        conn.commit()

        current = set(handles)
        first_time = not prior
        added = [h for h in handles if h not in prior]
        removed = sorted(prior - current)

        # Price the new arrivals so they land in the history too.
        priced = []
        for h in added[:MAX_NEW_PRICED]:
            try:
                data = fetch_json(W.js_url(e["base"], h))
            except Exception as exc:           # noqa: BLE001
                errors.append((f"{label}: {h}", str(exc)))
                continue
            variants = data.get("variants") or []
            cheapest = None
            for v in variants:
                p = W.to_rupees(v.get("price"))
                if p is not None and (cheapest is None
                                      or p < cheapest["price"]):
                    cheapest = {"price": p, "v": v}
            if not cheapest:
                continue
            v = cheapest["v"]
            rec = {
                "run_id": run_id,
                "site": e["site"],
                "variant_id": str(v.get("id")),
                "handle": h,
                "title": data.get("title") or h,
                "category": "page",
                "size": W.normalise(v.get("title") or ""),
                "price": cheapest["price"],
                "compare_at": W.to_rupees(v.get("compare_at_price")),
                "available": 1 if v.get("available") else 0,
                "url": W.page_url(e["base"], h),
                "seen_at": now,
            }
            rows.append(rec)
            priced.append(rec)
            time.sleep(REQUEST_PAUSE)

        changes.append({
            "label": label,
            "url": e["url"],
            "first_time": first_time,
            "total": len(handles),
            "added": added,
            "removed": removed,
            "priced": priced,
            "unpriced": max(0, len(added) - MAX_NEW_PRICED),
        })

        state = (f"{len(handles)} items, first run" if first_time else
                 f"{len(handles)} items, +{len(added)} -{len(removed)}")
        print(f"  {label[:40]:42s} {state}")
        time.sleep(REQUEST_PAUSE)

    store_rows(conn, rows)
    return changes, rows, errors


def render_page_changes(changes, markdown):
    """Lines describing page line-up changes, for either output."""
    out = []
    for c in changes:
        if markdown:
            out += [f"## {c['label']}", "",
                    f"[{c['url']}]({c['url']}) - {c['total']} items listed",
                    ""]
        else:
            out += [f"\n  {c['label']}  ({c['total']} items listed)",
                    "  " + "-" * 96]

        if c["first_time"]:
            line = ("First run - recording what is on the page now. "
                    "Changes appear from the next run onward.")
            out.append(f"_{line}_" if markdown else f"    {line}")
            out.append("")
            continue

        if not c["added"] and not c["removed"]:
            line = "No change since the last run."
            out.append(f"_{line}_" if markdown else f"    {line}")
            out.append("")
            continue

        if c["priced"]:
            if markdown:
                out += ["**New on the page:**", "",
                        "| Claim | Now | Was | Item |", "|---:|---:|---:|---|"]
                for i in c["priced"]:
                    claim = W.pct_drop(i["compare_at"], i["price"])
                    claim_s = f"{claim:.0f}%" if claim else "-"
                    title = i["title"].replace("|", "/")[:60]
                    if not i["available"]:
                        title += " - OUT OF STOCK"
                    out.append(f"| {claim_s} | {money(i['price'])} | "
                               f"{money(i['compare_at'])} | "
                               f"[{title}]({i['url']}) |")
                out.append("")
            else:
                out.append("    NEW ON THE PAGE:")
                for i in c["priced"]:
                    claim = W.pct_drop(i["compare_at"], i["price"])
                    claim_s = f"{claim:.0f}%" if claim else "-"
                    out.append(f"      {claim_s:>5}  {money(i['price']):>11}  "
                               f"{i['title'][:50]}")
                out.append("")

        if c["unpriced"]:
            line = (f"...and {c['unpriced']} more new item(s) not priced "
                    "this run.")
            out.append(f"_{line}_" if markdown else f"    {line}")
            out.append("")

        if c["removed"]:
            shown = ", ".join(c["removed"][:10])
            more = (f" (+{len(c['removed']) - 10} more)"
                    if len(c["removed"]) > 10 else "")
            line = f"Gone from the page: {shown}{more}"
            out.append(f"_{line}_" if markdown else f"    {line}")
            out.append("")
    return out


# ------------------------------------------------------------- report

def build_report(rows, prev):
    """Attach real/claimed drops. Every item is kept.

    Nothing is filtered out: the point of pinning an item is to see
    where it stands each run, in stock or not, moved or not.
    """
    out = []
    for r in rows:
        old_price, old_seen = prev.get((r["site"], r["variant_id"]),
                                       (None, None))
        item = dict(r)
        item["real_drop"] = W.pct_drop(old_price, r["price"])
        item["prev_price"] = old_price
        item["prev_seen"] = old_seen
        item["claimed_drop"] = W.pct_drop(r["compare_at"], r["price"])
        item.setdefault("stale_days", None)
        out.append(item)

    # Biggest real drop first, then biggest claimed, then by name so the
    # order is stable between runs when nothing has moved.
    out.sort(key=lambda x: (-(x["real_drop"] or 0),
                            -(x["claimed_drop"] or 0),
                            x["title"]))
    return out


def money(v):
    return "-" if v is None else f"Rs {v:,.0f}"


def print_report(items, errors, is_first_run, changes=()):
    print()
    print("=" * 100)
    print(f"  WATCHLIST     "
          f"{datetime.now().strftime('%a %d %b %Y, %H:%M')}")
    print("=" * 100)

    if is_first_run:
        print()
        print("  FIRST RUN - no price history yet, so the REAL column is")
        print("  empty. Run this again later and real drops appear.")

    if not items:
        print("\n  No items checked.\n")
    else:
        print(f"\n    {'REAL':>6}  {'CLAIM':>6}  {'NOW':>11}  "
              f"{'WAS':>11}  {'STORE':<18} ITEM")
        print("  " + "-" * 96)
        for i in items:
            real = f"{i['real_drop']:.0f}%" if i["real_drop"] else "-"
            claim = f"{i['claimed_drop']:.0f}%" if i["claimed_drop"] else "-"
            was = i["prev_price"] if i["real_drop"] else i["compare_at"]
            title = i["title"][:42]
            if not i["available"]:
                title += " [OUT OF STOCK]"
            if i.get("stale_days") is not None:
                title += f" (weekly, {i['stale_days']}d ago)"
            print(f"    {real:>6}  {claim:>6}  {money(i['price']):>11}  "
                  f"{money(was):>11}  {i['site']:<18} {title}")
            print(f"    {'':>6}  {'':>6}  {i['url']}")

    if changes:
        print()
        print("  " + "=" * 96)
        print("  DEAL PAGES")
        for line in render_page_changes(changes, markdown=False):
            print(line)

    if errors:
        print(f"\n  PROBLEMS ({len(errors)}):")
        for name, err in errors:
            print(f"    {name[:30]:32s} {err[:60]}")

    print(f"\n  Watching {len(items)} item(s) from {WATCHLIST_PATH.name}")
    print(f"  Database: {DB_PATH}")
    print("=" * 100 + "\n")


def write_markdown(items, errors, is_first_run, changes=()):
    """Write data/REPORT.md - this is what renders on GitHub/phone."""
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC")
    out = ["# Watchlist", "", f"_Last checked: {stamp}_", ""]

    if is_first_run:
        out += [
            "> **First run.** No price history yet, so the *Real* column",
            "> is empty. Real drops appear from the next run onward.", "",
        ]

    out += [
        "**Real** = how far the price actually fell since the last check.  ",
        "**Claim** = discount off the store's own crossed-out original.  ",
        "A big *Claim* with no *Real* movement usually means an inflated "
        "original price.", "",
    ]

    if not items:
        out += ["_No items checked._", ""]
    else:
        out += ["| Real | Claim | Now | Was | Store | Item |",
                "|---:|---:|---:|---:|---|---|"]
        for i in items:
            real = f"**{i['real_drop']:.0f}%**" if i["real_drop"] else "-"
            claim = f"{i['claimed_drop']:.0f}%" if i["claimed_drop"] else "-"
            was = i["prev_price"] if i["real_drop"] else i["compare_at"]
            title = i["title"].replace("|", "/")[:60]
            if not i["available"]:
                title += " - OUT OF STOCK"
            if i.get("stale_days") is not None:
                title += f" _(weekly - checked {i['stale_days']}d ago)_"
            out.append(
                f"| {real} | {claim} | {money(i['price'])} | {money(was)} "
                f"| {i['site']} | [{title}]({i['url']}) |"
            )
        out.append("")

    if changes:
        out += ["---", ""] + render_page_changes(changes, markdown=True)

    if errors:
        out += [f"## Problems ({len(errors)})", ""]
        out += [f"- `{n}` - {e[:80]}" for n, e in errors] + [""]

    out += ["---", "",
            f"Watching {len(items)} item(s). To add one, paste its product "
            "URL into `watchlist.txt`.", ""]

    MD_PATH.write_text("\n".join(out), encoding="utf-8")


def write_csv(items):
    import csv
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "title", "size", "in_stock", "price_now",
                    "previous_price", "real_drop_pct", "original_price",
                    "claimed_drop_pct", "url"])
        for i in items:
            w.writerow([i["site"], i["title"], i["size"],
                        "yes" if i["available"] else "no",
                        i["price"], i["prev_price"], i["real_drop"],
                        i["compare_at"], i["claimed_drop"], i["url"]])


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report-only", action="store_true",
                    help="reprint the last run without fetching")
    ap.add_argument("--quiet-ok", action="store_true",
                    help="exit 0 even when some items could not be checked")
    args = ap.parse_args()

    conn = connect()

    if args.report_only:
        last = conn.execute(
            "SELECT MAX(run_id) AS r FROM observations").fetchone()["r"]
        if last is None:
            print("No runs recorded yet. Run without --report-only first.")
            return 0
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM observations WHERE run_id = ?", (last,))]
        prev = previous_prices(conn, last)
        print_report(build_report(rows, prev), [], last == 1)
        return 0

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (started,))
    run_id = cur.lastrowid
    conn.commit()

    print(f"\nRun #{run_id} - checking watchlist\n")
    prev = previous_prices(conn, run_id)
    rows, carried, errors = collect(conn, run_id)
    changes, page_rows, page_errors = collect_pages(conn, run_id)
    errors = errors + page_errors

    conn.execute("UPDATE runs SET finished_at = ?, notes = ? WHERE id = ?",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  f"{len(rows)} items, {len(errors)} problems", run_id))
    conn.commit()

    items = build_report(rows + carried, prev)
    is_first = not prev
    print_report(items, errors, is_first, changes)

    # Always write, even when empty, so the committed report reflects
    # today rather than silently showing stale results.
    write_markdown(items, errors, is_first, changes)
    write_csv(items)
    print(f"  Report written to {MD_PATH}")
    print(f"  CSV written to {CSV_PATH}\n")

    # Nothing collected at all is a failure, not "no deals today".
    if not rows and not changes:
        print("ERROR: no items were checked.", file=sys.stderr)
        return 1
    if errors and not args.quiet_ok:
        print(f"WARNING: {len(errors)} item(s) could not be checked.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
