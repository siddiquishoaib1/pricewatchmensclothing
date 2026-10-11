"""Size parsing and product classification.

Kept separate from the network/storage code so it can be tested against
fixtures without hitting the network.
"""

import re

# ---------------------------------------------------------------- sizes

# Words that mean "XL" exactly. Deliberately excludes XXL/2XL/3XL.
_XL_FORMS = {
    "XL", "X-LARGE", "XLARGE", "X LARGE",
    "EXTRA LARGE", "EXTRA-LARGE", "EXTRALARGE",
}

# Things that look like XL but are bigger sizes.
_NOT_XL = re.compile(r"(X{2,}L|[2-9]\s*X\s*L|XX|DOUBLE|TRIPLE)", re.I)


def normalise(value):
    """Upper-case, collapse whitespace. None-safe."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().upper()


def is_xl(size_value):
    """True when the size means exactly XL, not XXL/2XL/etc.

    Handles the compound labels these stores use, e.g. "XL / Black" is
    not passed here (we read the size option specifically), but
    "X-Large" and "Extra Large" are.
    """
    s = normalise(size_value)
    if not s:
        return False
    if _NOT_XL.search(s):
        return False
    return s in _XL_FORMS


def is_shoe_45(size_value):
    """True when the size denotes EU/standard 45.

    Covers the schemes seen in the wild:
        "45", "45 EU", "EU 45", "PK 11 | EU 45", "Male Size 45"
    Rejects 45.5 and anything where 45 is part of a longer number.
    """
    s = normalise(size_value)
    if not s:
        return False
    # Reject decimal half sizes like 45.5
    if re.search(r"\b45\s*[.,]\s*5\b", s):
        return False
    return re.search(r"(?<!\d)45(?!\s*[.,]?\s*\d)", s) is not None


def size_from_variant(product, variant):
    """Pull the size value out of a variant.

    Shopify puts option values in option1/2/3 and names them in
    product["options"]. Store option names vary a lot: "Size",
    "Male Size", "Shoe Size", "PK Size", "Size (EU)". We find the
    option whose name mentions size; if none does, we return all option
    values so the caller can test each.
    """
    options = product.get("options") or []
    values = [variant.get("option1"), variant.get("option2"), variant.get("option3")]

    for opt in options:
        name = normalise(opt.get("name"))
        pos = opt.get("position")
        if "SIZE" in name and isinstance(pos, int) and 1 <= pos <= 3:
            return [values[pos - 1]]

    # No option is named "size" - hand back everything non-empty.
    return [v for v in values if v]


# ------------------------------------------------------- classification

_SHIRT_WORDS = re.compile(
    r"\b(shirt|shirts|oxford|flannel|camisa|kameez)\b", re.I
)

# Anything matching these is NOT a plain shirt, even though the word
# "shirt" appears inside some of them (t-shirt, sweatshirt, undershirt).
_SHIRT_EXCLUDE = re.compile(
    # NOTE: the \b before t-shirt matters. Without it, a product titled
    # "Casual Shirt" with product_type "Shirt" yields the haystack
    # "Casual Shirt Shirt", and "t Shirt" spanning that word boundary
    # matched - throwing away real shirts.
    r"(\bt[-\s]?shirts?\b|\btshirts?\b|\btee\b|\btees\b|\bpolo\b|"
    r"\bsweat[-\s]?shirts?\b|\bunder[-\s]?shirts?\b|\bnight[-\s]?shirts?\b|"
    r"\bshirt[-\s]?dress\b|\bhoodie\b|\bjersey\b|\bvest\b|\btank\b)",
    re.I,
)

_SHOE_WORDS = re.compile(
    r"\b(shoe|shoes|sneaker|sneakers|trainer|trainers|loafer|loafers|"
    r"boot|boots|sandal|sandals|slipper|slippers|moccasin|oxford|derby|"
    r"brogue|wholecut|monk|chukka|espadrille|kicks|footwear|peshawari|"
    r"chappal|khussa)\b",
    re.I,
)


def _haystack(product):
    """Text to classify a product from: title, type and tags."""
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("product_type") or ""),
            " ".join(str(t) for t in tags),
        ]
    )


def is_shirt(product):
    """A shirt proper - not a t-shirt, polo, sweatshirt or hoodie."""
    text = _haystack(product)
    if _SHIRT_EXCLUDE.search(text):
        return False
    return _SHIRT_WORDS.search(text) is not None


def is_shoe(product):
    text = _haystack(product)
    return _SHOE_WORDS.search(text) is not None


def classify(product, size_value):
    """Return 'shirt', 'shoe' or None for a product/size pair.

    A size-45 variant is treated as footwear when the product text says
    so, or when nothing contradicts it and the size is a bare number in
    the shoe range - some stores give shoes no useful product_type.
    """
    if is_xl(size_value) and is_shirt(product):
        return "shirt"

    if is_shoe_45(size_value):
        if is_shoe(product):
            return "shoe"
        # Bare numeric size in shoe range, no competing category signal.
        if not is_shirt(product) and re.fullmatch(
            r"[^0-9]*4[0-9][^0-9]*", normalise(size_value)
        ):
            return "shoe"
    return None


# ------------------------------------------------------------- pricing

def to_float(value):
    """Shopify sends prices as strings. None/'' -> None."""
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def pct_drop(old, new):
    """Percent drop from old to new. None when not computable or a rise."""
    if old is None or new is None or old <= 0:
        return None
    if new >= old:
        return None
    return round((old - new) / old * 100, 1)
