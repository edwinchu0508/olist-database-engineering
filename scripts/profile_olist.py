"""Read-only profile of the raw Olist CSVs: keys, foreign keys, nulls and known data quirks.

Usage: py scripts/profile_olist.py <data_dir>
Nothing is written; every check prints to stdout.
"""
import sys
from pathlib import Path

import pandas as pd

TABLES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}
ORDER_TS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
UTF8_BOM = b"\xef\xbb\xbf"


def section(title):
    print(f"\n## {title}")


def key_report(label, frame, cols):
    dup = frame.duplicated(subset=cols, keep=False)
    n_keys = frame.loc[dup, cols].drop_duplicates().shape[0]
    print(f"{label:48s} unique={str(not dup.any()):5s} dup_keys={n_keys:,} rows_in_dups={int(dup.sum()):,}")


def fk_report(label, child, ccol, parent, pcol):
    vals = child[ccol].dropna()
    orphan = ~vals.isin(set(parent[pcol].dropna()))
    print(f"{label:48s} orphan_rows={int(orphan.sum()):,} distinct_orphan_values={vals[orphan].nunique():,}")
    return vals[orphan]


def to_ts(frame, cols):
    out = frame.copy()
    for c in cols:
        parsed = pd.to_datetime(out[c], errors="coerce")
        bad = int((out[c].notna() & parsed.isna()).sum())
        if bad:
            print(f"  unparseable {c}: {bad}")
        out[c] = parsed
    return out


