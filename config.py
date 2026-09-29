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

# Champion Strategy Parameters: Donchian 24h Breakout + EMA 200 + ADX Trend Strength + Target TP
CHANNEL_PERIOD = 24       # 24-hour cycle high/low breakout
EMA_TREND_PERIOD = 200    # Macro trend filter (Long only above, Short only below)
ATR_PERIOD = 14           # Volatility measurement period
ATR_INITIAL_SL = 1.8      # Initial Stop Loss: 1.8 * ATR
ATR_TRAIL = 1.8           # Dynamic Trailing Stop
TP_TARGET_PCT = 0.016     # Fixed Target Take Profit: +1.6% (~$1.35-$1.45 USDT net win)
ADX_PERIOD = 14           # ADX strength period
ADX_MIN = 20.0            # Minimum ADX to enter trade (filters sideways/choppy noise)

# Fee structure (Binance Futures USDT-M)
MAKER_FEE = 0.0002        # 0.02%
TAKER_FEE = 0.0005        # 0.05%

# Execution Mode: 'PAPER' (Simulated with live market data) or 'LIVE' (Binance API)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "PAPER")

# Binance API Credentials (only used if EXECUTION_MODE == 'LIVE')
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "False").lower() in ("true", "1", "yes")
