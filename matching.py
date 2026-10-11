"""Size parsing and product classification.

Five categories, each with its own sizing rule:

    tee-polo       t-shirts and polo shirts        size XL
    casual-shirt   casual button-downs             size XL *or* collar 17
    formal-shirt   formal / dress shirts           collar 17
    belt           belts                           waist 34 or 36
    shoe           footwear                        size 45

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
    """True when the size means exactly XL, not XXL/2XL/etc."""
    s = normalise(size_value)
    if not s:
        return False
    if _NOT_XL.search(s):
        return False
    return s in _XL_FORMS


def _bare_number(size_value, number):
    """True when `number` appears as a standalone value, not part of a
    longer or decimal number. 45 matches "EU 45" but not 145 or 45.5."""
    s = normalise(size_value)
    if not s:
        return False
    if re.search(rf"\b{number}\s*[.,]\s*5\b", s):
        return False
    return re.search(rf"(?<!\d){number}(?!\s*[.,]?\s*\d)", s) is not None


def is_shoe_45(size_value):
    """EU/standard 45. Covers "45", "EU 45", "PK 11 | EU 45"."""
    return _bare_number(size_value, 45)


def is_collar_17(size_value):
    """Collar/neck 17 inches.

    Shirt makers label this as 17, 17", "17 inch", or the metric
    equivalent 43 (cm). 43 is only read as a collar by callers that have
    already established the product is a shirt - otherwise it would
    collide with shoe size 43.
    """
    s = normalise(size_value)
    if not s:
        return False
    if re.search(r"\b17\s*[.,]\s*5\b", s):     # 17.5 is a different collar
        return False
    return _bare_number(s, 17) or _bare_number(s, 43)


def is_belt_34_36(size_value):
    """Waist 34 or 36, in inches or their cm equivalents (85 / 90)."""
    s = normalise(size_value)
    if not s:
        return False
    if _bare_number(s, 34) or _bare_number(s, 36):
        return True
    # Metric belts: 85cm = 34in, 90cm = 36in.
    if re.search(r"\b(85|90)\s*(CM)\b", s):
        return True
    return False


_SIZE_OPTION = re.compile(r"SIZE|WAIST|COLLAR|NECK|LENGTH", re.I)


def size_from_variant(product, variant):
    """Pull the size value out of a variant.

    Shopify puts option values in option1/2/3 and names them in
    product["options"]. Store option names vary: "Size", "Male Size",
    "Shoe Size", "Waist", "Collar". We find the option whose name looks
    like a size; if none does, we return all option values so the
    caller can test each.
    """
    options = product.get("options") or []
    values = [variant.get("option1"), variant.get("option2"),
              variant.get("option3")]

    for opt in options:
        name = normalise(opt.get("name"))
        pos = opt.get("position")
        if _SIZE_OPTION.search(name) and isinstance(pos, int) and 1 <= pos <= 3:
            return [values[pos - 1]]

    return [v for v in values if v]


# ------------------------------------------------------- classification

_TEE_POLO = re.compile(
    r"(\bt[-\s]?shirts?\b|\btshirts?\b|\btee\b|\btees\b|\bpolo\b|"
    r"\bpolos\b)", re.I
)

_FORMAL = re.compile(
    r"(\bformal\b|\bdress\s?shirt\b|\bbusiness\s?shirt\b|\btuxedo\b|"
    r"\bdinner\s?shirt\b)", re.I
)

_SHIRT_WORDS = re.compile(r"\b(shirt|shirts|oxford|flannel|camisa)\b", re.I)

# Not a shirt of any kind, even though some contain the word.
_NOT_SHIRT = re.compile(
    r"(\bsweat[-\s]?shirts?\b|\bunder[-\s]?shirts?\b|\bnight[-\s]?shirts?\b|"
    r"\bshirt[-\s]?dress\b|\bhoodie\b|\bjersey\b|\btank\b)",
    re.I,
)

_BELT = re.compile(r"\b(belt|belts)\b", re.I)

# A belt buckle or a belt bag is not a belt.
_NOT_BELT = re.compile(r"\b(buckle|belt\s?bag|waist\s?bag|seat\s?belt)\b", re.I)

_SHOE_WORDS = re.compile(
    r"\b(shoe|shoes|sneaker|sneakers|trainer|trainers|loafer|loafers|"
    r"boot|boots|sandal|sandals|slipper|slippers|slide|slides|moccasin|"
    r"oxford|derby|brogue|wholecut|monk|chukka|espadrille|kicks|"
    r"footwear|peshawari|chappal|khussa)\b",
    re.I,
)


def _haystack(product):
    """Text to classify a product from: title, type and tags."""
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return " ".join([
        str(product.get("title") or ""),
        str(product.get("product_type") or ""),
        " ".join(str(t) for t in tags),
    ])


def is_tee_or_polo(product):
    text = _haystack(product)
    if _NOT_SHIRT.search(text):
        return False
    return _TEE_POLO.search(text) is not None


def is_formal_shirt(product):
    text = _haystack(product)
    if _NOT_SHIRT.search(text) or _TEE_POLO.search(text):
        return False
    if not _SHIRT_WORDS.search(text):
        return False
    return _FORMAL.search(text) is not None


def is_casual_shirt(product):
    """A shirt that is neither formal nor a tee/polo."""
    text = _haystack(product)
    if _NOT_SHIRT.search(text) or _TEE_POLO.search(text):
        return False
    if not _SHIRT_WORDS.search(text):
        return False
    return _FORMAL.search(text) is None


def is_belt(product):
    text = _haystack(product)
    if _NOT_BELT.search(text):
        return False
    return _BELT.search(text) is not None


def is_shoe(product):
    return _SHOE_WORDS.search(_haystack(product)) is not None


def classify(product, size_value):
    """Return the category for a product/size pair, or None.

    Order matters: belts and footwear are checked before shirts, since a
    product's text can mention more than one thing and the size is what
    disambiguates.
    """
    # Belts: waist 34 / 36
    if is_belt(product):
        return "belt" if is_belt_34_36(size_value) else None

    # Tees and polos: XL only
    if is_tee_or_polo(product):
        return "tee-polo" if is_xl(size_value) else None

    # Formal shirts: collar 17
    if is_formal_shirt(product):
        return "formal-shirt" if is_collar_17(size_value) else None

    # Casual shirts: XL or collar 17
    if is_casual_shirt(product):
        if is_xl(size_value) or is_collar_17(size_value):
            return "casual-shirt"
        return None

    # Footwear: 45
    if is_shoe_45(size_value):
        if is_shoe(product):
            return "shoe"
        # Bare numeric size in shoe range with no competing signal.
        if re.fullmatch(r"[^0-9]*4[0-9][^0-9]*", normalise(size_value)):
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
