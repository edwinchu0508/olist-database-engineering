"""The business queries (sql/queries/) against a second implementation.

Each query's result on the loaded test database must equal the same definition computed here in
plain Python from the CSV files, with the parameters declared in the query's header. The two share
nothing but the definitions in docs/queries.md: no SQL, no core tables.

The pitfall tests pin what each definition guards against, measured on the same data (the numbers
quoted in docs/queries.md).
"""
import csv
import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

import pytest

from olist_dbe import load, queries

QUERIES = {q.name: q for q in queries.all_queries()}
OPEN = {"created", "approved", "invoiced", "processing", "shipped"}


def pg_round(value: Fraction, places: int = 2) -> Decimal:
    """round(numeric, places) of PostgreSQL: half away from zero."""
    with localcontext() as ctx:
        ctx.prec = 60
        exact = Decimal(value.numerator) / Decimal(value.denominator)
        return exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def ts(text: str) -> datetime.datetime | None:
    return datetime.datetime.fromisoformat(text) if text else None


@pytest.fixture(scope="module")
def src(data_dir):
    def rows(table):
        # utf-8-sig: the translation file starts with a byte-order mark.
        with (data_dir / load.SOURCE_FILES[table]).open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    s = {}
    s["customers"] = {r["customer_id"]: (r["customer_unique_id"], r["customer_state"]) for r in rows("customers")}
    s["orders"] = [
        {"id": r["order_id"], "customer": r["customer_id"], "status": r["order_status"],
         "purchase": ts(r["order_purchase_timestamp"]), "delivered": ts(r["order_delivered_customer_date"]),
         "estimated": ts(r["order_estimated_delivery_date"]).date()}
        for r in rows("orders")
    ]
    s["items"] = [(r["order_id"], r["seller_id"], r["product_id"], Decimal(r["price"]), Decimal(r["freight_value"]))
                  for r in rows("order_items")]
    s["payments"] = [(r["order_id"], Decimal(r["payment_value"])) for r in rows("order_payments")]
    s["reviews"] = [(r["order_id"], int(r["review_score"])) for r in rows("order_reviews")]
    s["products"] = {r["product_id"]: r["product_category_name"] or None for r in rows("products")}
    s["translation"] = {r["product_category_name"]: r["product_category_name_english"]
                        for r in rows("product_category_name_translation")}
    s["sellers"] = {r["seller_id"]: r["seller_state"] for r in rows("sellers")}
    return s


def run_sql(conn, name):
    q = QUERIES[name]
    columns, rows = queries.execute(conn, q.text, q.params)
    return columns, [tuple(queries.canonical(v) for v in row) for row in rows]


def canonical(rows):
    return [tuple(queries.canonical(v) for v in row) for row in rows]


def items_by_order(src):
    totals = defaultdict(lambda: [0, Decimal(0), Decimal(0)])
    for order, _, _, price, freight in src["items"]:
        t = totals[order]
        t[0] += 1
        t[1] += price
        t[2] += freight
    return totals


def q1(src, p):
    ids = {cid for cid, (person, _) in src["customers"].items() if person == p["customer_unique_id"].replace("-", "")}
    items = items_by_order(src)
    paid = defaultdict(Decimal)
    for order, value in src["payments"]:
        paid[order] += value
    rows = [(o["id"], o["purchase"], o["status"], *items.get(o["id"], (0, Decimal(0), Decimal(0))), paid.get(o["id"], Decimal(0)))
            for o in src["orders"] if o["customer"] in ids]
    rows.sort(key=lambda r: r[0])
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def q2(src, p):
    as_of = datetime.datetime.fromisoformat(p["as_of"])
    start = as_of - datetime.timedelta(days=30)
    orders = {o["id"]: o for o in src["orders"] if start <= o["purchase"] < as_of}
    per_order = defaultdict(lambda: [0, Decimal(0), Decimal(0)])
    for order, seller, _, price, freight in src["items"]:
        if seller == p["seller_id"].replace("-", "") and order in orders:
            t = per_order[order]
            t[0] += 1
            t[1] += price
            t[2] += freight
    rows = [(o, orders[o]["purchase"], orders[o]["status"], *t) for o, t in per_order.items()]
    rows.sort(key=lambda r: r[0])
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def q3(src, p):
    as_of = datetime.date.fromisoformat(p["as_of"])
    rows = [(o["id"], o["status"], o["purchase"], (as_of - o["purchase"].date()).days, src["customers"][o["customer"]][1])
            for o in src["orders"] if o["status"] in OPEN]
    return sorted(rows, key=lambda r: (r[2], r[0]))


