import pandas as pd
import numpy as np
from market_data import MarketData

md = MarketData("SOLUSDT")
df = md.fetch_historical_dataset("15m", days=60) # 60 days of data for high statistical significance

# Add indicators
close = df["close"]
high = df["high"]
low = df["low"]
vol = df["volume"]

df["ema_20"] = close.ewm(span=20, adjust=False).mean()
df["ema_50"] = close.ewm(span=50, adjust=False).mean()
df["ema_200"] = close.ewm(span=200, adjust=False).mean()

# RSI
delta = close.diff()
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
ag = gain.ewm(alpha=1/14, adjust=False).mean()
al = loss.ewm(alpha=1/14, adjust=False).mean()
df["rsi"] = 100 - (100 / (1 + (ag / (al + 1e-9))))

# ATR
tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
df["atr"] = tr.rolling(14).mean()
df["vol_ma"] = vol.rolling(20).mean()

# Test several setups
for sl_pct in [0.012, 0.015]:
    for tp_pct in [0.025, 0.030, 0.035]:
        for be_pct in [0.012, 0.015]:
            cap = 21.79
            trades = []
            in_pos = False
            pos = {}
            for i in range(250, len(df)):
                c_p = close.iloc[i]
                c_h = high.iloc[i]
                c_l = low.iloc[i]
                c_o = df["open"].iloc[i]
                c_rsi = df["rsi"].iloc[i]
                p_rsi = df["rsi"].iloc[i-1]
                e20 = df["ema_20"].iloc[i]
                e50 = df["ema_50"].iloc[i]
                e200 = df["ema_200"].iloc[i]
                
                if in_pos:
                    pt = pos["type"]
                    ep = pos["entry"]
                    sl = pos["sl"]
                    tp = pos["tp"]
                    be = pos["be"]
                    
                    exit_p = None
                    if pt == "LONG":
                        if not be and c_h >= ep * (1 + be_pct):
                            pos["be"] = True
                            pos["sl"] = ep * 1.001
                            sl = pos["sl"]
                        if c_h >= tp:
                            exit_p = tp
                            ret = (tp - ep) / ep
                        elif c_l <= sl:
                            exit_p = sl
                            ret = (sl - ep) / ep
                    else:
                        if not be and c_l <= ep * (1 - be_pct):
                            pos["be"] = True
                            pos["sl"] = ep * 0.999
                            sl = pos["sl"]
                        if c_l <= tp:
                            exit_p = tp
                            ret = (ep - tp) / ep
                        elif c_h >= sl:
                            exit_p = sl
                            ret = (ep - sl) / ep
                            
                    if exit_p:
                        notional = min(18.0, cap * 0.85) * 5
                        pnl = notional * ret - notional * 0.001
                        cap += pnl
                        trades.append(pnl)
                        in_pos = False
                        pos = {}
                        
                if not in_pos and cap > 10.0:
                    # Filter: Only trade in direction of 200 EMA
                    # Long: Price > EMA 200, EMA 20 > EMA 50, price touched EMA 20, RSI bounced < 42
                    if (c_p > e200 and e20 > e50 and c_l <= e20 * 1.003 and p_rsi <= 42 and c_rsi > p_rsi and c_p > c_o):
                        in_pos = True
                        pos = {"type": "LONG", "entry": c_p, "sl": c_p * (1 - sl_pct), "tp": c_p * (1 + tp_pct), "be": False}
                    # Short: Price < EMA 200, EMA 20 < EMA 50, price touched EMA 20, RSI rejected > 58
                    elif (c_p < e200 and e20 < e50 and c_h >= e20 * 0.997 and p_rsi >= 58 and c_rsi < p_rsi and c_p < c_o):
                        in_pos = True
                        pos = {"type": "SHORT", "entry": c_p, "sl": c_p * (1 + sl_pct), "tp": c_p * (1 - tp_pct), "be": False}

            if len(trades) >= 5:
                wins = len([t for t in trades if t > 0])
                wr = wins / len(trades) * 100
                ret_p = (cap - 21.79) / 21.79 * 100
                if ret_p > 0:
                    print(f"60-Day Success: Trades={len(trades)}, WinRate={wr:.1f}%, Return={ret_p:+.1f}%, Final=${cap:.2f} (SL={sl_pct}, TP={tp_pct}, BE={be_pct})")
