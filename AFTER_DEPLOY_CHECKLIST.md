# After-deploy checklist

## 1. Technical checks

- [ ] `/robots.txt` loads with HTTP 200
- [ ] `/sitemap.xml` loads with HTTP 200
- [ ] sitemap URLs use `https://www.buyanything.sale`
- [ ] homepage source contains one canonical tag
- [ ] homepage source contains a meta description
- [ ] `/affiliate/login` contains `noindex`
- [ ] `/affiliate/signup` contains `noindex`
- [ ] a marketer `/s/...` page contains `noindex,follow`
- [ ] `/marketers` loads correctly
- [ ] `/how-it-works` loads correctly
- [ ] `/sell-products-online` loads correctly
- [ ] `/product-research` loads correctly

## 2. Google Search Console

- [ ] Property verified
- [ ] `sitemap.xml` submitted
- [ ] Homepage inspected
- [ ] `/marketers` inspected
- [ ] `/how-it-works` inspected
- [ ] `/sell-products-online` inspected
- [ ] `/product-research` inspected
- [ ] `/product` inspected if present

## 3. Structured data tests

Use Google's Rich Results Test on the live `/product` URL. Confirm the Product item has:

- name
- image
- offers
- price
- priceCurrency = USD
- availability

Warnings for optional fields can be improved later; critical errors should be fixed before relying on product rich results.

## 4. First 30-day SEO measurement

Watch these Search Console metrics weekly:

- Total impressions
- Total clicks
- Average click-through rate
- Average position
- Queries containing `buyanything`
- Queries around selling products online
- Queries around product research
- Queries that land on `/marketers`

Do not judge SEO from rankings alone. The first target is increasing valid indexed pages and search impressions, then improving clicks and qualified marketer signups.
