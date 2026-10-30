"""Benchmark experiments (sql/bench/experiments.toml): one factor at a time, the result checked first.

An experiment runs one business query in several variants. The first variant is the reference;
every other one changes exactly one factor against it: one candidate index, or one rewrite of the SQL
(a file in sql/bench/ that takes the query's parameters). Indexes an experiment declares for all its
variants are common ground, not a factor.

A run, on the main database:
- refuses to start while core has an index other than the key indexes (bench_* leftovers of an
  interrupted run are dropped), then runs VACUUM (ANALYZE) on core, so every variant of the run sees
  the same statistics and visibility map. No ANALYZE follows an index: the candidates are on plain
  columns, so it would only resample the same statistics and add noise between variants;
- per variant: creates its index (timed) and records its size; runs the query once and compares the
  result's fingerprint with the reference variant's, and a variant whose result differs is recorded
  and not timed; then warm-up runs, timed runs measured by the client (execute and fetch every row),
  as many EXPLAIN (ANALYZE, TIMING OFF) runs for the server's planning and execution time, and one
  EXPLAIN (ANALYZE, BUFFERS) in JSON and in text; finally drops the index and checks that only the
  key indexes remain.

A variant may carry diagnostics: the same query re-run with planner settings changed for one
transaction (SET LOCAL), to explain the variant's plan, for example what a plan the planner rejected
would have cost. They are reported apart from the variants and are not factors of the comparison.

Statements are never prepared, so every execution is planned afresh, as a literal query would be. The
caches are warm: core fits in shared_buffers, and nothing here empties the operating system's cache.
The record (docs/benchmarks/runs/<run id>.json) holds the raw timings, plans and sizes, and what they
were measured on: code, client, server settings, data, and other activity on the server.
"""
import datetime
import json
import math
import re
import statistics
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

from . import config, provenance, queries

BENCH_DIR = config.SQL_DIR / "bench"
EXPERIMENTS_FILE = BENCH_DIR / "experiments.toml"
BENCH_DOCS = config.REPO_ROOT / "docs" / "benchmarks"
RUNS_DIR = BENCH_DOCS / "runs"
REPORT_FILE = BENCH_DOCS / "report.md"
INDEX_NAME = re.compile(r"bench_[a-z0-9_]+")


class BenchError(Exception):
    pass


@dataclass(frozen=True)
class Index:
    name: str
    on: str  # what follows ON in CREATE INDEX: table, method, columns, predicate

    @property
    def definition(self) -> str:
        return f"CREATE INDEX {self.name} ON {self.on}"

    def create(self) -> sql.Composed:
        return sql.SQL("CREATE INDEX {} ON {}").format(sql.Identifier(self.name), sql.SQL(self.on))

    def drop(self) -> sql.Composed:
        return sql.SQL("DROP INDEX IF EXISTS core.{}").format(sql.Identifier(self.name))


@dataclass(frozen=True)
class Diagnostic:
    label: str
    settings: tuple[tuple[str, str], ...]  # planner settings, applied with SET LOCAL


@dataclass(frozen=True)
class Variant:
    label: str
    index: Index | None = None
    sql_file: Path | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def factor(self) -> str:
        if self.index:
            return f"+ index: {self.index.definition}"
        if self.sql_file:
            return f"SQL: sql/bench/{self.sql_file.name}"
        return "reference"

    def text(self, query: queries.Query) -> str:
        return self.sql_file.read_text(encoding="utf-8") if self.sql_file else query.text


@dataclass(frozen=True)
class Experiment:
    id: str
    query: queries.Query
    question: str
    hypothesis: str
    indexes: tuple[Index, ...]
    variants: tuple[Variant, ...]


def _index(entry: dict, where: str) -> Index:
    if set(entry) != {"name", "on"} or not INDEX_NAME.fullmatch(entry["name"]):
        raise BenchError(f"{where}: an index is {{ name = 'bench_...', on = '...' }}, got {entry!r}")
    return Index(entry["name"], entry["on"])


