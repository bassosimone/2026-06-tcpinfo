#!/usr/bin/env -S uv run

"""Gap distribution: client_elapsed - server_elapsed.

Computes the gap between the client-reported test duration
and several measurements of the server duration computed
using server-side data (ndt-server and the tcp-info sidecar).

In the context of this script, T1 means data collected by
the tcp-info sidecar; T2 means that collected by ndt-server;
T3 means data available to the client (including both
client generated data and data that the server provided
to the client and the client stored).

The main quantity we want to study is the gap at the T3 level
between the duration according to data produced by the
client and the duration according to data that the server
relayed to the client. This is the data submitted by `giga-meter`
to the Giga backend and available for querying via Superset.
"""

from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# TCP state numbers as reported by the kernel; this mirrors the
# enum in include/net/tcp_states.h (Linux).
TCP_STATES = {
    1: "ESTABLISHED",
    2: "SYN_SENT",
    3: "SYN_RECV",
    4: "FIN_WAIT1",
    5: "FIN_WAIT2",
    6: "TIME_WAIT",
    7: "CLOSE",
    8: "CLOSE_WAIT",
    9: "LAST_ACK",
    10: "LISTEN",
    11: "CLOSING",
    12: "NEW_SYN_RECV",
}


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


def quantile_row(series, label):
    """Print one quantile-table row for a duration/delta series."""
    s = series.dropna()
    qs = [0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    cells = "  ".join(f"{s.quantile(q):8.3f}" for q in qs)
    click.echo(f"  {label:<20} {cells}")


def quantile_header():
    """Print the header matching quantile_row's columns."""
    labels = ["p5", "p25", "p50", "p75", "p90", "p95", "p99"]
    cells = "  ".join(f"{x:>8}" for x in labels)
    click.echo(f"  {'':<20} {cells}")


def describe_durations(df):
    """Print duration distributions per tier and pairwise deltas."""
    m = {
        "t2_kernel": df["t2_tcp_ElapsedTime"] / 1e6,
        "t2_wall": df["t2_wall_s"],
        "t1_est": df["t1_elapsed_s"],
        "t1_any": df["t1_elapsed_any_s"],
        "t3_client": df["t3_client_elapsed_time"],
        "t3_kernel": df["t3_tcp_ElapsedTime"] / 1e6,
    }

    click.echo("Duration by tier (seconds):")
    click.echo("""
  1. t2_kernel: kernel ElapsedTime in the last TCPInfo snapshot
     collected by ndt-server (the measurement stop, ~10 s)

  2. t2_wall: ndt-server wall clock, StartTime to EndTime

  3. t1_est: T2 StartTime to the last ESTABLISHED sidecar
     snapshot (empirically, the moment the server closes the
     socket under typical ndt7 behavior)

  4. t1_any: T2 StartTime to the last sidecar snapshot
     regardless of state (end of the TCP endpoint in the kernel)

  5. t3_client: elapsed time reported by the giga-meter client

  6. t3_kernel: kernel ElapsedTime in the last TCPInfo snapshot
     the client received from the server
""")
    quantile_header()
    for label, series in m.items():
        quantile_row(series, label)
    click.echo("")

    # The pairings we care about: does the sidecar track the client
    # (t1_any - t3_client), when does the server close relative to
    # the client end (t1_est - t3_client), how long after the
    # measurement stop does the server close (t1_est - t2_kernel),
    # and how much wall clock the server spends beyond the
    # measurement (t2_wall - t2_kernel).
    deltas = {
        "t1_any - t3_client": m["t1_any"] - m["t3_client"],
        "t1_est - t3_client": m["t1_est"] - m["t3_client"],
        "t1_est - t2_kernel": m["t1_est"] - m["t2_kernel"],
        "t2_wall - t2_kernel": m["t2_wall"] - m["t2_kernel"],
    }
    click.echo("Pairwise deltas (seconds):\n")
    quantile_header()
    for label, series in deltas.items():
        quantile_row(series, label)
    click.echo("")


def describe_corner_cases(df):
    """Print statistics about the long-client-duration corner cases.

    The selector t3_client > 15 s is convenient but arbitrary. A more
    principled selector targets the mechanism directly: the last sidecar
    snapshot is FIN_WAIT1 and the post-ESTABLISHED drain lasted more
    than 5 s. We print both and their overlap.
    """
    t3_client = df["t3_client_elapsed_time"]
    drain_s = df["t1_elapsed_any_s"] - df["t1_elapsed_s"]

    long_client = t3_client > 15.0
    long_drain = (df["t1_any_state"] == 4) & (drain_s > 5.0)

    n = len(df)
    sub = df[long_client]
    click.echo(
        f"Corner cases, selector A (t3_client > 15 s): "
        f"{len(sub):,}/{n:,} tests ({len(sub) / n * 100:.2f}%)"
    )
    click.echo(
        f"Corner cases, selector B (last state FIN_WAIT1, "
        f"drain > 5 s): {int(long_drain.sum()):,}/{n:,} tests "
        f"({long_drain.mean() * 100:.2f}%)"
    )
    click.echo(
        f"Overlap: A&B {int((long_client & long_drain).sum()):,}  "
        f"A only {int((long_client & ~long_drain).sum()):,}  "
        f"B only {int((~long_client & long_drain).sum()):,}\n"
    )

    click.echo("Final sidecar state within selector A:")
    states = sub["t1_any_state"].map(lambda s: TCP_STATES.get(s, str(s)))
    for name, count in states.value_counts().items():
        click.echo(f"  {name:<12} {count:5,}  ({count / len(sub) * 100:.1f}%)")
    click.echo("")

    click.echo("Within selector A, does the sidecar track the client?\n")
    quantile_header()
    quantile_row(
        df.loc[long_client, "t1_elapsed_any_s"] - t3_client[long_client],
        "t1_any - t3_client",
    )
    quantile_row(drain_s[long_client], "drain")
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

    # 1. Compute the main metric we care about (level = T3).
    df["gap_s"] = df["t3_client_elapsed_time"] - df["t3_tcp_ElapsedTime"] / 1e6

    valid = df.dropna(subset=["gap_s"])
    click.echo("T3 gap distribution (client_elapsed - server_elapsed)\n")
    describe_gap(valid["gap_s"], "All MW+MD")
    for cc in sorted(valid["country_code"].dropna().unique()):
        sub = valid[valid["country_code"] == cc]
        describe_gap(sub["gap_s"], f"country = {cc}")

    # 2. Statistics helping to reason about whether some schools in
    # a specific country are generating many outliers.
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

    # 3. Statistics explaining the gap: how each tier measures
    # the test duration, how the measures pair up, and the corner
    # cases where the client duration exceeds the server's 15 s
    # force-close (ndt-server spec.MaxRuntime).
    describe_durations(df)
    describe_corner_cases(df)


if __name__ == "__main__":
    main()
