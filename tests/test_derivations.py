"""The core tables that are derived rather than copied, checked against the source files directly.

- reviews + order_reviews (the 2NF split): joined back, they reproduce the source review file field
  by field, as a multiset, and a review whose copies disagree is refused instead of being collapsed.
- zip_prefix_geo: recomputed in Python from the geolocation file with the documented rules, it
  matches core exactly.

Both comparisons read the CSV files with Python's csv module, independently of COPY and the SQL.
"""
import csv
import re
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime

import pytest

from conftest import last_run
from olist_dbe import load

REVIEWS_FILE = "olist_order_reviews_dataset.csv"
GEOLOCATION_FILE = "olist_geolocation_dataset.csv"
LAT_RANGE, LNG_RANGE = (-34.0, 5.3), (-74.0, -28.8)  # the bounding box of sql/core/sources/10_zip_prefix_geo.sql


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def text(value):
    # The csv module cannot tell an unquoted empty field (NULL for COPY) from a quoted one (''), so
    # both sides compare NULL and '' as equal.
    return value or ""


def timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def test_review_split_round_trips_to_the_source_rows(conn, loaded, data_dir):
    source = Counter(
        (uuid.UUID(row["review_id"]), uuid.UUID(row["order_id"]), int(row["review_score"]),
         text(row["review_comment_title"]), text(row["review_comment_message"]),
         timestamp(row["review_creation_date"]), timestamp(row["review_answer_timestamp"]))
        for row in read_csv(data_dir / REVIEWS_FILE)
    )
    rejoined = Counter(
        (review_id, order_id, score, text(title), text(message), created, answered)
        for review_id, order_id, score, title, message, created, answered in conn.execute(
            "SELECT r.review_id, o.order_id, r.review_score, r.review_comment_title, r.review_comment_message,"
            "       r.review_creation_date, r.review_answer_timestamp"
            " FROM core.order_reviews AS o JOIN core.reviews AS r USING (review_id)"
        )
    )
    assert sum(source.values()) == sum(rejoined.values()) == 99_224
    assert rejoined == source


def test_review_whose_copies_disagree_is_refused(conn, target, variant, baseline_checksums):
    review_id = conn.execute(
        "SELECT review_id FROM core.order_reviews GROUP BY review_id HAVING count(*) > 1 ORDER BY review_id LIMIT 1"
    ).fetchone()[0]
    # The first copy of that review gets another score; its other copies keep theirs.
    first_copy = re.compile(rf'^("{review_id.hex}","[0-9a-f]{{32}}",)([1-5]),', re.MULTILINE)

    def change_one_copy(text: str) -> str:
        match = first_copy.search(text)
        assert match, review_id
        other_score = "1" if match[2] != "1" else "2"
        return text[:match.start(2)] + other_score + text[match.end(2):]

    data = variant(**{REVIEWS_FILE: change_one_copy})
    with pytest.raises(load.BlockingChecksFailed, match="review_content_consistent"):
        load.run_load(data, target=target)

    load_id, status, _ = last_run(conn)
    assert status == "failed"
    blocking = dict(conn.execute(
        "SELECT check_name, violations FROM dq.check_results WHERE load_id = %s AND severity = 'blocking'"
        " AND status <> 'pass'", (load_id,)
    ).fetchall())
    assert blocking == {"review_content_consistent": 1}
    sample = conn.execute(
        "SELECT sample FROM dq.check_results WHERE load_id = %s AND check_name = 'review_content_consistent'", (load_id,)
    ).fetchone()[0]
    assert [row["review_id"] for row in sample] == [review_id.hex]
    assert load.table_checksums(conn) == baseline_checksums


def test_zip_prefix_geo_matches_an_independent_computation(conn, loaded, data_dir):
    """The documented rules: one record per distinct (prefix, lat, lng, city, state), coordinates
    compared as numbers; records outside the bounding box dropped; per prefix the median lat and lng
    and the most frequent city and state (ties: first in code-point order), all over records."""
    records = {
        (row["geolocation_zip_code_prefix"], float(row["geolocation_lat"]), float(row["geolocation_lng"]),
         row["geolocation_city"], row["geolocation_state"])
        for row in read_csv(data_dir / GEOLOCATION_FILE)
    }
    by_prefix = defaultdict(list)
    for prefix, lat, lng, city, state in records:
        if LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]:
            by_prefix[prefix].append((lat, lng, city, state))

    def mode(values):
        counts = Counter(values)
        return min(counts, key=lambda v: (-counts[v], v))

    expected = {
        prefix: (statistics.median(r[0] for r in rows), statistics.median(r[1] for r in rows),
                 mode(r[2] for r in rows), mode(r[3] for r in rows), len(rows))
        for prefix, rows in by_prefix.items()
    }
    actual = {
        prefix: (lat, lng, city, state, points)
        for prefix, lat, lng, city, state, points in conn.execute(
            "SELECT zip_code_prefix, lat, lng, city, state, source_points FROM core.zip_prefix_geo"
        )
    }
    assert actual.keys() == expected.keys()
    assert len(actual) == 19_011
    mismatched = [
        prefix for prefix, (lat, lng, city, state, points) in actual.items()
        if (city, state, points) != expected[prefix][2:]
        or abs(lat - expected[prefix][0]) > 1e-9 or abs(lng - expected[prefix][1]) > 1e-9
    ]
    assert mismatched == []
