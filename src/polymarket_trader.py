"""
Polymarket CLOB trading wrapper.
Handles authentication, order placement, balance checks, and gasless operations.
"""
import os
import time
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    MarketOrderArgs, OrderType, BalanceAllowanceParams, AssetType, ApiCreds
)
from py_clob_client.order_builder.constants import BUY, SELL

from config import Config


@dataclass
class TradeResult:
    success: bool
    order_id: str
    filled_amount: float
    avg_price: float
    side: str
    token_id: str
    error: str = ""
    raw_response: Optional[Dict] = None


class PolymarketTrader:
    """Wrapper for Polymarket CLOB trading operations."""

    def __init__(self, config: Config):
        self.config = config
        self.client: Optional[ClobClient] = None
        self._init_client()

    def _init_client(self):
        """Initialize CLOB client with credentials."""
        try:
            # Initialize with private key
            self.client = ClobClient(
                host=self.config.CLOB_HOST,
                key=self.config.POLY_PRIVATE_KEY,
                chain_id=self.config.CHAIN_ID,
                signature_type=self.config.POLY_SIGNATURE_TYPE,
                funder=self.config.POLY_FUNDER_ADDRESS,
            )

            # Use pre-derived credentials if available, otherwise derive
            if self.config.POLY_API_KEY and self.config.POLY_API_SECRET and self.config.POLY_API_PASSPHRASE:
                creds = ApiCreds(
                    api_key=self.config.POLY_API_KEY,
                    api_secret=self.config.POLY_API_SECRET,
                    api_passphrase=self.config.POLY_API_PASSPHRASE,
                )
                self.client.set_api_creds(creds)
            else:
                creds = self.client.create_or_derive_api_key()
                self.client.set_api_creds(creds)
                # Log these for user to save
                print(f"[SETUP] Derived API Key: {creds.api_key}")
                print(f"[SETUP] Derived API Secret: {creds.api_secret}")
                print(f"[SETUP] Derived API Passphrase: {creds.api_passphrase}")
                print("[SETUP] Save these to your .env file for faster startup!")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize CLOB client: {e}")

    def get_balance_usdc(self) -> float:
        """Get USDC balance in funder wallet."""
        try:
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self.config.POLY_SIGNATURE_TYPE,
            )
            result = self.client.get_balance_allowance(params=params)
            balance = float(result.get("balance", 0))
            return balance / 1e6  # Convert from 6 decimals
        except Exception as e:
            return 0.0

    def get_token_balance(self, token_id: str) -> float:
        """Get balance of a specific outcome token."""
        try:
            params = BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=token_id,
                signature_type=self.config.POLY_SIGNATURE_TYPE,
            )
            result = self.client.get_balance_allowance(params=params)
            balance = float(result.get("balance", 0))
            return balance / 1e6
        except Exception as e:
            return 0.0

    def place_market_order(
        self, 
        token_id: str, 
        amount_usdc: float, 
        side: str = "BUY"
    ) -> TradeResult:
        """
        Place a FOK market order.

        Args:
            token_id: The outcome token ID to trade
            amount_usdc: Dollar amount to spend (for BUY)
            side: BUY or SELL
        """
        if self.config.DRY_RUN:
            return TradeResult(
                success=True,
                order_id="DRY_RUN",
                filled_amount=amount_usdc,
                avg_price=0.0,
                side=side,
                token_id=token_id,
                error="",
            )

        try:
            side_const = BUY if side == "BUY" else SELL

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount_usdc,
                side=side_const,
                order_type=OrderType.FOK,
            )

            signed_order = self.client.create_market_order(order_args)
            response = self.client.post_order(signed_order, OrderType.FOK)

            if response.get("success", False):
                return TradeResult(
                    success=True,
                    order_id=response.get("orderID", ""),
                    filled_amount=amount_usdc,
                    avg_price=float(response.get("price", 0)),
                    side=side,
                    token_id=token_id,
                    raw_response=response,
                )
            else:
                return TradeResult(
                    success=False,
                    order_id="",
                    filled_amount=0.0,
                    avg_price=0.0,
                    side=side,
                    token_id=token_id,
                    error=response.get("error", "Unknown error"),
                    raw_response=response,
                )
        except Exception as e:
            return TradeResult(
                success=False,
                order_id="",
                filled_amount=0.0,
                avg_price=0.0,
                side=side,
                token_id=token_id,
                error=str(e),
            )

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.client.cancel_all()
            return True
        except Exception as e:
            return False

    def get_open_orders(self) -> list:
        """Get list of open orders."""
        try:
            return self.client.get_orders()
        except Exception as e:
            return []

    def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """Get order book for a token."""
        try:
            book = self.client.get_order_book(token_id)
            bids = book.bids if hasattr(book, "bids") else []
            asks = book.asks if hasattr(book, "asks") else []

            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0

            return {
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": best_ask - best_bid,
                "mid": (best_bid + best_ask) / 2,
            }
        except Exception as e:
            return {"bids": [], "asks": [], "best_bid": 0, "best_ask": 1, "spread": 1, "mid": 0.5}

    def get_price(self, token_id: str, side: str = "BUY") -> float:
        """Get best available price for a token."""
        try:
            result = self.client.get_price(token_id=token_id, side=side)
            return float(result.get("price", 0))
        except Exception as e:
            return 0.0

    def get_midpoint(self, token_id: str) -> float:
        """Get midpoint price."""
        try:
            result = self.client.get_midpoint(token_id=token_id)
            return float(result.get("mid", 0.5))
        except Exception as e:
            return 0.5

    def get_spread(self, token_id: str) -> float:
        """Get spread."""
        try:
            result = self.client.get_spread(token_id=token_id)
            return float(result.get("spread", 0))
        except Exception as e:
            return 0.0

    def redeem_position(self, condition_id: str) -> bool:
        """
        Redeem winning positions via relayer (gasless).
        Uses Relayer API for on-chain redemption.
        """
        try:
            # For now, this is a placeholder. Full implementation requires
            # calling the CTF Exchange contract via relayer.
            # The py-clob-client doesn't directly support redeem via relayer.
            # You would need to use the builder-relayer-client or call manually.

            headers = {
                "Content-Type": "application/json",
                "RELAYER_API_KEY": self.config.RELAYER_API_KEY,
                "RELAYER_API_KEY_ADDRESS": self.config.RELAYER_API_KEY_ADDRESS,
            }

            # This is a simplified placeholder - actual redemption requires
            # encoding the CTF redeem function call and submitting via relayer
            # or using Polymarket's web interface.

            # For production, consider using playwright to auto-claim via web UI
            # or implement full relayer transaction submission.
            return False
        except Exception as e:
            return False
