#!/usr/bin/env -S uv run

"""Build the per-snapshot parquet from a tcpinfo weekly JSON export
containing tcpinfo data for download and upload ndt7 tests."""

import gzip
import json
from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TCPINFO_FIELDS = [
    "State",
    "CAState",
    "ElapsedTime",
    "BytesAcked",
    "BytesReceived",
    "BytesSent",
    "BytesRetrans",
    "DeliveryRate",
    "PacingRate",
    "MinRTT",
    "RTT",
    "RTTVar",
    "SndCwnd",
    "SndMSS",
    "SndWnd",
    "Unacked",
    "Sacked",
    "Lost",
    "Retrans",
    "BusyTime",
    "RWndLimited",
    "SndBufLimited",
    "TotalRetrans",
    "NotsentBytes",
]

BBRINFO_FIELDS = [
    "BW",
    "MinRTT",
    "PacingGain",
    "CwndGain",
]


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

    in_path = DATA_DIR / f"tcpinfo_{suffix}.json.gz"
    if not in_path.exists():
        raise click.ClickException(f"input not found: {in_path}")
    out_path = DATA_DIR / f"tcpinfo_{suffix}.parquet"

    with gzip.open(in_path, "rt") as fp:
        data = json.load(fp)
    click.echo(f"loaded {in_path} ({len(data)} rows)")

    rows = []
    for item in data:
        r = json.loads(item["row"])
        uuid = r["id"]
        snaps = r.get("raw", {}).get("Snapshots") or []

        for idx, snap in enumerate(snaps):
            tcp = snap.get("TCPInfo") or {}
            bbr = snap.get("BBRInfo") or {}
            row = {
                "uuid": uuid,
                "timestamp": snap.get("Timestamp"),
                "snapshot_index": idx,
            }
            for field in TCPINFO_FIELDS:
                row[f"tcp_{field}"] = tcp.get(field)
            for field in BBRINFO_FIELDS:
                row[f"bbr_{field}"] = bbr.get(field)
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    n_tests = df["uuid"].nunique()
    click.echo(f"wrote {out_path} ({len(df)} snapshots, {n_tests} tests)")


if __name__ == "__main__":
    main()
