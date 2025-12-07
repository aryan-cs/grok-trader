from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

try:
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row("Left", "Right")

    panel = Panel(
        "Content",
        title=grid,
        border_style="green"
    )
    console.print(panel)
except Exception as e:
    print(f"Error: {e}")
