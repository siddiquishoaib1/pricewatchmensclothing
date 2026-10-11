"""Tests for watchlist URL parsing and the always-show rule."""

import watchlist as W

fails = []


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, want {want!r}")


# ---- the three real URLs supplied ------------------------------------
site, base, handle, variant = W.parse_watch_url(
    "https://www.brandstudio.pk/products/loro-piana-w-copy"
    "?variant=46454953967812")
check("site", site, "brandstudio.pk")
check("base", base, "https://www.brandstudio.pk")
check("handle", handle, "loro-piana-w-copy")
check("variant", variant, "46454953967812")

check("js_url", W.js_url(base, handle),
      "https://www.brandstudio.pk/products/loro-piana-w-copy.js")
check("page_url", W.page_url(base, handle, variant),
      "https://www.brandstudio.pk/products/loro-piana-w-copy"
      "?variant=46454953967812")

# ---- variations ------------------------------------------------------
# No variant pinned -> watch all sizes.
_, _, h, v = W.parse_watch_url("https://shop.pk/products/thing")
check("no variant handle", h, "thing")
check("no variant id", v, None)

# Extra query params alongside variant.
_, _, _, v = W.parse_watch_url(
    "https://shop.pk/products/thing?pr_prod=1&variant=123&utm_source=x")
check("variant among params", v, "123")

# A pasted .js / .json suffix is tolerated.
for suffix in (".js", ".json"):
    _, _, h, _ = W.parse_watch_url(f"https://shop.pk/products/thing{suffix}")
    check(f"suffix {suffix}", h, "thing")

# www stripped, port stripped, case normalised.
s, _, _, _ = W.parse_watch_url("https://WWW.Shop.PK:443/products/thing")
check("site normalised", s, "shop.pk")

# Collection-scoped product URLs still resolve.
_, _, h, _ = W.parse_watch_url(
    "https://shop.pk/collections/sale/products/thing?variant=9")
check("collection-scoped handle", h, "thing")


# ---- bad input is rejected, not guessed ------------------------------
bad = [
    "", "   ",
    "not a url",
    "ftp://shop.pk/products/thing",
    "https://shop.pk/pages/about",            # not a product URL
    "https://shop.pk/products/thing?variant=abc",   # non-numeric
]
for b in bad:
    try:
        W.parse_watch_url(b)
        fails.append(f"bad input accepted: {b!r}")
    except W.BadEntry:
        pass


# ---- file parsing ----------------------------------------------------
text = """
# a comment
https://www.brandstudio.pk/products/a?variant=1   # my note

https://www.brandstudio.pk/products/b
garbage line here
https://shop.pk/products/c?variant=3
"""
entries, problems = W.parse_file(text)
check("entries parsed", [e["handle"] for e in entries], ["a", "b", "c"])
check("note captured", entries[0]["note"], "my note")
check("no note", entries[1]["note"], None)
check("one problem", len(problems), 1)
check("problem line number", problems[0][0], 6)


# ---- minor units -> rupees -------------------------------------------
check("to_rupees 350000", W.to_rupees(350000), 3500.0)
check("to_rupees 0", W.to_rupees(0), 0.0)
check("to_rupees none", W.to_rupees(None), None)
check("to_rupees junk", W.to_rupees("abc"), None)


# ---- every item is kept, nothing filtered ---------------------------
import watcher as WT

rows = [
    # No discount at all and out of stock: must STILL appear.
    {"category": "watchlist", "site": "brandstudio.pk", "variant_id": "1",
     "title": "Pinned thing", "price": 7000.0, "compare_at": None,
     "available": 0, "url": "u", "size": "XL"},
    {"category": "watchlist", "site": "shop.pk", "variant_id": "2",
     "title": "Another thing", "price": 1000.0, "compare_at": 2000.0,
     "available": 1, "url": "u", "size": ""},
]
items = WT.build_report(rows, {})
check("both kept", sorted(i["variant_id"] for i in items), ["1", "2"])

# An item that DID move reports its real drop, and sorts first.
moved = WT.build_report(rows, {("brandstudio.pk", "1"): (10000.0, "t1")})
check("real drop computed", moved[0]["real_drop"], 30.0)
check("real drop sorts first", moved[0]["variant_id"], "1")

# Claimed discount computed from compare_at.
check("claimed drop", 
      [i["claimed_drop"] for i in items if i["variant_id"] == "2"][0], 50.0)

# Out-of-stock flag survives into the report.
check("out of stock kept",
      [i["available"] for i in items if i["variant_id"] == "1"][0], 0)


if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("all watchlist tests passed")
