"""BuyAnything.sale Google SEO add-on.

Drop-in module: it does not replace existing storefront, marketer, Stripe, CJ,
MongoDB, CSS, or template files. Register it with init_seo(app).
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
from urllib.parse import urljoin

from flask import Blueprint, Response, current_app, redirect, render_template, request

SEO = Blueprint("buyanything_seo", __name__)

DEFAULT_BASE_URL = "https://www.buyanything.sale"
DEFAULT_EMAIL = "contact@buyanything.sale"

# Pages that should not compete in Google Search.
NOINDEX_EXACT = {
    "/affiliate/login",
    "/affiliate/signup",
    "/purchase",
    "/success",
    "/health",
}
NOINDEX_PREFIXES = (
    "/admin",
    "/stripe",
    "/create-checkout-session",
    "/s/",  # marketer storefronts: prevent duplicate SEO pages competing with the main site
)

# Pages that should never be listed in the XML sitemap.
SITEMAP_EXCLUDE_EXACT = NOINDEX_EXACT | {"/robots.txt", "/sitemap.xml"}
SITEMAP_EXCLUDE_PREFIXES = NOINDEX_PREFIXES + ("/static/",)

PAGE_META = {
    "/": {
        "title": "BuyAnything | Product Research, Sourcing & Earning Storefronts",
        "description": (
            "BuyAnything helps marketers research high-demand products, source through suppliers, "
            "launch a focused product storefront, and sell online with automated fulfillment plus high Earnings"
        ),
    },
    "/marketers": {
        "title": "Sell Products Online With Your Own Storefront | BuyAnything ",
        "description": (
            "Join BuyAnything as a marketer, research products, choose what to sell, get a storefront in seconds, "
            "and promote products without managing sourcing or fulfillment yourself."
        ),
    },
    "/how-it-works": {
        "title": "How BuyAnything Works | Research, Source, Sell & Earn",
        "description": (
            "See how BuyAnything connects product research, supplier sourcing, storefront creation, "
            "secure checkout, and automated fulfillment in one selling workflow for you to Earn high!"
        ),
    },
    "/sell-products-online": {
        "title": "How to Sell Products Online Without Holding Inventory | BuyAnything",
        "description": (
            "Learn a practical workflow for choosing products, Having an online storefront, marketing "
            "to buyers, automated processing orders, and using our supplier fulfillment automation"
        ),
    },
    "/product-research": {
        "title": "How to Research High-Demand Products to Sell | BuyAnything",
        "description": (
            "Learn how to evaluate product demand, buyer intent, competition, ad suitability, margins, "
            "supplier availability, and fulfillment before choosing what to sell."
        ),
    },
    "/policies": {
        "title": "Shipping, Returns & Store Policies | BuyAnything",
        "description": "Read BuyAnything shipping, delivery, returns, refunds, and store policy information.",
    },
    "/affiliate/terms": {
        "title": "Marketer Terms | BuyAnything",
        "description": "Read the terms that apply to marketers using BuyAnything storefronts and sales tools.",
    },
}


def _base_url() -> str:
    value = (
        os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL") or DEFAULT_BASE_URL
    ).strip()
    return value.rstrip("/")


def _absolute_url(path: str) -> str:
    base = _base_url() + "/"
    return urljoin(base, path.lstrip("/"))


def _is_noindex(path: str) -> bool:
    if path in NOINDEX_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in NOINDEX_PREFIXES)


def _sitemap_allowed(path: str) -> bool:
    if path in SITEMAP_EXCLUDE_EXACT:
        return False
    if any(path.startswith(prefix) for prefix in SITEMAP_EXCLUDE_PREFIXES):
        return False
    return True


def _strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _extract_first(pattern: str, body: str) -> str | None:
    match = re.search(pattern, body, flags=re.I | re.S)
    return match.group(1).strip() if match else None


def _extract_product(body: str) -> dict | None:
    """Best-effort extraction from server-rendered product HTML.

    This keeps the add-on decoupled from whichever product/Mongo/CJ implementation
    the current BuyAnything v2 app is using.
    """
    h1 = _extract_first(r"<h1\b[^>]*>(.*?)</h1>", body)
    if not h1:
        return None
    name = _strip_tags(h1)
    if not name:
        return None

    description_html = _extract_first(
        r'<p\b[^>]*class=["\'][^"\']*(?:description|lead)[^"\']*["\'][^>]*>(.*?)</p>',
        body,
    )
    description = _strip_tags(description_html or "")

    image = _extract_first(r'<img\b[^>]*src=["\']([^"\']+)["\']', body)
    if image:
        image = urljoin(request.url_root, html_lib.unescape(image))

    # Prefer a price near a class named price; fall back to the first dollar price.
    price_block = _extract_first(
        r'<(?:div|span|p)\b[^>]*class=["\'][^"\']*price[^"\']*["\'][^>]*>(.*?)</(?:div|span|p)>',
        body,
    )
    price_source = _strip_tags(price_block or body)
    price_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", price_source)
    price = price_match.group(1) if price_match else None

    if not image or not price:
        return None

    return {
        "name": name,
        "description": description or f"{name} available from BuyAnything.",
        "image": image,
        "price": price,
    }


def _meta_for(path: str, body: str) -> tuple[str, str]:
    if path == "/product":
        product = _extract_product(body)
        if product:
            return (
                f"{product['name']} | BuyAnything",
                (
                    product["description"][:155]
                    if product.get("description")
                    else f"Shop {product['name']} securely on BuyAnything."
                ),
            )
    meta = PAGE_META.get(path)
    if meta:
        return meta["title"], meta["description"]

    # Sensible fallback for other public pages.
    current_title = _extract_first(r"<title\b[^>]*>(.*?)</title>", body)
    title = _strip_tags(current_title or "BuyAnything")
    return (
        title,
        "BuyAnything — Earnings, product research, sourcing, storefronts, secure checkout, and supplier fulfillment.",
    )


def _remove_existing_seo_tags(body: str) -> str:
    patterns = [
        r'<meta\b[^>]*(?:name|property)=["\'](?:description|robots|og:title|og:description|og:url|og:type|twitter:card|twitter:title|twitter:description)["\'][^>]*>\s*',
        r'<link\b[^>]*rel=["\']canonical["\'][^>]*>\s*',
        r'<meta\b[^>]*name=["\']google-site-verification["\'][^>]*>\s*',
    ]
    for pattern in patterns:
        body = re.sub(pattern, "", body, flags=re.I | re.S)
    return body


def _replace_title(body: str, title: str) -> str:
    safe_title = html_lib.escape(title, quote=False)
    if re.search(r"<title\b[^>]*>.*?</title>", body, flags=re.I | re.S):
        return re.sub(
            r"<title\b[^>]*>.*?</title>",
            f"<title>{safe_title}</title>",
            body,
            count=1,
            flags=re.I | re.S,
        )
    return body


def _schema_markup(path: str, canonical: str, body: str) -> list[dict]:
    schemas: list[dict] = []

    if path == "/":
        schemas.extend(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "@id": _base_url() + "/#organization",
                    "name": "BuyAnything",
                    "url": _base_url() + "/",
                    "email": os.getenv("SEO_CONTACT_EMAIL", DEFAULT_EMAIL),
                },
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "@id": _base_url() + "/#website",
                    "url": _base_url() + "/",
                    "name": "BuyAnything",
                    "publisher": {"@id": _base_url() + "/#organization"},
                },
            ]
        )

    if path == "/product":
        product = _extract_product(body)
        if product:
            schemas.append(
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": product["name"],
                    "image": [product["image"]],
                    "description": product["description"],
                    "offers": {
                        "@type": "Offer",
                        "url": canonical,
                        "priceCurrency": "USD",
                        "price": product["price"],
                        "availability": "https://schema.org/InStock",
                        "itemCondition": "https://schema.org/NewCondition",
                    },
                }
            )

    return schemas


def _inject_head(body: str, markup: str) -> str:
    match = re.search(r"</head\s*>", body, flags=re.I)
    if not match:
        return body
    return body[: match.start()] + markup + "\n" + body[match.start() :]


@SEO.get("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /stripe/",
        "Disallow: /create-checkout-session",
        "Disallow: /health",
        f"Sitemap: {_absolute_url('/sitemap.xml')}",
        "",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@SEO.get("/sitemap.xml")
def sitemap_xml():
    paths: set[str] = set()

    # Build from the final Flask url map at request time so this keeps working
    # with the current v2 app even when new public static routes are added.
    for rule in current_app.url_map.iter_rules():
        if "GET" not in rule.methods:
            continue
        path = str(rule.rule)
        if "<" in path or not _sitemap_allowed(path):
            continue
        paths.add(path)

    # Guarantee the add-on pages are present.
    paths.update(
        {
            "/",
            "/marketers",
            "/how-it-works",
            "/sell-products-online",
            "/product-research",
        }
    )

    urls = []
    for path in sorted(paths):
        loc = html_lib.escape(_absolute_url(path), quote=True)
        urls.append(f"  <url><loc>{loc}</loc></url>")

    xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *urls,
            "</urlset>",
            "",
        ]
    )
    return Response(xml, mimetype="application/xml")


@SEO.get("/marketers")
def marketers_page():
    return render_template("seo/marketers.html")


@SEO.get("/how-it-works")
def how_it_works_page():
    return render_template("seo/how_it_works.html")


@SEO.get("/sell-products-online")
def sell_products_online_page():
    return render_template("seo/sell_products_online.html")


@SEO.get("/product-research")
def product_research_page():
    return render_template("seo/product_research.html")


def init_seo(app):
    """Register all BuyAnything SEO routes and response enhancements."""
    app.register_blueprint(SEO)

    @app.before_request
    def _optional_canonical_redirect():
        # OFF by default. Enable only after your production domain works on HTTPS.
        if os.getenv("SEO_FORCE_CANONICAL", "0") != "1":
            return None
        if request.path.startswith("/static/"):
            return None

        target_base = _base_url()
        forwarded_proto = (
            request.headers.get("X-Forwarded-Proto", request.scheme)
            .split(",")[0]
            .strip()
        )
        incoming = f"{forwarded_proto}://{request.host}"
        if incoming.rstrip("/").lower() != target_base.lower():
            target = target_base + request.full_path
            if target.endswith("?"):
                target = target[:-1]
            return redirect(target, code=301)
        return None

    @app.after_request
    def _apply_seo(response):
        content_type = (response.content_type or "").lower()
        if response.status_code != 200 or "text/html" not in content_type:
            return response

        path = request.path
        body = response.get_data(as_text=True)
        if "<head" not in body.lower():
            return response

        noindex = _is_noindex(path)
        body = _remove_existing_seo_tags(body)

        if noindex:
            robots = "noindex,follow" if path.startswith("/s/") else "noindex,nofollow"
            markup = f'<meta name="robots" content="{robots}">'
            response.headers["X-Robots-Tag"] = robots
            body = _inject_head(body, markup)
            response.set_data(body)
            return response

        title, description = _meta_for(path, body)
        body = _replace_title(body, title)

        # Canonical ignores query strings by design.
        canonical = _absolute_url(path)
        if path == "/":
            canonical = _base_url() + "/"

        tags = [
            f'<meta name="description" content="{html_lib.escape(description, quote=True)}">',
            '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
            f'<link rel="canonical" href="{html_lib.escape(canonical, quote=True)}">',
            f'<meta property="og:title" content="{html_lib.escape(title, quote=True)}">',
            f'<meta property="og:description" content="{html_lib.escape(description, quote=True)}">',
            f'<meta property="og:url" content="{html_lib.escape(canonical, quote=True)}">',
            f'<meta property="og:type" content="{"product" if path == "/product" else "website"}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{html_lib.escape(title, quote=True)}">',
            f'<meta name="twitter:description" content="{html_lib.escape(description, quote=True)}">',
        ]

        verification = os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()
        if verification:
            tags.append(
                f'<meta name="google-site-verification" content="{html_lib.escape(verification, quote=True)}">'
            )

        for schema in _schema_markup(path, canonical, body):
            tags.append(
                '<script type="application/ld+json">'
                + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                + "</script>"
            )

        body = _inject_head(body, "\n".join(tags))
        response.set_data(body)
        return response

    return app
