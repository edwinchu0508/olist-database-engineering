"""The benchmark harness (src/olist_dbe/bench.py) and its experiments (sql/bench/experiments.toml).

The harness creates and drops indexes, so these tests run it on the test database with a single
timed execution: what they check is the protocol (one factor per variant, the result compared before
timing, the key indexes restored), not the timings.
"""
import pytest

from olist_dbe import bench, queries

EXPERIMENTS = bench.load_experiments()
REWRITES = [(e, v) for e in EXPERIMENTS for v in e.variants if v.sql_file]


def by_id(exp_id: str) -> bench.Experiment:
    return next(e for e in EXPERIMENTS if e.id == exp_id)


def test_experiments_cover_at_least_five_queries():
    assert len({e.query.name for e in EXPERIMENTS}) >= 5


REFERENCE = '[[experiment.variant]]\nlabel = "reference"\n'
BAD_EXPERIMENTS = {
    "two factors": REFERENCE + '[[experiment.variant]]\nlabel = "x"\nsql = "q6_cohort_retention_window.sql"\n'
                   'index = { name = "bench_x", on = "core.sellers (seller_state)" }\n',
    "no factor": REFERENCE + '[[experiment.variant]]\nlabel = "x"\n',
    "index in the reference": '[[experiment.variant]]\nlabel = "r"\nindex = { name = "bench_x", on = "core.sellers (seller_state)" }\n'
                              '[[experiment.variant]]\nlabel = "x"\nsql = "q6_cohort_retention_window.sql"\n',
    "index outside the bench_ prefix": REFERENCE + '[[experiment.variant]]\nlabel = "x"\n'
                                       'index = { name = "sellers_state", on = "core.sellers (seller_state)" }\n',
    "missing rewrite file": REFERENCE + '[[experiment.variant]]\nlabel = "x"\nsql = "no_such_file.sql"\n',
    "diagnostic without settings": REFERENCE + '[[experiment.variant]]\nlabel = "x"\nsql = "q6_cohort_retention_window.sql"\n'
                                   'diagnostics = [{ label = "d", settings = {} }]\n',
}


@pytest.mark.parametrize("variants", BAD_EXPERIMENTS.values(), ids=BAD_EXPERIMENTS.keys())
def test_an_experiment_must_change_exactly_one_named_factor(tmp_path, variants):
    path = tmp_path / "experiments.toml"
    path.write_text('[[experiment]]\nid = "X"\nquery = "q6_cohort_retention"\nquestion = "q"\nhypothesis = "h"\n'
                    + variants, encoding="utf-8")
    with pytest.raises(bench.BenchError):
        bench.load_experiments(path)


@pytest.mark.parametrize("experiment, variant", REWRITES, ids=[f"{e.id}-{v.sql_file.stem}" for e, v in REWRITES])
def test_rewrite_returns_the_reference_result(conn, loaded, experiment, variant):
    original = queries.execute(conn, experiment.query.text, experiment.query.params)
    rewritten = queries.execute(conn, variant.sql_file.read_text(encoding="utf-8"), experiment.query.params)
    assert rewritten == original


def test_experiment_times_every_variant_and_restores_the_key_indexes(conn, loaded):
    experiment = by_id("E3")  # three variants: reference, full index, partial index; a diagnostic
    assert bench.extra_indexes(conn) == []
    record = bench.run_experiment(conn, experiment, warmup=0, repeat=1, progress=lambda line: None)
    assert bench.extra_indexes(conn) == []
    variants = record["variants"]
    assert [v["label"] for v in variants] == [v.label for v in experiment.variants]
    assert all(v["matches_reference"] and len(v["client_ms"]) == len(v["execution_ms"]) == 1 for v in variants)
    assert len({v["fingerprint"] for v in variants}) == 1
    assert variants[0]["index"] is None and all(v["index"]["size_bytes"] > 0 for v in variants[1:])
    assert variants[2]["index"]["size_bytes"] < variants[1]["index"]["size_bytes"]  # the partial index
    assert any("bench_orders_status" in path for path in variants[1]["access_paths"])
    diagnostic = variants[0]["diagnostics"][0]
    assert diagnostic["matches_reference"] and diagnostic["settings"] == {"max_parallel_workers_per_gather": "0"}
    # SET LOCAL ended with the diagnostic's transaction.
    assert conn.execute("SELECT current_setting('max_parallel_workers_per_gather')").fetchone()[0] != "0"


def test_variant_with_a_different_result_is_not_timed(conn, loaded, tmp_path):
    original = by_id("E3")
    changed = tmp_path / "q3_without_shipped.sql"
    changed.write_text(original.query.text.replace(", 'shipped')", ")"), encoding="utf-8")
    experiment = bench.Experiment("T", original.query, "q", "h", (),
                                  (original.variants[0], bench.Variant("without shipped", sql_file=changed)))
    record = bench.run_experiment(conn, experiment, warmup=0, repeat=1, progress=lambda line: None)
    reference, variant = record["variants"]
    assert reference["matches_reference"] and "client_ms" in reference
    assert not variant["matches_reference"] and "client_ms" not in variant
    assert variant["rows"] < reference["rows"]


def test_run_refuses_an_index_it_does_not_own_and_drops_its_leftovers(conn, loaded):
    conn.execute("CREATE INDEX sellers_state_test ON core.sellers (seller_state)")
    try:
        with pytest.raises(bench.BenchError, match="sellers_state_test"):
            bench.run(conn, [], progress=lambda line: None)
    finally:
        conn.execute("DROP INDEX core.sellers_state_test")
    conn.execute("CREATE INDEX bench_leftover ON core.sellers (seller_state)")
    record = bench.run(conn, [], progress=lambda line: None)
    assert record["protocol"]["dropped_leftover_indexes"] == ["bench_leftover"]
    assert bench.extra_indexes(conn) == []
    assert conn.prepare_threshold is not None  # restored after the run


def test_report_renders_from_a_run(conn, loaded):
    record = bench.run(conn, [by_id("E5")], warmup=0, repeat=2, progress=lambda line: None)
    text = bench.render_report([record], EXPERIMENTS)
    assert "## E5:" in text and "Hypothesis, written before measuring" in text
    assert "range on order_purchase_timestamp::date" in text and "**differs**" not in text
