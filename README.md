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

