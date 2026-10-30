"""Loads publish into the fixed core tables in one transaction, load exactly the bytes they recorded,
and report their outcome truthfully: a load that fails before its commit leaves core untouched, a
failure after the commit is not reported as a failed load, and an unverifiable commit is reported as
unknown. Readers' snapshots always see one complete version."""
import dataclasses
import threading
import time

import pytest

from conftest import CATEGORY_QUERY, last_run
from olist_dbe import cli, db, load


def test_first_load_inserts_every_row(conn, loaded, baseline_checksums):
    status = conn.execute("SELECT status FROM meta.load_runs WHERE load_id = %s", (loaded.load_id,)).fetchone()[0]
    assert status == "succeeded"
    assert loaded.changes == {table: (rows, 0, 0) for table, (rows, _) in baseline_checksums.items()}
    assert load.recorded_changes(conn, loaded.load_id) == loaded.changes
    assert loaded.cleanup_errors == ()
    assert not loaded.confirmed_after_disconnect


def test_reload_changes_nothing_and_closes_abandoned_runs(conn, data_dir, target, baseline_checksums):
    abandoned = conn.execute(
        "INSERT INTO meta.load_runs (status, data_dir) VALUES ('running', 'simulated crash') RETURNING load_id"
    ).fetchone()[0]

    result = load.run_load(data_dir, target=target)

    assert last_run(conn)[:2] == (result.load_id, "succeeded")
    assert set(result.changes.values()) == {(0, 0, 0)}
    assert load.table_checksums(conn) == baseline_checksums
    status, error = conn.execute("SELECT status, error FROM meta.load_runs WHERE load_id = %s", (abandoned,)).fetchone()
    assert status == "failed" and error.startswith("abandoned")


def test_publish_changes_only_the_rows_that_changed(conn, data_dir, target, renamed, baseline_checksums):
    try:
        result = load.run_load(renamed, target=target)
        assert result.changes.pop("product_categories") == (0, 1, 0)
        assert set(result.changes.values()) == {(0, 0, 0)}
        assert conn.execute(CATEGORY_QUERY).fetchone() == ("health_beauty_v2",)
    finally:
        load.run_load(data_dir, target=target)
    assert load.table_checksums(conn) == baseline_checksums


def swap_customers_of_first_two_orders(text: str) -> tuple[str, tuple[str, str]]:
    lines = text.split("\n")
    a, b = lines[1].split(","), lines[2].split(",")
    a[1], b[1] = b[1], a[1]
    lines[1], lines[2] = ",".join(a), ",".join(b)
    return "\n".join(lines), (a[0].strip('"'), b[0].strip('"'))


def test_publish_accepts_two_orders_exchanging_their_customer_id(conn, data_dir, target, variant,
                                                                  baseline_checksums):
    """The new version satisfies UNIQUE (customer_id), but the MERGE updates one row at a time: the
    first update meets the other order's old value, which an immediate check would reject."""
    orders = load.SOURCE_FILES["orders"]
    _, (first, second) = swap_customers_of_first_two_orders((data_dir / orders).read_text(encoding="utf-8"))
    query = "SELECT order_id, customer_id FROM core.orders WHERE order_id = ANY(%s::uuid[])"
    before = {order.hex: customer for order, customer in conn.execute(query, ([first, second],))}
    swapped = variant(**{orders: lambda text: swap_customers_of_first_two_orders(text)[0]})
    try:
        result = load.run_load(swapped, target=target)
        assert result.changes.pop("orders") == (0, 2, 0)
        assert set(result.changes.values()) == {(0, 0, 0)}
        after = {order.hex: customer for order, customer in conn.execute(query, ([first, second],))}
        assert (after[first], after[second]) == (before[second], before[first])
    finally:
        load.run_load(data_dir, target=target)
    assert load.table_checksums(conn) == baseline_checksums


def test_header_mismatch_fails_before_staging(conn, target, variant, baseline_checksums):
    data = variant(**{"olist_sellers_dataset.csv": lambda text: text.replace('"seller_city"', '"seller_town"', 1)})

    with pytest.raises(load.SourceFileError, match="olist_sellers_dataset.csv"):
        load.run_load(data, target=target)

    load_id, status, _ = last_run(conn)
    assert status == "failed"
    assert conn.execute("SELECT count(*) FROM dq.check_results WHERE load_id = %s", (load_id,)).fetchone()[0] == 0
    assert load.table_checksums(conn) == baseline_checksums


