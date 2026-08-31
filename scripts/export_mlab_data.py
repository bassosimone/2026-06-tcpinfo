#!/usr/bin/env -S uv run

"""Export M-Lab data by running generated SQL queries via the bq CLI."""

import gzip
import json
import subprocess
from pathlib import Path

import click

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEFAULT_PROJECT = "measurement-lab"
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
@click.option(
    "--project",
    envvar="BQ_PROJECT",
    default=DEFAULT_PROJECT,
    show_default=True,
    help="Billing project for bq query (also via the BQ_PROJECT "
    "environment variable, which the make targets inherit).",
)
def main(start_date, end_date, project):
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

        # Skip chunks that already have an output file to avoid
        # querying for data that we have already queried.
        if out_path.exists():
            click.echo(f"skipping {out_path} (exists); delete to force a re-export")
            continue

        click.echo(f"=== {table} {start.isoformat()} to {end.isoformat()} ===")

        result = subprocess.run(
            [
                "bq",
                "query",
                f"--project_id={project}",
                "--use_legacy_sql=false",
                "--format=json",
                "--max_rows=1000000",
            ],
            input=query_path.read_text(),
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )

        # On error, surface the BQ CLI error emitted on the stdout.
        if result.returncode != 0:
            click.echo(result.stdout.strip(), err=True)
            raise click.ClickException(f"bq query failed for {table} {suffix}")

        # Use a temporary file and rename so that, if the file is
        # in place, we are sure the file is complete.
        tmp_path = out_path.with_suffix(".gz.tmp")
        with gzip.open(tmp_path, "wt") as fp:
            fp.write(result.stdout)
        tmp_path.rename(out_path)

        rows = json.loads(result.stdout)
        click.echo(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
