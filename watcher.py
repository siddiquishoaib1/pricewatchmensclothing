#!/usr/bin/env python3
"""Men's shirt (XL) and shoe (45) price-drop watcher for PK stores.

Pulls every page of each store's Shopify /products.json feed, keeps a
price history in SQLite, and reports the steepest drops two ways:

  REAL    - how far the price fell since the last time this script ran
  CLAIMED - discount off the store's own crossed-out original price

The real column is the honest one. The claimed column is there so you
can spot the stores inflating their "original" price - if an item shows
a 60% claimed discount but has never actually moved, that is marketing.

Usage:
    python watcher.py                 # fetch, store, report
    python watcher.py --report-only   # re-print last report, no fetching
    python watcher.py --probe         # just check which stores respond
    python watcher.py --min-drop 15   # only show real drops over 15%

Standard library only - nothing to install.
"""

import argparse
import json
import re
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import matching as M
from sites import SITES, BLOCKED

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DB_PATH = DATA_DIR / "prices.db"
CSV_PATH = DATA_DIR / "latest_report.csv"
MD_PATH = DATA_DIR / "REPORT.md"

PAGE_SIZE = 250
MAX_PAGES = 40           # safety stop: 10k products per store
REQUEST_PAUSE = 1.0      # be polite to small shops
TIMEOUT = 30
RETRIES = 3

UA = ("Mozilla/5.0 (compatible; personal-price-watcher/1.0; "
      "single user, 1 req/sec)")


# ----------------------------------------------------------- fetching

def fetch_json(url):
    """GET a URL and parse JSON. Raises on failure after retries."""
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
        except Exception as exc:          # noqa: BLE001 - report any failure
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def iter_products(base_url):
    """Yield every product dict from a store, paging until exhausted."""
    seen_ids = set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{base_url.rstrip('/')}/products.json?limit={PAGE_SIZE}&page={page}"
        data = fetch_json(url)
        products = data.get("products") or []
        if not products:
            return
        new = 0
        for p in products:
            pid = p.get("id")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            new += 1
            yield p
        # Some stores ignore ?page= and keep serving page 1.
        if new == 0:
            return
        if len(products) < PAGE_SIZE:
            return
        time.sleep(REQUEST_PAUSE)


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


# ------------------------------------------------------------ collect

def collect(conn, run_id, only_probe=False):
    """Walk every store, store matching variants, return (rows, errors)."""
    rows, errors = [], []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for name, base in SITES:
        count = 0
        try:
            for product in iter_products(base):
                if only_probe:
                    count += 1
                    break
                handle = product.get("handle") or ""
                url = f"{base.rstrip('/')}/products/{handle}"
                for variant in product.get("variants") or []:
                    for size in M.size_from_variant(product, variant):
                        category = M.classify(product, size)
                        if not category:
                            continue
                        price = M.to_float(variant.get("price"))
                        compare = M.to_float(variant.get("compare_at_price"))
                        rec = {
                            "run_id": run_id,
                            "site": name,
                            "variant_id": str(variant.get("id")),
                            "handle": handle,
                            "title": product.get("title") or "",
                            "category": category,
                            "size": M.normalise(size),
                            "price": price,
                            "compare_at": compare,
                            "available": 1 if variant.get("available") else 0,
                            "url": url,
                            "seen_at": now,
                        }
                        rows.append(rec)
                        count += 1
                        break   # one size value per variant is enough
        except Exception as exc:          # noqa: BLE001
            errors.append((name, str(exc)))
            print(f"  {name:22s} FAILED  {exc}", file=sys.stderr)
            continue

        label = "responded" if only_probe else f"{count} matching variants"
        print(f"  {name:22s} {label}")
        time.sleep(REQUEST_PAUSE)

    if not only_probe and rows:
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
    return rows, errors


# ------------------------------------------------------------- report

def build_report(rows, prev, min_drop):
    """Attach real/claimed drops to rows and sort by severity."""
    out = []
    for r in rows:
        if not r["available"]:
            continue
        old_price, old_seen = prev.get((r["site"], r["variant_id"]),
                                       (None, None))
        real = M.pct_drop(old_price, r["price"])
        claimed = M.pct_drop(r["compare_at"], r["price"])
        if real is None and claimed is None:
            continue
        if min_drop and (real or 0) < min_drop and (claimed or 0) < min_drop:
            continue
        item = dict(r)
        item["real_drop"] = real
        item["prev_price"] = old_price
        item["prev_seen"] = old_seen
        item["claimed_drop"] = claimed
        out.append(item)

    # Real drops first and largest-first; then claimed-only, largest-first.
    out.sort(key=lambda x: (x["real_drop"] is None,
                            -(x["real_drop"] or 0),
                            -(x["claimed_drop"] or 0)))
    return out


def money(v):
    return "-" if v is None else f"Rs {v:,.0f}"


