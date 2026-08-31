#!/usr/bin/env -S uv run

"""Build per-test download parquet from a Superset CSV export."""

import csv
import gzip
import json
from pathlib import Path

import click
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TCPINFO_FIELDS = [
    "State",
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

    in_path = DATA_DIR / f"superset_{suffix}.csv.gz"
    if not in_path.exists():
        raise click.ClickException(f"input not found: {in_path}")
    out_path = DATA_DIR / f"superset_{suffix}_download.parquet"

    rows = []
    with gzip.open(in_path, "rt") as fp:
        reader = csv.DictReader(fp)
        for item in reader:
            try:
                rj = json.loads(item["results_json"])
            except json.JSONDecodeError, TypeError:
                continue
            s2c = rj.get("NDTResult.S2C")
            if not s2c:
                continue
            lsm = s2c.get("LastServerMeasurement")
            if not lsm:
                continue

            tcp = lsm.get("TCPInfo") or {}
            bbr = lsm.get("BBRInfo") or {}
            lcm = s2c.get("LastClientMeasurement") or {}

            row = {
                "uuid": item["uuid"],
                "country_code": item.get("country_code"),
                "school_id": item.get("school_id"),
                "giga_id_school": item.get("giga_id_school"),
            }
            for field in TCPINFO_FIELDS:
                row[f"tcp_{field}"] = tcp.get(field)
            for field in BBRINFO_FIELDS:
                row[f"bbr_{field}"] = bbr.get(field)
            row["client_elapsed_time"] = lcm.get("ElapsedTime")
            row["client_num_bytes"] = lcm.get("NumBytes")
            rows.append(row)

    click.echo(f"loaded {in_path} ({len(rows)} download tests)")

    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    click.echo(f"wrote {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
