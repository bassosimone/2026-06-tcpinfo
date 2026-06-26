#!/usr/bin/env -S uv run

"""Superset tail loss: t2_elapsed - t3_elapsed.

Measures how much test duration the client's LastServerMeasurement
misses compared to the server's final ServerMeasurement. A positive
tail loss means the client stopped collecting snapshots before the
server did.
"""

from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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

    df["t2_elapsed_s"] = df["t2_tcp_ElapsedTime"] / 1e6
    df["t3_elapsed_s"] = df["t3_tcp_ElapsedTime"] / 1e6

    tail = df.dropna(subset=["t2_elapsed_s", "t3_elapsed_s"]).copy()
    tail["tail_loss_s"] = tail["t2_elapsed_s"] - tail["t3_elapsed_s"]
    n_tail = len(tail)

    loss_05 = (tail["tail_loss_s"] >= 0.5).sum()
    loss_1 = (tail["tail_loss_s"] >= 1.0).sum()

    click.echo(f"  Tests with both T2 and T3: {n_tail:,}")
    click.echo(f"  Tail loss >= 0.5s: {loss_05:,} ({loss_05/n_tail*100:.1f}%)")
    click.echo(f"  Tail loss >= 1.0s: {loss_1:,} ({loss_1/n_tail*100:.1f}%)")
    click.echo(f"  Median tail loss: {tail['tail_loss_s'].median():.3f} s")
    click.echo(f"  p95 tail loss:    {tail['tail_loss_s'].quantile(0.95):.3f} s")
    click.echo("")


if __name__ == "__main__":
    main()
