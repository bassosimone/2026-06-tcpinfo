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


def describe_closers(df):
    """Print who closed the connection first, by client duration.

    We read the first non-ESTABLISHED sidecar state: FIN_WAIT1 or
    later means the server sent its FIN first, CLOSE_WAIT or LAST_ACK
    means the client did, CLOSING means both sent a FIN before seeing
    the other's (simultaneous close). Because the ETL thins snapshots,
    the recorded state may be later than the first one the socket
    entered. When every archived snapshot is ESTABLISHED, we do not
    know how the socket ended (the sidecar saw no orderly close).
    """
    state = df["t1_first_non_est_state"]
    who = pd.Series("unknown", index=df.index)
    who[state.isin([4, 5, 6])] = "server"
    who[state.isin([8, 9])] = "client"
    who[state == 11] = "both"

    # Bins on the client duration: below 9.5 s (early end), 0.5 s
    # steps across the normal end and the 12 s timer, and the tail
    # above the 15 s server force-close. Start included, end excluded.
    edges = [0, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 15, float("inf")]
    labels = [f"[{a}, {b})" for a, b in zip(edges[:-1], edges[1:])]
    bins = pd.cut(df["t3_client_elapsed_time"], edges, right=False, labels=labels)

    cols = ["server", "client", "both", "unknown"]
    table = pd.crosstab(bins, who).reindex(columns=cols, fill_value=0)
    table["n"] = table.sum(axis=1)

    click.echo("Who closed first, by t3_client bin (counts, then row %):")
    click.echo(
        "  server: first non-ESTABLISHED sidecar state is FIN_WAIT1/2 or TIME_WAIT"
    )
    click.echo("  client: CLOSE_WAIT or LAST_ACK; both: CLOSING (simultaneous close)")
    click.echo("  unknown: every archived snapshot is ESTABLISHED\n")
    header = "  ".join(f"{c:>8}" for c in table.columns)
    click.echo(f"  {'t3_client':<14} {header}")
    for label, row in table.iterrows():
        cells = "  ".join(f"{int(v):8,}" for v in row)
        click.echo(f"  {label:<14} {cells}")
    click.echo("")
    click.echo(f"  {'t3_client':<14} {header}")
    for label, row in table.iterrows():
        n = row["n"]
        cells = "  ".join(f"{v / n * 100:7.1f}%" for v in row[cols])
        click.echo(f"  {label:<14} {cells}  {int(n):8,}")
    click.echo("")


