# 2026-06 TCPInfo

Comparative analysis of client-side data collected by ndt7
(including tcp-info), server-side data collected by ndt-server,
and server-side data collected by the tcp-info sidecar.

## Requirements

- [uv](https://docs.astral.sh/uv/) for managing Python
  dependencies and running scripts.

- GNU make (the `GNUmakefile` is not compatible with BSD
  make or other make variants).

## Query Templates

The `queries/templates/` directory contains SQL query templates
with `@DATE_START@` and `@DATE_END@` placeholders:

- [ndt7.sql](queries/templates/ndt7.sql) — exports full ndt7
  rows for giga-meter clients in MW and MD.

- [tcpinfo.sql](queries/templates/tcpinfo.sql) — exports
  tcp-info sidecar rows matching the corresponding ndt7 UUIDs.

- [superset.sql](queries/templates/superset.sql) — exports
  Giga client sessions from Superset for MW and MD.

Run `make generate_queries` to instantiate the templates
for all weekly blocks in May 2026. This produces files like
`queries/ndt7_20260501_20260508.sql` in the `queries/`
directory. Generated queries are gitignored.

## Fetching Data

The `data/` directory contains the raw query results. Data
files follow the same `{name}_{YYYYMMDD}_{YYYYMMDD}` naming
convention as the generated queries. Data files are gitignored.

To fetch M-Lab data (ndt7 and tcpinfo), use the `bq` CLI
tool. See [the M-Lab website](https://www.measurementlab.net/data/docs/bq/quickstart/)
for instructions on how to set it up. Then run
`make export_mlab_data` to export all weekly blocks.

To fetch Giga data (superset), you need an account for
[Superset](https://superset.giga.global/sqllab/). Run the
generated `superset_*.sql` query in the Superset SQL Lab
and export the result as CSV. Save it as
`data/superset_{YYYYMMDD}_{YYYYMMDD}.csv.gz`.

## Transforming ndt-server ndt7 Data

The [build_ndt7_download.py](scripts/build_ndt7_download.py) script
converts each raw ndt7 JSON export into a per-snapshot parquet file
for download tests. Each row is one `ServerMeasurements` snapshot
(not one test), preserving the full time series. The script projects
a fixed set of `TCPInfo` and `BBRInfo` fields without computing
any derived values.

Run `make build_ndt7_download` to build all weekly blocks. This
produces files like `data/ndt7_20260501_20260508_download.parquet`
in the `data/` directory.

## Transforming tcp-info Sidecar Data

The [build_tcpinfo_download.py](scripts/build_tcpinfo_download.py) script
converts each raw tcpinfo JSON export into a per-snapshot parquet file.
Each row is one sidecar `Snapshot` with its absolute `Timestamp` and
the same `TCPInfo` and `BBRInfo` fields as the ndt7 transform. The
tcpinfo query already filters by ndt7 UUIDs, so every row corresponds
to a download test.

Run `make build_tcpinfo_download` to build all weekly blocks. This
produces files like `data/tcpinfo_20260501_20260508_download.parquet`
in the `data/` directory.

## Transforming Superset Data

The [build_superset_download.py](scripts/build_superset_download.py) script
converts the Superset CSV export into a per-test parquet file for
download tests. Each row is one test with the `LastServerMeasurement`
`TCPInfo` and `BBRInfo` fields plus `LastClientMeasurement` elapsed
time and bytes (for app-level goodput). It also preserves the
`country_code`, `school_id`, and `giga_id_school` metadata.

Run `make build_superset_download` to build the monthly export.
This produces `data/superset_20260501_20260601_download.parquet`.

## Building the Three-Tier Joined Dataset

The [build_three_tier.py](scripts/build_three_tier.py) script
joins all three data sources into a single per-test parquet file.
It loads all per-snapshot parquets (T1 and T2) and per-test
parquets (T3) whose date ranges overlap the requested window,
aggregates T1 and T2 to one row per test (last ESTABLISHED
snapshot), and inner-joins on UUID — so only tests present in
all three tiers survive.

For T1 (tcpinfo sidecar), only ESTABLISHED snapshots are used,
filtering out post-test states (FIN_WAIT, CLOSE_WAIT). The
script also computes `t1_notsent_max` (peak NotsentBytes across
ESTABLISHED snapshots). The inner join with T1 and T2 provides temporal filtering
for T3 (Superset), which does not include a server-side
timestamp. Since the tcpinfo sidecar has no kernel
`ElapsedTime`, the script derives `t1_elapsed_s` as
wall-clock time from T2's `StartTime` to the last T1
snapshot timestamp.

Run `make build_three_tier` to build the joined dataset. This
produces `data/three_tier_20260501_20260601.parquet`.

## Analysis

The following scripts analyze the three-tier joined dataset.
Each script focuses on a single research question and reads
the parquet file produced by `build_three_tier`.

### Gap Distribution

The [gap_distribution.py](scripts/gap_distribution.py) script
measures the gap between client-reported and server-reported
test duration: `client_elapsed - server_elapsed`. It reports
percentile statistics overall, per country, and per-school
heterogeneity (schools with at least 10 tests).

Run `make gap_distribution` to produce the analysis.

### Gap Regression

The [gap_regression.py](scripts/gap_regression.py) script
tests whether the gap can be predicted by the ratio of peak
unsent bytes to pacing rate (`notsent_max / pacing_rate`),
which estimates the time to drain the send buffer. It runs
OLS regression on two clean-close subsets: tests where the
client elapsed time is at least 9.5s, and tests where the
server elapsed time is at least 9.5s.

Run `make gap_regression` to produce the analysis.