def load_experiments(path: Path = EXPERIMENTS_FILE) -> list[Experiment]:
    """The experiments, checked: known query, a reference first, then exactly one factor per variant."""
    known = {q.name: q for q in queries.all_queries()}
    experiments = []
    for e in tomllib.loads(path.read_text(encoding="utf-8"))["experiment"]:
        where = f"{path.name} {e.get('id')}"
        if e.get("query") not in known:
            raise BenchError(f"{where}: unknown query {e.get('query')!r}")
        query = known[e["query"]]
        common = tuple(_index(i, where) for i in e.get("indexes", []))
        variants = []
        for v in e["variant"]:
            index = _index(v["index"], where) if "index" in v else None
            sql_file = BENCH_DIR / v["sql"] if "sql" in v else None
            if sql_file and not sql_file.is_file():
                raise BenchError(f"{where}: no such file sql/bench/{v['sql']}")
            if sql_file and set(queries._VARIABLE.findall(sql_file.read_text(encoding="utf-8"))) - set(query.params):
                raise BenchError(f"{where}: sql/bench/{v['sql']} takes parameters {query.name} does not declare")
            diagnostics = []
            for d in v.get("diagnostics", []):
                settings = tuple((name, str(value)) for name, value in d["settings"].items())
                if not settings or not all(re.fullmatch(r"[a-z_]+", name) for name, _ in settings):
                    raise BenchError(f"{where}: a diagnostic changes at least one setting, by its plain name")
                diagnostics.append(Diagnostic(d["label"], settings))
            variants.append(Variant(v["label"], index, sql_file, tuple(diagnostics)))
        if len(variants) < 2 or variants[0].index or variants[0].sql_file:
            raise BenchError(f"{where}: needs a reference variant first (no index, no sql) and at least one more")
        if any(bool(v.index) == bool(v.sql_file) for v in variants[1:]):
            raise BenchError(f"{where}: every variant after the reference changes exactly one factor (index or sql)")
        names = [i.name for i in common] + [v.index.name for v in variants if v.index]
        if len(names) != len(set(names)):
            raise BenchError(f"{where}: an index appears twice")
        experiments.append(Experiment(e["id"], query, e["question"], e["hypothesis"].strip(), common, tuple(variants)))
    ids = [e.id for e in experiments]
    if len(ids) != len(set(ids)):
        raise BenchError(f"{path.name}: duplicate experiment ids")
    return experiments


# --- the database side ---

def extra_indexes(conn: psycopg.Connection) -> list[str]:
    """Indexes in core that back no constraint (the key indexes back primary and unique keys)."""
    return [name for (name,) in conn.execute(
        "SELECT c.relname FROM pg_index AS i"
        " JOIN pg_class AS c ON c.oid = i.indexrelid JOIN pg_namespace AS n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'core' AND NOT EXISTS (SELECT FROM pg_constraint AS k WHERE k.conindid = i.indexrelid)"
        " ORDER BY c.relname"
    )]


def other_activity(conn: psycopg.Connection) -> dict:
    """Other sessions on the whole server: client backends (all and not idle) and autovacuum workers."""
    clients, busy, autovacuum = conn.execute(
        "SELECT count(*) FILTER (WHERE backend_type = 'client backend'),"
        " count(*) FILTER (WHERE backend_type = 'client backend' AND state <> 'idle'),"
        " count(*) FILTER (WHERE backend_type = 'autovacuum worker')"
        " FROM pg_stat_activity WHERE pid <> pg_backend_pid()"
    ).fetchone()
    return {"client_backends": clients, "active_client_backends": busy, "autovacuum_workers": autovacuum}


def table_sizes(conn: psycopg.Connection) -> dict:
    return {name: {"rows": rows, "pages": pages, "bytes": size} for name, rows, pages, size in conn.execute(
        "SELECT c.relname, c.reltuples::bigint, c.relpages, pg_relation_size(c.oid) FROM pg_class AS c"
        " JOIN pg_namespace AS n ON n.oid = c.relnamespace WHERE n.nspname = 'core' AND c.relkind = 'r' ORDER BY 1"
    )}


def index_size(conn: psycopg.Connection, index: Index) -> int:
    return conn.execute("SELECT pg_relation_size(%s::regclass)", (f"core.{index.name}",)).fetchone()[0]


def explain(conn: psycopg.Connection, text: str, options: str) -> dict:
    plan = conn.execute(f"EXPLAIN ({options}, FORMAT JSON)\n{text}").fetchone()[0]
    return (json.loads(plan) if isinstance(plan, str) else plan)[0]


