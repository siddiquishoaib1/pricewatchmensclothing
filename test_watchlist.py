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


# ---- page monitoring -------------------------------------------------
import tempfile, pathlib

html_day1 = """
<a href="/products/raze-black">Raze</a>
<a href="/products/raze-black?variant=1">dup</a>
<a href="/collections/sale/products/nero-black">Nero</a>
<a href="/products/all">nav noise</a>
<a href="/pages/about">not a product</a>
"""
check("handles day1", W.extract_product_handles(html_day1),
      ["raze-black", "nero-black"])
check("empty html", W.extract_product_handles(""), [])
check("none html", W.extract_product_handles(None), [])

# pages.txt parsing
e, p = W.parse_pages_file(
    "# c\nhttps://shop.pk/pages/deals  # my note\nnot-a-url\n")
check("pages parsed", len(e), 1)
check("pages site", e[0]["site"], "shop.pk")
check("pages note", e[0]["note"], "my note")
check("pages problem", len(p), 1)


# ---- page diff across two runs --------------------------------------
tmp2 = pathlib.Path(tempfile.mkdtemp())
WT.DB_PATH = tmp2 / "p.db"
WT.PAGES_PATH = tmp2 / "pages.txt"
WT.PAGES_PATH.write_text("https://shop.pk/pages/deals  # Deals\n")
WT.REQUEST_PAUSE = 0

PAGE = {"html": '<a href="/products/aaa">a</a><a href="/products/bbb">b</a>'}
WT.fetch_text = lambda url: PAGE["html"]
WT.fetch_json = lambda url: {
    "title": url.rsplit("/", 1)[-1].replace(".js", "").upper(),
    "variants": [{"id": 1, "title": "XL", "price": 100000,
                  "compare_at_price": 200000, "available": True}],
}

conn2 = WT.connect()
r1 = conn2.execute("INSERT INTO runs (started_at) VALUES ('t1')").lastrowid
ch1, rows1, err1 = WT.collect_pages(conn2, r1)
check("page run1 no errors", err1, [])
check("page run1 first_time", ch1[0]["first_time"], True)
check("page run1 total", ch1[0]["total"], 2)

# Day 2: bbb gone, ccc arrives.
PAGE["html"] = '<a href="/products/aaa">a</a><a href="/products/ccc">c</a>'
r2 = conn2.execute("INSERT INTO runs (started_at) VALUES ('t2')").lastrowid
ch2, rows2, err2 = WT.collect_pages(conn2, r2)
check("page run2 not first", ch2[0]["first_time"], False)
check("page run2 added", ch2[0]["added"], ["ccc"])
check("page run2 removed", ch2[0]["removed"], ["bbb"])
check("page run2 priced new", [r["handle"] for r in rows2], ["ccc"])
check("page run2 claimed", WT.build_report(rows2, {})[0]["claimed_drop"], 50.0)

# Day 3: unchanged.
r3 = conn2.execute("INSERT INTO runs (started_at) VALUES ('t3')").lastrowid
ch3, rows3, _ = WT.collect_pages(conn2, r3)
check("page run3 no change", (ch3[0]["added"], ch3[0]["removed"]), ([], []))
check("page run3 nothing priced", rows3, [])

# A page whose layout broke yields an error, not silence.
PAGE["html"] = "<html>nothing here</html>"
r4 = conn2.execute("INSERT INTO runs (started_at) VALUES ('t4')").lastrowid
ch4, _, err4 = WT.collect_pages(conn2, r4)
check("broken layout reported", len(err4), 1)
check("broken layout no changes", ch4, [])

# Rendering must not crash in either mode.
for md in (True, False):
    WT.render_page_changes(ch2, markdown=md)


# ---- cadence markers -------------------------------------------------
check("cadence weekly", W._cadence("thing @weekly"), ("weekly", "thing"))
check("cadence daily explicit", W._cadence("x @daily"), ("daily", "x"))
check("cadence default", W._cadence("plain note"), ("daily", "plain note"))
check("cadence none", W._cadence(None), ("daily", None))
check("cadence only marker", W._cadence("@weekly"), ("weekly", None))
check("cadence case", W._cadence("A @WEEKLY")[0], "weekly")
# A word merely containing "weekly" must not trigger it.
check("cadence no false match", W._cadence("biweekly thing")[0], "daily")


# ---- weekly items are skipped but still reported ---------------------
tmp3 = pathlib.Path(tempfile.mkdtemp())
WT.DB_PATH = tmp3 / "c.db"
WT.WATCHLIST_PATH = tmp3 / "w.txt"
WT.PAGES_PATH = tmp3 / "none.txt"
WT.WATCHLIST_PATH.write_text(
    "https://shop.pk/products/daily-thing?variant=1   # Daily\n"
    "https://shop.pk/products/weekly-thing?variant=2  # Weekly @weekly\n")
WT.REQUEST_PAUSE = 0

CALLS = []
def fake_js(url):
    CALLS.append(url)
    h = url.rsplit("/", 1)[-1].replace(".js", "")
    vid = 1 if h == "daily-thing" else 2
    return {"title": h, "variants": [
        {"id": vid, "title": "XL", "price": 100000,
         "compare_at_price": 200000, "available": True}]}
WT.fetch_json = fake_js

conn3 = WT.connect()
r1 = conn3.execute("INSERT INTO runs (started_at) VALUES ('t1')").lastrowid
rows, carried, errs = WT.collect(conn3, r1)
check("run1 both fetched", len(rows), 2)
check("run1 nothing carried", carried, [])
check("run1 no errors", errs, [])

# Second run the same day: the weekly item is not due.
CALLS.clear()
r2 = conn3.execute("INSERT INTO runs (started_at) VALUES ('t2')").lastrowid
rows2, carried2, _ = WT.collect(conn3, r2)
check("run2 only daily fetched", len(rows2), 1)
check("run2 daily is the one fetched", rows2[0]["handle"], "daily-thing")
check("run2 weekly carried", len(carried2), 1)
check("run2 carried handle", carried2[0]["handle"], "weekly-thing")
check("run2 weekly not refetched",
      any("weekly-thing" in u for u in CALLS), False)

# The carried item must still appear in the report, flagged.
items2 = WT.build_report(rows2 + carried2, {})
check("run2 both in report", len(items2), 2)
flagged = [i for i in items2 if i.get("stale_days") is not None]
check("run2 one flagged stale", len(flagged), 1)
check("run2 flagged is weekly", flagged[0]["handle"], "weekly-thing")

# Backdate the weekly item's last check to 8 days ago: now due again.
conn3.execute(
    "UPDATE observations SET seen_at = ? WHERE handle = 'weekly-thing'",
    ["2000-01-01T00:00:00+00:00"])
conn3.commit()
CALLS.clear()
r3 = conn3.execute("INSERT INTO runs (started_at) VALUES ('t3')").lastrowid
rows3, carried3, _ = WT.collect(conn3, r3)
check("run3 weekly due again", len(rows3), 2)
check("run3 nothing carried", carried3, [])
check("run3 weekly refetched",
      any("weekly-thing" in u for u in CALLS), True)
