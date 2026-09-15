from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from quercus_sync.config import load_config, save_config
from quercus_sync.mock import MockCanvasClient
from quercus_sync.sync import CourseSync, course_access

app = typer.Typer(
    add_completion=False,
    help="Download your UTM Quercus course files, pages, and assignments via the Canvas API.",
)
console = Console()


def _client(demo: bool):
    config = load_config()
    if demo or config.demo_mode or not config.token:
        console.print("[italic]Using the built-in demo campus (no Quercus token).[/italic]")
        return MockCanvasClient(), config
    from quercus_sync.canvas import CanvasClient

    return CanvasClient(config.canvas_url, config.token), config


@app.command()
def doctor() -> None:
    """Check whether a token can talk to Quercus."""
    config = load_config()
    if config.demo_mode or not config.token:
        console.print("No token saved. Demo mode is on — run [bold]quercus-sync serve[/bold] to paste one.")
        raise typer.Exit(0)
    from quercus_sync.canvas import CanvasClient, CanvasError

    try:
        with CanvasClient(config.canvas_url, config.token) as client:
            me = client.me()
    except CanvasError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"Signed in as [bold]{me.get('name')}[/bold] ({me.get('login_id') or me.get('primary_email')})")


@app.command("courses")
def list_courses(demo: bool = typer.Option(False, "--demo", help="List the sample UTM courses.")) -> None:
    """List every course this token can still open, including past terms."""
    client, _config = _client(demo)
    sync = CourseSync(client, Path("."))
    table = Table(title="Courses you can still open")
    table.add_column("ID")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("Term")
    table.add_column("Access")
    for course in sync.list_courses():
        term = (course.get("term") or {}).get("name") or ""
        table.add_row(
            str(course["id"]),
            course.get("course_code") or "",
            course.get("name") or "",
            term,
            "past term" if course_access(course) == "past" else "current",
        )
    console.print(table)


@app.command()
def sync(
    demo: bool = typer.Option(False, "--demo", help="Archive the sample courses, not your real Quercus."),
    course_id: Optional[list[int]] = typer.Option(None, "--course", help="Limit to one or more Canvas course IDs."),
    out: Optional[Path] = typer.Option(None, "--out", help="Download directory."),
) -> None:
    """Download course files, pages, assignments, and announcements."""
    client, config = _client(demo)
    dest = Path(out or config.download_dir)
    engine = CourseSync(
        client,
        dest,
        include=config.include,
        on_event=lambda event: _print_event(event),
    )
    result = engine.run(course_id)
    console.print(
        f"[green]Done.[/green] {result.stats.downloaded} saved, "
        f"{result.stats.skipped} skipped, {result.stats.failed} failed → {result.root}"
    )
    if result.errors:
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 43147,
) -> None:
    """Open the local archive UI."""
    import uvicorn

    console.print(f"Quercus Sync → http://{host}:{port}")
    uvicorn.run("quercus_sync.web:app", host=host, port=port, log_level="info")


@app.command("set-token")
def set_token(
    token: str = typer.Option(..., prompt=True, hide_input=True),
    url: str = typer.Option("https://q.utoronto.ca"),
) -> None:
    """Save a Quercus access token on this machine."""
    config = load_config()
    config.token = token.strip()
    config.canvas_url = url.rstrip("/")
    config.demo_mode = False
    save_config(config)
    console.print("Token saved to data/config.json (not committed).")


def _print_event(event: dict) -> None:
    kind = event.get("type")
    if kind == "log":
        console.print(event.get("message"))
    elif kind == "course_start":
        console.print(f"\n[bold]{event.get('course')}[/bold]  {event.get('term')}")
    elif kind == "item":
        status = event.get("status")
        path = event.get("path")
        if status == "downloaded":
            console.print(f"  [green]+[/green] {path}")
        elif status == "skipped":
            console.print(f"  [dim]· {path} ({event.get('reason')})[/dim]")
        else:
            console.print(f"  [red]x {path} ({event.get('reason')})[/red]")
    elif kind == "error":
        console.print(f"[red]{event.get('message')}[/red]")


if __name__ == "__main__":
    app()
