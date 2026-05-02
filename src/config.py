"""
Configuration manager for Polymarket BTC 5m Bot.
Loads settings from .env file with validation.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Polymarket Credentials
    POLY_PRIVATE_KEY: str
    POLY_FUNDER_ADDRESS: str
    POLY_SIGNATURE_TYPE: int
    RELAYER_API_KEY: str
    RELAYER_API_KEY_ADDRESS: str

    # Optional pre-derived CLOB credentials
    POLY_API_KEY: str = ""
    POLY_API_SECRET: str = ""
    POLY_API_PASSPHRASE: str = ""

    # Trading
    STRONG_BET_SIZE: float = 1.0
    MODERATE_BET_SIZE: float = 0.5
    MIN_BET_SIZE: float = 1.0
    VOLUME_YES_THRESHOLD: float = 0.60
    PRICE_CHANGE_THRESHOLD: float = 0.03
    SPREAD_MAX_THRESHOLD: float = 0.02
    ENTRY_TIMING_SECONDS: int = 30
    SCAN_INTERVAL_SECONDS: int = 5

    # Binance
    BINANCE_SYMBOL: str = "BTCUSDT"
    BINANCE_INTERVAL: str = "1m"
    BINANCE_KLINE_LIMIT: int = 50

    # Misc
    DRY_RUN: bool = False
    LOG_LEVEL: str = "INFO"

    # Constants
    CLOB_HOST: str = "https://clob.polymarket.com"
    GAMMA_HOST: str = "https://gamma-api.polymarket.com"
    DATA_HOST: str = "https://data-api.polymarket.com"
    RELAYER_HOST: str = "https://relayer-v2.polymarket.com"
    CHAIN_ID: int = 137
    MARKET_WINDOW_SECONDS: int = 300  # 5 minutes
    MARKET_SLUG_PREFIX: str = "btc-updown-5m"


def load_config() -> Config:
    """Load and validate configuration from environment variables."""
    required = ["POLY_PRIVATE_KEY", "POLY_FUNDER_ADDRESS", "RELAYER_API_KEY", "RELAYER_API_KEY_ADDRESS"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing required env vars: {missing}")

    return Config(
        POLY_PRIVATE_KEY=os.getenv("POLY_PRIVATE_KEY", ""),
        POLY_FUNDER_ADDRESS=os.getenv("POLY_FUNDER_ADDRESS", ""),
        POLY_SIGNATURE_TYPE=int(os.getenv("POLY_SIGNATURE_TYPE", "1")),
        RELAYER_API_KEY=os.getenv("RELAYER_API_KEY", ""),
        RELAYER_API_KEY_ADDRESS=os.getenv("RELAYER_API_KEY_ADDRESS", ""),
        POLY_API_KEY=os.getenv("POLY_API_KEY", ""),
        POLY_API_SECRET=os.getenv("POLY_API_SECRET", ""),
        POLY_API_PASSPHRASE=os.getenv("POLY_API_PASSPHRASE", ""),
        STRONG_BET_SIZE=float(os.getenv("STRONG_BET_SIZE", "1.0")),
        MODERATE_BET_SIZE=float(os.getenv("MODERATE_BET_SIZE", "0.5")),
        MIN_BET_SIZE=float(os.getenv("MIN_BET_SIZE", "1.0")),
        VOLUME_YES_THRESHOLD=float(os.getenv("VOLUME_YES_THRESHOLD", "0.60")),
        PRICE_CHANGE_THRESHOLD=float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.03")),
        SPREAD_MAX_THRESHOLD=float(os.getenv("SPREAD_MAX_THRESHOLD", "0.02")),
        ENTRY_TIMING_SECONDS=int(os.getenv("ENTRY_TIMING_SECONDS", "30")),
        SCAN_INTERVAL_SECONDS=int(os.getenv("SCAN_INTERVAL_SECONDS", "5")),
        BINANCE_SYMBOL=os.getenv("BINANCE_SYMBOL", "BTCUSDT"),
        BINANCE_INTERVAL=os.getenv("BINANCE_INTERVAL", "1m"),
        BINANCE_KLINE_LIMIT=int(os.getenv("BINANCE_KLINE_LIMIT", "50")),
        DRY_RUN=os.getenv("DRY_RUN", "false").lower() == "true",
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
    )
