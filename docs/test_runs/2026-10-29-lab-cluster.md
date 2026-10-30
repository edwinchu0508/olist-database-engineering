# Test run 2026-10-30 03:12:33 UTC

- Command: `pytest -q --run-report docs/test_runs/2026-10-29-lab-cluster.md`
- Result: 113 passed in 441.7 s (exit status 0)
- Code fingerprint at start (SHA-256 of src, sql, tests, pyproject.toml, data_manifest.json; see provenance.py): `0bb83ee0e24af34e941203c59a821850d76c24f63e0fc7ef59d2e222c2743543`

## Client

- Python 3.11.5 on Windows-10-10.0.26200-SP0
- psycopg 3.3.6, libpq 180004, pytest 9.2.0
- PostgreSQL programs (psql for the bootstrap; initdb and pg_ctl for its test cluster): `C:\Program Files\PostgreSQL\18\bin` (psql (PostgreSQL) 18.6)

## Server

- Target: `dbe_owner@localhost:55433/olist_dbe_test (test)`, verified (endpoint, database, role, not a superuser, purpose marker)
- PostgreSQL 18.6 on x86_64-windows, compiled by msvc-19.44.35228, 64-bit
- Database locale: provider `b`, locale `C.UTF-8`

| Setting | Value |
|---|---|
| TimeZone | America/Los_Angeles |
| data_checksums | on |
| effective_cache_size | 4GB |
| effective_io_concurrency | 16 |
| fsync | on |
| jit | on |
| lc_messages | C |
| maintenance_work_mem | 64MB |
| max_parallel_workers_per_gather | 2 |
| random_page_cost | 4 |
| server_encoding | UTF8 |
| server_version | 18.6 |
| shared_buffers | 128MB |
| synchronous_commit | on |
| work_mem | 4MB |

Settings not at their built-in default:

| Setting | Value | Source |
|---|---|---|
| DateStyle | ISO, YMD | configuration file |
| TimeZone | America/Los_Angeles | configuration file |
| autovacuum_worker_slots | 16 | configuration file |
| default_text_search_config | pg_catalog.simple | configuration file |
| dynamic_shared_memory_type | windows | configuration file |
| lc_messages | C | configuration file |
| lc_monetary | Chinese (Simplified)_China.936 | configuration file |
| lc_numeric | Chinese (Simplified)_China.936 | configuration file |
| lc_time | Chinese (Simplified)_China.936 | configuration file |
| listen_addresses | localhost | command line |
| log_file_mode | 0640 | configuration file |
| log_timezone | America/Los_Angeles | configuration file |
| max_connections | 100 | configuration file |
| max_wal_size | 1GB | configuration file |
| min_wal_size | 80MB | configuration file |
| port | 55433 | command line |
| shared_buffers | 128MB | configuration file |

## Source data

- 9 files in `D:\project`: all match data_manifest.json

## Tests

