"""
Polymarket BTC Up/Down 5-Minute Trading Bot
============================================

Flow:
1. SCANNING  -> Discover market + analyze signal
2. ANALYZING -> Evaluate entry criteria
3. ENTERING  -> Place market order
4. MONITORING-> Track position until resolution
5. CASHING_OUT -> Redeem winnings, return to SCANNING

Strategy:
- Follow last money direction (volume + price)
- Entry 20-45s before market close
- Volume YES >= 60% + price rising = BUY YES
- Volume NO dominant + price rising = BUY NO
- Skip if volume low, price stagnant, or spread > 0.02
- Position: Strong=$1, Moderate=$0.5, Weak=skip
"""
import sys
import time
import signal
import logging
from datetime import datetime
from typing import Optional

from config import Config, load_config
from ui import BotUI, ui
from signal_engine import SignalEngine, SignalResult
from market_discovery import MarketDiscovery, BTCMarket
from polymarket_trader import PolymarketTrader, TradeResult
from position_monitor import PositionMonitor, Position


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BTCBot")


class BTCBot:
    """Main trading bot orchestrator."""

    def __init__(self):
        self.config = load_config()
        self.ui = ui
        self.signal_engine = SignalEngine(
            symbol=self.config.BINANCE_SYMBOL,
            interval=self.config.BINANCE_INTERVAL,
            limit=self.config.BINANCE_KLINE_LIMIT,
        )
        self.market_discovery = MarketDiscovery()
        self.trader: Optional[PolymarketTrader] = None
        self.monitor = PositionMonitor(self.config)
        self.running = True
        self.current_market: Optional[BTCMarket] = None
        self.current_position: Optional[Position] = None
        self.mode = "SCANNING"

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received. Exiting...")
        self.running = False
        self.ui.stop()
        sys.exit(0)

    def _init_trader(self):
        """Initialize Polymarket trader."""
        if self.trader is None:
            logger.info("Initializing Polymarket trader...")
            self.trader = PolymarketTrader(self.config)
            logger.info("Trader initialized successfully")

    def run(self):
        """Main bot loop."""
        self.ui.start()
        self.ui.log("Bot started. Initializing...")

        try:
            self._init_trader()
        except Exception as e:
            self.ui.log(f"ERROR: Failed to init trader: {e}")
            self.ui.stop()
            return

        self.ui.log("Trader ready. Entering main loop.")

        while self.running:
            try:
                if self.mode == "SCANNING":
                    self._scanning_phase()
                elif self.mode == "ANALYZING":
                    self._analyzing_phase()
                elif self.mode == "ENTERING":
                    self._entering_phase()
                elif self.mode == "MONITORING":
                    self._monitoring_phase()
                elif self.mode == "CASHING_OUT":
                    self._cashing_out_phase()

                time.sleep(self.config.SCAN_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Main loop error: {e}")
                self.ui.log(f"ERROR: {e}")
                time.sleep(5)

        self.ui.stop()

    # ============================================================
    # PHASE 1: SCANNING
    # ============================================================
    def _scanning_phase(self):
        """Scan for active market and analyze signals."""
        self.mode = "SCANNING"

        # Get current window
        window_ts = self.market_discovery.get_current_window_ts()
        window_end = window_ts + self.config.MARKET_WINDOW_SECONDS
        now = int(time.time())
        time_remaining = window_end - now

        # Update countdown
        self.ui.update(
            mode="SCANNING",
            countdown_target=window_end,
            countdown_total=self.config.MARKET_WINDOW_SECONDS,
            countdown_label="⏱️ Market Closes In",
            market_time_remaining=time_remaining,
        )

        # Skip if too late (less than 20s) or too early (more than 4min)
        if time_remaining < self.config.ENTRY_TIMING_SECONDS + 10:
            self.ui.log(f"Too late for this window ({time_remaining}s left). Waiting next...")
            time.sleep(max(1, time_remaining + 5))
            return

        if time_remaining > 240:
            self.ui.log(f"Window just started ({time_remaining}s left). Waiting...")
            time.sleep(min(30, time_remaining - 240))
            return

        # Discover market
        market = self.market_discovery.discover_market(window_ts)
        if market is None:
            self.ui.log("Market not found. Retrying...")
            return

        self.current_market = market

        # Get balance
        balance = self.trader.get_balance_usdc()

        # Get order book for volume analysis
        up_book = self.trader.get_order_book(market.up_token_id)
        down_book = self.trader.get_order_book(market.down_token_id)

        # Calculate volume dominance
        up_vol = up_book.get("bid_volume", 0) + up_book.get("ask_volume", 0)
        down_vol = down_book.get("bid_volume", 0) + down_book.get("ask_volume", 0)
        total_vol = up_vol + down_vol
        yes_vol_pct = up_vol / total_vol if total_vol > 0 else 0.5

        # Get prices
        up_mid = up_book.get("mid", market.up_price)
        down_mid = down_book.get("mid", market.down_price)
        spread = up_book.get("spread", 0.0)

        # Analyze signal
        signal = self.signal_engine.analyze(window_open_price=market.up_price)

        # Update UI
        self.ui.update(
            mode="SCANNING",
            balance_usdc=balance,
            funder_address=self.config.POLY_FUNDER_ADDRESS,
            signal_source=signal.source.upper(),
            signal_direction=signal.direction,
            signal_strength=signal.strength,
            btc_price=signal.btc_price,
            btc_change_24h=signal.price_change_pct,
            market_slug=market.slug,
            market_link=market.market_link,
            market_time_remaining=market.time_remaining,
            yes_price=up_mid,
            no_price=down_mid,
            yes_volume_pct=yes_vol_pct,
            spread=spread,
            countdown_target=window_end,
            countdown_total=self.config.MARKET_WINDOW_SECONDS,
            countdown_label="⏱️ Market Closes In",
        )

        self.ui.log(
            f"Scan | Signal: {signal.direction} ({signal.strength}) | "
            f"YES: ${up_mid:.4f} ({yes_vol_pct*100:.0f}%) | "
            f"Spread: {spread:.4f} | Balance: ${balance:.2f}"
        )

        # Evaluate entry criteria
        should_enter, side, amount, reason = self._evaluate_entry(
            signal, market, up_mid, down_mid, yes_vol_pct, spread, balance
        )

        if should_enter:
            self.ui.log(f"✅ ENTRY SIGNAL: {side} ${amount} | {reason}")
            self.mode = "ENTERING"
            self._pending_side = side
            self._pending_amount = amount
            self._pending_reason = reason
        else:
            self.ui.log(f"⏭️ SKIP: {reason}")
            # Wait a bit before next scan
            time.sleep(self.config.SCAN_INTERVAL_SECONDS)

    def _evaluate_entry(
        self,
        signal: SignalResult,
        market: BTCMarket,
        up_price: float,
        down_price: float,
        yes_vol_pct: float,
        spread: float,
        balance: float,
    ) -> tuple:
        """
        Evaluate if we should enter a position.
        Returns: (should_enter, side, amount, reason)
        """
        # Check balance
        if balance < self.config.MIN_BET_SIZE:
            return False, "", 0, f"Insufficient balance: ${balance:.2f}"

        # Check spread
        if spread > self.config.SPREAD_MAX_THRESHOLD:
            return False, "", 0, f"Spread too wide: {spread:.4f} > {self.config.SPREAD_MAX_THRESHOLD}"

        # Check volume
        if yes_vol_pct < 0.3 or yes_vol_pct > 0.7:
            # Volume is lopsided but not extremely - could be ok
            pass

        # Determine side based on signal + volume
        side = ""

        if signal.direction == "UP":
            # BUY YES if volume YES >= 60% and price rising
            if yes_vol_pct >= self.config.VOLUME_YES_THRESHOLD:
                if signal.window_delta_pct > 0:
                    side = "YES"
            # Even if volume is lower, strong signal can override
            elif signal.strength == "STRONG" and signal.confidence > 0.8:
                side = "YES"

        elif signal.direction == "DOWN":
            # BUY NO if volume NO dominant (YES < 40%) and price NO rising
            if yes_vol_pct <= (1 - self.config.VOLUME_YES_THRESHOLD):
                if signal.window_delta_pct < 0:
                    side = "NO"
            elif signal.strength == "STRONG" and signal.confidence > 0.8:
                side = "NO"

        if not side:
            return False, "", 0, "No clear directional signal"

        # Check price movement threshold
        if abs(signal.window_delta_pct) < 0.005:  # 0.005%
            return False, "", 0, f"Price stagnant: {signal.window_delta_pct:+.4f}%"

        # Position sizing
        if signal.strength == "STRONG":
            amount = min(self.config.STRONG_BET_SIZE, balance)
        elif signal.strength == "MODERATE":
            amount = min(self.config.MODERATE_BET_SIZE, balance)
        else:
            return False, "", 0, "Signal too weak"

        if amount < self.config.MIN_BET_SIZE:
            return False, "", 0, f"Position size ${amount} below minimum ${self.config.MIN_BET_SIZE}"

        return True, side, amount, f"{signal.direction} {signal.strength} | delta {signal.window_delta_pct:+.3f}%"

    # ============================================================
    # PHASE 2: ENTERING
    # ============================================================
    def _entering_phase(self):
        """Execute entry order."""
        self.mode = "ENTERING"

        if not self.current_market:
            self.mode = "SCANNING"
            return

        side = self._pending_side
        amount = self._pending_amount

        # Select token ID
        if side == "YES":
            token_id = self.current_market.up_token_id
        else:
            token_id = self.current_market.down_token_id

        self.ui.update(
            mode="ENTERING",
            entry_amount=amount,
            entry_side=f"BUY {side}",
            market_link=self.current_market.market_link,
        )

        self.ui.log(f"Placing BUY {side} order: ${amount} on token {token_id[:20]}...")

        # Place order
        result = self.trader.place_market_order(token_id, amount, side="BUY")

        if result.success:
            self.ui.log(f"✅ Order filled! ID: {result.order_id}")

            # Create position
            shares = result.filled_amount / max(result.avg_price, 0.01) if result.avg_price > 0 else result.filled_amount
            position = Position(
                condition_id=self.current_market.condition_id,
                token_id=token_id,
                side=side,
                entry_amount=result.filled_amount,
                entry_price=result.avg_price if result.avg_price > 0 else 0.5,
                shares=shares,
                market_slug=self.current_market.slug,
                market_link=self.current_market.market_link,
                window_end_ts=self.current_market.window_end_ts,
            )

            self.current_position = position
            self.monitor.add_position(position)
            self.mode = "MONITORING"

            self.ui.update(
                mode="MONITORING",
                entry_amount=position.entry_amount,
                entry_side=f"BUY {side}",
                entry_price=position.entry_price,
                position_status="OPEN",
                position_pnl=0.0,
                market_link=position.market_link,
            )
        else:
            self.ui.log(f"❌ Order failed: {result.error}")
            self.mode = "SCANNING"
            self.current_position = None

    # ============================================================
    # PHASE 3: MONITORING
    # ============================================================
    def _monitoring_phase(self):
        """Monitor open position until resolution."""
        self.mode = "MONITORING"

        if not self.current_position:
            self.mode = "SCANNING"
            return

        # Check if market resolved
        newly_resolved = self.monitor.check_all_positions()

        if self.current_position.resolved:
            self.ui.log(
                f"Market resolved! Result: {self.current_position.status} | "
                f"PnL: ${self.current_position.pnl:+.2f}"
            )
            self.mode = "CASHING_OUT"
            return

        # Update countdown to resolution
        time_remaining = max(0, self.current_position.window_end_ts - int(time.time()))

        # Get current market prices for PnL estimation
        try:
            current_price = self.trader.get_midpoint(self.current_position.token_id)
            if self.current_position.side == "YES":
                pnl = (current_price - self.current_position.entry_price) * self.current_position.shares
            else:
                pnl = ((1 - current_price) - self.current_position.entry_price) * self.current_position.shares
        except:
            pnl = 0.0
            current_price = self.current_position.entry_price

        self.ui.update(
            mode="MONITORING",
            entry_amount=self.current_position.entry_amount,
            entry_side=f"BUY {self.current_position.side}",
            entry_price=self.current_position.entry_price,
            position_status="OPEN",
            position_pnl=pnl,
            market_link=self.current_position.market_link,
            countdown_target=self.current_position.window_end_ts,
            countdown_total=self.config.MARKET_WINDOW_SECONDS,
            countdown_label="⏱️ Resolves In",
            market_time_remaining=time_remaining,
        )

        self.ui.log(
            f"Monitoring | {self.current_position.side} | "
            f"Entry: ${self.current_position.entry_price:.4f} | "
            f"Current: ${current_price:.4f} | "
            f"Unrealized: ${pnl:+.2f} | "
            f"Resolves in {time_remaining}s"
        )

        # Wait before next check
        if time_remaining > 60:
            time.sleep(10)
        elif time_remaining > 10:
            time.sleep(5)
        else:
            time.sleep(2)

    # ============================================================
    # PHASE 4: CASHING OUT
    # ============================================================
    def _cashing_out_phase(self):
        """Cash out resolved position and return to scanning."""
        self.mode = "CASHING_OUT"

        if not self.current_position:
            self.mode = "SCANNING"
            return

        self.ui.update(
            mode="CASHING_OUT",
            entry_amount=self.current_position.entry_amount,
            entry_side=f"BUY {self.current_position.side}",
            entry_price=self.current_position.entry_price,
            position_status=self.current_position.status,
            position_pnl=self.current_position.pnl,
            market_link=self.current_position.market_link,
        )

        if self.current_position.status == "WON":
            self.ui.log(f"🎉 WINNER! PnL: ${self.current_position.pnl:+.2f}")

            # Attempt redemption (best effort)
            if not self.config.DRY_RUN:
                redeemed = self.trader.redeem_position(self.current_position.condition_id)
                if redeemed:
                    self.ui.log("💰 Position redeemed successfully")
                else:
                    self.ui.log("⚠️ Auto-redeem failed. Redeem manually on Polymarket.")
        else:
            self.ui.log(f"💀 Loss: ${self.current_position.pnl:+.2f}")

        # Show summary
        summary = self.monitor.get_position_summary()
        self.ui.log(
            f"Session Stats | Trades: {summary['total_positions']} | "
            f"W: {summary['won']} L: {summary['lost']} | "
            f"Win%: {summary['win_rate']:.1f}% | "
            f"Total PnL: ${summary['total_pnl']:+.2f}"
        )

        # Reset for next cycle
        self.current_position = None
        self.current_market = None
        self.mode = "SCANNING"

        # Brief pause before next scan
        time.sleep(5)


def main():
    """Entry point."""
    print("=" * 60)
    print("  POLYMARKET BTC UP/DOWN 5-MINUTE TRADING BOT")
    print("=" * 60)
    print()

    # Check dry run
    import os
    if os.getenv("DRY_RUN", "false").lower() == "true":
        print("⚠️  DRY RUN MODE - No real trades will be placed")
        print()

    bot = BTCBot()
    bot.run()


if __name__ == "__main__":
    main()
