"""
One-time setup script to derive Polymarket CLOB API credentials from private key.
Run this once, then save the output to your .env file.
"""
import os
import sys
from dotenv import load_dotenv

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()


def main():
    print("=" * 60)
    print("  POLYMARKET API CREDENTIAL SETUP")
    print("=" * 60)
    print()

    # Get credentials from env
    private_key = os.getenv("POLY_PRIVATE_KEY")
    funder_address = os.getenv("POLY_FUNDER_ADDRESS")
    signature_type = int(os.getenv("POLY_SIGNATURE_TYPE", "1"))

    if not private_key or not funder_address:
        print("❌ Error: POLY_PRIVATE_KEY and POLY_FUNDER_ADDRESS must be set in .env")
        print()
        print("Please create a .env file with:")
        print("  POLY_PRIVATE_KEY=0x...")
        print("  POLY_FUNDER_ADDRESS=0x...")
        print("  POLY_SIGNATURE_TYPE=1")
        sys.exit(1)

    print(f"Funder Address: {funder_address}")
    print(f"Signature Type: {signature_type}")
    print()

    try:
        # Initialize client
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=signature_type,
            funder=funder_address,
        )

        print("Deriving API credentials...")
        creds = client.derive_api_key()

        print()
        print("✅ SUCCESS! Save these to your .env file:")
        print()
        print("-" * 60)
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
        print("-" * 60)
        print()
        print("Add the above lines to your .env file for faster bot startup.")
        print()

        # Test balance
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        balance = client.get_balance_allowance(params=params)
        usdc = float(balance.get("balance", 0)) / 1e6
        print(f"💰 USDC Balance: ${usdc:.2f}")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
