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

With `--bbr`, the byte counters are replaced by the BBR state
(bandwidth estimate, min RTT, gains) and the pacing rate, which
help to understand why the sender keeps data in flight.

With `--limits`, the byte counters are replaced by the kernel
counters of the time spent busy, receive-window limited, and send-buffer
limited, along with the peer's advertised window and the delivery
rate, which help to understand what limited sending. It also prints
extra variables (e.g., SndMSS) useful for interpreting the output.
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
@click.option(
    "--bbr",
    "bbr",
    is_flag=True,
    help="Print BBR state instead of byte counters.",
)
@click.option(
    "--limits",
    "limits",
    is_flag=True,
    help="Print sending limits instead of byte counters.",
)
def main(uuid, bbr, limits):
    if bbr and limits:
        raise click.UsageError("--bbr and --limits are mutually exclusive")

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
    # by build_three_tier.py. We do not warn here because we do already
    # warn there; we just keep the first occurrence.
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("snapshot_index")
    df = df.drop_duplicates(subset="snapshot_index").reset_index(drop=True)

    # 3. Derive the columns common to all modes: time relative to
    # the first archived snapshot and the human-friendly TCP state.
    ts = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    out = pd.DataFrame(
        {
            "idx": df["snapshot_index"],
            "t_s": (ts - ts.iloc[0]).dt.total_seconds().round(3),
            "state": df["tcp_State"].map(lambda s: TCP_STATES.get(s, str(s))),
        }
    )

    # 4. Add the BBR state (with --bbr), the sending limits (with
    # --limits), or the byte counters (default).
    #
    # For BBR, units follow the m-lab/tcp-info v1.9.0 struct comments
    # (inetdiag/structs.go, BBRInfo): BW is in bytes/second, MinRTT
    # in microseconds, and the gains are shifted left by 8 bits
    # (i.e., 256 means 1.0). PacingRate mirrors the kernel's
    # tcpi_pacing_rate, which tcp_get_info (net/ipv4/tcp.c) copies
    # from sk_pacing_rate, documented as "bytes per second" in
    # include/net/sock.h. A snapshot without BBRInfo (e.g., the
    # first one) prints NaN.
    #
    # For the limits, units follow the m-lab/tcp-info v1.9.0 struct
    # comments (tcp/tcpinfo.go, LinuxTCPInfo): BusyTime, RWndLimited,
    # and SndBufLimited are cumulative times in microseconds, and
    # SndWnd is the peer's advertised window after scaling, in bytes.
    # DeliveryRate mirrors the kernel's tcpi_delivery_rate, which
    # tcp_compute_delivery_rate (net/ipv4/tcp.c) computes in
    # bytes/second. Because the times are cumulative, the
    # difference between two rows is exact regardless of sampling.
    #
    # We also print SndMSS with --limits because Unacked mirrors the
    # kernel's tcpi_unacked, which tcp_get_info copies from
    # packets_out, a count of segments (include/linux/tcp.h). Hence,
    # Unacked * SndMSS approximates the bytes in flight, which we
    # can compare with SndWnd to tell whether the peer's window
    # limits sending.
    #
    # The kernel references above were checked against the Ubuntu
    # linux-source-7.0.0 package, version 7.0.0-34.34.
    if bbr:
        out["bw_kbps"] = (df["bbr_BW"] * 8 / 1e3).round(1)
        out["min_rtt_ms"] = (df["bbr_MinRTT"] / 1e3).round(1)
        out["pacing_gain"] = (df["bbr_PacingGain"] / 256).round(2)
        out["cwnd_gain"] = (df["bbr_CwndGain"] / 256).round(2)
        out["pacing_kbps"] = (df["tcp_PacingRate"] * 8 / 1e3).round(1)
        out["rtt_ms"] = (df["tcp_RTT"] / 1e3).round(1)
        out["SndCwnd"] = df["tcp_SndCwnd"]
        out["Unacked"] = df["tcp_Unacked"]
    elif limits:
        out["busy_ms"] = (df["tcp_BusyTime"] / 1e3).round(0)
        out["rwnd_lim_ms"] = (df["tcp_RWndLimited"] / 1e3).round(0)
        out["sndbuf_lim_ms"] = (df["tcp_SndBufLimited"] / 1e3).round(0)
        out["SndWnd"] = df["tcp_SndWnd"]
        out["Unacked"] = df["tcp_Unacked"]
        out["SndMSS"] = df["tcp_SndMSS"]
        out["delivery_kbps"] = (df["tcp_DeliveryRate"] * 8 / 1e3).round(1)
    else:
        out["BytesSent"] = df["tcp_BytesSent"]
        out["BytesAcked"] = df["tcp_BytesAcked"]
        out["BytesRetrans"] = df["tcp_BytesRetrans"]
        out["NotsentBytes"] = df["tcp_NotsentBytes"]
        out["Unacked"] = df["tcp_Unacked"]
        out["rtt_ms"] = (df["tcp_RTT"] / 1e3).round(1)
        out["SndCwnd"] = df["tcp_SndCwnd"]

    click.echo(f"\nuuid: {uuid}")
    click.echo(f"first snapshot: {ts.iloc[0].isoformat()}")
    click.echo(f"last snapshot:  {ts.iloc[-1].isoformat()}\n")
    click.echo(out.to_string(index=False))


if __name__ == "__main__":
    main()
