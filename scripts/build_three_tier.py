#!/usr/bin/env -S uv run

"""Build per-test three-tier joined parquet.

Reads per-snapshot ndt7 (T2) and tcpinfo (T1) parquets plus per-test
superset (T3) parquets whose date ranges overlap the requested window.
Aggregates T1 and T2 to one row per test (last snapshot), joins all
three tiers on UUID (inner join), and writes the result.

The ndt7 spec states that the server SHOULD be the party closing the
underlying TLS and TCP connections. For this reason, in the common
case, a transition away from the ESTABLISHED state marks the end of
the userspace observable download test. There are also cases in
which, of course, clients may close the connection. Either way, when
the socket enters a draining state, it may become unstable, which
is why, for T1 (tcpinfo sidecar) the canonical per-test row contains
data extracted from the latest ESTABLISHED snapshot (corresponding
to tcp_State == 1). However, observing the draining behavior of the
socket is also relevant to this investigation. For this reason, in
addition to the canonical columns, we include the t1_any_* columns
and the t1_elapsed_any_s column. Collectively, these columns
allow studying what happens during the drain phase and answer
the question of why the `giga-meter` client runs, at times, for
more than 50 seconds, which is unexpected behavior considering that
the spec wants the test to run for 10s plus some leeway.

To merge T3 (Superset) we rely on the inner join with T1 and T2.

Since the tcpinfo sidecar has no kernel ElapsedTime, we derive
t1_elapsed_s (and t1_elapsed_any_s) as wall-clock time from T2's
StartTime to the corresponding T1 snapshot timestamp. We also
materialize t2_wall_s from T2's StartTime and EndTime.
"""

import re
from datetime import date
from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# TODO(bassosimone): this regex currently works because the directory
# either contains parquet for download files or tcp-info snapshots. We
# will need to improve this code when we add support for upload.
FILE_RE = re.compile(r"^\w+_(\d{8})_(\d{8})(_download)?\.parquet$")


def parse_ymd(s):
    """Parses year month and date from a YYYYMMDD string."""
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def find_parquets(prefix, win_start, win_end):
    """Find a tier's parquets whose date range overlaps [win_start, win_end)."""
    results = []
    # TODO(bassosimone): see above comment about supporting upload.
    for p in sorted(DATA_DIR.glob(f"{prefix}_*.parquet")):
        m = FILE_RE.match(p.name)
        if not m:
            continue
        fs = parse_ymd(m.group(1))
        fe = parse_ymd(m.group(2))
        if fs < win_end and fe > win_start:
            results.append(p)
    return results


def dedup(df, label, key):
    """Drop rows sharing the same key, warning when this happens.

    The key varies depending on the input data source:

    1. it is (uuid, snapshot_index) for data sources including multiple
       rows per uuid (tcpinfo and ndt7)

    2. it is just the uuid for superset where there is a single row
       capturing the last snapshot the server sent to the client

    Elevated numbers of duplicates suggest upstream data quality issues, while
    low numbers compared to the data volume should be tolerated.

    We drop rather than just warn because downstream consumers treat the
    uuid as the test identity: the explorer indexes by uuid (and raises
    on a non-unique index) and the analysis scripts would otherwise count
    the duplicated tests more than once. We keep the first occurrence,
    which is deterministic because we load the input files in sorted
    order, and we renumber the index so that it stays contiguous.
    """
    n = int(df.duplicated(subset=key).sum())
    if n > 0:
        click.echo(
            f"  WARNING: {label}: dropping {n} rows "
            f"duplicating an earlier ({', '.join(key)})"
        )
    return df.drop_duplicates(subset=key).reset_index(drop=True)


def load_concat(paths, label, key):
    """Load and concatenate parquet files, dropping duplicate rows."""
    if not paths:
        raise click.ClickException(f"no {label} parquet files found")
    dfs = []
    for p in paths:
        df = pd.read_parquet(p)
        click.echo(f"  {p.name}: {len(df)} rows")
        dfs.append(df)
    return dedup(pd.concat(dfs, ignore_index=True), label, key)


def prefix_cols(df, prefix, skip=("uuid",)):
    """Add tier prefix to all columns except those in skip."""
    rename = {}
    for col in df.columns:
        if col in skip or col.startswith(f"{prefix}_"):
            continue
        rename[col] = f"{prefix}_{col}"
    return df.rename(columns=rename)


def agg_ndt7(df):
    """Aggregate ndt7 (T2) per-snapshot -> per-test (last ESTABLISHED snapshot)."""
    df = df[df["tcp_State"] == 1].copy()
    df = df.sort_values(["uuid", "snapshot_index"])
    last = df.drop_duplicates(subset="uuid", keep="last").copy()
    counts = df.groupby("uuid").size().reset_index(name="t2_n_samples")
    result = last.drop(columns=["snapshot_index"]).merge(counts, on="uuid")
    return prefix_cols(result, "t2")


