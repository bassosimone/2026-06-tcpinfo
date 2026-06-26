#!/usr/bin/env -S uv run

"""Build per-test three-tier joined parquet.

Reads per-snapshot ndt7 (T2) and tcpinfo (T1) parquets plus per-test
superset (T3) parquets whose date ranges overlap the requested window.
Aggregates T1 and T2 to one row per test (last snapshot), joins all
three tiers on UUID (inner join), and writes the result.

For T1 (tcpinfo sidecar), only ESTABLISHED snapshots (tcp_State == 1)
are used, filtering out post-test states (e.g. FIN_WAIT).

To merge T3 (Superset) we rely on the inner join with T1 and T2.
"""

import re
from datetime import date
from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILE_RE = re.compile(r"^\w+_(\d{8})_(\d{8})_download\.parquet$")


def parse_ymd(s):
    """Parses year month and date from a YYYYMMDD string."""
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def find_parquets(prefix, win_start, win_end):
    """Find download parquets whose date range overlaps [win_start, win_end)."""
    results = []
    for p in sorted(DATA_DIR.glob(f"{prefix}_*_download.parquet")):
        m = FILE_RE.match(p.name)
        if not m:
            continue
        fs = parse_ymd(m.group(1))
        fe = parse_ymd(m.group(2))
        if fs < win_end and fe > win_start:
            results.append(p)
    return results


def load_concat(paths, label):
    """Load and concatenate parquet files."""
    if not paths:
        raise click.ClickException(f"no {label} parquet files found")
    dfs = []
    for p in paths:
        df = pd.read_parquet(p)
        click.echo(f"  {p.name}: {len(df)} rows")
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


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
    """Aggregate tcpinfo (T1) per-snapshot -> per-test (last ESTABLISHED snapshot)."""
    est = df[df["tcp_State"] == 1].copy()
    est = est.sort_values(["uuid", "snapshot_index"])

    last = est.drop_duplicates(subset="uuid", keep="last").copy()
    stats = est.groupby("uuid").agg(
        t1_n_snapshots=("snapshot_index", "count"),
        t1_notsent_max=("tcp_NotsentBytes", "max"),
    ).reset_index()

    result = last.drop(columns=["snapshot_index"]).merge(stats, on="uuid")
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
    t2_raw = load_concat(find_parquets("ndt7", start, end), "ndt7")
    n_t2_tests = t2_raw["uuid"].nunique()
    click.echo(f"  total: {len(t2_raw)} snapshots, {n_t2_tests} tests\n")

    click.echo("Loading tcpinfo (T1)...")
    t1_raw = load_concat(find_parquets("tcpinfo", start, end), "tcpinfo")
    n_t1_tests = t1_raw["uuid"].nunique()
    click.echo(f"  total: {len(t1_raw)} snapshots, {n_t1_tests} tests\n")

    click.echo("Loading superset (T3)...")
    t3_raw = load_concat(find_parquets("superset", start, end), "superset")
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

    out_path = DATA_DIR / f"three_tier_{suffix}.parquet"
    joined.to_parquet(out_path, index=False)

    click.echo(f"\nT2 (ndt7):      {len(t2)} tests")
    click.echo(f"T1 (tcpinfo):   {len(t1)} tests")
    click.echo(f"T3 (superset):  {len(t3)} tests")
    click.echo(f"Inner join:     {len(joined)} tests")
    click.echo(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
