# BuyAnything.sale — Google SEO Add-on

This package was prepared as an **add-on only**. It is intentionally isolated so you do not have to replace your existing BuyAnything v2 storefront, marketer logic, Stripe checkout, CJdropshipping integration, MongoDB code, CSS, or JavaScript.

## What this adds

- `/robots.txt`
- `/sitemap.xml`
- Unique SEO titles and meta descriptions
- Canonical URLs
- Open Graph and Twitter metadata
- Google Search Console verification through an environment variable
- `Organization` + `WebSite` JSON-LD on the homepage
- Basic `Product` + `Offer` JSON-LD on `/product` when the server-rendered page exposes a product name, image and price
- `noindex` rules for admin/login/signup/checkout pages
- `noindex,follow` on `/s/...` marketer storefront URLs so many similar marketer pages do not compete with the main BuyAnything domain in Google
- Four new crawlable SEO landing pages:
  - `/marketers`
  - `/how-it-works`
  - `/sell-products-online`
  - `/product-research`

## Install — exact file locations 

Copy the package files into your BuyAnything project like this:

```text
BuyAnything/
├── app.py                         <-- KEEP your existing file
├── seo_addon.py                   <-- ADD this new file
├── templates/
│   ├── base.html                  <-- KEEP your existing file
│   └── seo/                       <-- ADD this new folder
│       ├── marketers.html
│       ├── how_it_works.html
│       ├── sell_products_online.html
│       └── product_research.html
└── ...everything else unchanged
```

Then add only two lines to `app.py`. See `APP_PY_ADD.txt`.

### Line 1 — import

Near the other imports:

```python
from seo_addon import init_seo
```

### Line 2 — register

Immediately after your Flask application is created:

```python
app = Flask(__name__)
init_seo(app)
```

If your current v2 file creates the Flask object with different arguments, keep your line exactly as it is and put `init_seo(app)` on the next line.

## Environment variables

In Render, add:

```text
PUBLIC_BASE_URL=https://www.buyanything.sale
SEO_CONTACT_EMAIL=contact@buyanything.sale
SEO_FORCE_CANONICAL=0
```

Do **not** turn `SEO_FORCE_CANONICAL` on until the site is confirmed working correctly through the preferred `https://www.buyanything.sale` host. The canonical tags already tell Google which hostname you prefer.

## Google Search Console setup

After deployment:

1. Open Google Search Console.
2. Add the URL-prefix property `https://www.buyanything.sale/` (or use a Domain property if you prefer DNS verification).
3. If you select **HTML tag** verification, Google gives you something similar to:

```html
<meta name="google-site-verification" content="ABC123...">
```

4. Copy **only** the value inside `content`, e.g. `ABC123...`.
5. Add it in Render as:

```text
GOOGLE_SITE_VERIFICATION=ABC123...
```

6. Redeploy and click **Verify** in Search Console.
7. In Search Console → **Sitemaps**, submit:

```text
sitemap.xml
```

8. Use **URL Inspection** and request indexing for these first:

```text
https://www.buyanything.sale/
https://www.buyanything.sale/marketers
https://www.buyanything.sale/how-it-works
https://www.buyanything.sale/sell-products-online
https://www.buyanything.sale/product-research
https://www.buyanything.sale/product
```

Only request `/product` if that route exists in your live v2 application.

## URLs to test after deployment

Open each URL directly:

- `https://www.buyanything.sale/robots.txt`
- `https://www.buyanything.sale/sitemap.xml`
- `https://www.buyanything.sale/marketers`
- `https://www.buyanything.sale/how-it-works`
- `https://www.buyanything.sale/sell-products-online`
- `https://www.buyanything.sale/product-research`

View page source on the homepage. Inside `<head>` you should see:

- `meta name="description"`
- `link rel="canonical"`
- `meta property="og:title"`
- `application/ld+json`

## Why marketer storefronts are noindexed

Your platform can produce many URLs under `/s/<marketer>`. If multiple marketers choose the same product, Google can see many substantially similar storefront pages. That can split search signals across duplicate pages. The add-on therefore leaves those pages usable for customers and marketers but tells search engines not to index them as separate SEO landing pages.

This does **not** block customers from opening the storefront links.

## Product structured data

The add-on deliberately does not mark up the visible review number as an `AggregateRating`. Only use rating structured data when the rating/review count is backed by genuine customer review data that meets Google's structured-data policies.

The `/product` schema includes the product name, image, description, USD price, availability and offer URL when those values can be detected in the rendered HTML.

## No requirements.txt change

This add-on uses Flask and Python's standard library only. It does not require an additional pip package.

## Important deployment order

1. Add `seo_addon.py`.
2. Add `templates/seo/` and its four files.
3. Add the two `app.py` lines.
4. Add `PUBLIC_BASE_URL` and `SEO_CONTACT_EMAIL` in Render.
5. Deploy.
6. Test `robots.txt` and `sitemap.xml`.
7. Add Search Console verification token.
8. Submit the sitemap.
9. Request indexing for the priority pages.

## What this package does NOT change

- Product research engine
- Product approval logic
- CJdropshipping sourcing
- Product variants
- Stripe
- Webhooks
- Orders
- MongoDB
- Marketer commissions
- Login/signup behavior
- Existing CSS
- Existing JavaScript
- Existing templates

The only integration point is `init_seo(app)`.
