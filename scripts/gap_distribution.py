#!/usr/bin/env -S uv run

"""Gap distribution: client_elapsed - server_elapsed.

Computes the gap between the client-reported test duration
(LastClientMeasurement.ElapsedTime) and the server-reported
TCP elapsed time (LastServerMeasurement.TCPInfo.ElapsedTime)
for each test. Reports percentile stats overall, per country,
and per-school heterogeneity.
"""

from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def describe_gap(gap, label):
    """Print percentile summary and threshold fractions for a gap series."""
    g = gap.dropna()
    n = len(g)
    if n == 0:
        click.echo(f"--- {label}: no data ---\n")
        return
    click.echo(f"--- {label} (n={n:,}) ---")
    click.echo(
        f"  p50={g.median():+.3f}  p90={g.quantile(0.90):+.3f}  "
        f"p95={g.quantile(0.95):+.3f}  p99={g.quantile(0.99):+.3f}"
    )
    click.echo(
        f"  > 1s: {(g > 1.0).mean() * 100:.1f}%  "
        f"> 0.5s: {(g > 0.5).mean() * 100:.1f}%  "
        f"<= 0: {(g <= 0).mean() * 100:.1f}%"
    )
    click.echo("")


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to three_tier parquet file.",
)
def main(input_path):
    df = pd.read_parquet(input_path)
    click.echo(f"Loaded {input_path.name}: {len(df):,} tests\n")

    df["gap_s"] = df["t3_client_elapsed_time"] - df["t3_tcp_ElapsedTime"] / 1e6

    valid = df.dropna(subset=["gap_s"])
    click.echo("Gap distribution (client_elapsed - server_elapsed)\n")
    describe_gap(valid["gap_s"], "All MW+MD")
    for cc in sorted(valid["country_code"].dropna().unique()):
        sub = valid[valid["country_code"] == cc]
        describe_gap(sub["gap_s"], f"country = {cc}")

    click.echo("Per-school heterogeneity (schools with >= 10 tests):")
    for cc in sorted(valid["country_code"].dropna().unique()):
        sub = valid[valid["country_code"] == cc]
        by_school = sub.groupby("school_id")["gap_s"].agg(["count", "median"])
        big = by_school[by_school["count"] >= 10]
        click.echo(
            f"  {cc}: {len(big)} schools with >=10 tests, "
            f"per-school median gap range: "
            f"{big['median'].min():+.2f} to {big['median'].max():+.2f} s"
        )
    click.echo("")


if __name__ == "__main__":
    main()
