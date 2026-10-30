"""DQ results on the reference dataset.

The warning counts were measured independently with pandas during the data assessment; the SQL
checks must reproduce every one of them exactly.
"""

EXPECTED_WARNINGS = {
    "category_missing_translation": 2,  # categories
    "customer_zip_without_geolocation": 157,  # zip prefixes
    "geolocation_city_spellings": 8_556,  # zip prefixes
    "geolocation_duplicate_rows": 261_831,
    "geolocation_outside_bbox": 31,  # file rows
    "geolocation_prefix_without_valid_point": 4,  # zip prefixes
    "orders_carrier_before_approval": 1_359,
    "orders_carrier_before_purchase": 166,
    "orders_delivered_before_carrier": 23,
    "orders_delivered_without_approval": 14,
    "orders_delivered_without_carrier_date": 2,
    "orders_delivered_without_delivery_date": 8,
    "orders_undelivered_with_delivery_date": 6,
    "orders_with_multiple_reviews": 547,
    "orders_without_items": 775,
    "orders_without_payments": 1,
    "orders_without_reviews": 768,
    "payments_total_mismatch": 303,
    "payments_type_not_defined": 3,
    "payments_zero_installments": 2,
    "payments_zero_value": 9,
    "product_category_missing": 610,
    "product_dimensions_missing": 2,
    "product_weight_zero": 4,
    "reviews_created_before_purchase": 74,
    "reviews_shared_across_orders": 789,  # reviews
    "seller_zip_multiple_states": 17,  # zip prefixes
    "seller_zip_without_geolocation": 7,  # zip prefixes
}


def results(conn, load_id: int, severity: str) -> dict[str, tuple[str, int | None]]:
    rows = conn.execute(
        "SELECT check_name, status, violations FROM dq.check_results WHERE load_id = %s AND severity = %s",
        (load_id, severity),
    )
    return {name: (status, violations) for name, status, violations in rows}


def test_blocking_checks_pass_on_the_reference_data(conn, loaded):
    blocking = results(conn, loaded.load_id, "blocking")
    assert blocking
    assert set(blocking.values()) == {("pass", 0)}


def test_warning_counts_match_the_independent_profile(conn, loaded):
    warnings = results(conn, loaded.load_id, "warning")
    assert {name: violations for name, (_, violations) in warnings.items()} == EXPECTED_WARNINGS
    assert {status for status, _ in warnings.values()} == {"warn"}


def test_violations_come_with_a_sample(conn, loaded):
    sample = conn.execute(
        "SELECT sample FROM dq.check_results WHERE load_id = %s AND check_name = 'payments_type_not_defined'",
        (loaded.load_id,),
    ).fetchone()[0]
    assert len(sample) == 3
    assert all(set(row) == {"order_id", "payment_sequential", "payment_value"} for row in sample)
