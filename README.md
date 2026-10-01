# BuyAnything V2 — Multi-Affiliate Single-Product Commerce

V2 preserves the classic brown/white BuyAnything storefront while converting the original single-admin architecture into a multi-affiliate platform.

## V2 features

- Affiliate signup/login with hashed passwords.
- Each affiliate gets an isolated storefront: `/s/<affiliate-slug>`.
- Each affiliate runs their own AI-assisted **Top 20** product research and approves one product for their store.
- Approved products are sourced from CJdropshipping and stored per affiliate in MongoDB.
- CJ product variants (color/size/style/etc. as returned by CJ) are shown on checkout, with variant-specific price/image and quantity 1–20.
- Stripe metadata carries affiliate, store, CJ variant and quantity through payment.
- Stripe webhook creates the CJ fulfillment order and records it only under the selling affiliate.
- Affiliate fulfillment center shows order date, product/variant, quantity, sale, affiliate profit and CJ status.
- Separate platform admin dashboard shows affiliates, fulfillments, GMV, affiliate earnings, platform share, recent purchases and top-selling products.
- Static storefront social proof: **4.5 stars · 800+ reviews**. Only use this claim publicly if you can substantiate it; otherwise replace it with verified review data.
- MongoDB database name defaults to `buyanything`.

## Profit model

V2 follows the requested rule. For each unit:

`commissionable margin = selling price - $16 shipping component - CJ product cost`

`admin share = 15% × commissionable margin`

`affiliate profit = 90% × commissionable margin`

The $16 shipping component is excluded before the 15% split. Both `ADMIN_PROFIT_RATE` and `SHIPPING_COMPONENT` are configurable in `.env`.

## Collections

MongoDB creates/uses:

- `affiliates` — identity, email, password hash, unique storefront slug.
- `products` — one currently approved/sourced product per affiliate, including CJ variants.
- `candidates` — Top-20 research snapshots per affiliate.
- `orders` — Stripe/CJ fulfillment, affiliate ownership, product, variant, quantities and profit ledger.

Indexes are initialized by the Flask app.

## Setup

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env`.
3. Add MongoDB Atlas/local URI, Stripe keys, Stripe webhook secret, CJ API token, OpenAI API key, and strong admin/session secrets.
4. Set `BASE_URL` to the public HTTPS domain.
5. Configure Stripe webhook to POST `checkout.session.completed` to `/stripe/webhook`.
6. Ensure the CJ account/token is valid and your configured logistics method is available for your products/destinations.
7. Run `py app.py` for local development. Use a production WSGI server/platform for deployment.

## URLs

- `/` — affiliate network gateway
- `/affiliate/signup` — affiliate registration
- `/affiliate/login` — affiliate login
- `/affiliate` — affiliate dashboard
- `/s/<slug>` — affiliate storefront
- `/s/<slug>/product` — affiliate product details
- `/s/<slug>/purchase` — variant + quantity checkout
- `/admin/login` — platform administrator login
- `/admin` — platform administrator dashboard
- `/health` — configuration/DB health

## Important production notes

- Never commit `.env` or API keys.
- The V1 GitHub repository is not modified by this V2 package.
- Stripe webhooks are the source of truth for paid-order fulfillment. The order insert is idempotent by Stripe session ID.
- CJ can reject fulfillment for unsupported logistics, invalid address/variant, balance or inventory conditions. Such orders are stored as `needs_attention` rather than discarded.
- Before public launch, add email verification/password reset, CSRF protection, rate limiting, privacy/terms/refund pages, tax handling, and a payout workflow if affiliates will receive real-money payouts.


## V2 policy and affiliate agreement update
- Storefronts display an estimated delivery window of 3–7 days. This is presented as an estimate, not a carrier guarantee.
- `/policies` contains shipping, 7-day-after-delivery return eligibility, refunds, cancellations, damaged-item, payment/privacy, and contact terms.
- `/affiliate/terms` contains the affiliate agreement. Signup requires explicit acceptance and MongoDB records the terms version and acceptance timestamp.
- Platform fee default is 15% of commissionable product margin. The configured $16 shipping component is excluded before the margin split: `(sell price - $16 shipping - supplier cost) × 85%` is the affiliate earning.
