# Test run 2026-10-29 22:57:28 UTC

- Command: `pytest -q --durations=5 --run-report docs/test_runs/2026-10-29-dev-cluster.md`
- Result: 59 passed in 306.6 s (exit status 0)
- Code fingerprint at start (SHA-256 of src, sql, tests, pyproject.toml, data_manifest.json): `85f408f4c257c2795456635eb5cf2ceb44d7d6589f8475baf47341222e1fe19b`

## Client

- Python 3.11.5 on Windows-10-10.0.26200-SP0
- psycopg 3.3.6, libpq 180004, pytest 9.2.0

## Server

- Target: `dbe_owner@localhost:55432/olist_dbe_test (test)`, verified (endpoint, database, role, not a superuser, purpose marker)
- PostgreSQL 18.6 on x86_64-windows, compiled by msvc-19.44.35228, 64-bit
- Database locale: provider `b`, locale `C.UTF-8`

| Setting | Value |
|---|---|
| TimeZone | America/Los_Angeles |
| data_checksums | on |
| effective_cache_size | 524288 8kB |
| effective_io_concurrency | 16 |
| fsync | on |
| jit | on |
| lc_messages | C |
| maintenance_work_mem | 65536 kB |
| max_parallel_workers_per_gather | 2 |
| random_page_cost | 4 |
| server_encoding | UTF8 |
| server_version | 18.6 |
| shared_buffers | 16384 8kB |
| synchronous_commit | on |
| work_mem | 4096 kB |

Settings not at their built-in default:

| Setting | Value | Source |
|---|---|---|
| DateStyle | ISO, YMD | configuration file |
| TimeZone | America/Los_Angeles | configuration file |
| autovacuum_worker_slots | 16 | configuration file |
| default_text_search_config | pg_catalog.simple | configuration file |
| dynamic_shared_memory_type | windows | configuration file |
| lc_messages | C | command line |
| lc_monetary | Chinese (Simplified)_China.936 | configuration file |
| lc_numeric | Chinese (Simplified)_China.936 | configuration file |
| lc_time | Chinese (Simplified)_China.936 | configuration file |
| listen_addresses | localhost | command line |
| log_file_mode | 0640 | configuration file |
| log_timezone | America/Los_Angeles | configuration file |
| max_connections | 100 | configuration file |
| max_wal_size | 1024 MB | configuration file |
| min_wal_size | 80 MB | configuration file |
| port | 55432 | command line |
| shared_buffers | 16384 8kB | configuration file |

## Source data

- 9 files in `D:\project`: all match data_manifest.json

## Tests

| Test | Outcome | Seconds |
|---|---|---:|
| `tests/test_core_schema.py::test_row_counts` | passed | 27.67 |
| `tests/test_core_schema.py::test_foreign_keys` | passed | 0.00 |
| `tests/test_core_schema.py::test_foreign_keys_are_deferrable_but_checked_immediately_by_default` | passed | 0.00 |
| `tests/test_core_schema.py::test_only_key_indexes_exist` | passed | 0.00 |
| `tests/test_core_schema.py::test_review_content_is_stored_once` | passed | 0.02 |
| `tests/test_core_schema.py::test_customer_unique_id_identifies_repeat_buyers` | passed | 0.17 |
| `tests/test_core_schema.py::test_constraint_rejects[price must be positive]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[unknown order status]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[approval before purchase]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[zip prefix with a letter]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[review score out of range]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[second order for one customer_id]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[item of an unknown product]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[deleting an order that has items]` | passed | 0.00 |
| `tests/test_core_schema.py::test_reader_role_can_read_but_not_write` | passed | 0.01 |
| `tests/test_derivations.py::test_review_split_round_trips_to_the_source_rows` | passed | 1.87 |
| `tests/test_derivations.py::test_review_whose_copies_disagree_is_refused` | passed | 15.29 |
| `tests/test_derivations.py::test_zip_prefix_geo_matches_an_independent_computation` | passed | 2.99 |
| `tests/test_dq.py::test_blocking_checks_pass_on_the_reference_data` | passed | 0.00 |
| `tests/test_dq.py::test_warning_counts_match_the_independent_profile` | passed | 0.00 |
| `tests/test_dq.py::test_violations_come_with_a_sample` | passed | 0.00 |
| `tests/test_load.py::test_first_load_inserts_every_row` | passed | 0.00 |
| `tests/test_load.py::test_reload_changes_nothing_and_closes_abandoned_runs` | passed | 22.02 |
| `tests/test_load.py::test_publish_changes_only_the_rows_that_changed` | passed | 42.42 |
| `tests/test_load.py::test_header_mismatch_fails_before_staging` | passed | 1.93 |
| `tests/test_load.py::test_file_changed_after_hashing_is_not_loaded` | passed | 3.28 |
| `tests/test_load.py::test_blocking_violation_stops_the_load_and_names_the_check` | passed | 14.06 |
| `tests/test_load.py::test_failure_inside_the_publish_transaction_rolls_back` | passed | 21.14 |
| `tests/test_load.py::test_snapshots_taken_before_a_load_keep_seeing_the_previous_version` | passed | 45.79 |
| `tests/test_load.py::test_connection_lost_before_commit_is_confirmed_as_not_published` | passed | 21.45 |
| `tests/test_load.py::test_connection_lost_after_commit_is_confirmed_and_cleanup_errors_do_not_fail_the_load` | passed | 42.82 |
| `tests/test_load.py::test_unverifiable_commit_is_raised_as_unknown_not_as_failure` | passed | 39.53 |
| `tests/test_load.py::test_commit_outcome_stays_unknown_while_the_publishing_session_lives` | passed | 0.67 |
| `tests/test_load.py::test_commit_outcome_is_unknown_when_the_server_cannot_be_reached` | passed | 2.01 |
| `tests/test_load.py::test_cli_exit_status_separates_unknown_outcome_from_failure` | passed | 0.01 |
| `tests/test_load.py::test_concurrent_load_is_rejected` | passed | 0.44 |
| `tests/test_source_files.py::test_missing_file_is_reported_by_name` | passed | 0.00 |
| `tests/test_source_files.py::test_source_files_are_the_reference_dataset` | passed | 0.28 |
| `tests/test_source_files.py::test_translation_header_is_read_without_its_byte_order_mark` | passed | 0.27 |
| `tests/test_source_files.py::test_every_dq_check_is_named_described_and_classified` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[matching]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other endpoint]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other database]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other role]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[switched role]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[superuser]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[no marker]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[main database]` | passed | 0.00 |
| `tests/test_target.py::test_connection_to_a_database_with_another_purpose_is_refused` | passed | 0.14 |
| `tests/test_target.py::test_connection_to_an_unmarked_database_is_refused` | passed | 0.04 |
| `tests/test_target.py::test_marker_is_read_from_the_catalog_not_the_session` | passed | 0.03 |
| `tests/test_target.py::test_stale_libpq_variables_do_not_redirect_connections` | passed | 0.03 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGHOSTADDR]` | passed | 0.00 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGSERVICE]` | passed | 0.00 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGOPTIONS]` | passed | 0.00 |
| `tests/test_target.py::test_test_database_name_must_end_in_test` | passed | 0.00 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[PGPASSWORD=secret-pgpass.conf]` | passed | 0.00 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[PGHOST=elsewhere-OLIST_DBE_]` | passed | 0.00 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[no separator-KEY=VALUE]` | passed | 0.00 |