| Test | Outcome | Seconds |
|---|---|---:|
| `tests/test_bench.py::test_experiments_cover_at_least_five_queries` | passed | 0.00 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[two factors]` | passed | 0.01 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[no factor]` | passed | 0.00 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[index in the reference]` | passed | 0.01 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[index outside the bench_ prefix]` | passed | 0.00 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[missing rewrite file]` | passed | 0.01 |
| `tests/test_bench.py::test_an_experiment_must_change_exactly_one_named_factor[diagnostic without settings]` | passed | 0.00 |
| `tests/test_bench.py::test_rewrite_returns_the_reference_result[E5-q4_daily_orders_cast_to_date]` | passed | 29.64 |
| `tests/test_bench.py::test_rewrite_returns_the_reference_result[E7-q6_cohort_retention_window]` | passed | 0.49 |
| `tests/test_bench.py::test_experiment_times_every_variant_and_restores_the_key_indexes` | passed | 0.48 |
| `tests/test_bench.py::test_variant_with_a_different_result_is_not_timed` | passed | 0.28 |
| `tests/test_bench.py::test_run_refuses_an_index_it_does_not_own_and_drops_its_leftovers` | passed | 0.62 |
| `tests/test_bench.py::test_report_renders_from_a_run` | passed | 0.74 |
| `tests/test_bootstrap.py::test_creates_the_roles_and_marked_databases_and_a_rerun_changes_nothing` | passed | 7.89 |
| `tests/test_bootstrap.py::test_dry_run_reports_the_plan_and_changes_nothing` | passed | 1.02 |
| `tests/test_bootstrap.py::test_unmarked_databases_are_adopted_only_when_named` | passed | 2.43 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[database owned by another role]` | passed | 1.58 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[database with another collation]` | passed | 0.88 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[database marked for the other purpose]` | passed | 1.27 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[database with other settings]` | passed | 1.93 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[schema this project does not create]` | passed | 2.02 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[table in public]` | passed | 2.17 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[core table owned by another role]` | passed | 1.97 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[function]` | passed | 2.00 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role with other attributes]` | passed | 1.10 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[reader role that can log in]` | passed | 0.32 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role with another membership]` | passed | 0.31 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role granted to another role]` | passed | 0.32 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role with settings]` | passed | 0.33 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role owning another database]` | passed | 0.74 |
| `tests/test_bootstrap.py::test_refuses_a_mismatching_role_or_database_before_changing_anything[role with privileges in another database]` | passed | 0.48 |
| `tests/test_bootstrap.py::test_refuses_the_wrong_session` | passed | 2.40 |
| `tests/test_bootstrap.py::test_connection_settings_in_the_environment_do_not_reach_psql` | passed | 3.56 |
| `tests/test_core_schema.py::test_row_counts` | passed | 1.77 |
| `tests/test_core_schema.py::test_foreign_keys` | passed | 0.00 |
| `tests/test_core_schema.py::test_foreign_keys_are_deferrable_but_checked_immediately_by_default` | passed | 0.00 |
| `tests/test_core_schema.py::test_unique_keys_other_than_primary_keys_are_deferrable` | passed | 0.00 |
| `tests/test_core_schema.py::test_only_key_indexes_exist` | passed | 0.00 |
| `tests/test_core_schema.py::test_review_content_is_stored_once` | passed | 0.03 |
| `tests/test_core_schema.py::test_customer_unique_id_identifies_repeat_buyers` | passed | 0.19 |
| `tests/test_core_schema.py::test_constraint_rejects[price must be positive]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[unknown order status]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[approval before purchase]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[zip prefix with a letter]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[review score out of range]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[second order for one customer_id]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[item of an unknown product]` | passed | 0.00 |
| `tests/test_core_schema.py::test_constraint_rejects[deleting an order that has items]` | passed | 0.00 |
| `tests/test_core_schema.py::test_reader_role_can_read_but_not_write` | passed | 0.00 |
| `tests/test_derivations.py::test_review_split_round_trips_to_the_source_rows` | passed | 2.19 |
| `tests/test_derivations.py::test_review_whose_copies_disagree_is_refused` | passed | 18.83 |
| `tests/test_derivations.py::test_zip_prefix_geo_matches_an_independent_computation` | passed | 3.66 |
| `tests/test_dq.py::test_blocking_checks_pass_on_the_reference_data` | passed | 0.00 |
| `tests/test_dq.py::test_warning_counts_match_the_independent_profile` | passed | 0.00 |
| `tests/test_dq.py::test_violations_come_with_a_sample` | passed | 0.00 |
| `tests/test_load.py::test_first_load_inserts_every_row` | passed | 0.01 |
| `tests/test_load.py::test_reload_changes_nothing_and_closes_abandoned_runs` | passed | 24.54 |
| `tests/test_load.py::test_publish_changes_only_the_rows_that_changed` | passed | 48.42 |
| `tests/test_load.py::test_publish_accepts_two_orders_exchanging_their_customer_id` | passed | 48.56 |
| `tests/test_load.py::test_header_mismatch_fails_before_staging` | passed | 2.23 |
| `tests/test_load.py::test_file_changed_after_hashing_is_not_loaded` | passed | 3.72 |
| `tests/test_load.py::test_blocking_violation_stops_the_load_and_names_the_check` | passed | 16.35 |
| `tests/test_load.py::test_failure_inside_the_publish_transaction_rolls_back` | passed | 24.77 |
| `tests/test_load.py::test_snapshots_taken_before_a_load_keep_seeing_the_previous_version` | passed | 51.01 |
| `tests/test_load.py::test_connection_lost_before_commit_is_confirmed_as_not_published` | passed | 24.99 |
| `tests/test_load.py::test_connection_lost_after_commit_is_confirmed_and_cleanup_errors_do_not_fail_the_load` | passed | 48.85 |
| `tests/test_load.py::test_unverifiable_commit_is_raised_as_unknown_not_as_failure` | passed | 45.26 |
| `tests/test_load.py::test_commit_outcome_stays_unknown_while_the_publishing_session_lives` | passed | 0.62 |
| `tests/test_load.py::test_commit_outcome_is_unknown_when_the_server_cannot_be_reached` | passed | 2.00 |
| `tests/test_load.py::test_commit_outcome_is_unknown_in_time_when_the_confirming_query_is_blocked` | passed | 1.04 |
| `tests/test_load.py::test_cli_exit_status_separates_unknown_outcome_from_failure` | passed | 0.01 |
| `tests/test_load.py::test_concurrent_load_is_rejected` | passed | 0.38 |
| `tests/test_queries.py::test_every_query_has_a_second_implementation` | passed | 0.00 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q1_customer_order_history]` | passed | 1.29 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q2_seller_recent_orders]` | passed | 0.06 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q3_open_orders]` | passed | 0.05 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q4_daily_orders]` | passed | 0.07 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q5_monthly_gmv]` | passed | 0.28 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q6_cohort_retention]` | passed | 0.45 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q7_delivery_delay_reviews]` | passed | 0.49 |
| `tests/test_queries.py::test_query_matches_the_second_implementation[q8_top_sellers_by_category]` | passed | 0.48 |
| `tests/test_queries.py::test_render_substitutes_literals_and_requires_every_parameter` | passed | 0.00 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q1: orders with several items and several payments, which a joint join multiplies]` | passed | 0.06 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q1: total paid over a joint join of items and payments, instead of 16,008,872.12]` | passed | 0.14 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q4: orders of the window that BETWEEN on dates loses (the whole last day)]` | passed | 0.01 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q6: customer_ids with more than one delivered order]` | passed | 0.02 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q6: persons with delivered orders in more than one month]` | passed | 0.09 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q7: deliveries on the estimated day that a timestamp comparison counts as late]` | passed | 0.01 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q7: rows of orders joined directly to reviews, for 95,824 reviewed delivered orders]` | passed | 0.04 |
| `tests/test_queries.py::test_pitfall_measured_on_the_data[q5: items value of canceled and unavailable orders in 2017-01 to 2018-08, part of gmv only]` | passed | 0.07 |
| `tests/test_source_files.py::test_missing_file_is_reported_by_name` | passed | 0.00 |
| `tests/test_source_files.py::test_source_files_are_the_reference_dataset` | passed | 0.30 |
| `tests/test_source_files.py::test_translation_header_is_read_without_its_byte_order_mark` | passed | 0.32 |
| `tests/test_source_files.py::test_every_dq_check_is_named_described_and_classified` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[matching]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other endpoint]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other database]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[other role]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[switched role]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[superuser]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[no marker]` | passed | 0.00 |
| `tests/test_target.py::test_target_problems[main database]` | passed | 0.00 |
| `tests/test_target.py::test_connection_to_a_database_with_another_purpose_is_refused` | passed | 0.03 |
| `tests/test_target.py::test_connection_to_an_unmarked_database_is_refused` | passed | 0.04 |
| `tests/test_target.py::test_marker_is_read_from_the_catalog_not_the_session` | passed | 0.03 |
| `tests/test_target.py::test_stale_libpq_variables_do_not_redirect_connections` | passed | 0.04 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGHOSTADDR]` | passed | 0.00 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGSERVICE]` | passed | 0.00 |
| `tests/test_target.py::test_variables_that_override_explicit_parameters_are_refused[PGOPTIONS]` | passed | 0.00 |
| `tests/test_target.py::test_test_database_name_must_end_in_test` | passed | 0.00 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[PGPASSWORD=secret-pgpass.conf]` | passed | 0.00 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[PGHOST=elsewhere-OLIST_DBE_]` | passed | 0.01 |
| `tests/test_target.py::test_env_file_refuses_passwords_and_libpq_names[no separator-KEY=VALUE]` | passed | 0.01 |
