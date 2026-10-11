"""Fixture tests for matching.py.

Size labels below are taken from the actual feeds of the stores in the
list, so these are the shapes the parser really has to survive.
"""

import matching as m

fails = []


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, want {want!r}")


# ---- XL must be XL, not XXL -----------------------------------------
for v in ["XL", "xl", " Xl ", "X-Large", "Extra Large", "XLARGE"]:
    check(f"is_xl({v!r})", m.is_xl(v), True)

for v in ["XXL", "2XL", "3XL", "XXXL", "L", "M", "Small", "Large", "", None,
          "2 XL", "Double XL"]:
    check(f"is_xl({v!r})", m.is_xl(v), False)


# ---- shoe size 45 in every label scheme seen -------------------------
for v in ["45", " 45 ", "EU 45", "45 EU", "PK 11 | EU 45", "Male Size 45",
          "EU-45"]:
    check(f"is_shoe_45({v!r})", m.is_shoe_45(v), True)

for v in ["44", "46", "45.5", "45,5", "145", "450", "4", "", None, "XL"]:
    check(f"is_shoe_45({v!r})", m.is_shoe_45(v), False)


# ---- size extraction from the real option layouts --------------------
# brandstudio: Size is option1, Color is option2
p = {"options": [{"name": "Size", "position": 1},
                 {"name": "Color", "position": 2}]}
v = {"option1": "XL", "option2": "Black"}
check("size_from_variant brandstudio", m.size_from_variant(p, v), ["XL"])

# turbobrandsfactory: Color is option1, Size is option2 (reversed!)
p = {"options": [{"name": "Color", "position": 1},
                 {"name": "Size", "position": 2}]}
v = {"option1": "Green", "option2": "XL"}
check("size_from_variant turbo", m.size_from_variant(p, v), ["XL"])

# weebyshoes: option named "Male Size"
p = {"options": [{"name": "Male Size", "position": 1}]}
v = {"option1": "45", "option2": None}
check("size_from_variant weeby", m.size_from_variant(p, v), ["45"])

# no option mentions size -> return all values for the caller to test
p = {"options": [{"name": "Title", "position": 1}]}
v = {"option1": "Default Title", "option2": None}
check("size_from_variant titleonly", m.size_from_variant(p, v),
      ["Default Title"])


# ---- shirt classification -------------------------------------------
shirts = [
    {"title": "Oxford Casual Shirt", "product_type": "Shirt", "tags": []},
    {"title": "Men Formal Shirt Blue", "product_type": "", "tags": ["MEN"]},
    {"title": "Denim Shirt", "product_type": "", "tags": []},
    {"title": "Checked Flannel", "product_type": "Shirts", "tags": []},
]
for s in shirts:
    check(f"is_shirt({s['title']!r})", m.is_shirt(s), True)

not_shirts = [
    {"title": "Premium T-Shirt", "product_type": "Men Tee", "tags": []},
    {"title": "par-ada gold lo-go", "product_type": "", "tags": ["Men Tee"]},
    {"title": "Polo Shirt Navy", "product_type": "Polo", "tags": []},
    {"title": "Sweatshirt Grey", "product_type": "", "tags": []},
    {"title": "Cotton Tee", "product_type": "", "tags": []},
    {"title": "Dry-fit Trouser", "product_type": "TURBO TROUSER", "tags": []},
    {"title": "Hoodie Black", "product_type": "", "tags": []},
]
for s in not_shirts:
    check(f"is_shirt({s['title']!r})", m.is_shirt(s), False)


# ---- shoe classification --------------------------------------------
shoes = [
    {"title": "Herm Like Mule - Blue", "product_type": "Shoes", "tags": []},
    {"title": "Frank - Men's Brown Calf Leather Wholecut",
     "product_type": "", "tags": []},
    {"title": "Air Max Sneakers", "product_type": "", "tags": []},
    {"title": "Chelsea Boot", "product_type": "Boots", "tags": []},
]
for s in shoes:
    check(f"is_shoe({s['title']!r})", m.is_shoe(s), True)


# ---- end-to-end classify --------------------------------------------
shirt_xl = {"title": "Casual Shirt", "product_type": "Shirt", "tags": []}
check("classify shirt XL", m.classify(shirt_xl, "XL"), "shirt")
check("classify shirt XXL", m.classify(shirt_xl, "XXL"), None)

tee_xl = {"title": "Premium T-Shirt", "product_type": "Men Tee", "tags": []}
check("classify tee XL", m.classify(tee_xl, "XL"), None)

shoe = {"title": "Leather Derby", "product_type": "Shoes", "tags": []}
check("classify shoe 45", m.classify(shoe, "PK 11 | EU 45"), "shoe")
check("classify shoe 44", m.classify(shoe, "44"), None)

# bare numeric size, no category hint -> treated as footwear
vague = {"title": "Item 2201", "product_type": "", "tags": []}
check("classify vague 45", m.classify(vague, "45"), "shoe")

# trouser with waist 45 should not be read as a shoe
trouser = {"title": "Cotton Shirt", "product_type": "Shirt", "tags": []}
check("classify shirt w/ 45", m.classify(trouser, "45"), None)


# ---- pricing ---------------------------------------------------------
check("pct_drop 10000->7000", m.pct_drop(10000, 7000), 30.0)
check("pct_drop 6141->4299", m.pct_drop(6141, 4299), 30.0)
check("pct_drop rise", m.pct_drop(100, 150), None)
check("pct_drop same", m.pct_drop(100, 100), None)
check("pct_drop none", m.pct_drop(None, 100), None)
check("to_float str", m.to_float("4,299.00"), 4299.0)
check("to_float none", m.to_float(None), None)


if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("all matching tests passed")
