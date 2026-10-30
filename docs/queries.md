# Business queries

Eight queries, one file each in [`sql/queries/`](../sql/queries/). They are the workload planned in
the [assessment](olist_dbe_assessment.md) (§6), where Q4 and Q5 were the same time-window report
measured two ways; here that is one query (Q4), and the non-sargable rewrite is one of its
[experiments](benchmarks.md) (E5).
Each file's header holds the full definition and the parameter values behind the
[saved results](query_results/README.md). A file runs unchanged in psql with `-v name=value`, and
`olist-dbe queries` runs them all with those values.

Every result is checked against a second implementation: `tests/test_queries.py` recomputes each
definition in plain Python from the CSV files, without SQL or the core tables, and the rows must be
equal.

## Definitions

Shared terms:
- A **person** is `customer_unique_id`; `customer_id` is issued for every order.
- **gmv** is price + freight of the items of all orders placed (any status, so including orders
  later canceled). **delivered_value** is the same for delivered orders. Both come from the items,
  not the payments.
- Dates are by purchase timestamp, and windows are half-open, `[from, to)`.

| Query | Metrics | Filter | Grain | Output |
|---|---|---|---|---|
| Q1 customer order history | items, items value, freight, paid | one person; all statuses | order | 17 orders of the most frequent buyer, newest first |
| Q2 seller's recent orders | this seller's items, value and freight per order | one seller; purchased in the 30 days before `as_of` = 2018-09-01; all statuses | order | 181 orders, newest first |
| Q3 open order backlog | days open as of 2018-10-18, customer state | status created, approved, invoiced, processing or shipped | order | 1,729 orders, oldest first |
| Q4 daily orders in a window | orders, gmv, delivered_value | purchased in [2017-11-20, 2017-11-27), Black Friday week | day (empty days included) | 7 days; 1,176 orders on 2017-11-24 |
| Q5 monthly GMV and growth | orders, gmv, delivered_value, change against the previous month in % | months 2017-01 to 2018-08 (the complete ones) | month (generated series, empty months included) | 20 months |
| Q6 cohort retention | active persons, cohort size, retention % | delivered orders; cohorts 2017-01 to 2018-08 | cohort month × months since the first delivered order | 207 cells |
| Q7 delivery delay vs review | delivered and reviewed orders, mean order score, share of scores ≤ 2 | delivered orders with a delivery date | delay bucket: on time, 1–3, 4–7, 8+ days late | 4 buckets: 4.29 on time, 1.70 at 8+ days |
| Q8 top sellers per category | revenue (price only), orders, items, rank, share of the category | delivered orders purchased in [2017-01-01, 2018-09-01) | category × seller, top 3 by rank | 217 rows |

## What the definitions guard against

Measured on the reference data, and pinned by `tests/test_queries.py` (except where marked).

| Query | Pitfall | Effect on this data | What the query does |
|---|---|---|---|
| Q1 | Joining items and payments to the order at once | 275 orders have several of both; total paid would read 20,308,134.71 instead of 16,008,872.12 | sums items and payments per order before the join |
| Q1, Q6 | Counting a person by `customer_id` | no `customer_id` has a second delivered order, so retention would be 0%; 1,693 persons have delivered orders in more than one month | uses `customer_unique_id` |
| Q2 | Attributing a whole order to a seller | 1 of the seller's 181 orders also has another seller's items (not pinned) | counts only this seller's items |
| Q4 | `BETWEEN '2017-11-20' AND '2017-11-26'` on a timestamp | stops at midnight of the 26th and loses that whole day: 391 orders | half-open range on the raw timestamp |
| Q5 | `LAG` over the months that have orders | 2016-11 has no orders, so 2016-12 would be compared with 2016-10 (not pinned) | LAG over a generated month series |
| Q5 | Partial first and last months | 2016-09 has 4 orders and 2018-10 has 4, which give absurd growth rates | range limited to 2017-01 to 2018-08 |
| Q4, Q5 | Revenue that includes canceled orders | items worth 102,496.83 belong to canceled or unavailable orders in the range | reports gmv and delivered_value separately |
| Q7 | Comparing the delivery timestamp with the estimated date | 1,292 deliveries on the estimated day would count as late | compares dates |
| Q7 | Joining orders to reviews directly | 96,353 rows for 95,824 reviewed orders: orders with several reviews count several times | one score per order, the mean of its reviews |
| Q8 | Items without a category, untranslated categories | 1,535 items without a category and 22 in untranslated categories in the window (not pinned) | `(no category)` and the Portuguese name, instead of dropping them |
