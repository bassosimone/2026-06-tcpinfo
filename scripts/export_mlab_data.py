#!/usr/bin/env -S uv run

"""Export M-Lab data by running generated SQL queries via the bq CLI."""

import gzip
import json
import subprocess
from pathlib import Path

import click

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BQ_PROJECT = "measurement-lab"
TABLES = ["ndt7", "tcpinfo"]


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

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for table in TABLES:
        query_path = QUERIES_DIR / f"{table}_{suffix}.sql"
        if not query_path.exists():
            raise click.ClickException(
                f"query not found: {query_path} (run make generate_queries first)"
            )

        out_path = DATA_DIR / f"{table}_{suffix}.json.gz"
        click.echo(f"=== {table} {start.isoformat()} to {end.isoformat()} ===")

        result = subprocess.run(
            [
                "bq",
                "query",
                f"--project_id={BQ_PROJECT}",
                "--use_legacy_sql=false",
                "--format=json",
                "--max_rows=1000000",
            ],
            input=query_path.read_text(),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )

        with gzip.open(out_path, "wt") as fp:
            fp.write(result.stdout)

        rows = json.loads(result.stdout)
        click.echo(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
