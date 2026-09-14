"""``missionctl`` CLI shell.

This is scaffold only (T1): the Typer app wiring, no real commands yet.
Every workflow in PRD §7 (auth, crew, missions, matching, assignments) lands
here in T7, each command a thin ``httpx`` call against the running API.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="missionctl",
    help="A thin HTTP client over the Mission Control API. Commands land in T7.",
)


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo("missionctl 0.1.0 (scaffold - commands land in T7)")


if __name__ == "__main__":
    app()
