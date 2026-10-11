"""Store list for the price watcher.

Each entry is a Shopify storefront confirmed to expose /products.json.
`note` is shown in the report footer when a store fails.

Sites that could NOT be included, and why:
  hopkicks.pk                  - robots.txt disallows automated access
  accoutreclothing.com         - bot detection blocks non-browser requests
  ahmedfabricsinternational.com- robots.txt disallows automated access
  amoosajeesons.com            - robots.txt disallows automated access
  calabria.com.pk              - server error on /products.json
  brandedkicks.pk              - server error on /products.json
  aieopeson (AliExpress)       - marketplace seller, no storefront feed

Some of these may start working later; try moving them into SITES and
run with --probe to check.
"""

SITES = [
    # name,                    base url
    ("brandstudio",            "https://www.brandstudio.pk"),
    ("turbobrandsfactory",     "https://turbobrandsfactory.com"),
    ("boutiquederoyal",        "https://www.boutiquederoyal.com"),
    ("dealsexpress",           "https://dealsexpress.pk"),
    ("designdistrict",         "https://designdistrict.pk"),
    ("gomilaintersole",        "https://gomilaintersole.pk"),
    ("ismailfarid",            "https://ismailfarid.com"),
    ("silentluxury",           "https://silentluxury.com.pk"),
    ("weebyshoes",             "https://weebyshoes.com"),
    ("aspire",                 "https://aspire.pk"),
    ("alfatah",                "https://alfatah.pk"),
    ("saleemfabrics",          "https://saleemfabrics.pk"),
    ("leftoversden",           "https://leftoversden.com"),
    ("enemmall",               "https://enemmall.com"),
    ("justbrands",             "https://justbrands.com.pk"),
    ("casualcollection",       "https://casualcollection.com.pk"),
    ("amazonleftover",         "https://amazonleftover.com"),
]

# Stores that blocked automated access at the time of setup. Listed so the
# report can remind you they are not covered. Move one into SITES to retry.
BLOCKED = [
    ("hopkicks",               "https://hopkicks.pk",                 "robots.txt disallows"),
    ("accoutre",               "https://accoutreclothing.com",        "bot detection"),
    ("ahmedfabrics",           "https://ahmedfabricsinternational.com","robots.txt disallows"),
    ("amoosajeesons",          "https://amoosajeesons.com",           "robots.txt disallows"),
    ("calabria",               "https://calabria.com.pk",             "server error"),
    ("brandedkicks",           "https://brandedkicks.pk",             "server error"),
    ("aieopeson",              "aliexpress seller",                   "marketplace, no feed"),
]
