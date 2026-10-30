"""The published core: contents, keys, constraints and privileges.

Pinned numbers were measured independently with pandas on the reference files during the data
assessment, so these tests check the SQL pipeline against a second implementation.
"""
import psycopg
import pytest
from psycopg import errors

EXPECTED_ROWS = {
    "customers": 99_441,
    "order_items": 112_650,
    "order_payments": 103_886,
    "order_reviews": 99_224,
    "orders": 99_441,
    "product_categories": 73,
    "products": 32_951,
    "reviews": 98_410,  # 99,224 links minus 814 repeated copies of 789 shared reviews
    "sellers": 3_095,
    "zip_prefix_geo": 19_011,  # 19,015 prefixes minus 4 with no record inside the bounding box
}

EXPECTED_FOREIGN_KEYS = {
    ("core.products", "core.product_categories"),
    ("core.orders", "core.customers"),
    ("core.order_items", "core.orders"),
    ("core.order_items", "core.products"),
    ("core.order_items", "core.sellers"),
    ("core.order_payments", "core.orders"),
    ("core.order_reviews", "core.orders"),
    ("core.order_reviews", "core.reviews"),
}


def test_row_counts(baseline_checksums):
    assert {table: rows for table, (rows, _) in baseline_checksums.items()} == EXPECTED_ROWS


def test_foreign_keys(conn, loaded):
    rows = conn.execute(
        "SELECT conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint"
        " WHERE contype = 'f' AND connamespace = 'core'::regnamespace"
    ).fetchall()
    assert set(rows) == EXPECTED_FOREIGN_KEYS


def test_foreign_keys_are_deferrable_but_checked_immediately_by_default(conn, loaded):
    """Only the publish transaction defers them (SET CONSTRAINTS ALL DEFERRED)."""
    rows = conn.execute(
        "SELECT DISTINCT condeferrable, condeferred FROM pg_constraint"
        " WHERE contype = 'f' AND connamespace = 'core'::regnamespace"
    ).fetchall()
    assert rows == [(True, False)]


def test_unique_keys_other_than_primary_keys_are_deferrable(conn, loaded):
    """The MERGEs match on primary keys, so only those cannot collide halfway through a publish."""
    rows = conn.execute(
        "SELECT conname, condeferrable, condeferred FROM pg_constraint"
        " WHERE contype = 'u' AND connamespace = 'core'::regnamespace"
    ).fetchall()
    assert rows == [("orders_customer_id_key", True, False)]


def test_only_key_indexes_exist(conn, loaded):
    """The benchmark baseline has no secondary indexes; each one is added by an experiment."""
    rows = conn.execute(
        "SELECT i.indexrelid::regclass::text FROM pg_index AS i"
        " JOIN pg_class AS c ON c.oid = i.indrelid"
        " WHERE c.relnamespace = 'core'::regnamespace AND NOT i.indisprimary"
    ).fetchall()
    assert rows == [("core.orders_customer_id_key",)]


def test_review_content_is_stored_once(conn, loaded):
    shared = conn.execute(
        "SELECT count(*) FROM (SELECT review_id FROM core.order_reviews GROUP BY review_id HAVING count(*) > 1) AS s"
    ).fetchone()[0]
    assert shared == 789


def test_customer_unique_id_identifies_repeat_buyers(conn, loaded):
    per_customer_id, per_person = conn.execute(
        "SELECT count(*) FILTER (WHERE n_id > 1), count(DISTINCT customer_unique_id) FILTER (WHERE n_person > 1)"
        " FROM (SELECT c.customer_unique_id,"
        "              count(*) OVER (PARTITION BY o.customer_id) AS n_id,"
        "              count(*) OVER (PARTITION BY c.customer_unique_id) AS n_person"
        "       FROM core.orders AS o JOIN core.customers AS c USING (customer_id)) AS s"
    ).fetchone()
    assert per_customer_id == 0
    assert per_person == 2_997


REJECTED_CHANGES = [
    pytest.param(
        "UPDATE core.order_items SET price = 0"
        " WHERE (order_id, order_item_id) = (SELECT order_id, order_item_id FROM core.order_items LIMIT 1)",
        errors.CheckViolation, id="price must be positive"),
    pytest.param(
        "UPDATE core.orders SET order_status = 'lost' WHERE order_id = (SELECT order_id FROM core.orders LIMIT 1)",
        errors.CheckViolation, id="unknown order status"),
    pytest.param(
        "UPDATE core.orders SET order_approved_at = order_purchase_timestamp - interval '1 second'"
        " WHERE order_id = (SELECT order_id FROM core.orders LIMIT 1)",
        errors.CheckViolation, id="approval before purchase"),
    pytest.param(
        "UPDATE core.customers SET customer_zip_code_prefix = '1234A'"
        " WHERE customer_id = (SELECT customer_id FROM core.customers LIMIT 1)",
        errors.CheckViolation, id="zip prefix with a letter"),
    pytest.param(
        "UPDATE core.reviews SET review_score = 6 WHERE review_id = (SELECT review_id FROM core.reviews LIMIT 1)",
        errors.CheckViolation, id="review score out of range"),
    pytest.param(
        "INSERT INTO core.orders (order_id, customer_id, order_status, order_purchase_timestamp,"
        " order_estimated_delivery_date)"
        " SELECT gen_random_uuid(), customer_id, 'created', order_purchase_timestamp, order_estimated_delivery_date"
        " FROM core.orders LIMIT 1",
        errors.UniqueViolation, id="second order for one customer_id"),
    pytest.param(
        "INSERT INTO core.order_items"
        " SELECT order_id, 99, gen_random_uuid(), seller_id, shipping_limit_date, price, freight_value"
        " FROM core.order_items LIMIT 1",
        errors.ForeignKeyViolation, id="item of an unknown product"),
    pytest.param(
        "DELETE FROM core.orders WHERE order_id = (SELECT order_id FROM core.order_items LIMIT 1)",
        errors.ForeignKeyViolation, id="deleting an order that has items"),
]


@pytest.mark.parametrize(("statement", "error"), REJECTED_CHANGES)
def test_constraint_rejects(conn, loaded, statement, error):
    with conn.transaction(force_rollback=True):
        with pytest.raises(error):
            conn.execute(statement)


def test_reader_role_can_read_but_not_write(conn, loaded):
    with conn.transaction(force_rollback=True):
        conn.execute("SET LOCAL ROLE dbe_reader")
        assert conn.execute("SELECT count(*) FROM core.orders").fetchone()[0] == EXPECTED_ROWS["orders"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM core.order_payments")
