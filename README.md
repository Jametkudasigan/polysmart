# 🤖 Polymarket BTC Up/Down 5-Minute Trading Bot

Bot automation untuk trading market **BTC Up or Down 5 menit** di [Polymarket](https://polymarket.com) menggunakan Python.

## Arsitektur

```
[Private Key / EOA]
        ↓ (sign)
[Proxy Wallet / Smart Contract]
        ↓ (execute)
[Polymarket CLOB / Relayer API]
```

## Flow Bot

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ SCANNING │ ──▶ │ ANALYZE  │ ──▶ │ ENTERING │ ──▶ │MONITORING│ ──▶ │CASH OUT  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘     └──────────┘
     ▲                                                                    │
     └────────────────────────────────────────────────────────────────────┘
```

1. **SCANNING** → Cari market aktif + analisa momentum (Binance API → Yahoo Finance fallback)
2. **ANALYZE** → Evaluasi kriteria entry (volume, spread, signal)
3. **ENTRY** → Eksekusi otomatis kalau signal sesuai & dalam entry window (20–45 detik sebelum tutup)
4. **MONITORING** → Pantau position sampai market resolved
5. **CASH OUT** → Auto redeem via relayer, balik ke SCANNING

## Strategy

| Kondisi | Action |
|---------|--------|
| Volume YES ≥ 60% + harga YES naik + signal bullish | **BUY YES** |
| Volume NO ≥ 60% + harga NO naik + signal bearish | **BUY NO** |
| Spread > 0.02 / volume kecil / harga stagnan | **SKIP** |

**Position sizing:**
- Strong signal → $1.00
- Moderate signal → $0.50
- Weak → skip

## Prerequisites

- Python **3.10+** (3.11 recommended)
- Akun Polymarket dengan Proxy Wallet
- Relayer API Key dari [Polymarket Settings > API Keys](https://polymarket.com/)
- USDC balance di funder address

## Installation

```bash
# Clone repo
git clone https://github.com/yourusername/polymarket-btc-5m-bot.git
cd polymarket-btc-5m-bot

# Buat virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# atau: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
# Edit .env dengan credential kamu
nano .env
```

Isi semua variabel di `.env`:

| Variable | Description |
|----------|-------------|
| `POLY_PRIVATE_KEY` | Private key untuk sign transaksi |
| `POLY_FUNDER_ADDRESS` | Proxy wallet address (tempat dana) |
| `POLY_SIGNATURE_TYPE` | `1` untuk Proxy/Email wallet |
| `RELAYER_API_KEY` | Relayer API key dari Polymarket |
| `RELAYER_API_KEY_ADDRESS` | Address yang memiliki relayer key |

### One-Time Setup (Derive API Keys)

```bash
python src/setup_creds.py
```

Copy output ke `.env`:
```
POLY_API_KEY=...
POLY_API_SECRET=...
POLY_API_PASSPHRASE=...
```

## Usage

```bash
# Production mode (real trades)
python main.py

# Dry run mode (simulasi, tidak ada trade real)
DRY_RUN=true python main.py
```

Bot akan menampilkan UI terminal fullscreen dengan:
- 💰 Balance USDC di funder address
- 📊 Signal BTC real-time (Binance → Yahoo fallback)
- 🎯 Market BTC Up/Down 5m yang sedang di-scan
- 🧠 Evaluasi strategi dan countdown
- 📍 Detail position saat monitoring

## File Structure

```
polymarket-btc-5m-bot/
├── .env                    # Credential (jangan di-commit!)
├── .env.example            # Template credential
├── .gitignore
├── requirements.txt        # Dependencies
├── main.py                 # Entry point
├── src/
│   ├── __init__.py
│   ├── config.py           # Konfigurasi & validasi
│   ├── ui.py               # Rich terminal UI
│   ├── signal_engine.py    # BTC momentum analysis
│   ├── market_discovery.py # Polymarket market discovery
│   ├── polymarket_trader.py# CLOB trading wrapper
│   ├── position_monitor.py # Position tracking
│   ├── bot.py              # Main orchestrator
│   ├── setup_creds.py      # One-time API key derivation
│   └── auto_claim.py       # Redeem automation (placeholder)
```

## UI Preview

### Mode Scanning
```
┌──────────────────────────────────────────────────────────────┐
│ 🤖 POLYMARKET BTC 5M BOT   MODE: SCANNING                    │
├──────────────────────────────┬───────────────────────────────┤
│ 💰 WALLET                    │ 📈 MARKET                     │
│   Balance USDC    $42.50     │   Slug     btc-updown-5m-...  │
│   Funder Address  0x1234...  │   YES Price    $0.5234        │
│                              │   NO Price     $0.4766        │
│ 📊 SIGNAL                    │   YES Volume   62.3%          │
│   Source          BINANCE    │   Spread       0.008          │
│   Direction       UP         │   Time Left    145s           │
│   Strength        STRONG     │                               │
│   BTC Price       $94,230.50 │                               │
│   BTC 24h Chg     +0.45%     │                               │
├──────────────────────────────┴───────────────────────────────┤
│ Activity Log                                                 │
│ [14:32:01] Scan | Signal: UP (STRONG) | YES: $0.5234 (62%)  │
│ [14:31:56] Window delta strong: +0.125%; EMA9 > EMA21       │
└──────────────────────────────────────────────────────────────┘
```

### Mode Monitoring
```
┌──────────────────────────────────────────────────────────────┐
│ 🤖 POLYMARKET BTC 5M BOT   MODE: MONITORING                  │
├──────────────────────────────┬───────────────────────────────┤
│ 📍 POSITION                  │ ⏳ MARKET STATUS              │
│   Entry Amount    $1.00      │   Status       OPEN 🟢        │
│   Side            BUY YES    │   Closes In    02:15          │
│   Entry Price     $0.5234    │                               │
│   Shares          1.9106     │ 📊 LIVE P&L                   │
│   Market          BTC Up/Down│   Current Price    $0.6123    │
│   Link            [polymarket│   Unrealized P&L   +$0.17     │
│                   .com/event/│   Return           +32.5%     │
│                   ...]       │                               │
├──────────────────────────────┴───────────────────────────────┤
│ ⏳ MARKET LIFECYCLE                                          │
│ [████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░] 42%         │
│ Time remaining: 02:15                                        │
└──────────────────────────────────────────────────────────────┘
```

## Important Notes

⚠️ **RISK WARNING:** Trading binary prediction markets sangat berisiko. Bot ini untuk educational purposes. Gunakan dengan risiko sendiri. Jangan trade dengan dana yang tidak sanggup hilang.

🔒 **SECURITY:**
- Jangan pernah commit file `.env` ke GitHub
- Private key = akses penuh ke dana
- Gunakan dedicated wallet untuk bot

⛽ **Gasless:** Semua transaksi (trading via CLOB, redeem via relayer) gasless — Polymarket yang bayar gas fee di Polygon.

🔄 **Auto Redeem:** Redeem posisi menang otomatis memerlukan implementasi tambahan. Saat ini bot menampilkan instruksi manual redeem. Untuk auto-redeem, implementasi Playwright atau direct relayer transaction encoding diperlukan.

## License

MIT
