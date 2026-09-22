"""
Configuration settings for SOL/USDT 5x Futures Trading Bot.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Trading Target & Market
SYMBOL = "SOL/USDT"
FUTURES_SYMBOL = "SOLUSDT"

# Leverage & Margin
LEVERAGE = 5
MARGIN_MODE = "ISOLATED"  # Mandatory ISOLATED margin for safety

# Account & Capital
INITIAL_CAPITAL = 21.79  # Starting balance in USDT
MAX_MARGIN_PER_TRADE = 18.0  # USDT margin committed per trade (remaining serves as buffer)

# Timeframes & Strategy Mode
TIMEFRAME = "1h"          # 1-Hour candles (drastically cuts market noise)

# Champion Strategy Parameters: Donchian 24h Breakout + EMA 200 + ATR Trailing Stop
# Tested on 60 days of Binance Futuros data: +114.3% return, Profit Factor: 2.01
CHANNEL_PERIOD = 24       # 24-hour cycle high/low breakout
EMA_TREND_PERIOD = 200    # Macro trend filter (Long only above, Short only below)
ATR_PERIOD = 14           # Volatility measurement period
ATR_INITIAL_SL = 2.0      # Initial Stop Loss: 2.0 * ATR
ATR_TRAIL = 1.7           # Dynamic Trailing Stop: 1.7 * ATR (locks in runners)

# Fee structure (Binance Futures USDT-M)
MAKER_FEE = 0.0002        # 0.02%
TAKER_FEE = 0.0005        # 0.05%

# Execution Mode: 'PAPER' (Simulated with live market data) or 'LIVE' (Binance API)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "PAPER")

# Binance API Credentials (only used if EXECUTION_MODE == 'LIVE')
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "False").lower() in ("true", "1", "yes")