def main(data_dir):
    d = Path(data_dir)
    df = {}

    section("Row counts / encoding")
    for name, fname in TABLES.items():
        path = d / fname
        has_bom = path.read_bytes()[:3] == UTF8_BOM
        df[name] = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        print(f"{name:12s} rows={len(df[name]):>10,} cols={df[name].shape[1]:>2} size_mb={path.stat().st_size / 1e6:6.1f} bom={has_bom}")
    print(f"total rows: {sum(len(f) for f in df.values()):,}")

    section("Null counts (columns with any null)")
    for name, frame in df.items():
        nulls = frame.isna().sum()
        nulls = nulls[nulls > 0]
        for col, n in nulls.items():
            print(f"{name:12s} {col:34s} {n:>8,} ({n / len(frame):.1%})")

    section("Candidate primary keys")
    key_report("customers(customer_id)", df["customers"], ["customer_id"])
    key_report("orders(order_id)", df["orders"], ["order_id"])
    key_report("items(order_id, order_item_id)", df["items"], ["order_id", "order_item_id"])
    key_report("payments(order_id, payment_sequential)", df["payments"], ["order_id", "payment_sequential"])
    key_report("reviews(review_id)", df["reviews"], ["review_id"])
    key_report("reviews(review_id, order_id)", df["reviews"], ["review_id", "order_id"])
    key_report("reviews(order_id)", df["reviews"], ["order_id"])
    key_report("products(product_id)", df["products"], ["product_id"])
    key_report("sellers(seller_id)", df["sellers"], ["seller_id"])
    key_report("translation(product_category_name)", df["translation"], ["product_category_name"])
    key_report("geolocation(zip_code_prefix)", df["geolocation"], ["geolocation_zip_code_prefix"])
    key_report("geolocation(all columns)", df["geolocation"], list(df["geolocation"].columns))

    section("Foreign keys")
    fk_report("orders.customer_id -> customers", df["orders"], "customer_id", df["customers"], "customer_id")
    fk_report("customers.customer_id -> orders (reverse)", df["customers"], "customer_id", df["orders"], "customer_id")
    fk_report("items.order_id -> orders", df["items"], "order_id", df["orders"], "order_id")
    fk_report("items.product_id -> products", df["items"], "product_id", df["products"], "product_id")
    fk_report("items.seller_id -> sellers", df["items"], "seller_id", df["sellers"], "seller_id")
    fk_report("payments.order_id -> orders", df["payments"], "order_id", df["orders"], "order_id")
    fk_report("reviews.order_id -> orders", df["reviews"], "order_id", df["orders"], "order_id")
    missing_cat = fk_report("products.category -> translation", df["products"], "product_category_name",
                            df["translation"], "product_category_name")
    print(f"  categories missing from translation: {sorted(missing_cat.unique())}")
    fk_report("customers.zip -> geolocation", df["customers"], "customer_zip_code_prefix",
              df["geolocation"], "geolocation_zip_code_prefix")
    fk_report("sellers.zip -> geolocation", df["sellers"], "seller_zip_code_prefix",
              df["geolocation"], "geolocation_zip_code_prefix")

    section("Zip code format")
    for name, col in [("customers", "customer_zip_code_prefix"), ("sellers", "seller_zip_code_prefix"),
                      ("geolocation", "geolocation_zip_code_prefix")]:
        z = df[name][col].dropna()
        print(f"{name:12s} lengths={dict(z.str.len().value_counts())} leading_zero={int(z.str.startswith('0').sum()):,}")

    section("Customers: customer_id vs customer_unique_id")
    c, o = df["customers"], df["orders"]
    print(f"customer_id distinct={c.customer_id.nunique():,}  customer_unique_id distinct={c.customer_unique_id.nunique():,}")
    per_cid = o.groupby("customer_id").size()
    print(f"orders per customer_id: max={per_cid.max()}  (1:1 with orders = {bool((per_cid == 1).all())})")
    ou = o.merge(c[["customer_id", "customer_unique_id"]], on="customer_id")
    per_uid = ou.groupby("customer_unique_id").order_id.nunique()
    print(f"unique customers with >1 order: {int((per_uid > 1).sum()):,} of {len(per_uid):,} "
          f"({(per_uid > 1).mean():.2%}); max orders by one customer={per_uid.max()}")
    print(f"repeat rate if customer_id is (wrongly) used: {(per_cid > 1).mean():.2%}")

    section("Orders: status and timestamps")
    o = to_ts(o, ORDER_TS)
    print(dict(o.order_status.value_counts()))
    p = o.order_purchase_timestamp
    print(f"purchase range: {p.min()} -> {p.max()}")
    monthly = p.dt.to_period("M").value_counts().sort_index()
    print(f"months={len(monthly)}  first 4: {dict(monthly.head(4))}  last 4: {dict(monthly.tail(4))}")
    deliv = o.order_status == "delivered"
    checks = {
        "delivered but delivered_customer_date null": deliv & o.order_delivered_customer_date.isna(),
        "delivered but approved_at null": deliv & o.order_approved_at.isna(),
        "delivered but carrier_date null": deliv & o.order_delivered_carrier_date.isna(),
        "not delivered but has delivered_customer_date": ~deliv & o.order_delivered_customer_date.notna(),
        "approved_at < purchase": o.order_approved_at < p,
        "carrier_date < purchase": o.order_delivered_carrier_date < p,
        "carrier_date < approved_at": o.order_delivered_carrier_date < o.order_approved_at,
        "delivered_customer < carrier_date": o.order_delivered_customer_date < o.order_delivered_carrier_date,
        "delivered_customer < purchase": o.order_delivered_customer_date < p,
        "estimated_delivery < purchase": o.order_estimated_delivery_date < p,
    }
    for label, mask in checks.items():
        print(f"{label:48s} {int(mask.sum()):>7,}")
    print("not-delivered orders with delivered date, by status:",
          dict(o.loc[checks["not delivered but has delivered_customer_date"], "order_status"].value_counts()))

    section("Orders: missing children")
    items, pay, rev = df["items"], df["payments"], df["reviews"]
    no_items = o[~o.order_id.isin(set(items.order_id))]
    print(f"orders without items: {len(no_items):,}  by status: {dict(no_items.order_status.value_counts())}")
    print(f"orders without payments: {int((~o.order_id.isin(set(pay.order_id))).sum()):,}")
    print(f"orders without reviews: {int((~o.order_id.isin(set(rev.order_id))).sum()):,}")

    section("Order items")
    it = items.copy()
    it["price"] = it.price.astype(float)
    it["freight_value"] = it.freight_value.astype(float)
    it["order_item_id"] = it.order_item_id.astype(int)
    print(f"price<=0: {int((it.price <= 0).sum())}  freight==0: {int((it.freight_value == 0).sum()):,}  "
          f"max items in one order: {it.order_item_id.max()}")
    sellers_per_order = it.groupby("order_id").seller_id.nunique()
    print(f"orders with >1 seller: {int((sellers_per_order > 1).sum()):,}")
    sl = pd.to_datetime(it.shipping_limit_date, errors="coerce")
    print(f"shipping_limit_date range: {sl.min()} -> {sl.max()}")

    section("Payments")
    pm = pay.copy()
    pm["payment_value"] = pm.payment_value.astype(float)
    pm["payment_installments"] = pm.payment_installments.astype(int)
    print(dict(pm.payment_type.value_counts()))
    print(f"installments==0: {int((pm.payment_installments == 0).sum())}  payment_value==0: "
          f"{int((pm.payment_value == 0).sum())}  max payment_sequential: {pm.payment_sequential.astype(int).max()}")
    paid = pm.groupby("order_id").payment_value.sum()
    owed = it.assign(total=it.price + it.freight_value).groupby("order_id").total.sum()
    both = pd.concat([paid.rename("paid"), owed.rename("owed")], axis=1, join="inner")
    diff = (both.paid - both.owed).round(2)
    print(f"orders with both payments and items: {len(both):,}")
    print(f"|paid - (price+freight)| > 0.01: {int((diff.abs() > 0.01).sum()):,}  "
          f"paid>owed: {int((diff > 0.01).sum()):,}  paid<owed: {int((diff < -0.01).sum()):,}  "
          f"max abs diff: {diff.abs().max():.2f}")

    section("Reviews")
    rv = to_ts(rev, ["review_creation_date", "review_answer_timestamp"])
    print(dict(rv.review_score.value_counts().sort_index()))
    per_order = rv.groupby("order_id").size()
    per_rid = rv.groupby("review_id").order_id.nunique()
    print(f"orders with >1 review: {int((per_order > 1).sum()):,}  review_ids spanning >1 order: {int((per_rid > 1).sum()):,}")
    print(f"answer < creation: {int((rv.review_answer_timestamp < rv.review_creation_date).sum())}")
    rp = rv.merge(o[["order_id", "order_purchase_timestamp"]], on="order_id")
    print(f"review created before purchase: {int((rp.review_creation_date < rp.order_purchase_timestamp).sum()):,}")

    section("Products")
    pr = df["products"]
    print(f"null category: {int(pr.product_category_name.isna().sum())}  distinct categories: {pr.product_category_name.nunique()}")
    w = pd.to_numeric(pr.product_weight_g, errors="coerce")
    print(f"weight==0: {int((w == 0).sum())}  weight null: {int(w.isna().sum())}")
    print(f"misspelled columns: {[col for col in pr.columns if 'lenght' in col]}")

    section("Geolocation")
    g = df["geolocation"].copy()
    lat = g.geolocation_lat.astype(float)
    lng = g.geolocation_lng.astype(float)
    print(f"distinct zip prefixes: {g.geolocation_zip_code_prefix.nunique():,}  "
          f"max rows per prefix: {g.groupby('geolocation_zip_code_prefix').size().max():,}")
    outside = ~lat.between(-34, 5.3) | ~lng.between(-74, -34.7)
    print(f"rows outside the bounding box: {int(outside.sum())}")
    cities = g.groupby("geolocation_zip_code_prefix").geolocation_city.nunique()
    print(f"prefixes with >1 city spelling: {int((cities > 1).sum()):,}")
    print(f"distinct cities raw={g.geolocation_city.nunique():,}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: scripts/profile_olist.py <data_dir>")
    main(sys.argv[1])
