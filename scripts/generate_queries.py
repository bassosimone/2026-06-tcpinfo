#!/usr/bin/env -S uv run

"""Generate SQL queries from templates by substituting date placeholders."""

from datetime import date
from pathlib import Path

import click

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "queries" / "templates"
QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"


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
    "--template",
    multiple=True,
    help="Template name(s) to generate. If omitted, generates all.",
)
def main(start_date, end_date, template):
    start = start_date.date()
    end = end_date.date()
    suffix = f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"

    if template:
        template_paths = []
        for name in template:
            path = TEMPLATES_DIR / f"{name}.sql"
            if not path.exists():
                raise click.ClickException(f"template not found: {path}")
            template_paths.append(path)
    else:
        template_paths = sorted(TEMPLATES_DIR.glob("*.sql"))

    for template_path in template_paths:
        name = template_path.stem
        sql = template_path.read_text()
        sql = sql.replace("@DATE_START@", start.isoformat())
        sql = sql.replace("@DATE_END@", end.isoformat())
        out_path = QUERIES_DIR / f"{name}_{suffix}.sql"
        out_path.write_text(sql)
        click.echo(f"wrote {out_path}")


if __name__ == "__main__":
    main()