def describe_classes(df):
    """Print the three-class model of the TCP-level condition at close.

    The classes describe where the sender's data was being held up,
    as seen by the tcp-info sidecar, before user space reacts:

      Z (flow control): the receiver advertised a zero window at some
        point while ESTABLISHED (t1_sndwnd_min == 0).
      Q (bufferbloat): at the last ESTABLISHED snapshot, the backlog
        the kernel still has to deliver (NotsentBytes in the socket
        send buffer plus Unacked * SndMSS in flight) would take one
        second or more at the test's mean throughput (BytesAcked over
        t1_elapsed_s). Most of this backlog is the server's own send
        buffer, which the kernel autotunes regardless of path rate.
      O (rest): neither.

    Z takes precedence because a stalled receiver also leaves a
    backlog. We restrict to tests whose client reported more than
    9 s, so that early ends (the setup eating the 12 s client budget)
    do not mix with the drain symptoms. Both the 1 s backlog cut and
    the 9 s cut are arbitrary cuts through continuous distributions.
    In an ad-hoc run (2026-09-30, not reproduced by this script),
    raising the backlog cut to 2 s and 5 s reduced the Q share from
    17.9% to 11.1% and 2.6%, and the share of the tests above 15 s
    attributed to Q from 84% to 78% and 59%.
    """
    sub = df[df["t3_client_elapsed_time"] > 9].copy()

    # 1. Classify. A test with no acked bytes has no rate; we clip
    # the rate to one byte per second so that a nonzero backlog
    # counts as (effectively) infinite drain time.
    backlog = sub["t1_tcp_NotsentBytes"] + sub["t1_tcp_Unacked"] * sub["t1_tcp_SndMSS"]
    rate = (sub["t1_tcp_BytesAcked"] / sub["t1_elapsed_s"].clip(lower=0.1)).clip(
        lower=1.0
    )
    sub["backlog_s"] = backlog / rate
    cls = pd.Series("O", index=sub.index)
    cls[sub["backlog_s"] >= 1.0] = "Q"
    cls[sub["t1_sndwnd_min"] == 0] = "Z"
    sub["cls"] = cls
    order = ["Z", "Q", "O"]
    names = {"Z": "Z flow control", "Q": "Q bufferbloat", "O": "O rest"}

    # 2. Class by symptom, as counts with the column percentage in
    # parentheses. Each column sums to 100%: the n column gives the
    # class share of the population, and each symptom column says
    # which class the tests showing that symptom belong to.
    sub["drain_s"] = sub["t1_elapsed_any_s"] - sub["t1_elapsed_s"]
    symptoms = [
        ("endpoint>15s", sub["t1_elapsed_any_s"] > 15),
        ("drain>5s", sub["drain_s"] > 5),
        ("client>12.5s", sub["t3_client_elapsed_time"] > 12.5),
        ("client>15s", sub["t3_client_elapsed_time"] > 15),
    ]
    counts = pd.DataFrame(
        {
            label: [int(cond[sub["cls"] == c].sum()) for c in order]
            for label, cond in symptoms
        },
        index=order,
    )
    counts.insert(0, "n", [int((sub["cls"] == c).sum()) for c in order])

    click.echo("TCP-level condition at close (tests with t3_client > 9 s):")
    click.echo("  Z: zero send window seen while ESTABLISHED (flow control)")
    click.echo("  Q: backlog at close (unsent + in flight) >= 1 s at mean throughput")
    click.echo("  O: neither; Z takes precedence over Q")
    click.echo("  cells: count (% of the column total)\n")
    header = "  ".join(f"{c:>16}" for c in counts.columns)
    click.echo(f"  {'class':<16} {header}")
    totals = counts.sum()
    for c in order:
        cells = "  ".join(
            f"{int(v):8,} ({v / t * 100:5.1f}%)" for v, t in zip(counts.loc[c], totals)
        )
        click.echo(f"  {names[c]:<16} {cells}")
    cells = "  ".join(f"{int(v):8,}         " for v in totals)
    click.echo(f"  {'total':<16} {cells}\n")

    # 4. Network view per class, at the last ESTABLISHED snapshot:
    # p50 [p25, p75]. Units follow scripts/dump_test_snapshots.py
    # (RTTs in microseconds, rates in bytes per second).
    metrics = [
        (
            "mean throughput (Mbit/s)",
            sub["t1_tcp_BytesAcked"] * 8 / 1e6 / sub["t1_elapsed_s"].clip(lower=0.1),
        ),
        ("BBR max BW (Mbit/s)", sub["t1_bbr_BW"] * 8 / 1e6),
        ("MinRTT (ms)", sub["t1_tcp_MinRTT"] / 1e3),
        ("smoothed RTT (ms)", sub["t1_tcp_RTT"] / 1e3),
        ("backlog at close (s)", sub["backlog_s"]),
        (
            "rwnd-limited / busy",
            sub["t1_tcp_RWndLimited"] / sub["t1_tcp_BusyTime"].clip(lower=1),
        ),
    ]

    def cell(series):
        q = series.quantile([0.25, 0.5, 0.75])
        digits = 2 if q[0.75] < 1 else 1
        return f"{q[0.5]:.{digits}f} [{q[0.25]:.{digits}f}, {q[0.75]:.{digits}f}]"

    click.echo("  Per class, p50 [p25, p75] at the last ESTABLISHED snapshot:\n")
    header = "  ".join(f"{names[c]:>20}" for c in order)
    click.echo(f"  {'':<26} {header}")
    for label, series in metrics:
        cells = "  ".join(f"{cell(series[sub['cls'] == c]):>20}" for c in order)
        click.echo(f"  {label:<26} {cells}")
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
    # the test duration, who closed the connection first, and the
    # TCP-level condition at close for the long tests (those where
    # the client duration exceeds ~9 s; see describe_classes).
    describe_durations(df)
    describe_closers(df)
    describe_classes(df)


if __name__ == "__main__":
    main()
