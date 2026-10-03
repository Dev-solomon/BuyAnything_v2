import os, uuid, re
from datetime import datetime, timezone
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
import stripe
from services.research import (
    research_trending_products,
    build_product,
    find_cj_candidates
)
from services.cj import test_connection, create_order, CJError
from seo_addon import init_seo

load_dotenv()
app = Flask(__name__)
init_seo(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1",
)

mongo = MongoClient(
    os.getenv("MONGODB_URI", "mongodb://localhost:27017/"),
    serverSelectionTimeoutMS=10000,
)
db = mongo[os.getenv("MONGODB_DB", "buyanything")]
affiliates, products, candidates, orders = (
    db.affiliates,
    db.products,
    db.candidates,
    db.orders,
)
try:
    affiliates.create_index("email", unique=True)
    affiliates.create_index("slug", unique=True)
    products.create_index("affiliate_id", unique=True)
    candidates.create_index([("affiliate_id", 1), ("created_at", DESCENDING)])
    orders.create_index("stripe_session", unique=True, sparse=True)
    orders.create_index([("affiliate_id", 1), ("created_at", DESCENDING)])
except Exception:
    pass

DEFAULT_PRODUCT = {
    "name": "Your next remarkable find",
    "tagline": "An approved-selected product will appear here.",
    "description": "This storefront is ready for a curated product.",
    "price": 49.99,
    "compare_at": 64.99,
    "currency": "usd",
    "image": "",
    "images": [],
    "benefits": ["Useful by design", "Secure checkout", "Automated fulfillment"],
    "variants": [],
}


def now():
    return datetime.now(timezone.utc)


def oidstr(x):
    return str(x) if x is not None else ""


def affiliate_ok():
    return bool(session.get("affiliate_id"))


def admin_ok():
    return session.get("super_admin") is True


def affiliate_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not affiliate_ok():
            return redirect(url_for("affiliate_login"))
        return fn(*a, **kw)

    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not admin_ok():
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)

    return wrapped


def current_affiliate():
    if not affiliate_ok():
        return None
    from bson import ObjectId

    try:
        return affiliates.find_one({"_id": ObjectId(session["affiliate_id"])})
    except Exception:
        return None


def get_product_for_affiliate(aid):
    return products.find_one({"affiliate_id": str(aid)}) or DEFAULT_PRODUCT.copy()


def get_affiliate_by_slug(slug):
    return affiliates.find_one({"slug": slug.lower()})


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "affiliate"
    base = s
    i = 2
    while affiliates.find_one({"slug": s}):
        s = f"{base}-{i}"
        i += 1
    return s


def storefront_path(a):
    return url_for("storefront", slug=a["slug"])


@app.get("/")
def home():
    # Main domain is a simple gateway; logged-in affiliates can preview their store.
    a = current_affiliate()
    if a:
        return redirect(storefront_path(a))
    return render_template("network_home.html")


@app.get("/s/<slug>")
def storefront(slug):
    a = get_affiliate_by_slug(slug)
    if not a:
        return render_template("not_found.html"), 404
    return render_template(
        "index.html",
        p=get_product_for_affiliate(a["_id"]),
        affiliate=a,
        store_slug=slug,
    )


@app.get("/s/<slug>/product")
def product(slug):
    a = get_affiliate_by_slug(slug)

    if not a:
        return render_template("not_found.html"), 404

    p = get_product_for_affiliate(a["_id"])

    app.logger.debug(
        "Product type: %s, value: %r",
        type(p).__name__,
        p
    )

    return render_template(
        "product.html",
        p=p,
        affiliate=a,
        store_slug=slug,
    )


@app.get("/s/<slug>/purchase")
def purchase(slug):
    a = get_affiliate_by_slug(slug)
    if not a:
        return render_template("not_found.html"), 404
    p = get_product_for_affiliate(a["_id"])
    try:
        quantity = max(1, min(int(request.args.get("quantity", "1")), 20))
    except Exception:
        quantity = 1
    # Derive display options from the saved CJ variants, including older
    # approved products that have no stored variant_options schema.
    display_options = []
    variants_for_picker = p.get("variants") or []
    if variants_for_picker:
        attrs = [v.get("attributes") or {} for v in variants_for_picker]
        labels = list(attrs[0]) if attrs else []
        # Mixed/missing attribute schemas cannot safely form combined selectors.
        if labels and all(set(x) == set(labels) and all(str(x[k]).strip() for k in labels) for x in attrs):
            for label in labels:
                values = list(dict.fromkeys(str(x[label]) for x in attrs))
                display_options.append({"label": label, "values": values})
    return render_template(
        "purchase.html", p=p, affiliate=a, store_slug=slug,
        quantity=quantity, display_options=display_options
    )


