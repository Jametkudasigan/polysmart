"""
Position monitoring and resolution tracking.
Monitors open positions until market resolution.
"""
import time
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from config import Config


@dataclass
class Position:
    condition_id: str
    token_id: str
    side: str  # "YES" or "NO"
    entry_amount: float
    entry_price: float
    shares: float
    market_slug: str
    market_link: str
    window_end_ts: int
    status: str = "OPEN"  # OPEN, WON, LOST, CASHED_OUT
    pnl: float = 0.0
    resolved: bool = False
    resolution_price: float = 0.0

    @property
    def potential_payout(self) -> float:
        """Calculate potential payout if won."""
        return self.shares * 1.0  # Each share pays $1

    @property
    def potential_profit(self) -> float:
        """Calculate potential profit if won."""
        return self.potential_payout - self.entry_amount


class PositionMonitor:
    """Monitors positions and checks for resolution."""

    GAMMA_API = "https://gamma-api.polymarket.com"
    DATA_API = "https://data-api.polymarket.com"

    def __init__(self, config: Config):
        self.config = config
        self.positions: list[Position] = []
        self.session = requests.Session()

    def add_position(self, position: Position):
        """Add a new position to monitor."""
        self.positions.append(position)

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self.positions if p.status == "OPEN"]

    def check_resolution(self, position: Position) -> bool:
        """
        Check if a market has resolved.
        Returns True if resolution status changed.
        """
        try:
            # Check via Gamma API
            url = f"{self.GAMMA_API}/events"
            params = {"slug": position.market_slug}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if not data or len(data) == 0:
                return False

            event = data[0]
            market = event.get("markets", [{}])[0]
            if not market:
                return False

            # Check if market is resolved
            is_resolved = market.get("resolved", False)
            if not is_resolved:
                return False

            # Get winning outcome
            winning_outcome = market.get("winningOutcome", "")
            outcome_prices = self._safe_json_parse(market.get("outcomePrices", "[]"))
            outcomes = self._safe_json_parse(market.get("outcomes", "[]"))

            # Determine if we won
            # Our position.side is "YES" (Up) or "NO" (Down)
            if position.side == "YES" and winning_outcome == "Up":
                position.status = "WON"
                position.pnl = position.potential_profit
                position.resolution_price = 1.0
            elif position.side == "NO" and winning_outcome == "Down":
                position.status = "WON"
                position.pnl = position.potential_profit
                position.resolution_price = 1.0
            else:
                position.status = "LOST"
                position.pnl = -position.entry_amount
                position.resolution_price = 0.0

            position.resolved = True
            return True

        except Exception as e:
            return False

    def check_all_positions(self) -> list[Position]:
        """Check all open positions and return newly resolved ones."""
        newly_resolved = []
        for pos in self.positions:
            if pos.status == "OPEN":
                if self.check_resolution(pos):
                    newly_resolved.append(pos)
        return newly_resolved

    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of all positions."""
        open_pos = [p for p in self.positions if p.status == "OPEN"]
        won_pos = [p for p in self.positions if p.status == "WON"]
        lost_pos = [p for p in self.positions if p.status == "LOST"]

        total_pnl = sum(p.pnl for p in self.positions)
        total_won = sum(p.potential_profit for p in won_pos)
        total_lost = sum(p.entry_amount for p in lost_pos)

        return {
            "total_positions": len(self.positions),
            "open": len(open_pos),
            "won": len(won_pos),
            "lost": len(lost_pos),
            "total_pnl": total_pnl,
            "total_won": total_won,
            "total_lost": total_lost,
            "win_rate": len(won_pos) / (len(won_pos) + len(lost_pos)) * 100 if (len(won_pos) + len(lost_pos)) > 0 else 0,
        }

    @staticmethod
    def _safe_json_parse(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except:
                return []
        return []