def agg_tcpinfo(df):
    """Aggregate tcpinfo (T1) per-snapshot -> per-test. We collect
    both the "canonical" columns corresponding to ESTABLISHED and
    the t1_any_* columns capturing the drain state. See the module
    docstring for additional information. Tests not containing any
    ESTABLISHED snapshots are dropped from the output.
    """

    # 1. Collect the columns corresponding to the ESTABLISHED state.
    est = df[df["tcp_State"] == 1].copy()
    est = est.sort_values(["uuid", "snapshot_index"])

    last = est.drop_duplicates(subset="uuid", keep="last").copy()
    stats = (
        est.groupby("uuid")
        .agg(
            t1_n_snapshots=("snapshot_index", "count"),
            t1_notsent_max=("tcp_NotsentBytes", "max"),
        )
        .reset_index()
    )

    # 2. Last snapshot regardless of state. Keep BytesAcked and
    # BytesRetrans because these are the counters that still move
    # while the queue drains; drain metrics are derivable by
    # subtracting the corresponding last-ESTABLISHED columns.
    anystate = df.sort_values(["uuid", "snapshot_index"])
    any_last = anystate.drop_duplicates(subset="uuid", keep="last")
    any_last = any_last[
        ["uuid", "timestamp", "tcp_State", "tcp_BytesAcked", "tcp_BytesRetrans"]
    ].rename(
        columns={
            "timestamp": "t1_any_timestamp",
            "tcp_State": "t1_any_state",
            "tcp_BytesAcked": "t1_any_BytesAcked",
            "tcp_BytesRetrans": "t1_any_BytesRetrans",
        }
    )

    # 3. Merge ESTABLISHED and any rows together.
    result = (
        last.drop(columns=["snapshot_index"])
        .merge(stats, on="uuid")
        .merge(any_last, on="uuid")
    )
    return prefix_cols(result, "t1")


def prepare_superset(df):
    """Prepare superset (T3) -- already per-test, just prefix."""
    return prefix_cols(
        df, "t3", skip=("uuid", "country_code", "school_id", "giga_id_school")
    )


@click.command()
@click.option(
    "--start-date",
    required=True,
    type=click.DateTime(["%Y-%m-%d"]),
    help="Start date, included.",
)
@click.option(
    "--end-date",
    required=True,
    type=click.DateTime(["%Y-%m-%d"]),
    help="End date, excluded.",
)
def main(start_date, end_date):
    start = start_date.date()
    end = end_date.date()
    suffix = f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"

    click.echo("Loading ndt7 (T2)...")
    t2_raw = load_concat(
        find_parquets("ndt7", start, end), "ndt7", ["uuid", "snapshot_index"]
    )
    n_t2_tests = t2_raw["uuid"].nunique()
    click.echo(f"  total: {len(t2_raw)} snapshots, {n_t2_tests} tests\n")

    click.echo("Loading tcpinfo (T1)...")
    t1_raw = load_concat(
        find_parquets("tcpinfo", start, end), "tcpinfo", ["uuid", "snapshot_index"]
    )
    n_t1_tests = t1_raw["uuid"].nunique()
    click.echo(f"  total: {len(t1_raw)} snapshots, {n_t1_tests} tests\n")

    click.echo("Loading superset (T3)...")
    t3_raw = load_concat(find_parquets("superset", start, end), "superset", ["uuid"])
    click.echo(f"  total: {len(t3_raw)} tests\n")

    click.echo("Aggregating T2 (last snapshot per test)...")
    t2 = agg_ndt7(t2_raw)
    click.echo(f"  {len(t2)} tests")

    click.echo("Aggregating T1 (last ESTABLISHED snapshot per test)...")
    t1 = agg_tcpinfo(t1_raw)
    click.echo(f"  {len(t1)} tests")

    click.echo("Preparing T3...")
    t3 = prepare_superset(t3_raw)
    click.echo(f"  {len(t3)} tests\n")

    click.echo("Joining on UUID (inner)...")
    joined = t2.merge(t1, on="uuid").merge(t3, on="uuid")

    # T1 has no kernel ElapsedTime; compute wall-clock elapsed
    # from T2's StartTime to the last T1 snapshot timestamp.
    t1_ts = pd.to_datetime(joined["t1_timestamp"], utc=True)
    t2_st = pd.to_datetime(joined["t2_start_time"], utc=True)
    joined["t1_elapsed_s"] = (t1_ts - t2_st).dt.total_seconds()

    # Same construction for the last snapshot regardless of state.
    t1_any_ts = pd.to_datetime(joined["t1_any_timestamp"], utc=True)
    joined["t1_elapsed_any_s"] = (t1_any_ts - t2_st).dt.total_seconds()

    # Server wall-clock duration, for convenience.
    t2_et = pd.to_datetime(joined["t2_end_time"], utc=True)
    joined["t2_wall_s"] = (t2_et - t2_st).dt.total_seconds()

    out_path = DATA_DIR / f"three_tier_{suffix}.parquet"
    joined.to_parquet(out_path, index=False)

    click.echo(f"\nT2 (ndt7):      {len(t2)} tests")
    click.echo(f"T1 (tcpinfo):   {len(t1)} tests")
    click.echo(f"T3 (superset):  {len(t3)} tests")
    click.echo(f"Inner join:     {len(joined)} tests")
    click.echo(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