@app.post("/s/<slug>/create-checkout-session")
def checkout(slug):
    a = get_affiliate_by_slug(slug)
    if not a:
        return "Store not found", 404
    p = get_product_for_affiliate(a["_id"])
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        flash("Stripe is not configured.")
        return redirect(url_for("purchase", slug=slug))
    try:
        quantity = max(1, min(int(request.form.get("quantity", "1")), 20))
    except Exception:
        quantity = 1
    selected_vid = request.form.get("variant_vid", "").strip()
    variant = None
    if p.get("variants"):
        variant = next((v for v in p["variants"] if v.get("vid") == selected_vid), None)
        if not variant:
            flash("Please choose a product option.")
            return redirect(url_for("purchase", slug=slug))
    else:
        selected_vid = p.get("cj_vid")
    if not selected_vid:
        flash("This product is not connected online Yet!.")
        return redirect(url_for("purchase", slug=slug))
    unit_price = float((variant or {}).get("retail_price") or p["price"])
    base = os.getenv("BASE_URL", request.host_url.rstrip("/")).rstrip("/")
    order_no = "BA-" + uuid.uuid4().hex[:10].upper()
    s = stripe.checkout.Session.create(
        mode="payment",
         managed_payments={"enabled": False},
        payment_method_types=["card"],
        billing_address_collection="auto",
        shipping_address_collection={
    "allowed_countries": [
        "US", "CA", "GB", "AU", "NZ",
        "DE", "FR", "IT", "ES", "NL",
        "BE", "AT", "CH", "SE", "NO",
        "DK", "FI", "IE", "PT", "PL",
        "JP", "SG", "HK", "AE", "SA",
        "MX", "BR", "ZA", "NG", "KE",
        "GH", "IN", "MY", "PH", "TH"
    ]
},
        phone_number_collection={"enabled": True},
        customer_creation="always",
        metadata={
            "order_number": order_no,
            "affiliate_id": oidstr(a["_id"]),
            "affiliate_email": a["email"],
            "store_slug": slug,
            "cj_pid": str(p.get("cj_pid") or ""),
            "cj_vid": selected_vid,
            "quantity": str(quantity),
            "variant_name": (variant or {}).get("name", "Default"),
            "variant_attributes": __import__("json").dumps(
                (variant or {}).get("attributes", {}), separators=(",", ":")
            )[:450],
        },
        line_items=[
            {
                "price_data": {
                    "currency": p.get("currency", "usd"),
                    "product_data": {
                        "name": p["name"]
                        + (
                            (" — " + (variant or {}).get("name", ""))
                            if (variant or {}).get("name")
                            and (variant or {}).get("name") != "Default"
                            else ""
                        ),
                        "description": p.get("tagline", ""),
                        "images": (
                            [(variant or {}).get("image") or p.get("image")]
                            if ((variant or {}).get("image") or p.get("image"))
                            else []
                        ),
                    },
                    "unit_amount": int(round(unit_price * 100)),
                },
                "quantity": quantity,
            }
        ],
        success_url=base + f"/s/{slug}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=base + f"/s/{slug}/purchase",
    )
    return redirect(s.url, 303)


