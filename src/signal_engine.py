"""
Signal analysis engine using Binance API with Yahoo Finance fallback.
Analyzes BTC momentum for 5-minute directional prediction.
"""
import time
import requests
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

import yfinance as yf


@dataclass
class SignalResult:
    direction: str  # "UP", "DOWN", or "NEUTRAL"
    strength: str   # "STRONG", "MODERATE", "WEAK"
    confidence: float  # 0.0 to 1.0
    source: str     # "binance" or "yahoo"
    btc_price: float
    price_change_pct: float
    volume_trend: str
    ema_signal: str
    rsi: float
    window_delta_pct: float
    reason: str


class SignalEngine:
    """Generates trading signals from Binance or Yahoo Finance data."""

    BINANCE_BASE = "https://api.binance.com"

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 50):
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        self.last_binance_success = True

    def analyze(self, window_open_price: Optional[float] = None) -> SignalResult:
        """
        Analyze BTC momentum and return a signal.
        Tries Binance first, falls back to Yahoo Finance.
        """
        # Try Binance first
        data, source = self._fetch_data()

        if data is None or len(data) < 10:
            return SignalResult(
                direction="NEUTRAL",
                strength="WEAK",
                confidence=0.0,
                source="failed",
                btc_price=0.0,
                price_change_pct=0.0,
                volume_trend="unknown",
                ema_signal="neutral",
                rsi=50.0,
                window_delta_pct=0.0,
                reason="Failed to fetch data from both sources"
            )

        return self._compute_signal(data, source, window_open_price)

    def _fetch_data(self) -> Tuple[Optional[pd.DataFrame], str]:
        """Fetch OHLCV data. Returns (df, source)."""
        # Try Binance
        if self.last_binance_success:
            df = self._fetch_binance()
            if df is not None and len(df) >= 10:
                self.last_binance_success = True
                return df, "binance"
            self.last_binance_success = False

        # Fallback to Yahoo Finance
        df = self._fetch_yahoo()
        if df is not None and len(df) >= 10:
            self.last_binance_success = True  # Reset for next try
            return df, "yahoo"

        return None, "failed"

    def _fetch_binance(self) -> Optional[pd.DataFrame]:
        """Fetch klines from Binance API."""
        try:
            url = f"{self.BINANCE_BASE}/api/v3/klines"
            params = {
                "symbol": self.symbol,
                "interval": self.interval,
                "limit": self.limit,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore"
            ])

            numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote"]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df = df.dropna()
            return df
        except Exception as e:
            return None

    def _fetch_yahoo(self) -> Optional[pd.DataFrame]:
        """Fetch data from Yahoo Finance as fallback."""
        try:
            ticker = yf.Ticker("BTC-USD")
            df = ticker.history(period="1d", interval="1m")
            if df.empty or len(df) < 10:
                return None

            df = df.reset_index()
            df = df.rename(columns={
                "Datetime": "open_time",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df["quote_volume"] = df["volume"] * df["close"]
            df["taker_buy_quote"] = df["quote_volume"] * 0.5
            return df
        except Exception as e:
            return None

    def _compute_signal(
        self, 
        df: pd.DataFrame, 
        source: str,
        window_open_price: Optional[float] = None
    ) -> SignalResult:
        """Compute trading signal from OHLCV data."""

        close = df["close"].values
        volume = df["volume"].values
        current_price = float(close[-1])

        # Window delta (most important for 5m markets)
        window_delta_pct = 0.0
        if window_open_price and window_open_price > 0:
            window_delta_pct = (current_price - window_open_price) / window_open_price * 100

        # EMA crossovers
        ema9 = self._ema(close, 9)
        ema21 = self._ema(close, 21)
        ema_bullish = ema9[-1] > ema21[-1] if len(ema9) > 0 and len(ema21) > 0 else False

        # RSI
        rsi = self._rsi(close, 14)

        # Volume trend
        vol_recent = np.mean(volume[-3:]) if len(volume) >= 3 else volume[-1]
        vol_prior = np.mean(volume[-6:-3]) if len(volume) >= 6 else volume[0]
        volume_surge = vol_recent > vol_prior * 1.5 if vol_prior > 0 else False
        volume_trend = "surge" if volume_surge else "normal"

        # Recent price change (last 3 candles)
        price_change_pct = (close[-1] - close[-4]) / close[-4] * 100 if len(close) >= 4 else 0.0

        # Micro momentum (last 2 candles)
        micro_up = close[-1] > close[-2] if len(close) >= 2 else False
        micro_down = close[-1] < close[-2] if len(close) >= 2 else False

        # Composite scoring (weighted)
        score = 0.0
        reasons = []

        # Window delta is king (weight 5-7)
        if abs(window_delta_pct) > 0.10:
            score += 7.0 if window_delta_pct > 0 else -7.0
            reasons.append(f"Window delta strong: {window_delta_pct:+.3f}%")
        elif abs(window_delta_pct) > 0.02:
            score += 5.0 if window_delta_pct > 0 else -5.0
            reasons.append(f"Window delta moderate: {window_delta_pct:+.3f}%")
        elif abs(window_delta_pct) > 0.005:
            score += 3.0 if window_delta_pct > 0 else -3.0
            reasons.append(f"Window delta slight: {window_delta_pct:+.3f}%")

        # EMA (weight 1)
        if ema_bullish:
            score += 1.0
            reasons.append("EMA9 > EMA21")
        else:
            score -= 1.0
            reasons.append("EMA9 < EMA21")

        # Micro momentum (weight 2)
        if micro_up:
            score += 2.0
            reasons.append("Micro momentum UP")
        elif micro_down:
            score -= 2.0
            reasons.append("Micro momentum DOWN")

        # Volume surge (weight 1)
        if volume_surge:
            score += 1.0 if score > 0 else -1.0
            reasons.append("Volume surge confirms")

        # RSI extremes (weight 1-2)
        if rsi > 75:
            score += 1.5
            reasons.append("RSI overbought (momentum)")
        elif rsi < 25:
            score -= 1.5
            reasons.append("RSI oversold (momentum)")

        # Determine direction and strength
        abs_score = abs(score)
        if abs_score >= 8.0:
            strength = "STRONG"
            confidence = min(0.95, 0.60 + abs_score * 0.03)
        elif abs_score >= 4.0:
            strength = "MODERATE"
            confidence = min(0.80, 0.50 + abs_score * 0.05)
        elif abs_score >= 1.5:
            strength = "WEAK"
            confidence = min(0.60, 0.40 + abs_score * 0.08)
        else:
            strength = "WEAK"
            confidence = 0.0

        if score > 0:
            direction = "UP"
        elif score < 0:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"
            strength = "WEAK"
            confidence = 0.0

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            source=source,
            btc_price=current_price,
            price_change_pct=price_change_pct,
            volume_trend=volume_trend,
            ema_signal="bullish" if ema_bullish else "bearish",
            rsi=rsi,
            window_delta_pct=window_delta_pct,
            reason="; ".join(reasons) if reasons else "No clear signal"
        )

    @staticmethod
    def _ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return prices
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
        return ema

    @staticmethod
    def _rsi(prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
