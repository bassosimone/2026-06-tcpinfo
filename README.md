# 2026-06 TCPInfo

Comparative analysis of client-side data collected by ndt7
(including tcp-info), server-side data collected by ndt-server,
and server-side data collected by the tcp-info sidecar.

## Requirements

- [uv](https://docs.astral.sh/uv/) for managing Python
  dependencies and running scripts. All Python dependencies
  (click, pandas, plotly, pyarrow, statsmodels, streamlit)
  are declared in `pyproject.toml` and resolved automatically
  by `uv run` — no manual install step is needed.

- GNU make (the `GNUmakefile` is not compatible with BSD
  make or other make variants).

## Data Window

Every make target operates on a date window bounded by `START`
(included) and `END` (excluded). They default to `2026-01-01`
and `2026-08-01`, that is, January through July 2026. Override
them on the command line for partial re-runs, e.g.
`make build_three_tier START=2026-01-01 END=2026-02-01`.

BigQuery targets chunk the window weekly; Superset targets chunk
it monthly. Weekly chunks are clipped at calendar month
boundaries, so a chunk never spans two months and each month is
a self-contained set of chunks. See
[list_chunks.py](scripts/list_chunks.py).

Run `make help` for the list of targets.

## Query Templates

The `queries/templates/` directory contains SQL query templates
with `@DATE_START@` and `@DATE_END@` placeholders:

- [ndt7.sql](queries/templates/ndt7.sql) — exports full ndt7
  rows for giga-meter clients in MW and MD.

- [tcpinfo.sql](queries/templates/tcpinfo.sql) — exports
  tcp-info sidecar rows matching the corresponding ndt7 UUIDs.

- [superset.sql](queries/templates/superset.sql) — exports
  Giga client sessions from Superset for MW and MD.

Run `make generate_queries` to instantiate the templates over
the data window: `ndt7` and `tcpinfo` weekly, `superset`
monthly. This produces files like
`queries/ndt7_20260101_20260108.sql` and
`queries/superset_20260101_20260201.sql` in the `queries/`
directory. Generated queries are gitignored.

## Fetching Data

The `data/` directory contains the raw query results. Data
files follow the same `{name}_{YYYYMMDD}_{YYYYMMDD}` naming
convention as the generated queries. Data files are gitignored.

To fetch M-Lab data (ndt7 and tcpinfo), use the `bq` CLI
tool. See [the M-Lab website](https://www.measurementlab.net/data/docs/bq/quickstart/)
for instructions on how to set it up. Then run
`make export_mlab_data` to export all weekly chunks.

The export skips chunks whose output file already exists, so an
interrupted run resumes by re-running the same command. Delete
an output file to force its re-export. Set `BQ_PROJECT` to choose
the billing project.

Each weekly chunk scans roughly 0.65 TB for ndt7 and 3.0 TB for
tcpinfo. A first attempt at the default window hit a BigQuery
`QueryUsagePerUserPerDay` custom quota after three chunks, so
the full window of 34 chunks needs either pacing across days or
a dedicated, alternative billing project.

To fetch Giga data (superset), you need an account for
[Superset](https://superset.giga.global/sqllab/). Run each
generated `superset_*.sql` query, one per month in the window,
in the Superset SQL Lab and export each result as CSV. Save them
as `data/superset_{YYYYMMDD}_{YYYYMMDD}.csv.gz`.

## Transforming ndt-server ndt7 Data

The [build_ndt7_download.py](scripts/build_ndt7_download.py) script
converts each raw ndt7 JSON export into a per-snapshot parquet file
for download tests. Each row is one `ServerMeasurements` snapshot
(not one test), preserving the full time series. The script projects
a fixed set of `TCPInfo` and `BBRInfo` fields without computing
any derived values.

Run `make build_ndt7_download` to build all weekly chunks. This
produces files like `data/ndt7_20260501_20260508_download.parquet`
in the `data/` directory.

## Transforming tcp-info Sidecar Data

The [build_tcpinfo.py](scripts/build_tcpinfo.py) script converts each
raw tcpinfo JSON export into a per-snapshot parquet file. Each row is
one sidecar `Snapshot` with its absolute `Timestamp` and the same
`TCPInfo` and `BBRInfo` fields as the ndt7 transform.

There is no download/upload direction for tcpinfo snapshots. Hence,
the end result is a single parquet file per chunk, containing snapshots
for both directions. Merging with ndt7 data on the UUID (an operation
performed by subsequent stages) ensures that we only select the
UUIDs of interest for the direction that we are analyzing.

Run `make build_tcpinfo` to build all weekly chunks. This produces
files like `data/tcpinfo_20260501_20260508.parquet` in the `data/`
directory.

## Transforming Superset Data

The [build_superset_download.py](scripts/build_superset_download.py) script
converts the Superset CSV export into a per-test parquet file for
download tests. Each row is one test with the `LastServerMeasurement`
`TCPInfo` and `BBRInfo` fields plus `LastClientMeasurement` elapsed
time and bytes (for app-level goodput). It also preserves the
`country_code`, `school_id`, and `giga_id_school` metadata.

Run `make build_superset_download` to build all monthly chunks.
This produces files like
`data/superset_20260101_20260201_download.parquet` in the
`data/` directory.

## Building the Three-Tier Joined Dataset

The [build_three_tier.py](scripts/build_three_tier.py) script
joins all three data sources into a single per-test parquet file.
It loads all per-snapshot parquets (T1 and T2) and per-test
parquets (T3) whose date ranges overlap the requested window,
aggregates T1 and T2 to one row per test (last ESTABLISHED
snapshot), and inner-joins on UUID — so only tests present in
all three tiers survive.

For T1 (tcpinfo sidecar), we collect canonical columns
associated with the ESTABLISHED state. In addition, it also
computes extra columns representing the socket drain using
the `t1_any_` prefix to set them apart. The script also
computes `t1_notsent_max` (peak NotsentBytes across ESTABLISHED
snapshots). The inner join with T1 and T2 provides temporal filtering
for T3 (Superset), which does not include a server-side
timestamp. Since the tcpinfo sidecar has no kernel
`ElapsedTime`, the script derives `t1_elapsed_s` as
wall-clock time from T2's `StartTime` to the last T1
snapshot timestamp.

Run `make build_three_tier` to build the joined dataset. This
produces one file covering the whole window, e.g.
`data/three_tier_20260101_20260801.parquet` for the default
window.

## Explorer

The [explorer/](explorer/) directory contains a Streamlit app for
interactive inspection of individual ndt7 download tests. It shows
the full TCPInfo/BBRInfo time series from two independent data
sources — the ndt7 server and the tcp-info sidecar — which can
be overlaid, viewed separately, or merged. Each chart includes an
expandable description explaining the plotted variables; the
authoritative reference for variable definitions is
[docs/tcpinfo_inventory_llm.txt](docs/tcpinfo_inventory_llm.txt).

Run `make explorer` to launch the app. It requires the three-tier
parquet and per-snapshot parquets in `data/`.

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

### Error Propagation

The [error_propagation.py](scripts/error_propagation.py) script
measures how accurately different speed metrics approximate the
ground truth. It uses T1 (tcpinfo sidecar) `BytesAcked / elapsed`
as the reference and compares T3 app goodput, T2 and T3
`BytesAcked / elapsed`, T3 `DeliveryRate`, and T3 `BBR BW`.
It reports the median and p90 of the absolute relative error,
overall and per country.

Run `make error_propagation` to produce the analysis.

### T3-Only Regression

The [t3_only_regression.py](scripts/t3_only_regression.py) script
runs the same gap regression as `gap_regression.py` but using
only Superset (T3) predictors — `NotsentBytes / PacingRate`
from the client's `LastServerMeasurement`. This tests whether
the gap can be predicted without the tcpinfo sidecar.

Run `make t3_only_regression` to produce the analysis.

### Tail Loss

The [tail_loss.py](scripts/tail_loss.py) script measures how
much test duration the client's `LastServerMeasurement` misses
compared to the server's final `ServerMeasurement`. A positive
tail loss means the client stopped collecting snapshots before
the server did.

Run `make tail_loss` to produce the analysis.
