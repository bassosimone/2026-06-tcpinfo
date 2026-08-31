#!/usr/bin/env -S uv run

"""T3-only regression: gap ~ t3_notsent / t3_pacing.

Same regression as gap_regression.py but using only Superset
(T3) predictors — NotsentBytes and PacingRate from the client's
LastServerMeasurement. Tests whether the gap can be predicted
without access to the tcpinfo sidecar (T1).
"""

from pathlib import Path

import click
import pandas as pd
import statsmodels.api as sm

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

    df["gap_s"] = df["t3_client_elapsed_time"] - df["t3_tcp_ElapsedTime"] / 1e6

    dfr = df.dropna(subset=["gap_s", "t3_tcp_NotsentBytes", "t3_tcp_PacingRate"])
    dfr = dfr[dfr["t3_tcp_PacingRate"] > 0].copy()
    dfr["pred_drain_t3"] = dfr["t3_tcp_NotsentBytes"] / dfr["t3_tcp_PacingRate"]

    t3_elapsed_s = dfr["t3_tcp_ElapsedTime"] / 1e6
    t2_elapsed_s = dfr["t2_tcp_ElapsedTime"] / 1e6

    clean_t3 = dfr[t3_elapsed_s >= 9.5].copy()
    clean_t2 = dfr[t2_elapsed_s >= 9.5].copy()
    clean_both = dfr[(t3_elapsed_s >= 9.5) & (t2_elapsed_s >= 9.5)].copy()

    click.echo(f"Tests with T3 flight data: {len(dfr):,}")
    click.echo(
        f"  clean-close (t3 >= 9.5): {len(clean_t3):,} ({len(clean_t3) / len(dfr) * 100:.0f}%)"
    )
    click.echo(
        f"  clean-close (t2 >= 9.5): {len(clean_t2):,} ({len(clean_t2) / len(dfr) * 100:.0f}%)"
    )
    click.echo(
        f"  clean-close (both):      {len(clean_both):,} ({len(clean_both) / len(dfr) * 100:.0f}%)"
    )
    click.echo("")

    for subset_label, subset in [
        ("client elapsed >= 9.5s", clean_t3),
        ("server elapsed >= 9.5s", clean_t2),
        ("both >= 9.5s", clean_both),
    ]:
        if len(subset) < 10:
            click.echo(f"  {subset_label}: too few rows\n")
            continue
        X = sm.add_constant(subset["pred_drain_t3"])
        model = sm.OLS(subset["gap_s"], X).fit()
        a, b = model.params.iloc[0], model.params.iloc[1]
        click.echo(f"  {subset_label} (n={len(subset):,}):")
        click.echo(
            f"    gap = {a:+.4f} + {b:+.4f} × (t3_notsent/t3_pacing)  R² = {model.rsquared:.3f}"
        )
        click.echo("")


if __name__ == "__main__":
    main()
