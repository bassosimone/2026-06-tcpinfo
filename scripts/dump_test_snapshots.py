#!/usr/bin/env -S uv run

"""Dump the tcpinfo sidecar snapshot timeline of a single test.

Scans the weekly `data/tcpinfo_*.parquet` files for the given UUID
and prints one row per archived snapshot: relative time, TCP state,
byte counters, RTT, and congestion window. The tool is meant for
staring at individual tests (e.g. the long-duration corner cases
that may help us to understand why, based on network data, the
`giga-meter` may run for 50+ seconds while the ndt7 test is expected
to terminate on both ends after 10s plus leeway (see v0.11.0
of the ndt7 spec).

The relative time is computed from the first archived snapshot of
the test itself, so the output does not depend on the three-tier
join at the cost of not being exactly comparable with the definition
of elapsed time we use in other scripts.

Note that the archived timeline is sparse: the sidecar records
a snapshot only when it differs from the previous one, and the ETL
pipeline keeps only every tenth snapshot, always preserving the last
one. This explains why we observe fewer snapshots than the ones the
sidecar is supposed to collect (~one every 10ms).
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


@click.command()
@click.option(
    "--uuid",
    "uuid",
    required=True,
    help="UUID of the test to dump.",
)
def main(uuid):
    # 1. Scan the weekly files, keeping only the rows matching the
    # UUID. The pyarrow filter pushdown avoids materializing each
    # whole file in memory.
    frames = []
    for p in sorted(DATA_DIR.glob("tcpinfo_*.parquet")):
        df = pd.read_parquet(p, filters=[("uuid", "==", uuid)])
        if len(df) > 0:
            click.echo(f"{p.name}: {len(df)} snapshots")
            frames.append(df)
    if not frames:
        raise click.ClickException(f"uuid not found: {uuid}")

    # 2. Concatenate and order by snapshot index. Duplicate indexes
    # would indicate the same upstream data quality issues handled
    # by build_three_tier.py. We do not warn here because we do
    # already warn there; we just keep the first occurrence.
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("snapshot_index")
    df = df.drop_duplicates(subset="snapshot_index").reset_index(drop=True)

    # 3. Derive the human-friendly columns: time relative to the
    # first archived snapshot and RTT in milliseconds (tcp_RTT is
    # in microseconds so we need to divide by 1e03).
    ts = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    out = pd.DataFrame(
        {
            "idx": df["snapshot_index"],
            "t_s": (ts - ts.iloc[0]).dt.total_seconds().round(3),
            "state": df["tcp_State"].map(lambda s: TCP_STATES.get(s, str(s))),
            "BytesSent": df["tcp_BytesSent"],
            "BytesAcked": df["tcp_BytesAcked"],
            "BytesRetrans": df["tcp_BytesRetrans"],
            "NotsentBytes": df["tcp_NotsentBytes"],
            "Unacked": df["tcp_Unacked"],
            "rtt_ms": (df["tcp_RTT"] / 1e3).round(1),
            "SndCwnd": df["tcp_SndCwnd"],
        }
    )

    click.echo(f"\nuuid: {uuid}")
    click.echo(f"first snapshot: {ts.iloc[0].isoformat()}")
    click.echo(f"last snapshot:  {ts.iloc[-1].isoformat()}\n")
    click.echo(out.to_string(index=False))


if __name__ == "__main__":
    main()
