import time
import sys
import os
import argparse
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'market2datafeed')))
from process_market import get_market_sentiment

console = Console()

def display_insight(market, item):
    sentiment_color = "green" if item['sentiment'] == 'positive' else "red" if item['sentiment'] == 'negative' else "yellow"
    
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(f"[bold cyan]{market}[/bold cyan]", f"[{sentiment_color}]{item['sentiment'].upper()}[/{sentiment_color}]")
    
    panel = Panel(
        f"{item['content']}\n\n[italic dim]Reasoning: {item['reasoning']}[/italic dim]",
        title=grid,
        border_style=sentiment_color,
        subtitle=f"Source: {item['source']}"
    )
    console.print(panel)

def watch_markets(markets, interval=120):
    console.print(f"[bold blue]Grok Hawk Watcher Started[/bold blue]")
    console.print(f"Monitoring {len(markets)} markets every {interval} seconds...\n")

    while True:
        for market in markets:
            try:
                console.print(f"[dim]Scanning: {market}...[/dim]")
                
                results = get_market_sentiment(market, limit=10, verbose=False)
                
                relevant_count = 0
                for item in results:
                    display_insight(market, item)
                    relevant_count += 1
                
                if relevant_count == 0:
                    console.print(f"[dim]No new significant insights for: {market}[/dim]")
                    
            except Exception as e:
                console.print(f"[bold red]Error monitoring {market}: {e}[/bold red]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(f"[cyan]Next scan in...[/cyan]", total=interval)
            for _ in range(interval):
                time.sleep(1)
                progress.advance(task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grok Hawk - Market Watcher")
    parser.add_argument("markets", nargs="*", help="List of markets to monitor")
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    markets_to_watch = args.markets
    if not markets_to_watch:
        markets_to_watch = [
            "Will Bitcoin hit 100k by end of 2025?",
            "Will AI take over the world?",
            "Who will win the 2024 US Election?"
        ]
    
    try:
        watch_markets(markets_to_watch, interval=args.interval)
    except KeyboardInterrupt:
        console.print("\n[bold red]Watcher stopped by user.[/bold red]")
