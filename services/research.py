import json, os, re
from collections import OrderedDict
from openai import OpenAI
from services.cj import search_products, product_detail, variants, storefront_url


def _client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _json(text):
    return json.loads(text.strip().replace("```json", "").replace("```", ""))


def research_trending_products(limit=20):
    # Validate requested number of products
    limit = max(1, min(int(limit), 100))

    # Return demo products if no OpenAI API key exists
    if not os.getenv("OPENAI_API_KEY"):
        return [
            {
                "name": f"Demo Product {i}",
                "reason": "Add OPENAI_API_KEY to enable live AI web research.",
                "trend_score": max(1, 101 - i),
                "supplier_search_query": "home gadget"
            }
            for i in range(1, limit + 1)
        ]

    # Research prompt
    prompt = f"""
    Research ecommerce products showing strong consumer buying
    and demand momentum during approximately the last 14-30 days.

    Return exactly {limit} physical, ad-friendly products,
    ranked from strongest to weakest based on available evidence.

    Avoid:
    - Regulated or unsafe products
    - Weapons
    - Alcohol and nicotine
    - Gambling products
    - Adult products
    - Prescription products and unsupported medical claims
    - Counterfeit products

    For every product, provide:
    1. name
    2. reason grounded in recent demand signals
    3. trend_score between 1 and 100
    4. supplier_search_query suitable for CJdropshipping

    Return JSON only in this structure:

    {{
        "products": [
            {{
                "name": "Product name",
                "reason": "Evidence supporting demand",
                "trend_score": 95,
                "supplier_search_query": "Supplier search terms"
            }}
        ]
    }}

    Do not invent exact sales figures or unsupported evidence.
    If recent evidence is insufficient, acknowledge uncertainty.
    """

    response = _client().responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        tools=[{"type": "web_search"}],
        input=prompt
    )

    products = _json(response.output_text)["products"]

    return products[:limit]


def _margin_price(cost):
    try:
        cost = float(str(cost).split("-")[0])
    except:
        cost = 10
    return round((cost * 3) + 16, 2)


_LABEL_ALIASES = {
    "colour": "Color",
    "color": "Color",
    "colors": "Color",
    "colours": "Color",
    "size": "Size",
    "sizes": "Size",
    "shoe size": "Size",
    "shoesize": "Size",
    "style": "Style",
    "styles": "Style",
    "type": "Style",
    "pattern": "Style",
    "model": "Model",
    "models": "Model",
    "model number": "Model",
    "material": "Material",
    "materials": "Material",
    "specification": "Specification",
    "spec": "Specification",
    "capacity": "Capacity",
    "volume": "Capacity",
    "length": "Length",
    "width": "Width",
    "pack": "Pack",
    "quantity": "Pack",
}


def _clean_label(label):
    label = re.sub(r"[_-]+", " ", str(label or "")).strip()
    return _LABEL_ALIASES.get(label.lower(), label.title() if label else "")


def _attributes_from_variant(v):
    """Normalize CJ's different variant payload shapes into friendly label/value pairs."""
    attrs = OrderedDict()
    # Newer CJ payloads can expose property/option arrays or dictionaries.
    for key in (
        "variantProperty",
        "variantProperties",
        "propertyList",
        "properties",
        "attributes",
        "options",
    ):
        raw = v.get(key)
        if isinstance(raw, dict):
            for k, val in raw.items():
                if val not in (None, ""):
                    attrs[_clean_label(k)] = str(val).strip()
        elif isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                label = (
                    item.get("propertyName")
                    or item.get("name")
                    or item.get("key")
                    or item.get("attributeName")
                    or item.get("variantName")
                )
                val = (
                    item.get("propertyValue")
                    or item.get("value")
                    or item.get("attributeValue")
                    or item.get("variantValue")
                )
                if label and val not in (None, ""):
                    attrs[_clean_label(label)] = str(val).strip()
    # Some CJ responses provide parallel property name/value strings.
    names = v.get("variantPropertyName") or v.get("propertyName")
    values = v.get("variantPropertyValue") or v.get("propertyValue")
    if isinstance(names, str) and isinstance(values, str):
        ns = [x.strip() for x in re.split(r"[,;/|]+", names) if x.strip()]
        vs = [x.strip() for x in re.split(r"[,;/|]+", values) if x.strip()]
        if len(ns) == len(vs):
            for k, val in zip(ns, vs):
                attrs[_clean_label(k)] = val
    return dict(attrs)


KNOWN_SIZES = (
    "XXXXXL", "XXXXL", "XXXL", "XXL",
    "2XL", "3XL", "4XL", "5XL", "6XL",
    "XXS", "XS", "XL", "S", "M", "L"
)


def _friendly_variant(v):
    attrs = _attributes_from_variant(v)

    raw = str(
        v.get("variantKey")
        or v.get("variantNameEn")
        or v.get("variantName")
        or v.get("variantSku")
        or "Default"
    ).strip()

    # Prefer explicit CJ attributes whenever available.
    if attrs:
        return attrs, " / ".join(str(x) for x in attrs.values())

    # Recognize a trailing size only when it is clearly
    # separated from the preceding color/style name.
    match = re.fullmatch(
        r"(.+?)[\s_-]+("
        + "|".join(KNOWN_SIZES)
        + r")",
        raw,
        flags=re.IGNORECASE
    )

    if match:
        color = match.group(1).strip()
        size = match.group(2).upper()

        if color:
            attrs = {
                "Color": color,
                "Size": size
            }
            return attrs, f"{color} / {size}"

    # Preserve unrecognized CJ names without guessing.
    if raw and raw.lower() != "default":
        attrs = {"Style": raw}

    return attrs, raw or "Default"



