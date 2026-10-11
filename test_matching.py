"""Fixture tests for matching.py.

Size labels and product titles below are taken from the actual feeds of
the stores in the list, so these are the shapes the parser really has
to survive.
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


# ---- collar 17 -------------------------------------------------------
for v in ["17", '17"', "17 inch", "Collar 17", "43", "43 cm"]:
    check(f"is_collar_17({v!r})", m.is_collar_17(v), True)

for v in ["17.5", "16", "18", "", None, "XL", "170"]:
    check(f"is_collar_17({v!r})", m.is_collar_17(v), False)


# ---- belt waist 34 / 36 ---------------------------------------------
for v in ["34", "36", "34 inch", 'Waist 36"', "85 cm", "90 CM"]:
    check(f"is_belt_34_36({v!r})", m.is_belt_34_36(v), True)

for v in ["32", "38", "40", "34.5", "", None, "XL", "340"]:
    check(f"is_belt_34_36({v!r})", m.is_belt_34_36(v), False)


# ---- size extraction from the real option layouts --------------------
# brandstudio: Size is option1, Color is option2
p = {"options": [{"name": "Size", "position": 1},
                 {"name": "Color", "position": 2}]}
v = {"option1": "XL", "option2": "Black"}
check("size_from_variant brandstudio", m.size_from_variant(p, v), ["XL"])

# turbobrandsfactory: Color is option1, Size is option2 (reversed)
p = {"options": [{"name": "Color", "position": 1},
                 {"name": "Size", "position": 2}]}
v = {"option1": "Green", "option2": "XL"}
check("size_from_variant turbo", m.size_from_variant(p, v), ["XL"])

# weebyshoes: option named "Male Size"
p = {"options": [{"name": "Male Size", "position": 1}]}
v = {"option1": "45", "option2": None}
check("size_from_variant weeby", m.size_from_variant(p, v), ["45"])

# belts are often sized by an option named "Waist"
p = {"options": [{"name": "Waist", "position": 1}]}
v = {"option1": "36", "option2": None}
check("size_from_variant waist", m.size_from_variant(p, v), ["36"])

# formal shirts by "Collar"
p = {"options": [{"name": "Collar Size", "position": 1}]}
v = {"option1": "17", "option2": None}
check("size_from_variant collar", m.size_from_variant(p, v), ["17"])


# ---- product type detection ------------------------------------------
tee_polo = [
    {"title": "Premium T-Shirt", "product_type": "Men Tee", "tags": []},
    {"title": "LCST12 P/S PIQUE COTTON POLO SHIRT (BLACK)",
     "product_type": "", "tags": []},
    {"title": "par-ada gold lo-go", "product_type": "", "tags": ["Men Tee"]},
    {"title": "Cotton Tee", "product_type": "", "tags": []},
]
for s in tee_polo:
    check(f"is_tee_or_polo({s['title'][:20]!r})", m.is_tee_or_polo(s), True)

formal = [
    {"title": "Men Formal Shirt Blue", "product_type": "Shirt", "tags": []},
    {"title": "Classic Dress Shirt", "product_type": "", "tags": []},
]
for s in formal:
    check(f"is_formal_shirt({s['title'][:20]!r})", m.is_formal_shirt(s), True)
    check(f"not casual({s['title'][:20]!r})", m.is_casual_shirt(s), False)

casual = [
    {"title": "LP - Blue - Linen Classic Fit Casual Shirt",
     "product_type": "", "tags": []},
    {"title": "Men's Regular Fit Oxford Shirt", "product_type": "", "tags": []},
    {"title": "Checked Flannel", "product_type": "Shirts", "tags": []},
]
for s in casual:
    check(f"is_casual_shirt({s['title'][:20]!r})", m.is_casual_shirt(s), True)
    check(f"not formal({s['title'][:20]!r})", m.is_formal_shirt(s), False)

belts = [
    {"title": "Leather Reversible Belt", "product_type": "Belts", "tags": []},
    {"title": "Men's Belt Black", "product_type": "", "tags": []},
]
for s in belts:
    check(f"is_belt({s['title'][:20]!r})", m.is_belt(s), True)

not_belts = [
    {"title": "Belt Buckle Silver", "product_type": "", "tags": []},
    {"title": "Belt Bag Nylon", "product_type": "", "tags": []},
]
for s in not_belts:
    check(f"is_belt({s['title'][:20]!r})", m.is_belt(s), False)

shoes = [
    {"title": "Herm Like Mule - Blue", "product_type": "Shoes", "tags": []},
    {"title": "Frank - Men's Brown Calf Leather Wholecut",
     "product_type": "", "tags": []},
    {"title": "Adi Comfort Stripe Slide - White Duo",
     "product_type": "", "tags": []},
]
for s in shoes:
    check(f"is_shoe({s['title'][:20]!r})", m.is_shoe(s), True)


# ---- end-to-end classify --------------------------------------------
tee = {"title": "Premium T-Shirt", "product_type": "Men Tee", "tags": []}
check("tee XL", m.classify(tee, "XL"), "tee-polo")
check("tee XXL", m.classify(tee, "XXL"), None)
check("tee collar 17 ignored", m.classify(tee, "17"), None)

polo = {"title": "COTTON EAGLE CLASSIC POLO SHIRT (BEIGE)",
        "product_type": "", "tags": []}
check("polo XL", m.classify(polo, "XL"), "tee-polo")

fshirt = {"title": "Men Formal Shirt White", "product_type": "Shirt",
          "tags": []}
check("formal collar 17", m.classify(fshirt, "17"), "formal-shirt")
check("formal collar 43", m.classify(fshirt, "43"), "formal-shirt")
check("formal XL rejected", m.classify(fshirt, "XL"), None)
check("formal collar 17.5 rejected", m.classify(fshirt, "17.5"), None)

cshirt = {"title": "LP - Blue - Linen Classic Fit Casual Shirt",
          "product_type": "", "tags": []}
check("casual XL", m.classify(cshirt, "XL"), "casual-shirt")
check("casual collar 17", m.classify(cshirt, "17"), "casual-shirt")
check("casual L rejected", m.classify(cshirt, "L"), None)

belt = {"title": "Leather Reversible Belt", "product_type": "Belts",
        "tags": []}
check("belt 34", m.classify(belt, "34"), "belt")
check("belt 36", m.classify(belt, "36"), "belt")
check("belt 40 rejected", m.classify(belt, "40"), None)
check("belt 85cm", m.classify(belt, "85 cm"), "belt")

shoe = {"title": "Leather Derby", "product_type": "Shoes", "tags": []}
check("shoe 45", m.classify(shoe, "PK 11 | EU 45"), "shoe")
check("shoe 44 rejected", m.classify(shoe, "44"), None)

# A shoe sized 43 must NOT be read as a collar-17 shirt.
check("shoe 43 not collar", m.classify(shoe, "43"), None)

# Bare numeric size, no category hint -> treated as footwear.
vague = {"title": "Item 2201", "product_type": "", "tags": []}
check("vague 45", m.classify(vague, "45"), "shoe")

# Sweatshirts are still excluded entirely.
sweat = {"title": "RL12 Multi Polo Cotton Terry Sweatshirt Charcoal Grey",
         "product_type": "", "tags": []}
check("sweatshirt excluded", m.classify(sweat, "XL"), None)


# ---- pricing ---------------------------------------------------------
check("pct_drop 10000->7000", m.pct_drop(10000, 7000), 30.0)
check("pct_drop 6141->4299", m.pct_drop(6141, 4299), 30.0)
check("pct_drop rise", m.pct_drop(100, 150), None)
check("pct_drop same", m.pct_drop(100, 100), None)
check("pct_drop none", m.pct_drop(None, 100), None)
check("pct_drop zero compare_at", m.pct_drop(0.0, 2599.0), None)
check("to_float str", m.to_float("4,299.00"), 4299.0)
check("to_float none", m.to_float(None), None)


if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("all matching tests passed")
