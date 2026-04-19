"""
RepoScan CLI — run directly when you don't need the web UI.

Usage:
  python main.py scan https://github.com/owner/repo
  python main.py scan https://github.com/owner/repo --verbose
  python main.py graphs https://github.com/owner/repo
  python main.py similar https://github.com/owner/repo
  python main.py serve   (start FastAPI backend)
"""

from __future__ import annotations

import sys
import json
import os

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

load_dotenv()
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        console.print(f"[bold red]Error:[/] {name} is not set. "
                      "Copy .env.example to .env and fill it in.")
        sys.exit(1)
    return val


def _print_scan(result: dict) -> None:
    repo = result.get("repo", {})
    console.print(Panel.fit(
        f"[bold cyan]{repo.get('full_name', 'Unknown')}[/]\n"
        f"[dim]{repo.get('description', '')}[/]",
        title="[bold]Repository[/]",
        border_style="cyan",
    ))
    console.print(f"\n[bold]Summary:[/] {result.get('summary', 'N/A')}\n")
    console.print(f"[bold]Purpose:[/] {result.get('purpose', 'N/A')}\n")

    # Stats table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("⭐ Stars",  str(repo.get("stars", 0)))
    table.add_row("🍴 Forks",  str(repo.get("forks", 0)))
    table.add_row("🐛 Issues", str(repo.get("open_issues", 0)))
    table.add_row("🌐 Language", repo.get("language", "Unknown"))
    table.add_row("📄 License", repo.get("license", "None"))
    console.print(table)

    # Tech stack
    if result.get("tech_stack"):
        console.print(f"\n[bold]Tech Stack:[/] {', '.join(result['tech_stack'])}")

    # Key features
    if result.get("key_features"):
        console.print("\n[bold]Key Features:[/]")
        for feat in result["key_features"]:
            console.print(f"  • {feat}")

    # Activity
    activity = result.get("activity", {})
    console.print(f"\n[bold]Commit Trend:[/] {activity.get('commit_trend', 'unknown')} "
                  f"({activity.get('total_commits_last_year', 0)} commits last year)")

    # Similar repos
    similar = result.get("similar_repos", [])
    if similar:
        console.print(f"\n[bold]Similar Repos ({len(similar)}):[/]")
        for r in similar[:5]:
            console.print(f"  • [link={r.get('html_url', '')}]{r.get('full_name', '')}[/link]"
                          f" ⭐{r.get('stars', 0):,}  {r.get('language', '')}")


# ---------------------------------------------------------------------------
# CLI groups
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """🔭 RepoScan — AI-powered GitHub repository scanner."""


@cli.command()
@click.argument("github_url")
@click.option("--verbose", "-v", is_flag=True, help="Show agent reasoning steps")
@click.option("--json-out", is_flag=True, help="Output raw JSON instead of pretty print")
def scan(github_url: str, verbose: bool, json_out: bool) -> None:
    """Run a full AI-powered scan on GITHUB_URL."""
    _require_env("OPENAI_API_KEY")

    console.print(f"\n[bold cyan]Scanning[/] {github_url} …\n")
    from src.agents.scanner_agent import scan_repository

    with console.status("[bold green]Agent working…"):
        result = scan_repository(github_url, verbose=verbose)

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        _print_scan(result)


@cli.command()
@click.argument("github_url")
def graphs(github_url: str) -> None:
    """Generate Plotly graphs for GITHUB_URL (no LLM needed)."""

    console.print(f"\n[bold cyan]Fetching data for[/] {github_url} …")
    from src.tools.github_tools import (
        get_repo_info, get_language_breakdown, get_contributors, get_commit_activity,
    )
    from src.graphs.repo_visualizer import build_all_graphs
    import pathlib

    repo_info = get_repo_info.invoke(github_url)
    lang = get_language_breakdown.invoke(github_url)
    contributors = get_contributors.invoke(github_url)
    activity = get_commit_activity.invoke(github_url)

    scan_data = {
        "repo": repo_info,
        "language_breakdown": lang,
        "top_contributors": contributors,
        "commit_activity": activity,
        "similar_repos": [],
    }
    graphs_data = build_all_graphs(scan_data)

    out_dir = pathlib.Path(os.getenv("OUTPUT_DIR", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "graphs.json"
    out_file.write_text(json.dumps(graphs_data, indent=2))
    console.print(f"[bold green]✓[/] Graphs saved to {out_file}")


@cli.command()
@click.argument("github_url")
def similar(github_url: str) -> None:
    """Find similar repositories for GITHUB_URL."""

    console.print(f"\n[bold cyan]Finding similar repos for[/] {github_url} …")
    from src.tools.similarity_tools import find_similar_repos

    with console.status("Searching…"):
        repos = find_similar_repos.invoke(github_url)

    if not repos or "error" in repos[0]:
        console.print("[red]No results or error.[/]")
        return

    for r in repos:
        console.print(
            f"• [link={r.get('html_url', '')}][bold]{r.get('full_name', '')}[/bold][/link]"
            f"  ⭐{r.get('stars', 0):,}  [{r.get('language', 'Unknown')}]"
            f"\n  {r.get('description', 'No description')}\n"
        )


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.option("--reload", is_flag=True, help="Auto-reload on file changes (dev mode)")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the FastAPI backend server."""
    import uvicorn
    console.print(f"[bold green]Starting RepoScan API[/] on http://{host}:{port}")
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    cli()