def fulfill_checkout(cs):
    if hasattr(cs, "to_dict"):
        cs = cs.to_dict()
    md = cs.get("metadata") or {}
    sid = cs.get("id")
    if sid and orders.find_one({"stripe_session": sid}):
        return
    aid = md.get("affiliate_id")
    p = get_product_for_affiliate(aid)
    details = cs.get("customer_details") or {}
    addr = details.get("address") or {}
    shipping = {
        "name": details.get("name", ""),
        "email": details.get("email", ""),
        "phone": details.get("phone", ""),
        "line1": addr.get("line1", ""),
        "line2": addr.get("line2", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state", ""),
        "postal_code": addr.get("postal_code", ""),
        "country": addr.get("country", ""),
        "country_name": addr.get("country", ""),
    }
    qty = int(md.get("quantity", "1"))
    vid = md.get("cj_vid")
    variant = next((v for v in p.get("variants", []) if v.get("vid") == vid), {})
    sell = float(variant.get("retail_price") or p.get("price", 0))
    cost = float(variant.get("supplier_cost") or p.get("supplier_cost", 0))
    # User rule: $16 shipping component is excluded from the commissionable margin.
    shipping_component = float(os.getenv("SHIPPING_COMPONENT", "16"))
    gross_margin = max(0, (sell - shipping_component - cost)) * qty
    admin_profit = round(
        gross_margin * float(os.getenv("ADMIN_PROFIT_RATE", "0.15")), 2
    )
    affiliate_profit = round(gross_margin - admin_profit, 2)

    try:
        variant_attributes = __import__("json").loads(
            md.get("variant_attributes") or "{}"
        )
    except Exception:
        variant_attributes = variant.get("attributes", {})
    rec = {
        "order_number": md.get("order_number") or "BA-" + uuid.uuid4().hex[:10].upper(),
        "stripe_session": sid,
        "payment_status": cs.get("payment_status"),
        "affiliate_id": aid,
        "affiliate_email": md.get("affiliate_email"),
        "store_slug": md.get("store_slug"),
        "product": p.get("name"),
        "cj_pid": p.get("cj_pid"),
        "cj_vid": vid,
        "variant_name": md.get("variant_name", "Default"),
        "variant_attributes": variant_attributes,
        "quantity": qty,
        "unit_sell_price": sell,
        "unit_supplier_cost": cost,
        "shipping_component": shipping_component,
        "revenue": round(sell * qty, 2),
        "gross_margin_ex_shipping": round(gross_margin, 2),
        "admin_profit": admin_profit,
        "affiliate_profit": affiliate_profit,
        "customer_email": details.get("email", ""),
        "created_at": now(),
        "cj_status": "pending",
    }
    try:
        result = create_order(rec["order_number"], shipping, vid, qty)
        rec.update(cj_status="submitted", cj_result=result)
    except Exception as e:
        rec.update(cj_status="needs_attention", cj_error=str(e))
    orders.insert_one(rec)


@app.post("/stripe/webhook")
def stripe_webhook():
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return "Webhook secret missing", 400
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception:
        return "Invalid webhook", 400
    if event["type"] == "checkout.session.completed":
        fulfill_checkout(event["data"]["object"])
    return "", 200


@app.get("/s/<slug>/success")
def success(slug):
    a = get_affiliate_by_slug(slug)
    return render_template(
        "success.html",
        p=get_product_for_affiliate(a["_id"]) if a else DEFAULT_PRODUCT,
        affiliate=a,
        store_slug=slug,
    )


@app.get("/policies")
def policies():
    return render_template("policies.html")


@app.get("/affiliate/terms")
@affiliate_required
def affiliate_terms():
    return render_template("affiliate_terms.html")


# Affiliate auth
@app.route("/affiliate/signup", methods=["GET", "POST"])
def affiliate_signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 8:
            flash(
                "Enter your name, a valid email, and a password of at least 8 characters."
            )
            return redirect(url_for("affiliate_signup"))
        if request.form.get("accept_terms") != "yes":
            flash("You must accept the Affiliate Terms to create an account.")
            return redirect(url_for("affiliate_signup"))
        doc = {
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "slug": slugify(request.form.get("store_name") or name),
            "created_at": now(),
            "status": "active",
            "affiliate_terms_version": "2026-10-01",
            "affiliate_terms_accepted_at": now(),
        }
        try:
            r = affiliates.insert_one(doc)
        except DuplicateKeyError:
            flash("An account with that email already exists.")
            return redirect(url_for("affiliate_login"))
        session.clear()
        session["affiliate_id"] = str(r.inserted_id)
        return redirect(url_for("affiliate_dashboard"))
    return render_template("affiliate_signup.html")


@app.route("/affiliate/login", methods=["GET", "POST"])
def affiliate_login():
    if request.method == "POST":
        a = affiliates.find_one(
            {"email": request.form.get("email", "").strip().lower()}
        )
        if a and check_password_hash(
            a["password_hash"], request.form.get("password", "")
        ):
            session.clear()
            session["affiliate_id"] = str(a["_id"])
            return redirect(url_for("affiliate_dashboard"))
        flash("Incorrect email or password.")
    return render_template("affiliate_login.html")


@app.post("/affiliate/logout")
def affiliate_logout():
    session.clear()
    return redirect(url_for("affiliate_login"))


@app.get("/affiliate")
@affiliate_required
def affiliate_dashboard():
    a = current_affiliate()
    aid = str(a["_id"])
    p = get_product_for_affiliate(a["_id"])
    latest = candidates.find_one(
        {"affiliate_id": aid}, sort=[("created_at", DESCENDING)]
    )
    recent = list(
        orders.find({"affiliate_id": aid}).sort("created_at", DESCENDING).limit(20)
    )
    stats = list(
        orders.aggregate(
            [
                {"$match": {"affiliate_id": aid, "payment_status": "paid"}},
                {
                    "$group": {
                        "_id": None,
                        "orders": {"$sum": 1},
                        "units": {"$sum": "$quantity"},
                        "revenue": {"$sum": "$revenue"},
                        "earnings": {"$sum": "$affiliate_profit"},
                    }
                },
            ]
        )
    )
    return render_template(
        "affiliate_dashboard.html",
        affiliate=a,
        p=p,
        candidates=(latest or {}).get("items", []),
        orders=recent,
        stats=stats[0] if stats else {},
        store_url=request.host_url.rstrip("/") + storefront_path(a),
    )


@app.post("/affiliate/research")
@affiliate_required
def affiliate_research():
    a = current_affiliate()
    aid = str(a["_id"])
    try:
        items = research_trending_products(limit=20)
        candidates.insert_one(
            {"affiliate_id": aid, "items": items, "created_at": now()}
        )
        flash("Research complete. Review the Top 20 ranked products.")
    except Exception as e:
        flash("Research error: " + str(e))
    return redirect(url_for("affiliate_dashboard"))



@app.post("/affiliate/approve/<int:i>")
@affiliate_required
def affiliate_approve(i):
    """
    Display actual CJ supplier matches for the
    selected research opportunity.
    Do not publish anything yet.
    """
    a = current_affiliate()
    aid = str(a["_id"])

    latest = candidates.find_one(
        {"affiliate_id": aid},
        sort=[("created_at", DESCENDING)]
    )

    if (
        not latest
        or not isinstance(latest.get("items"), list)
        or not 0 <= i < len(latest["items"])
    ):
        flash(
            "Research selection expired. "
            "Run research again."
        )
        return redirect(url_for("affiliate_dashboard"))

    item = latest["items"][i]

    try:
        matches = find_cj_candidates(item)

        if not matches:
            flash(
                "Supplier returned no similar matches - Try another research opportunity."
            )
            return redirect(url_for("affiliate_dashboard"))

        # Bind approved supplier choices to this
        # affiliate and research snapshot.
        session["pending_cj_approval"] = {
            "affiliate_id": aid,
            "candidate_document_id": str(latest["_id"]),
            "candidate_index": i,
            "allowed_pids": [
                x["pid"] for x in matches
            ]
        }

        return render_template(
            "select_cj_product.html",
            candidate=item,
            matches=matches
        )

    except Exception as exc:
        app.logger.exception(
            "Supplier search failed"
        )
        flash("Supplier search error: " + str(exc))

        return redirect(
            url_for("affiliate_dashboard")
        )


@app.post("/affiliate/confirm-cj")
@affiliate_required
def affiliate_confirm_cj():
    """
    Publish only the exact CJ product
    selected from the displayed results.
    """
    from bson import ObjectId

    a = current_affiliate()
    aid = str(a["_id"])

    pending = session.get(
        "pending_cj_approval"
    ) or {}

    selected_pid = str(
        request.form.get("cj_pid") or ""
    ).strip()

    # Reject products that were not presented
    # during this affiliate's selection process.
    if (
        pending.get("affiliate_id") != aid
        or not selected_pid
        or selected_pid not in pending.get(
            "allowed_pids", []
        )
    ):
        flash(
            "Supplier approval expired or invalid. Try Again!"
        )
        return redirect(
            url_for("affiliate_dashboard")
        )

    try:
        snapshot_id = ObjectId(
            pending["candidate_document_id"]
        )

        snapshot = candidates.find_one({
            "_id": snapshot_id,
            "affiliate_id": aid
        })

        idx = pending["candidate_index"]

        if (
            not snapshot
            or not isinstance(idx, int)
            or not 0 <= idx < len(
                snapshot.get("items", [])
            )
        ):
            raise ValueError(
                "The original research selection "
                "is unavailable."
            )

        # Ensure another research run hasn't
        # silently changed the selected product.
        latest = candidates.find_one(
            {"affiliate_id": aid},
            sort=[("created_at", DESCENDING)]
        )

        if (
            not latest
            or latest["_id"] != snapshot_id
        ):
            raise ValueError(
                "Research has changed. "
                "Please select your product again."
            )

        item = snapshot["items"][idx]

        # Source only the explicitly selected CJ ID.
        product = build_product({
            **item,
            "approved_cj_pid": selected_pid
        })

        product.update({
            "affiliate_id": aid,
            "affiliate_email": a["email"],
            "approved_at": now()
        })

        # Publish only after successful
        # supplier verification and import.
        products.replace_one(
            {"affiliate_id": aid},
            product,
            upsert=True
        )

        session.pop(
            "pending_cj_approval",
            None
        )

        flash(
            "Approved! Your exact selected product is now on your storefront."
        )

    except Exception as exc:
        app.logger.exception(
            "Supplier approval failed"
        )
        flash("Approval error: " + str(exc))

    return redirect(
        url_for("affiliate_dashboard")
    )



@app.post("/affiliate/test-cj")
@affiliate_required
def affiliate_test_cj():
    try:
        test_connection()
        flash("StoreFront connection is working.")
    except Exception as e:
        flash("Connection Error: " + str(e))
    return redirect(url_for("affiliate_dashboard"))


# Super admin
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("email", "").lower() == os.getenv(
            "SUPER_ADMIN_EMAIL", "admin@buyanything.sale"
        ).lower() and request.form.get("password") == os.getenv(
            "SUPER_ADMIN_PASSWORD", "change-me"
        ):
            session.clear()
            session["super_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect administrator credentials.")
    return render_template("admin_login.html")


@app.get("/admin")
@admin_required
def admin_dashboard():
    affiliate_rows = []
    for a in affiliates.find().sort("created_at", DESCENDING):
        aid = str(a["_id"])
        st = list(
            orders.aggregate(
                [
                    {"$match": {"affiliate_id": aid, "payment_status": "paid"}},
                    {
                        "$group": {
                            "_id": None,
                            "fulfillments": {"$sum": 1},
                            "revenue": {"$sum": "$revenue"},
                            "affiliate_profit": {"$sum": "$affiliate_profit"},
                            "admin_profit": {"$sum": "$admin_profit"},
                        }
                    },
                ]
            )
        )
        affiliate_rows.append({"affiliate": a, "stats": st[0] if st else {}})
    top = list(
        orders.aggregate(
            [
                {"$match": {"payment_status": "paid"}},
                {
                    "$group": {
                        "_id": "$product",
                        "units": {"$sum": "$quantity"},
                        "orders": {"$sum": 1},
                        "revenue": {"$sum": "$revenue"},
                        "admin_profit": {"$sum": "$admin_profit"},
                    }
                },
                {"$sort": {"units": -1}},
                {"$limit": 20},
            ]
        )
    )
    recent = list(orders.find().sort("created_at", DESCENDING).limit(50))
    totals = list(
        orders.aggregate(
            [
                {"$match": {"payment_status": "paid"}},
                {
                    "$group": {
                        "_id": None,
                        "orders": {"$sum": 1},
                        "revenue": {"$sum": "$revenue"},
                        "admin_profit": {"$sum": "$admin_profit"},
                        "affiliate_profit": {"$sum": "$affiliate_profit"},
                    }
                },
            ]
        )
    )
    return render_template(
        "admin_dashboard.html",
        affiliates=affiliate_rows,
        top_products=top,
        recent=recent,
        totals=totals[0] if totals else {},
        affiliate_count=affiliates.count_documents({}),
    )


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/health")
def health():
    try:
        mongo.admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return jsonify(
        ok=True,
        mongodb=mongo_ok,
        cj_configured=bool(os.getenv("CJ_ACCESS_TOKEN")),
        stripe_configured=bool(os.getenv("STRIPE_SECRET_KEY")),
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )
