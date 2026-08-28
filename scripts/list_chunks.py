#!/usr/bin/env -S uv run

"""Print chunk boundaries for a date window, one chunk per line.

Each emitted line is "START:END" with START included and END excluded,
both in ISO format. This script never prints an empty chunk.

Weekly chunks stride 7 days but are clipped at calendar month
boundaries, so a chunk never spans two months and each month is a
self-contained set of chunks. This matches the chunk naming of the
May 2026 pull (May 1, 8, 15, 22, 29) and pairs with the per-month
Superset exports. Monthly chunks advance to the first day of the
next calendar month. The first chunk may be partial when the start
date is not the 1st day of the month.

Consumed by the GNUmakefile to loop the per-chunk pipeline scripts
over an arbitrary window.
"""

from datetime import date, timedelta

import click


def next_month(d: date) -> date:
    """Return the first day of the month after the one containing d."""
    if d.month >= 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


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
    "--step",
    type=click.Choice(["week", "month"]),
    default="week",
    help="Chunk stride (default: week).",
)
def main(start_date, end_date, step):
    start = start_date.date()
    end = end_date.date()
    if start >= end:
        raise click.ClickException("start date must precede end date")

    cursor = start
    while cursor < end:
        if step == "week":
            stop = min(cursor + timedelta(days=7), next_month(cursor))
        else:
            stop = next_month(cursor)
        stop = min(stop, end)
        click.echo(f"{cursor.isoformat()}:{stop.isoformat()}")
        cursor = stop


if __name__ == "__main__":
    main()