def nodes(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from nodes(child)


def access_paths(plan: dict) -> list[str]:
    """How each relation was read: 'Index Scan using x on t', 'Parallel Seq Scan on t', ..."""
    paths = []
    for node in nodes(plan["Plan"]):
        if "Relation Name" in node or "Index Name" in node:
            text = ("Parallel " if node.get("Parallel Aware") else "") + node["Node Type"]
            text += f" using {node['Index Name']}" if "Index Name" in node else ""
            text += f" on {node['Relation Name']}" if "Relation Name" in node else ""
            paths.append(text)
    return paths


BUFFER_KEYS = ("Shared Hit Blocks", "Shared Read Blocks", "Shared Dirtied Blocks", "Temp Read Blocks", "Temp Written Blocks")


def server_times(conn, text: str, repeat: int) -> tuple[list[float], list[float]]:
    """(planning ms, execution ms) of `repeat` EXPLAIN (ANALYZE, TIMING OFF) runs."""
    planning, execution = [], []
    for _ in range(repeat):
        timing = explain(conn, text, "ANALYZE, TIMING OFF, BUFFERS OFF")
        planning.append(timing["Planning Time"])
        execution.append(timing["Execution Time"])
    return planning, execution


def plan_details(conn, text: str) -> dict:
    """One EXPLAIN (ANALYZE, BUFFERS): top-level buffers and access paths from the JSON form, and the text form."""
    plan = explain(conn, text, "ANALYZE, BUFFERS")
    return {"buffers": {key: plan["Plan"].get(key, 0) for key in BUFFER_KEYS}, "access_paths": access_paths(plan),
            "plan_text": "\n".join(line for (line,) in conn.execute(f"EXPLAIN (ANALYZE, BUFFERS)\n{text}"))}


def run_diagnostic(conn, text: str, diagnostic: Diagnostic, reference: str, repeat: int) -> dict:
    """The query with the diagnostic's settings, in one transaction: result check, server times, plan."""
    with conn.transaction():
        for name, value in diagnostic.settings:
            conn.execute("SELECT set_config(%s, %s, true)", (name, value))
        digest = queries.fingerprint(*queries.execute(conn, text, {}))
        planning_ms, execution_ms = server_times(conn, text, repeat)
        return {"label": diagnostic.label, "settings": dict(diagnostic.settings), "fingerprint": digest,
                "matches_reference": digest == reference, "planning_ms": planning_ms, "execution_ms": execution_ms,
                **plan_details(conn, text)}


def run_variant(conn, experiment: Experiment, variant: Variant, reference: str | None, warmup: int, repeat: int) -> dict:
    text = queries.render(conn, variant.text(experiment.query), experiment.query.params)
    result: dict = {"label": variant.label, "factor": variant.factor,
                    "sql_file": f"sql/bench/{variant.sql_file.name}" if variant.sql_file else None, "index": None}
    if variant.index:
        start = time.perf_counter()
        conn.execute(variant.index.create())
        build_ms = (time.perf_counter() - start) * 1000
        result["index"] = {"name": variant.index.name, "definition": variant.index.definition,
                           "size_bytes": index_size(conn, variant.index), "build_ms": build_ms}
    try:
        columns, rows = queries.execute(conn, text, {})
        digest = queries.fingerprint(columns, rows)
        result.update(rows=len(rows), fingerprint=digest, matches_reference=reference in (None, digest))
        if not result["matches_reference"]:
            return result
        with conn.cursor() as cur:
            for _ in range(warmup):
                cur.execute(text)
                cur.fetchall()
            client_ms = []
            for _ in range(repeat):
                start = time.perf_counter()
                cur.execute(text)
                cur.fetchall()
                client_ms.append((time.perf_counter() - start) * 1000)
        planning_ms, execution_ms = server_times(conn, text, repeat)
        result.update(client_ms=client_ms, planning_ms=planning_ms, execution_ms=execution_ms, **plan_details(conn, text))
        result["diagnostics"] = [run_diagnostic(conn, text, d, reference or digest, repeat) for d in variant.diagnostics]
        return result
    finally:
        if variant.index:
            conn.execute(variant.index.drop())


def run_experiment(conn, experiment: Experiment, *, warmup: int, repeat: int, progress=print) -> dict:
    record = {"id": experiment.id, "query": experiment.query.name, "params": experiment.query.params,
              "common_indexes": [], "variants": []}
    try:
        for index in experiment.indexes:
            conn.execute(index.create())
            record["common_indexes"].append({"name": index.name, "definition": index.definition,
                                             "size_bytes": index_size(conn, index)})
        reference = None
        for number, variant in enumerate(experiment.variants, start=1):
            v = run_variant(conn, experiment, variant, reference, warmup, repeat)
            reference = reference or v["fingerprint"]
            record["variants"].append(v)
            took = f"p50 {statistics.median(v['client_ms']):9.2f} ms" if "client_ms" in v else "RESULT DIFFERS, not timed"
            progress(f"{experiment.id} {number}/{len(experiment.variants)} {v['fingerprint'][:16]} {took}  {variant.label}")
    finally:
        for index in experiment.indexes:
            conn.execute(index.drop())
    left = extra_indexes(conn)
    if left:
        raise BenchError(f"after {experiment.id}, core still has indexes other than the key indexes: {', '.join(left)}")
    return record


def run(conn, experiments: list[Experiment], *, warmup: int = 3, repeat: int = 20, progress=print) -> dict:
    extra = extra_indexes(conn)
    foreign = [name for name in extra if not INDEX_NAME.fullmatch(name)]
    if foreign:
        raise BenchError(f"core has indexes other than the key indexes: {', '.join(foreign)}; "
                         "every experiment's reference must have none")
    for name in extra:
        conn.execute(Index(name, "").drop())
    threshold = conn.prepare_threshold
    conn.prepare_threshold = None  # never prepare: each execution is planned like a literal query
    try:
        return _run(conn, experiments, warmup, repeat, progress, dropped=extra)
    finally:
        conn.prepare_threshold = threshold


def _run(conn, experiments: list[Experiment], warmup: int, repeat: int, progress, dropped: list[str]) -> dict:
    started = datetime.datetime.now(datetime.timezone.utc)
    record = {
        "run_id": f"{started:%Y%m%dT%H%M%SZ}",
        "started": started.isoformat(timespec="seconds"),
        "code_fingerprint": provenance.code_fingerprint(),
        "client": provenance.client(),
        "server": provenance.server(conn),
        "database": conn.info.dbname,
        "protocol": {"warmup": warmup, "repeat": repeat, "prepared_statements": False,
                     "dropped_leftover_indexes": dropped},
    }
    data = provenance.loaded_data(conn)
    record["data"] = {**data, "finished": data["finished"] and data["finished"].isoformat(timespec="seconds")}
    tables = [name for (name,) in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'core' ORDER BY 1")]
    start = time.perf_counter()
    conn.execute(sql.SQL("VACUUM (ANALYZE) {}").format(sql.SQL(", ").join(sql.Identifier("core", t) for t in tables)))
    record["protocol"]["vacuum_analyze_ms"] = (time.perf_counter() - start) * 1000
    record["tables"] = table_sizes(conn)
    record["activity_before"] = other_activity(conn)
    record["experiments"] = [run_experiment(conn, e, warmup=warmup, repeat=repeat, progress=progress) for e in experiments]
    record["activity_after"] = other_activity(conn)
    record["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return record


def save(record: dict, directory: Path = RUNS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --- the report ---

def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def ms(value: float) -> str:
    return f"{value:,.3f}" if value < 1 else f"{value:,.2f}" if value < 100 else f"{value:,.1f}"


def size(value: int) -> str:
    return f"{value / 1024:,.0f} kB" if value < 1024 * 1024 else f"{value / 1024 / 1024:,.2f} MB"


def change(value: float, reference: float) -> str:
    if value == reference:
        return "±0%"
    ratio = reference / value
    pct = 100 * (value - reference) / reference
    return f"{pct:+.0f}% ({ratio:.1f}× faster)" if ratio >= 1 else f"{pct:+.0f}% ({1 / ratio:.2f}× slower)"


def load_runs(directory: Path = RUNS_DIR) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def render_report(runs: list[dict], experiments: list[Experiment]) -> str:
    if not runs:
        raise BenchError("no runs to report")
    first = runs[0]
    fingerprints = sorted({r["code_fingerprint"] for r in runs})
    settings = first["server"]["settings"]
    differing = sorted(k for k in settings if any(r["server"]["settings"].get(k) != settings[k] for r in runs))
    current = provenance.code_fingerprint()
    run_ids = ", ".join(f"`{r['run_id']}`" for r in runs)
    seen = {key: max(max(r["activity_before"][key], r["activity_after"][key]) for r in runs)
            for key in ("client_backends", "active_client_backends", "autovacuum_workers")}
    lines = [
        "# Benchmark report",
        "",
        "Generated by `olist-dbe bench-report` from the run records in [runs/](runs/); method and findings in",
        "[docs/benchmarks.md](../benchmarks.md), experiments in [sql/bench/experiments.toml](../../sql/bench/experiments.toml).",
        "Times are in milliseconds. *Client* is execute plus fetching every row, measured in Python; *server* is",
        "the execution time EXPLAIN (ANALYZE, TIMING OFF) reports, without planning. p50 is the median of a run's",
        f"{first['protocol']['repeat']} timed executions, after {first['protocol']['warmup']} warm-up runs; the table gives each run's p50 and",
        "their median. Buffers are 8 kB pages, from one EXPLAIN (ANALYZE, BUFFERS) of the last run.",
        "",
        "## Environment",
        "",
        f"- Runs: {run_ids}",
        f"- Code fingerprint: {' / '.join(f'`{f[:16]}`' for f in fingerprints)}"
        + (" (all runs)" if len(fingerprints) == 1 else " (**runs differ**)")
        + ("; the current code is the same" if fingerprints == [current] else f"; current code `{current[:16]}`"),
        f"- Server: {first['server']['version']}; locale {first['server']['locale']}; JIT available: {first['server']['jit_available']}",
        f"- Client: Python {first['client']['python']}, psycopg {first['client']['psycopg']}, libpq {first['client']['libpq']},"
        f" {first['client']['platform']}",
        f"- Data: database `{first['database']}`, load {first['data']['load_id']} ({first['data']['finished']}), source files"
        f" {'matching' if all(r['data']['files_match_reference'] for r in runs) else '**not matching**'} `data_manifest.json`",
        f"- Each run: VACUUM (ANALYZE) of core first, no prepared statements, warm caches. Other sessions on the server,"
        f" at the start and end of each run, at most: {seen['client_backends']} client sessions"
        f" ({seen['active_client_backends']} active), {seen['autovacuum_workers']} autovacuum workers",
        "",
        "| Setting | Value |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v}{' (**differs between runs**)' if k in differing else ''} |" for k, v in settings.items()]
    lines += ["", "| Table | Rows | Pages | Size |", "|---|---:|---:|---:|"]
    lines += [f"| core.{t} | {s['rows']:,} | {s['pages']:,} | {size(s['bytes'])} |" for t, s in first["tables"].items()]

    summary, sections, index_rows = [], [], {}
    by_id = {e.id: e for e in experiments}
    for exp_id in [e["id"] for e in first["experiments"]]:
        records = [next(e for e in r["experiments"] if e["id"] == exp_id) for r in runs if any(e["id"] == exp_id for e in r["experiments"])]
        experiment = by_id.get(exp_id)
        section = [f"## {exp_id}: {experiment.question if experiment else ''}", ""]
        section.append(f"Query `{records[0]['query']}` ({', '.join(f'{k} = {v}' for k, v in records[0]['params'].items()) or 'no parameters'}),"
                       f" {len(records)} runs.")
        for common in records[0]["common_indexes"]:
            section.append(f"Present in every variant: `{common['definition']}` ({size(common['size_bytes'])}).")
        if experiment:
            section += ["", "Hypothesis, written before measuring:", "", "> " + experiment.hypothesis.replace("\n", " "), ""]
        section += [
            "| Variant | Result | Index size | Client p50 per run | Client p50 | Client p95 | Client min | Server p50 | Planning p50 | Change (client p50) | Shared hit / read | Temp read / written |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|",
        ]
        reference_p50 = None
        plans, diagnostics = [], []
        for number in range(len(records[0]["variants"])):
            vs = [r["variants"][number] for r in records]
            v = vs[-1]
            same = all(x["matches_reference"] for x in vs) and len({x["fingerprint"] for x in vs}) == 1
            result = f"same, `{v['fingerprint'][:8]}`" if same else "**differs**"
            index = size(statistics.median(x["index"]["size_bytes"] for x in vs)) if v["index"] else ""
            if v["index"]:
                definition, sizes, builds = index_rows.setdefault(v["index"]["name"], (v["index"]["definition"], [], []))
                sizes += [x["index"]["size_bytes"] for x in vs]
                builds += [x["index"]["build_ms"] for x in vs]
            if not all("client_ms" in x for x in vs):
                section.append(f"| {v['label']} | {result} | {index} | not timed | | | | | | | | |")
                summary.append(f"| {exp_id} | {v['label']} | {result} | {index} | | | |")
                continue
            run_p50 = [statistics.median(x["client_ms"]) for x in vs]
            p50 = statistics.median(run_p50)
            server = statistics.median(statistics.median(x["execution_ms"]) for x in vs)
            planning = statistics.median(statistics.median(x["planning_ms"]) for x in vs)
            reference_p50 = reference_p50 if reference_p50 is not None else p50
            delta = "reference" if number == 0 else change(p50, reference_p50)
            b = v["buffers"]
            section.append(
                f"| {v['label']} | {result} | {index} | {' / '.join(ms(x) for x in run_p50)} | {ms(p50)}"
                f" | {ms(statistics.median(p95(x['client_ms']) for x in vs))} | {ms(min(min(x['client_ms']) for x in vs))}"
                f" | {ms(server)} | {ms(planning)} | {delta} | {b['Shared Hit Blocks']:,} / {b['Shared Read Blocks']:,}"
                f" | {b['Temp Read Blocks']:,} / {b['Temp Written Blocks']:,} |"
            )
            paths = "; ".join(dict.fromkeys(v["access_paths"]))
            summary.append(f"| {exp_id} | {v['label']} | {result} | {index} | {ms(p50)} | {delta} | {paths} |")
            plans.append((v["label"], v["access_paths"], v["plan_text"]))
            for number_d in range(len(v.get("diagnostics", []))):
                ds = [x["diagnostics"][number_d] for x in vs]
                d = ds[-1]
                diagnostics.append(
                    f"| {v['label']} | {d['label']} | {', '.join(f'`{k} = {value}`' for k, value in d['settings'].items())}"
                    f" | {'same' if all(x['matches_reference'] for x in ds) else '**differs**'}"
                    f" | {' / '.join(ms(statistics.median(x['execution_ms'])) for x in ds)}"
                    f" | {ms(statistics.median(statistics.median(x['execution_ms']) for x in ds))}"
                    f" | {'; '.join(dict.fromkeys(d['access_paths']))} |"
                )
                plans.append((f"{v['label']}, diagnostic: {d['label']}", d["access_paths"], d["plan_text"]))
        section += ["", "Access paths (last run):", ""]
        section += [f"- {label}: {'; '.join(paths)}" for label, paths, _ in plans]
        if diagnostics:
            section += ["", "Diagnostics: the variant's query with planner settings changed for one transaction, to explain"
                        " its plan. They are not variants, and only the server time is measured.", "",
                        "| Variant | Diagnostic | Settings | Result | Server p50 per run | Server p50 | Access paths |",
                        "|---|---|---|---|---|---:|---|"] + diagnostics
        section += ["", "<details><summary>EXPLAIN (ANALYZE, BUFFERS), last run</summary>", ""]
        for label, _, text in plans:
            section += [f"**{label}**", "", "```text", text, "```", ""]
        section += ["</details>", ""]
        sections += section

    lines += ["", "## Summary", "",
              "| Experiment | Variant | Result | Index size | Client p50 | Change against the reference | Access paths |",
              "|---|---|---|---:|---:|---|---|"]
    lines += summary
    lines += ["", "## Candidate indexes", "", "| Index | Definition | Size | Share of its table | Build time |", "|---|---|---:|---:|---:|"]
    for name, (definition, sizes, builds) in index_rows.items():
        table = re.search(r"ON core\.(\w+)", definition).group(1)
        table_bytes = first["tables"][table]["bytes"]
        lines.append(f"| `{name}` | `{definition}` | {size(statistics.median(sizes))} |"
                     f" {100 * statistics.median(sizes) / table_bytes:.1f}% | {ms(statistics.median(builds))} ms |")
    lines += [""] + sections
    return "\n".join(lines)
