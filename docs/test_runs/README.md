# Test run records

Each file is written by `pytest --run-report <file>` (`tests/run_report.py`) at the end of a run: the
command, outcome per test, client and server versions, the server's configuration, the check of the
source files against `data_manifest.json`, and a SHA-256 fingerprint of the code taken when the run
started.

| Record | Instance |
|---|---|
| [2026-10-29-dev-cluster.md](2026-10-29-dev-cluster.md) | A throwaway PostgreSQL 18.6 cluster created with `initdb` for independent testing (port 55432, local trust authentication, locale settings as listed). It was deleted after this run. Not the PostgreSQL 18 service the project is meant to run on. |
| [2026-10-29-lab-cluster.md](2026-10-29-lab-cluster.md) | The business queries and the benchmark harness (113 tests). The "lab" cluster: a throwaway PostgreSQL 18.6 cluster created with `initdb` (port 55433, local trust authentication, default configuration), bootstrapped with `olist-dbe bootstrap` and loaded once on the main database. The same cluster then ran the three benchmark runs in [docs/benchmarks/runs/](../benchmarks/runs/), after this suite and with no other session. `tests/test_bootstrap.py` ran on a further cluster of its own. The lab cluster was deleted after the benchmarks. Not the shared PostgreSQL 18 service. |
| [2026-10-29-dev-cluster-2.md](2026-10-29-dev-cluster-2.md) | The fixes of the second review (bootstrap checks, confirmation deadline covering its queries, deferrable `orders.customer_id`). A new throwaway PostgreSQL 18.6 cluster made the same way, bootstrapped with `olist-dbe bootstrap` (dry run, then the real run), then `check`, `check --test`, `init`, and `load` twice on the main database before the suite. `tests/test_bootstrap.py` ran on a further cluster of its own, which it created and stopped. The main cluster was deleted after the run. Not the shared PostgreSQL 18 service. |