def daily_or_monthly(src, keys, key_of, start, end):
    value = defaultdict(Decimal)
    for order, _, _, price, freight in src["items"]:
        value[order] += price + freight
    acc = {k: [0, Decimal(0), Decimal(0)] for k in keys}
    for o in src["orders"]:
        if start <= o["purchase"] < end:
            a = acc[key_of(o["purchase"])]
            a[0] += 1
            a[1] += value.get(o["id"], Decimal(0))
            if o["status"] == "delivered":
                a[2] += value.get(o["id"], Decimal(0))
    return [(k, *acc[k]) for k in keys]


def q4(src, p):
    start, end = (datetime.datetime.fromisoformat(p[k]) for k in ("from", "to"))
    days = [(start + datetime.timedelta(days=n)).date() for n in range((end - start).days)]
    return daily_or_monthly(src, days, lambda t: t.date(), start, end)


def next_month(m: datetime.date) -> datetime.date:
    return datetime.date(m.year + m.month // 12, m.month % 12 + 1, 1)


def q5(src, p):
    first, last = (datetime.date.fromisoformat(p[k]) for k in ("from_month", "to_month"))
    keys = [first]
    while keys[-1] < last:
        keys.append(next_month(keys[-1]))
    start, end = (datetime.datetime.combine(d, datetime.time()) for d in (first, next_month(last)))
    base = daily_or_monthly(src, keys, lambda t: t.date().replace(day=1), start, end)

    def growth(cur, prev):
        return None if prev is None or prev == 0 else pg_round(Fraction(100) * (Fraction(cur) - Fraction(prev)) / Fraction(prev))

    rows, previous = [], None
    for month, orders, gmv, delivered in base:
        rows.append((month, orders, gmv, delivered,
                     growth(gmv, previous and previous[0]), growth(delivered, previous and previous[1])))
        previous = (gmv, delivered)
    return rows


def q6(src, p):
    first, last = (datetime.date.fromisoformat(p[k]) for k in ("from_month", "to_month"))
    activity = defaultdict(set)  # person -> months with a delivered order
    for o in src["orders"]:
        if o["status"] == "delivered":
            activity[src["customers"][o["customer"]][0]].add(o["purchase"].date().replace(day=1))
    active = defaultdict(set)
    for person, ms in activity.items():
        cohort = min(ms)
        if first <= cohort <= last:
            for m in ms:
                active[(cohort, (m.year - cohort.year) * 12 + m.month - cohort.month)].add(person)
    rows = []
    for (cohort, n), persons in sorted(active.items()):
        size = len(active[(cohort, 0)])
        rows.append((cohort, n, len(persons), size, pg_round(Fraction(100 * len(persons), size))))
    return rows


def q7(src, p):
    scores = defaultdict(list)
    for order, score in src["reviews"]:
        scores[order].append(score)
    buckets = defaultdict(list)  # bucket -> per-order score or None
    for o in src["orders"]:
        if o["status"] == "delivered" and o["delivered"] is not None:
            delay = (o["delivered"].date() - o["estimated"]).days
            bucket = 1 if delay <= 0 else 2 if delay <= 3 else 3 if delay <= 7 else 4
            s = scores.get(o["id"])
            buckets[bucket].append(Fraction(sum(s), len(s)) if s else None)
    names = {1: "on time or early", 2: "1-3 days late", 3: "4-7 days late", 4: "8+ days late"}
    rows = []
    for b in sorted(buckets):
        reviewed = [s for s in buckets[b] if s is not None]
        rows.append((names[b], len(buckets[b]), len(reviewed), pg_round(sum(reviewed) / len(reviewed)),
                     pg_round(Fraction(100 * sum(1 for s in reviewed if s <= 2), len(reviewed)))))
    return rows


def q8(src, p):
    start, end = (datetime.datetime.fromisoformat(p[k]) for k in ("from", "to"))
    delivered = {o["id"] for o in src["orders"] if o["status"] == "delivered" and start <= o["purchase"] < end}
    acc = defaultdict(lambda: [set(), 0, Decimal(0)])
    for order, seller, product, price, _ in src["items"]:
        if order in delivered:
            pt = src["products"][product]
            category = src["translation"].get(pt) or pt or "(no category)"
            a = acc[(category, seller)]
            a[0].add(order)
            a[1] += 1
            a[2] += price
    by_category = defaultdict(list)
    for (category, seller), (orders, items, revenue) in acc.items():
        by_category[category].append((seller, len(orders), items, revenue))
    rows = []
    for category, sellers in by_category.items():
        total = sum(s[3] for s in sellers)
        for seller, orders, items, revenue in sellers:
            rank = 1 + sum(1 for s in sellers if s[3] > revenue)
            if rank <= int(p["top_n"]):
                rows.append((category, rank, seller, src["sellers"][seller], orders, items, revenue,
                             pg_round(Fraction(100) * Fraction(revenue) / Fraction(total))))
    return sorted(rows, key=lambda r: (r[0], r[1], r[2]))


SECOND_IMPLEMENTATION = {
    "q1_customer_order_history": q1, "q2_seller_recent_orders": q2, "q3_open_orders": q3,
    "q4_daily_orders": q4, "q5_monthly_gmv": q5, "q6_cohort_retention": q6,
    "q7_delivery_delay_reviews": q7, "q8_top_sellers_by_category": q8,
}


def test_every_query_has_a_second_implementation():
    assert set(SECOND_IMPLEMENTATION) == set(QUERIES)


@pytest.mark.parametrize("name", sorted(SECOND_IMPLEMENTATION))
def test_query_matches_the_second_implementation(conn, loaded, src, name):
    _, rows = run_sql(conn, name)
    expected = canonical(SECOND_IMPLEMENTATION[name](src, QUERIES[name].params))
    assert rows, "the published parameters must select something"
    assert rows == expected


def test_render_substitutes_literals_and_requires_every_parameter(conn):
    assert queries.render(conn, "SELECT :'a'::date, x::text", {"a": "2018-01-01"}) == "SELECT '2018-01-01'::date, x::text"
    assert queries.render(conn, "SELECT :'a'", {"a": "it's"}) == "SELECT 'it''s'"
    with pytest.raises(ValueError, match="no value for b"):
        queries.render(conn, "SELECT :'a', :'b'", {"a": 1})


PITFALLS = [
    ("q1: orders with several items and several payments, which a joint join multiplies",
     "WITH i AS (SELECT order_id, count(*) AS n FROM core.order_items GROUP BY 1),"
     " p AS (SELECT order_id, count(*) AS n FROM core.order_payments GROUP BY 1)"
     " SELECT count(*) FROM i JOIN p USING (order_id) WHERE i.n > 1 AND p.n > 1", 275),
    ("q1: total paid over a joint join of items and payments, instead of 16,008,872.12",
     "SELECT sum(p.payment_value) FROM core.order_payments AS p JOIN core.order_items USING (order_id)",
     Decimal("20308134.71")),
    ("q4: orders of the window that BETWEEN on dates loses (the whole last day)",
     "SELECT count(*) FILTER (WHERE order_purchase_timestamp >= '2017-11-20' AND order_purchase_timestamp < '2017-11-27')"
     " - count(*) FILTER (WHERE order_purchase_timestamp BETWEEN '2017-11-20' AND '2017-11-26') FROM core.orders", 391),
    ("q6: customer_ids with more than one delivered order",
     "SELECT count(*) FROM (SELECT customer_id FROM core.orders WHERE order_status = 'delivered'"
     " GROUP BY 1 HAVING count(*) > 1) AS s", 0),
    ("q6: persons with delivered orders in more than one month",
     "SELECT count(*) FROM (SELECT c.customer_unique_id FROM core.orders AS o JOIN core.customers AS c USING (customer_id)"
     " WHERE o.order_status = 'delivered' GROUP BY 1"
     " HAVING count(DISTINCT date_trunc('month', o.order_purchase_timestamp)) > 1) AS s", 1_693),
    ("q7: deliveries on the estimated day that a timestamp comparison counts as late",
     "SELECT count(*) FROM core.orders WHERE order_status = 'delivered'"
     " AND order_delivered_customer_date::date = order_estimated_delivery_date"
     " AND order_delivered_customer_date > order_estimated_delivery_date", 1_292),
    ("q7: rows of orders joined directly to reviews, for 95,824 reviewed delivered orders",
     "SELECT count(*) FROM core.orders AS o JOIN core.order_reviews USING (order_id)"
     " WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL", 96_353),
    ("q5: items value of canceled and unavailable orders in 2017-01 to 2018-08, part of gmv only",
     "SELECT sum(i.price + i.freight_value) FROM core.orders AS o JOIN core.order_items AS i USING (order_id)"
     " WHERE o.order_status IN ('canceled', 'unavailable')"
     " AND o.order_purchase_timestamp >= '2017-01-01' AND o.order_purchase_timestamp < '2018-09-01'",
     Decimal("102496.83")),
]


@pytest.mark.parametrize("statement, expected", [p[1:] for p in PITFALLS], ids=[p[0] for p in PITFALLS])
def test_pitfall_measured_on_the_data(conn, loaded, statement, expected):
    assert conn.execute(statement).fetchone()[0] == expected