def test_file_changed_after_hashing_is_not_loaded(conn, target, variant, baseline_checksums, monkeypatch):
    """The recorded SHA-256 must describe the bytes COPY actually received, not an earlier read."""
    data = variant(**{"olist_sellers_dataset.csv": lambda text: text})  # a private copy, safe to rewrite
    sellers = data / "olist_sellers_dataset.csv"
    check_headers = load._check_headers

    def check_headers_then_change_the_file(conn_, files):
        check_headers(conn_, files)
        sellers.write_bytes(sellers.read_bytes().replace(b"sao paulo", b"sao paulx", 1))

    monkeypatch.setattr(load, "_check_headers", check_headers_then_change_the_file)
    with pytest.raises(load.SourceFileError, match="olist_sellers_dataset.csv changed while it was being loaded"):
        load.run_load(data, target=target)

    load_id, status, _ = last_run(conn)
    assert status == "failed"
    # The staging transaction rolled back as a whole, and no check or publish ran on its contents.
    assert conn.execute("SELECT count(rows_loaded) FROM meta.load_files WHERE load_id = %s", (load_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM dq.check_results WHERE load_id = %s", (load_id,)).fetchone()[0] == 0
    assert load.table_checksums(conn) == baseline_checksums


def test_blocking_violation_stops_the_load_and_names_the_check(conn, target, variant, baseline_checksums):
    # Hour 25 in the purchase time of the first order.
    data = variant(**{"olist_orders_dataset.csv": lambda text: text.replace("2017-10-02 10:56:33", "2017-10-02 25:56:33", 1)})

    with pytest.raises(load.BlockingChecksFailed, match="timestamps_parse"):
        load.run_load(data, target=target)

    load_id, status, _ = last_run(conn)
    assert status == "failed"
    results = {
        name: (check_status, violations)
        for name, check_status, violations in conn.execute(
            "SELECT check_name, status, violations FROM dq.check_results WHERE load_id = %s AND severity = 'blocking'",
            (load_id,),
        )
    }
    assert results.pop("timestamps_parse") == ("fail", 1)
    # constraint_preconditions casts the same value, so it cannot run at all.
    assert results.pop("constraint_preconditions")[0] == "error"
    assert {status for status, _ in results.values()} == {"pass"}
    assert load.table_checksums(conn) == baseline_checksums


def test_failure_inside_the_publish_transaction_rolls_back(conn, target, renamed, baseline_checksums):
    with pytest.raises(load.InjectedFault):
        load.run_load(renamed, target=target, fault="publish")

    load_id, status, _ = last_run(conn)
    assert status == "failed"
    assert load.recorded_changes(conn, load_id) == {}
    assert load.table_checksums(conn) == baseline_checksums


def test_snapshots_taken_before_a_load_keep_seeing_the_previous_version(conn, data_dir, target, renamed,
                                                                         baseline_checksums):
    """REPEATABLE READ readers whose snapshot predates a load see exactly the previous version after it
    commits, whether they had already read core (b) or not touched it yet (a). The schema-swap publish
    this design replaced failed for reader a: it saw the new, empty-looking tables."""
    try:
        with db.connect(target) as a, db.connect(target) as b:
            a.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
            a.execute("SELECT count(*) FROM meta.load_runs")  # snapshot taken; core not touched yet
            b.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
            assert b.execute(CATEGORY_QUERY).fetchone() == ("health_beauty",)

            load.run_load(renamed, target=target)

            for reader in (a, b):
                assert load.table_checksums(reader) == baseline_checksums
                reader.execute("COMMIT")
        assert conn.execute(CATEGORY_QUERY).fetchone() == ("health_beauty_v2",)
    finally:
        load.run_load(data_dir, target=target)
    assert load.table_checksums(conn) == baseline_checksums


def test_connection_lost_before_commit_is_confirmed_as_not_published(conn, target, renamed, baseline_checksums):
    with pytest.raises(load.LoadError, match="not published"):
        load.run_load(renamed, target=target, fault="lost_before_commit")

    load_id, status, error = last_run(conn)
    assert status == "failed" and error.startswith("AdminShutdown")
    assert load.recorded_changes(conn, load_id) == {}
    assert load.table_checksums(conn) == baseline_checksums


def test_connection_lost_after_commit_is_confirmed_and_cleanup_errors_do_not_fail_the_load(
        conn, data_dir, target, renamed, baseline_checksums):
    try:
        result = load.run_load(renamed, target=target, fault="lost_after_commit")

        assert result.confirmed_after_disconnect
        assert result.changes["product_categories"] == (0, 1, 0)
        # Releasing the lock on the dead connection failed, and is reported as a cleanup error only.
        assert [e for e in result.cleanup_errors if e.startswith("releasing the loader lock failed")]
        assert last_run(conn)[:2] == (result.load_id, "succeeded")
        assert conn.execute(CATEGORY_QUERY).fetchone() == ("health_beauty_v2",)
    finally:
        load.run_load(data_dir, target=target)
    assert load.table_checksums(conn) == baseline_checksums


def test_unverifiable_commit_is_raised_as_unknown_not_as_failure(conn, data_dir, target, renamed, monkeypatch):
    monkeypatch.setattr(load, "confirm_publish", lambda *args, **kwargs: "unknown")
    try:
        with pytest.raises(load.PublishOutcomeUnknown, match="either the previous or the new version"):
            load.run_load(renamed, target=target, fault="lost_after_commit")
        # This run did commit, which is what the error tells the operator to check for.
        assert last_run(conn)[1] == "succeeded"
    finally:
        monkeypatch.undo()
        load.run_load(data_dir, target=target)
    assert not issubclass(load.PublishOutcomeUnknown, load.LoadError)


def test_commit_outcome_stays_unknown_while_the_publishing_session_lives(conn, target):
    """'running' is not proof of a rollback while the old session might still commit; once that
    session is gone, it is."""
    load_id = conn.execute(
        "INSERT INTO meta.load_runs (status, data_dir) VALUES ('running', 'simulated lost reply') RETURNING load_id"
    ).fetchone()[0]
    try:
        with db.connect(target) as publisher:
            backend = publisher.execute(
                "SELECT pid, backend_start FROM pg_stat_activity WHERE pid = pg_backend_pid()"
            ).fetchone()
            assert load.confirm_publish(target, load_id, backend, timeout=0.5) == "unknown"
        assert load.confirm_publish(target, load_id, backend) == "not_published"
        conn.execute(
            "UPDATE meta.load_runs SET status = 'succeeded', finished_at = clock_timestamp() WHERE load_id = %s",
            (load_id,),
        )
        assert load.confirm_publish(target, load_id, backend) == "published"
        assert load.confirm_publish(target, load_id, backend, timeout=0) == "unknown"  # no time to ask
    finally:
        conn.execute("DELETE FROM meta.load_runs WHERE load_id = %s", (load_id,))


def test_commit_outcome_is_unknown_when_the_server_cannot_be_reached(target):
    """Within a bounded time, even when connection attempts hang instead of failing fast."""
    unreachable = dataclasses.replace(target, host="127.0.0.1", port=1)
    started = time.monotonic()
    assert load.confirm_publish(unreachable, 1, (0, None), timeout=0.2) == "unknown"
    assert time.monotonic() - started < 5


def test_commit_outcome_is_unknown_in_time_when_the_confirming_query_is_blocked(conn, target):
    """The deadline covers the queries, not only the connection attempt: with meta.load_runs locked by
    another session the status read waits, and the answer is still 'unknown' within the timeout."""
    load_id = conn.execute(
        "INSERT INTO meta.load_runs (status, data_dir) VALUES ('running', 'simulated lost reply') RETURNING load_id"
    ).fetchone()[0]
    outcome = []
    try:
        with db.connect(target) as locker:
            # The locking session stands in for the publisher: it is alive, so 'running' is not final.
            backend = locker.execute(
                "SELECT pid, backend_start FROM pg_stat_activity WHERE pid = pg_backend_pid()"
            ).fetchone()
            locker.execute("BEGIN")
            locker.execute("LOCK TABLE meta.load_runs IN ACCESS EXCLUSIVE MODE")
            confirming = threading.Thread(
                target=lambda: outcome.append(load.confirm_publish(target, load_id, backend, timeout=1)), daemon=True)
            started = time.monotonic()
            confirming.start()
            confirming.join(timeout=15)
            elapsed = time.monotonic() - started
            still_waiting = confirming.is_alive()
            locker.execute("ROLLBACK")
            confirming.join()
        assert not still_waiting, "confirm_publish() was still waiting for the lock after 15 s"
        assert outcome == ["unknown"]
        assert elapsed < 3
    finally:
        conn.execute("DELETE FROM meta.load_runs WHERE load_id = %s", (load_id,))


def test_cli_exit_status_separates_unknown_outcome_from_failure(monkeypatch, tmp_path, capsys):
    def raising(exc):
        def run_load(*args, **kwargs):
            raise exc
        return run_load

    monkeypatch.setattr(load, "run_load", raising(load.PublishOutcomeUnknown("simulated")))
    assert cli.main(["load", "--data-dir", str(tmp_path)]) == 3
    monkeypatch.setattr(load, "run_load", raising(load.LoadError("simulated")))
    assert cli.main(["load", "--data-dir", str(tmp_path)]) == 1
    assert "OUTCOME UNKNOWN" in capsys.readouterr().err


def test_concurrent_load_is_rejected(conn, data_dir, target):
    runs_before = conn.execute("SELECT count(*) FROM meta.load_runs").fetchone()[0]
    with db.connect(target) as other:
        other.execute("SELECT pg_advisory_lock(%s)", (load.LOCK_KEY,))
        try:
            with pytest.raises(load.LoadInProgress):
                load.run_load(data_dir, target=target)
        finally:
            other.execute("SELECT pg_advisory_unlock(%s)", (load.LOCK_KEY,))
    assert conn.execute("SELECT count(*) FROM meta.load_runs").fetchone()[0] == runs_before