def _build_option_schema(normalized):
    schema = []
    labels = []
    for v in normalized:
        for label in v.get("attributes", {}):
            if label not in labels:
                labels.append(label)
    for label in labels:
        values = []
        for v in normalized:
            val = v.get("attributes", {}).get(label)
            if val and val not in values:
                values.append(val)
        if values:
            schema.append(
                {
                    "key": label.lower().replace(" ", "_"),
                    "label": label,
                    "values": values,
                }
            )
    return schema


def find_cj_candidates(candidate, limit=8):
    """Display real supplier products for explicit approval."""
    query = (
        candidate.get("supplier_search_query")
        or candidate.get("name")
    )

    if not query:
        raise ValueError("Missing supplier search query.")

    return [
        {
            "pid": str(p["id"]),
            "name": p.get("nameEn") or "",
            "image": p.get("bigImage") or "",
            "price": p.get("sellPrice")
        }
        for p in search_products(query, limit)
        if p.get("id")
    ]



def build_product(candidate):
    # A research suggestion is not supplier approval.
    # Require an exact CJ product ID.
    pid = str(
        candidate.get("approved_cj_pid") or ""
    ).strip()

    if not pid:
        raise ValueError(
            "Select and approve an exact CJ product "
            "before sourcing."
        )

    # Retrieve the actual selected CJ product.
    detail = product_detail(pid)

    if not isinstance(detail, dict):
        raise RuntimeError(
            "CJ did not return product details "
            "for the approved PID."
        )

    actual_pid = str(
        detail.get("pid")
        or detail.get("id")
        or ""
    ).strip()

    if actual_pid != pid:
        raise RuntimeError(
            "CJ returned a product different "
            "from the approved PID."
        )

    best = {
        **detail,
        "id": pid,
        "nameEn": (
            detail.get("productNameEn")
            or detail.get("nameEn")
            or ""
        ),
        "bigImage": (
            detail.get("bigImage")
            or detail.get("productImage")
            or ""
        ),
        "sellPrice": detail.get("sellPrice"),
        "sku": detail.get("productSku")
    }

    vs = variants(pid)

    if not isinstance(vs, list) or not vs:
        raise RuntimeError(
            "The approved CJ product has "
            "no orderable variants."
        )

    # Keep your existing code from:
    # normalized = []
    # through the end of build_product().

    normalized = []
    for v in vs:
        try:
            cost = float(v.get("variantSellPrice") or best.get("sellPrice") or 10)
        except:
            cost = 10.0
        attrs, name = _friendly_variant(v)
        normalized.append(
            {
                "vid": str(v.get("vid") or ""),
                "sku": v.get("variantSku"),
                "name": name,
                "attributes": attrs,
                "image": v.get("variantImage") or "",
                "supplier_cost": cost,
                "retail_price": _margin_price(cost),
            }
        )
    normalized = [v for v in normalized if v["vid"]]
    if not normalized:
        raise RuntimeError("CJ product variants did not include orderable variant IDs.")
    chosen = min(normalized, key=lambda v: v["supplier_cost"])
    cost = chosen["supplier_cost"]
    price = chosen["retail_price"]
    compare = round(price * 1.28 + 0.01, 2)
    raw_desc = re.sub(
        "<[^>]+>", " ", str(detail.get("description") or best.get("description") or "")
    )
    copy = {
        "tagline": "A smart everyday upgrade, selected for usefulness and value.",
        "description": raw_desc[:650] or best.get("nameEn", ""),
        "benefits": [
            "Practical design for everyday use",
            "Selected from an established fulfillment catalog",
            "Secure checkout with tracked order processing",
        ],
    }
    if os.getenv("OPENAI_API_KEY"):
        prompt = f"""Write elegant, factual conversion copy for this CJdropshipping product. Product: {best.get('nameEn')}. Supplier description: {raw_desc[:2500]}. Return JSON only with tagline (max 18 words), description (60-100 words), benefits (exactly 3 short strings). Do not invent reviews, certifications, scarcity, shipping times, guarantees, health claims, materials, or capabilities not present in the supplied facts."""
        r = _client().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"), input=prompt
        )
        copy.update(_json(r.output_text))
    images = detail.get("productImageSet") or []
    image = chosen.get("image") or detail.get("bigImage") or best.get("bigImage") or ""
    if image and image not in images:
        images = [image] + images
    return {
        "name": best.get("nameEn") or candidate["name"],
        "tagline": copy["tagline"],
        "description": copy["description"],
        "price": price,
        "compare_at": compare,
        "currency": "usd",
        "image": image,
        "images": images[:6],
        "benefits": copy["benefits"],
        "supplier": "CJdropshipping",
        "supplier_url": storefront_url(pid),
        "supplier_cost": cost,
        "cj_pid": pid,
        "cj_sku": best.get("sku") or detail.get("productSku"),
        "cj_vid": chosen["vid"],
        "cj_variant_name": chosen["name"],
        "variants": normalized,
        "variant_options": _build_option_schema(normalized),
        "cj_listed_num": best.get("listedNum", 0),
        "source_note": "Product data, customer-selectable variant attributes and fulfillment identifiers imported from CJdropshipping API. Retail copy is affiliate-approved.",
    }
