"""
Polymarket market discovery for BTC Up/Down 5-minute markets.
Markets regenerate every 5 minutes with deterministic slugs.
"""
import time
import requests
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class BTCMarket:
    slug: str
    condition_id: str
    up_token_id: str
    down_token_id: str
    up_price: float
    down_price: float
    up_volume: float
    down_volume: float
    spread: float
    market_link: str
    window_start_ts: int
    window_end_ts: int
    outcomes: list

    @property
    def yes_volume_pct(self) -> float:
        total = self.up_volume + self.down_volume
        return self.up_volume / total if total > 0 else 0.5

    @property
    def time_remaining(self) -> float:
        return max(0, self.window_end_ts - int(time.time()))

    @property
    def is_open(self) -> bool:
        now = int(time.time())
        return self.window_start_ts <= now < self.window_end_ts


class MarketDiscovery:
    """Discovers active BTC Up/Down 5m markets on Polymarket."""

    GAMMA_API = "https://gamma-api.polymarket.com"
    SLUG_PREFIX = "btc-updown-5m"
    WINDOW_SECONDS = 300

    def __init__(self):
        self.session = requests.Session()

    def get_current_window_ts(self) -> int:
        """Get the current 5-minute window start timestamp."""
        now = int(time.time())
        return now - (now % self.WINDOW_SECONDS)

    def get_next_window_ts(self) -> int:
        """Get the next 5-minute window start timestamp."""
        return self.get_current_window_ts() + self.WINDOW_SECONDS

    def discover_market(self, timestamp: Optional[int] = None) -> Optional[BTCMarket]:
        """
        Discover BTC Up/Down market for a given timestamp.
        If no timestamp provided, uses current window.
        """
        if timestamp is None:
            timestamp = self.get_current_window_ts()

        slug = f"{self.SLUG_PREFIX}-{timestamp}"

        try:
            url = f"{self.GAMMA_API}/events"
            params = {"slug": slug}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if not data or len(data) == 0:
                return None

            event = data[0]
            market = event.get("markets", [{}])[0]
            if not market:
                return None

            token_ids = self._safe_json_parse(market.get("clobTokenIds", "[]"))
            outcomes = self._safe_json_parse(market.get("outcomes", "[]"))
            outcome_prices = self._safe_json_parse(market.get("outcomePrices", "[]"))
            volume = self._safe_json_parse(market.get("volume", "0"))

            # Determine Up/Down indices
            up_idx = outcomes.index("Up") if "Up" in outcomes else 0
            down_idx = outcomes.index("Down") if "Down" in outcomes else 1

            if len(token_ids) < 2 or len(outcomes) < 2:
                return None

            up_price = float(outcome_prices[up_idx]) if len(outcome_prices) > up_idx else 0.5
            down_price = float(outcome_prices[down_idx]) if len(outcome_prices) > down_idx else 0.5

            # Volume split (approximate from outcome prices if not available)
            up_vol = float(volume) * up_price if isinstance(volume, (int, float, str)) else 0
            down_vol = float(volume) * down_price if isinstance(volume, (int, float, str)) else 0

            spread = abs(up_price - (1.0 - down_price))  # Approximate spread

            return BTCMarket(
                slug=slug,
                condition_id=market.get("conditionId", ""),
                up_token_id=str(token_ids[up_idx]),
                down_token_id=str(token_ids[down_idx]),
                up_price=up_price,
                down_price=down_price,
                up_volume=up_vol,
                down_volume=down_vol,
                spread=spread,
                market_link=f"https://polymarket.com/event/{slug}",
                window_start_ts=timestamp,
                window_end_ts=timestamp + self.WINDOW_SECONDS,
                outcomes=outcomes,
            )
        except Exception as e:
            return None

    def get_order_book_snapshot(
        self, 
        token_id: str, 
        clob_client=None
    ) -> Dict[str, Any]:
        """
        Get order book snapshot for a token.
        Uses py-clob-client if available, otherwise returns empty.
        """
        if clob_client is None:
            return {"bids": [], "asks": [], "spread": 0.0, "mid": 0.5}

        try:
            book = clob_client.get_order_book(token_id)
            bids = book.bids if hasattr(book, "bids") else []
            asks = book.asks if hasattr(book, "asks") else []

            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0
            spread = best_ask - best_bid
            mid = (best_bid + best_ask) / 2.0

            # Calculate volume at top of book
            bid_volume = sum(float(b["size"]) for b in bids[:5]) if bids else 0
            ask_volume = sum(float(a["size"]) for a in asks[:5]) if asks else 0

            return {
                "bids": bids,
                "asks": asks,
                "spread": spread,
                "mid": mid,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
            }
        except Exception as e:
            return {"bids": [], "asks": [], "spread": 0.0, "mid": 0.5}

    @staticmethod
    def _safe_json_parse(value):
        """Safely parse JSON string or return as-is."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except:
                return []
        return []
