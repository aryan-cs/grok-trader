import time
import sys
import os
import argparse
from datetime import datetime
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'pre-processing')))
from process_market import get_market_sentiment

console = Console()

def display_insight(market, item):
    sentiment_color = "green" if item['sentiment'] == 'positive' else "red" if item['sentiment'] == 'negative' else "yellow"
    
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(f"[bold cyan]{market}[/bold cyan]", f"[{sentiment_color}]{item['sentiment'].upper()}[/{sentiment_color}]")
    
    content = Group(
        grid,
        f"\n{item['content']}\n\n[italic dim]Reasoning: {item['reasoning']}[/italic dim]"
    )
    
    panel = Panel(
        content,
        border_style=sentiment_color,
        subtitle=f"Source: {item['source']}"
    )
    console.print(panel)

def watch_markets(markets, interval=120, accounts=None):
    console.print(f"[bold blue]Grok Hawk Watcher Started[/bold blue]")
    console.print(f"Monitoring {len(markets)} markets every {interval} seconds...\n")
    if accounts:
        console.print(f"[bold yellow]Special Account Monitoring Enabled:[/bold yellow] {len(accounts)} accounts loaded.")

    while True:
        for market in markets:
            try:
                market_label = market if market else "General Account Feed"
                console.print(f"[dim]Scanning: {market_label}...[/dim]")
                
                results = get_market_sentiment(market, limit=10, verbose=False, accounts=accounts)
                
                relevant_count = 0
                for item in results:
                    display_insight(market_label, item)
                    relevant_count += 1
                
                if relevant_count == 0:
                    console.print(f"[dim]No new significant insights for: {market_label}[/dim]")
                    
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
    parser.add_argument("--account-list", action="store_true", help="Enable monitoring of specific X accounts from accounts.txt")
    
    args = parser.parse_args()
    
    accounts = None
    if args.account_list:
        accounts_file = os.path.join(os.path.dirname(__file__), 'accounts.txt')
        if os.path.exists(accounts_file):
            with open(accounts_file, 'r') as f:
                accounts = [line.strip() for line in f if line.strip()]
        else:
            console.print(f"[bold red]Warning:[/bold red] {accounts_file} not found. Ignoring --account-list.")
    
    markets_to_watch = args.markets
    if not markets_to_watch:
        if args.account_list:
            markets_to_watch = [None]
        else:
            markets_to_watch = [
                "Will Bitcoin hit 100k by end of 2025?",
                "Will AI take over the world?",
                "Who will win the 2024 US Election?"
            ]
    
    try:
        watch_markets(markets_to_watch, interval=args.interval, accounts=accounts)
    except KeyboardInterrupt:
        console.print("\n[bold red]Watcher stopped by user.[/bold red]")
