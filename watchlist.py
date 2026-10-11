"""Parsing for the per-item watchlist.

A watchlist entry is a Shopify product URL, normally with the specific
variant pinned:

    https://www.brandstudio.pk/products/ami-ri-copy?variant=46794715758788

Without ?variant= we watch every variant of that product.

These are fetched one at a time from the storefront `.js` endpoint
(/products/<handle>.js), which returns a single small product including
per-variant `available`. That is one modest request per item, rather
than paging a whole catalogue, so a watchlist is far less likely to
trip a store's rate limiting.

Note: the `.js` endpoint returns prices in MINOR units (paisa), so
350000 means Rs 3,500. `to_rupees` handles that.
"""

import re
from urllib.parse import urlparse, parse_qs


class BadEntry(ValueError):
    """A watchlist line that could not be understood."""


def parse_watch_url(url):
    """Return (site, base, handle, variant_id) for a product URL.

    variant_id is None when the URL does not pin one.
    Raises BadEntry when the URL is not a Shopify product URL.
    """
    url = (url or "").strip()
    if not url:
        raise BadEntry("empty line")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise BadEntry(f"not an http(s) URL: {url}")

    match = re.search(r"/products/([^/?#]+)", parsed.path)
    if not match:
        raise BadEntry(f"no /products/<handle> in URL: {url}")

    handle = match.group(1)
    # Tolerate a pasted .json or .js suffix.
    handle = re.sub(r"\.(json|js)$", "", handle)
    if not handle:
        raise BadEntry(f"empty product handle: {url}")

    variant = None
    qs = parse_qs(parsed.query)
    if "variant" in qs and qs["variant"]:
        raw = qs["variant"][0].strip()
        if not raw.isdigit():
            raise BadEntry(f"variant is not numeric: {raw}")
        variant = raw

    base = f"{parsed.scheme}://{parsed.netloc}"
    site = parsed.netloc.lower()
    if site.startswith("www."):
        site = site[4:]
    site = site.split(":")[0]

    return site, base, handle, variant


def js_url(base, handle):
    """The storefront endpoint that returns one product with stock."""
    return f"{base.rstrip('/')}/products/{handle}.js"


def page_url(base, handle, variant=None):
    """The human-facing product URL, for the report link."""
    url = f"{base.rstrip('/')}/products/{handle}"
    return f"{url}?variant={variant}" if variant else url


def to_rupees(minor_units):
    """The .js endpoint gives paisa; convert to rupees. None-safe."""
    if minor_units in (None, ""):
        return None
    try:
        return round(float(minor_units) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def parse_file(text):
    """Parse watchlist file text.

    Blank lines and lines starting with # are skipped. A line may be
    just a URL, or "URL  # my note". Returns (entries, problems) so a
    single bad line never kills the whole run.
    """
    entries, problems = [], []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip a trailing comment, but not a # inside the URL fragment.
        url = line.split()[0]
        note = line[len(url):].strip().lstrip("#").strip() or None
        try:
            site, base, handle, variant = parse_watch_url(url)
        except BadEntry as exc:
            problems.append((lineno, str(exc)))
            continue
        entries.append({
            "site": site, "base": base, "handle": handle,
            "variant": variant, "note": note,
            "url": page_url(base, handle, variant),
        })
    return entries, problems


def pct_drop(old, new):
    """Percent drop from old to new. None when not computable or a rise."""
    if old is None or new is None or old <= 0:
        return None
    if new >= old:
        return None
    return round((old - new) / old * 100, 1)


def normalise(value):
    """Upper-case, collapse whitespace. None-safe."""
    import re as _re
    if value is None:
        return ""
    return _re.sub(r"\s+", " ", str(value)).strip().upper()
