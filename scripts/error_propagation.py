#!/usr/bin/env -S uv run

"""Error propagation: speed metric accuracy across tiers.

Uses T1 (tcpinfo sidecar) BytesAcked/elapsed as the ground
truth speed and compares it against several alternative speed
metrics from T2 (ndt-server) and T3 (Superset client). Reports
the median and p90 of the absolute relative error, overall
and per country.
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

    df["t1_speed"] = df["t1_tcp_BytesAcked"] / df["t1_elapsed_s"]
    df["t2_speed"] = df["t2_tcp_BytesAcked"] / (df["t2_tcp_ElapsedTime"] / 1e6)
    df["t3_app_goodput"] = df["t3_client_num_bytes"] / df["t3_client_elapsed_time"]
    df["t3_speed"] = df["t3_tcp_BytesAcked"] / (df["t3_tcp_ElapsedTime"] / 1e6)

    ep = df.dropna(subset=["t1_speed"]).copy()
    ep = ep[ep["t1_speed"] > 0].copy()
    ground_truth = ep["t1_speed"]

    metrics = [
        ("T3 App goodput", ep["t3_app_goodput"]),
        ("T2 BytesAcked/elapsed", ep["t2_speed"]),
        ("T3 BytesAcked/elapsed", ep["t3_speed"]),
        ("T3 DeliveryRate", ep["t3_tcp_DeliveryRate"]),
        ("T3 BBR BW", ep["t3_bbr_BW"]),
    ]

    click.echo(
        f"{'Metric':<30}  {'n':>6}  {'median |err|':>12}  {'p90 |err|':>10}  {'median err':>11}"
    )
    for name, vals in metrics:
        valid_mask = vals.notna() & (ground_truth > 0)
        v = vals[valid_mask]
        gt = ground_truth[valid_mask]
        signed_err = (v - gt) / gt
        abs_err = signed_err.abs()
        click.echo(
            f"  {name:<28}  {len(abs_err):>6}  "
            f"{abs_err.median() * 100:>10.1f} %  "
            f"{abs_err.quantile(0.90) * 100:>8.1f} %  "
            f"{signed_err.median() * 100:>+9.1f} %"
        )
    click.echo("")

    for cc in sorted(ep["country_code"].dropna().unique()):
        sub = ep[ep["country_code"] == cc]
        gt_sub = sub["t1_speed"]
        click.echo(f"  Error propagation — {cc} (n={len(sub):,}):")
        for name, vals_full in metrics:
            vals = vals_full.reindex(sub.index)
            valid_mask = vals.notna() & (gt_sub > 0)
            v = vals[valid_mask]
            gt = gt_sub[valid_mask]
            if len(gt) == 0:
                continue
            signed_err = (v - gt) / gt
            abs_err = signed_err.abs()
            click.echo(
                f"    {name:<28}  median |err| = {abs_err.median() * 100:.1f}%  "
                f"p90 = {abs_err.quantile(0.90) * 100:.1f}%  "
                f"median err = {signed_err.median() * 100:+.1f}%"
            )
        click.echo("")


if __name__ == "__main__":
    main()
