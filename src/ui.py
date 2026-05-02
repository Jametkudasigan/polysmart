"""
Terminal UI renderer using Rich library.
Provides boxed, detailed, non-spamming display with countdown.
"""
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.align import Align

console = Console()


class BotUI:
    """Rich-based terminal UI for the Polymarket BTC Bot."""

    def __init__(self):
        self.live: Optional[Live] = None
        self.last_render_time = 0
        self.render_interval = 0.5  # Minimum seconds between renders
        self._pending_update = False
        self._state: Dict[str, Any] = {
            "mode": "SCANNING",
            "balance_usdc": 0.0,
            "signal_source": "-",
            "signal_direction": "-",
            "signal_strength": "-",
            "btc_price": 0.0,
            "btc_change_24h": 0.0,
            "market_slug": "-",
            "market_link": "-",
            "market_time_remaining": 0,
            "yes_price": 0.0,
            "no_price": 0.0,
            "yes_volume_pct": 0.0,
            "spread": 0.0,
            "entry_amount": 0.0,
            "entry_side": "-",
            "entry_price": 0.0,
            "position_pnl": 0.0,
            "position_status": "-",
            "logs": [],
            "countdown_target": None,
            "countdown_label": "",
        }

    def start(self):
        """Start the live display."""
        self.live = Live(self._build_layout(), refresh_per_second=4, console=console)
        self.live.start()

    def stop(self):
        """Stop the live display."""
        if self.live:
            self.live.stop()
            self.live = None

    def update(self, **kwargs):
        """Update state and refresh display (throttled)."""
        self._state.update(kwargs)
        self._pending_update = True
        now = time.time()
        if now - self.last_render_time >= self.render_interval:
            self._refresh()

    def _refresh(self):
        """Force refresh the display."""
        if self.live and self._pending_update:
            self.live.update(self._build_layout())
            self.last_render_time = time.time()
            self._pending_update = False

    def log(self, message: str):
        """Add a log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._state["logs"].append(f"[{timestamp}] {message}")
        if len(self._state["logs"]) > 20:
            self._state["logs"] = self._state["logs"][-20:]
        self.update()

    def _build_layout(self) -> Layout:
        """Build the full layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=8),
        )
        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        layout["header"].update(self._build_header())
        layout["left"].update(self._build_left_panel())
        layout["right"].update(self._build_right_panel())
        layout["footer"].update(self._build_footer())
        return layout

    def _build_header(self) -> Panel:
        """Build header with mode and countdown."""
        state = self._state
        mode = state["mode"]

        # Countdown
        countdown_text = ""
        if state["countdown_target"]:
            remaining = max(0, state["countdown_target"] - time.time())
            total = state.get("countdown_total", 300)
            pct = 1.0 - (remaining / total) if total > 0 else 0
            bar_filled = int(30 * pct)
            bar_empty = 30 - bar_filled
            bar = "█" * bar_filled + "░" * bar_empty
            countdown_text = f"\n{state['countdown_label']} [{bar}] {remaining:.1f}s"

        mode_colors = {
            "SCANNING": "cyan",
            "ANALYZING": "yellow",
            "ENTERING": "magenta",
            "MONITORING": "green",
            "CASHING_OUT": "blue",
            "IDLE": "white",
        }
        color = mode_colors.get(mode, "white")

        text = Text()
        text.append("🤖 POLYMARKET BTC 5M BOT ", style="bold white on dark_blue")
        text.append(f"  MODE: ", style="dim")
        text.append(f"{mode}", style=f"bold {color}")
        text.append(countdown_text, style="bright_yellow")

        return Panel(Align.center(text), border_style=color, padding=(0, 1))

    def _build_left_panel(self) -> Panel:
        """Build left panel: Wallet & Signal."""
        state = self._state

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan", width=20)
        table.add_column("Value", style="white")

        # Wallet Section
        table.add_row("", "")
        table.add_row("💰 WALLET", "", style="bold bright_yellow")
        table.add_row("  Balance USDC", f"${state['balance_usdc']:.2f}")
        table.add_row("  Funder Address", f"{state.get('funder_address', '-')[:10]}...{state.get('funder_address', '-')[-8:]}")

        # Signal Section
        table.add_row("", "")
        table.add_row("📊 SIGNAL", "", style="bold bright_green")
        table.add_row("  Source", state["signal_source"])
        table.add_row("  Direction", state["signal_direction"], style="bold green" if "UP" in state["signal_direction"] else "bold red" if "DOWN" in state["signal_direction"] else "")
        table.add_row("  Strength", state["signal_strength"])
        table.add_row("  BTC Price", f"${state['btc_price']:,.2f}")
        table.add_row("  BTC 24h Chg", f"{state['btc_change_24h']:+.2f}%", style="green" if state['btc_change_24h'] >= 0 else "red")

        return Panel(table, title="[bold]Account & Signal[/bold]", border_style="bright_blue", padding=(1, 1))

    def _build_right_panel(self) -> Panel:
        """Build right panel: Market & Position."""
        state = self._state
        mode = state["mode"]

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan", width=20)
        table.add_column("Value", style="white")

        # Market Section
        table.add_row("", "")
        table.add_row("📈 MARKET", "", style="bold bright_magenta")
        table.add_row("  Slug", state["market_slug"])
        table.add_row("  YES Price", f"${state['yes_price']:.4f}")
        table.add_row("  NO Price", f"${state['no_price']:.4f}")
        table.add_row("  YES Volume %", f"{state['yes_volume_pct']*100:.1f}%")
        table.add_row("  Spread", f"{state['spread']:.4f}", style="green" if state['spread'] <= 0.02 else "red")
        table.add_row("  Time Left", f"{state['market_time_remaining']:.0f}s")

        if state["market_link"] and state["market_link"] != "-":
            table.add_row("  Link", state["market_link"], style="dim blue")

        # Position Section (only show if not scanning)
        if mode in ("ENTERING", "MONITORING", "CASHING_OUT"):
            table.add_row("", "")
            table.add_row("🎯 POSITION", "", style="bold bright_cyan")
            table.add_row("  Entry Amount", f"${state['entry_amount']:.2f} USDC")
            side_style = "bold green" if "YES" in state["entry_side"] else "bold red"
            table.add_row("  Side", state["entry_side"], style=side_style)
            table.add_row("  Entry Price", f"${state['entry_price']:.4f}")
            table.add_row("  Status", state["position_status"])
            pnl_style = "green" if state['position_pnl'] >= 0 else "red"
            table.add_row("  PnL", f"${state['position_pnl']:+.2f}", style=pnl_style)

        return Panel(table, title="[bold]Market & Position[/bold]", border_style="bright_magenta", padding=(1, 1))

    def _build_footer(self) -> Panel:
        """Build footer: Logs."""
        logs = "\n".join(self._state["logs"][-6:])
        return Panel(logs, title="[bold]Activity Log[/bold]", border_style="dim", padding=(0, 1))


# Singleton instance
ui = BotUI()
