#!/usr/bin/env python3
"""
Polymarket BTC Up/Down 5-Minute Bot
====================================

Entry point. Run with:
    python main.py

Setup (one-time):
    1. Copy .env.example to .env and fill in credentials
    2. Run: python src/setup_creds.py  (to derive API keys)
    3. Add derived keys to .env
    4. Run: python main.py

For dry-run testing (no real trades):
    DRY_RUN=true python main.py
"""
import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from bot import main

if __name__ == "__main__":
    main()