def print_report(items, errors, is_first_run, min_drop):
    print()
    print("=" * 100)
    print(f"  PRICE DROPS - shirts XL / shoes 45     "
          f"{datetime.now().strftime('%a %d %b %Y, %H:%M')}")
    print("=" * 100)

    if is_first_run:
        print()
        print("  FIRST RUN - no price history yet, so the REAL column is")
        print("  empty. Everything below is the store's own claimed")
        print("  discount. Run this again tomorrow and real drops appear.")

    if not items:
        print("\n  Nothing met the threshold this run.\n")
    else:
        for group, label in (("shirt", "SHIRTS - size XL"),
                             ("shoe", "SHOES - size 45")):
            chunk = [i for i in items if i["category"] == group]
            print(f"\n  {label}  ({len(chunk)})")
            print("  " + "-" * 96)
            if not chunk:
                print("    nothing found")
                continue
            print(f"    {'REAL':>6}  {'CLAIM':>6}  {'NOW':>11}  "
                  f"{'WAS':>11}  {'STORE':<18} ITEM")
            for i in chunk[:40]:
                real = f"{i['real_drop']:.0f}%" if i["real_drop"] else "-"
                claim = f"{i['claimed_drop']:.0f}%" if i["claimed_drop"] else "-"
                was = i["prev_price"] if i["real_drop"] else i["compare_at"]
                title = i["title"][:42]
                print(f"    {real:>6}  {claim:>6}  {money(i['price']):>11}  "
                      f"{money(was):>11}  {i['site']:<18} {title}")
                print(f"    {'':>6}  {'':>6}  {i['url']}")

    if errors:
        print(f"\n  STORES THAT FAILED THIS RUN ({len(errors)}):")
        for name, err in errors:
            print(f"    {name:22s} {err[:70]}")

    print(f"\n  Not covered (blocked or no feed): "
          f"{', '.join(n for n, _, _ in BLOCKED)}")
    print(f"  Threshold: real or claimed drop >= {min_drop}%")
    print(f"  Database: {DB_PATH}")
    print("=" * 100 + "\n")


def write_markdown(items, errors, is_first_run, min_drop):
    """Write data/REPORT.md - this is what renders on GitHub/phone."""
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC")
    out = [f"# Price drops - shirts XL / shoes 45", "",
           f"_Last checked: {stamp}_", ""]

    if is_first_run:
        out += [
            "> **First run.** No price history yet, so the *Real* column",
            "> is empty. Everything below is the store's own claimed",
            "> discount. Real drops appear from the next run onward.", "",
        ]

    out += [
        "**Real** = how far the price actually fell since the last check.  ",
        "**Claim** = discount off the store's own crossed-out original.  ",
        "A big *Claim* with no *Real* movement usually means an inflated "
        "original price.", "",
    ]

    for group, label in (("shirt", "Shirts - size XL"),
                         ("shoe", "Shoes - size 45")):
        chunk = [i for i in items if i["category"] == group]
        out += [f"## {label} ({len(chunk)})", ""]
        if not chunk:
            out += ["_Nothing met the threshold this run._", ""]
            continue
        out += ["| Real | Claim | Now | Was | Store | Item |",
                "|---:|---:|---:|---:|---|---|"]
        for i in chunk[:40]:
            real = f"**{i['real_drop']:.0f}%**" if i["real_drop"] else "-"
            claim = f"{i['claimed_drop']:.0f}%" if i["claimed_drop"] else "-"
            was = i["prev_price"] if i["real_drop"] else i["compare_at"]
            title = i["title"].replace("|", "/")[:60]
            out.append(
                f"| {real} | {claim} | {money(i['price'])} | {money(was)} "
                f"| {i['site']} | [{title}]({i['url']}) |"
            )
        out.append("")

    if errors:
        out += [f"## Stores that failed this run ({len(errors)})", ""]
        out += [f"- `{n}` - {e[:80]}" for n, e in errors] + [""]

    out += ["---", "",
            f"Threshold: real or claimed drop >= {min_drop:.0f}%.  ",
            "Not covered (blocked or no feed): "
            + ", ".join(f"`{n}`" for n, _, _ in BLOCKED) + ".", ""]

    MD_PATH.write_text("\n".join(out), encoding="utf-8")


def write_csv(items):
    import csv
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "site", "title", "size", "price_now",
                    "previous_price", "real_drop_pct", "original_price",
                    "claimed_drop_pct", "url"])
        for i in items:
            w.writerow([i["category"], i["site"], i["title"], i["size"],
                        i["price"], i["prev_price"], i["real_drop"],
                        i["compare_at"], i["claimed_drop"], i["url"]])


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="only check which stores respond")
    ap.add_argument("--report-only", action="store_true",
                    help="reprint the last run without fetching")
    ap.add_argument("--min-drop", type=float, default=10.0,
                    help="hide drops smaller than this percent (default 10)")
    args = ap.parse_args()

    conn = connect()

    if args.probe:
        print("\nProbing stores...\n")
        collect(conn, 0, only_probe=True)
        print()
        return

    if args.report_only:
        last = conn.execute(
            "SELECT MAX(run_id) AS r FROM observations").fetchone()["r"]
        if last is None:
            print("No runs recorded yet. Run without --report-only first.")
            return
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM observations WHERE run_id = ?", (last,))]
        prev = previous_prices(conn, last)
        items = build_report(rows, prev, args.min_drop)
        print_report(items, [], last == 1, args.min_drop)
        return

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (started,))
    run_id = cur.lastrowid
    conn.commit()

    print(f"\nRun #{run_id} - checking {len(SITES)} stores\n")
    prev = previous_prices(conn, run_id)
    rows, errors = collect(conn, run_id)

    conn.execute("UPDATE runs SET finished_at = ?, notes = ? WHERE id = ?",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  f"{len(rows)} variants, {len(errors)} store errors",
                  run_id))
    conn.commit()

    items = build_report(rows, prev, args.min_drop)
    is_first = not prev
    print_report(items, errors, is_first, args.min_drop)

    # Always write both, even when empty, so the committed report in the
    # repo reflects today rather than silently showing stale results.
    write_markdown(items, errors, is_first, args.min_drop)
    write_csv(items)
    print(f"  Report written to {MD_PATH}")
    print(f"  CSV written to {CSV_PATH}\n")


if __name__ == "__main__":
    main()
