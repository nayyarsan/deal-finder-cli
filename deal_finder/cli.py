"""
Entry point jarvis expects at: ../deal-finder-cli/deal_finder.py
Also callable as: deal-finder --item "query" or deal-finder --watchlist add "AirPods Pro 2"
"""
import asyncio
import json
import typer
from rich.console import Console
from rich.table import Table
from typing import Optional

from deal_finder.watchlist import WatchlistDB
from deal_finder.price_fetcher import fetch_current_prices
from deal_finder.deal_agent import compute_verdict, _load_calendar

app = typer.Typer(help="Deal finder — price comparison and watchlist management.")
console = Console()
db = WatchlistDB()


@app.command()
def item(query: str = typer.Argument(..., help="Product name to search for")):
    """Fetch current prices for a product (on-demand lookup for jarvis ShoppingModule)."""
    results = asyncio.run(fetch_current_prices(query))
    if not results:
        console.print(f"[yellow]No results found for: {query}[/yellow]")
        raise typer.Exit(1)
    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Store"); t.add_column("Price", justify="right"); t.add_column("URL")
    for r in sorted(results, key=lambda x: x.price):
        t.add_row(r.retailer, f"${r.price:.2f}", r.url)
    console.print(t)


@app.command()
def watchlist(
    action: str = typer.Argument(..., help="add | remove | list | check"),
    name: Optional[str] = typer.Argument(None, help="Item name (for add/remove/check)"),
    category: str = typer.Option("general", help="electronics | appliances | grocery | general"),
    target_price: Optional[float] = typer.Option(None, help="Your target price"),
):
    """Manage the watchlist and run deal intelligence."""
    if action == "add":
        if not name:
            console.print("[red]Provide item name[/red]"); raise typer.Exit(1)
        item_id = db.add_item(name, category=category, target_price=target_price)
        console.print(f"[green]Added '{name}' to watchlist (id={item_id})[/green]")

    elif action == "remove":
        if not name:
            console.print("[red]Provide item name[/red]"); raise typer.Exit(1)
        items = [i for i in db.list_items() if name.lower() in i.name.lower()]
        if not items:
            console.print(f"[yellow]No active item matching '{name}'[/yellow]")
        for i in items:
            db.remove_item(i.id)
            console.print(f"[green]Removed '{i.name}'[/green]")

    elif action == "list":
        items = db.list_items()
        if not items:
            console.print("[dim]Watchlist is empty.[/dim]")
        else:
            t = Table(show_header=True, header_style="bold")
            t.add_column("ID"); t.add_column("Name"); t.add_column("Category"); t.add_column("Target")
            for i in items:
                t.add_row(str(i.id), i.name, i.category, f"${i.target_price:.2f}" if i.target_price else "—")
            console.print(t)

    elif action == "check":
        target = name
        items = db.list_items() if not target else [i for i in db.list_items() if target.lower() in i.name.lower()]
        calendar = _load_calendar()
        for item in items:
            prices = asyncio.run(fetch_current_prices(item.name))
            history = db.get_price_history(item.id)
            verdict = compute_verdict(item, prices, history, calendar)
            color = {"buy_now": "green", "cutthroat": "bold red", "hold": "yellow",
                     "move_store": "cyan", "monitor": "dim"}.get(verdict.verdict, "white")
            console.print(f"[{color}]{verdict.verdict.upper()}[/{color}] {item.name}: {verdict.explanation}")
    else:
        console.print(f"[red]Unknown action: {action}[/red]"); raise typer.Exit(1)


if __name__ == "__main__":
    app()
