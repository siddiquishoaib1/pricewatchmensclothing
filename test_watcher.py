"""End-to-end test of storage + drop detection using a fake feed.

Simulates two runs a day apart: on day two one shirt really drops and
one shoe's price is unchanged despite a big claimed discount. Verifies
the report tells those two apart - which is the whole point.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import watcher as W

# Point the module at a throwaway database.
tmp = Path(tempfile.mkdtemp())
W.DB_PATH = tmp / "test.db"
W.CSV_PATH = tmp / "test.csv"
W.REQUEST_PAUSE = 0

fails = []


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def make_feed(shirt_price):
    """One of each category, plus variants that must be excluded."""
    return [
        {
            "id": 1, "handle": "oxford-shirt", "title": "Oxford Casual Shirt",
            "product_type": "Shirt", "tags": ["MEN"],
            "options": [{"name": "Size", "position": 1},
                        {"name": "Color", "position": 2}],
            "variants": [
                {"id": 101, "option1": "L", "option2": "Blue",
                 "price": str(shirt_price), "compare_at_price": "5000.00",
                 "available": True},
                {"id": 102, "option1": "XL", "option2": "Blue",
                 "price": str(shirt_price), "compare_at_price": "5000.00",
                 "available": True},
            ],
        },
        {
            # Tees and polos ARE wanted now, at XL.
            "id": 2, "handle": "basic-tee", "title": "Premium T-Shirt",
            "product_type": "Men Tee", "tags": [],
            "options": [{"name": "Size", "position": 1}],
            "variants": [
                {"id": 201, "option1": "XL", "price": "1000.00",
                 "compare_at_price": "9000.00", "available": True},
                {"id": 202, "option1": "XXL", "price": "1000.00",
                 "compare_at_price": "9000.00", "available": True},
            ],
        },
        {
            "id": 3, "handle": "derby", "title": "Leather Derby Shoes",
            "product_type": "Shoes", "tags": [],
            "options": [{"name": "Male Size", "position": 1}],
            "variants": [
                {"id": 301, "option1": "44", "price": "8000.00",
                 "compare_at_price": "20000.00", "available": True},
                {"id": 302, "option1": "45", "price": "8000.00",
                 "compare_at_price": "20000.00", "available": True},
                {"id": 303, "option1": "45", "price": "7000.00",
                 "compare_at_price": None, "available": False},
            ],
        },
        {
            # Formal shirt goes by collar, not XL.
            "id": 4, "handle": "formal", "title": "Men Formal Shirt White",
            "product_type": "Shirt", "tags": [],
            "options": [{"name": "Collar", "position": 1}],
            "variants": [
                {"id": 401, "option1": "16", "price": "3000.00",
                 "compare_at_price": "6000.00", "available": True},
                {"id": 402, "option1": "17", "price": "3000.00",
                 "compare_at_price": "6000.00", "available": True},
            ],
        },
        {
            "id": 5, "handle": "belt", "title": "Leather Reversible Belt",
            "product_type": "Belts", "tags": [],
            "options": [{"name": "Waist", "position": 1}],
            "variants": [
                {"id": 501, "option1": "34", "price": "2000.00",
                 "compare_at_price": "5000.00", "available": True},
                {"id": 502, "option1": "40", "price": "2000.00",
                 "compare_at_price": "5000.00", "available": True},
            ],
        },
    ]


CURRENT = {"price": 5000}


def fake_iter(base_url):
    for p in make_feed(CURRENT["price"]):
        yield p


W.iter_products = fake_iter
W.SITES = [("teststore", "https://example.test")]

# ---- run 1: baseline, shirt at full price ---------------------------
conn = W.connect()
run1 = conn.execute(
    "INSERT INTO runs (started_at) VALUES ('t1')").lastrowid
prev1 = W.previous_prices(conn, run1)
rows1, errors1 = W.collect(conn, run1)

check("run1 errors", errors1, [])
# Wanted: casual shirt XL (102), tee XL (201), shoe 45 (302 + unavailable
# 303), formal collar 17 (402), belt waist 34 (501).
# Excluded: L shirt (101), XXL tee (202), shoe 44 (301), collar 16 (401),
# belt 40 (502).
ids1 = sorted(r["variant_id"] for r in rows1)
check("run1 variants captured", ids1,
      ["102", "201", "302", "303", "402", "501"])
check("run1 no baseline", prev1, {})

cats = {r["variant_id"]: r["category"] for r in rows1}
check("casual shirt category", cats["102"], "casual-shirt")
check("tee category", cats["201"], "tee-polo")
check("formal category", cats["402"], "formal-shirt")
check("belt category", cats["501"], "belt")
check("shoe category", cats["302"], "shoe")

items1 = W.build_report(rows1, prev1, min_drop=10.0)
# Unavailable 303 must be dropped from the report.
check("run1 report excludes unavailable",
      all(i["variant_id"] != "303" for i in items1), True)
# No history yet, so real drops are all None.
check("run1 no real drops",
      all(i["real_drop"] is None for i in items1), True)
# In run 1 the casual shirt sits at its full list price (5000 vs
# compare_at 5000), so it is correctly NOT a drop. The tee, shoe,
# formal shirt and belt all carry claimed discounts and should surface.
surfaced1 = sorted(i["variant_id"] for i in items1)
check("run1 surfaced", surfaced1, ["201", "302", "402", "501"])
check("run1 full-price shirt excluded",
      all(i["variant_id"] != "102" for i in items1), True)

# ---- run 2: shirt genuinely drops, shoe unchanged -------------------
CURRENT["price"] = 3500          # 30% real drop on the shirt
run2 = conn.execute(
    "INSERT INTO runs (started_at) VALUES ('t2')").lastrowid
prev2 = W.previous_prices(conn, run2)
check("run2 sees baseline", prev2[("teststore", "102")][0], 5000.0)

rows2, _ = W.collect(conn, run2)
items2 = W.build_report(rows2, prev2, min_drop=10.0)

by_id = {i["variant_id"]: i for i in items2}

check("shirt real drop detected", by_id["102"]["real_drop"], 30.0)
check("shirt previous price", by_id["102"]["prev_price"], 5000.0)
check("shirt claimed drop", by_id["102"]["claimed_drop"], 30.0)

# The shoe never moved, but claims 60% off - real must stay None.
check("shoe real drop is none", by_id["302"]["real_drop"], None)
check("shoe claimed drop", by_id["302"]["claimed_drop"], 60.0)

# Real drops must sort above claimed-only ones.
check("real drop ranked first", items2[0]["variant_id"], "102")

# ---- threshold ------------------------------------------------------
# At 70% only the tee (1000 from 9000 = 89% claimed) survives.
items_70 = W.build_report(rows2, prev2, min_drop=70.0)
check("70pc threshold keeps tee only",
      sorted(i["variant_id"] for i in items_70), ["201"])

# At 95% nothing qualifies.
items_95 = W.build_report(rows2, prev2, min_drop=95.0)
check("95pc threshold filters all", len(items_95), 0)

# ---- csv ------------------------------------------------------------
W.write_csv(items2)
csv_text = W.CSV_PATH.read_text(encoding="utf-8")
check("csv has header", csv_text.splitlines()[0].startswith("category,"), True)
check("csv has shirt row", "Oxford Casual Shirt" in csv_text, True)
check("csv has tee row", "Premium T-Shirt" in csv_text, True)
check("csv has belt row", "Leather Reversible Belt" in csv_text, True)

if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("all watcher tests passed")
