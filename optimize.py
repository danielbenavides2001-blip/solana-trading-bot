"""
Strategy optimizer and robust signal generator for SOL/USDT Futures.
Tests multiple indicator combinations (EMA trend, Supertrend, ATR trailing stop, RSI confirmation).
"""
import pandas as pd
import numpy as np
from market_data import MarketData

def run_simulation(df, ema_fast=20, ema_slow=50, rsi_os=40, rsi_ob=60, sl_mult=1.8, tp_mult=3.2, be_trigger=0.015, leverage=5):
    # Calculate indicators
    close = df["close"]
    high = df["high"]
    low = df["low"]
    
    ema_f = close.ewm(span=ema_fast, adjust=False).mean()
    ema_s = close.ewm(span=ema_slow, adjust=False).mean()
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - (100 / (1 + (avg_gain / (avg_loss + 1e-9))))
    
    # ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    
    capital = 21.79
    margin_trade = 18.0
    fee_pct = 0.0005
    trades = []
    in_pos = False
    pos = {}
    
    for i in range(60, len(df)):
        c_price = close.iloc[i]
        c_high = high.iloc[i]
        c_low = low.iloc[i]
        c_open = df["open"].iloc[i]
        ts = df["timestamp"].iloc[i]
        
        c_atr = atr.iloc[i]
        if np.isnan(c_atr):
            continue
            
        c_rsi = rsi.iloc[i]
        p_rsi = rsi.iloc[i-1]
        
        c_ef = ema_f.iloc[i]
        c_es = ema_s.iloc[i]
        
        if in_pos:
            pos_type = pos["type"]
            entry_p = pos["entry"]
            sl_p = pos["sl"]
            tp_p = pos["tp"]
            be_active = pos["be"]
            
            exit_trade = False
            exit_p = None
            reason = ""
            
            if pos_type == "LONG":
                # Breakeven
                if not be_active and c_high >= entry_p * (1.0 + be_trigger):
                    pos["be"] = True
                    pos["sl"] = entry_p * 1.001
                    sl_p = pos["sl"]
                    
                if c_high >= tp_p:
                    exit_trade = True
                    exit_p = tp_p
                    reason = "TP"
                elif c_low <= sl_p:
                    exit_trade = True
                    exit_p = sl_p
                    reason = "SL" if not be_active else "BE"
                
                if exit_trade:
                    ret = (exit_p - entry_p) / entry_p
            else: # SHORT
                if not be_active and c_low <= entry_p * (1.0 - be_trigger):
                    pos["be"] = True
                    pos["sl"] = entry_p * 0.999
                    sl_p = pos["sl"]
                    
                if c_low <= tp_p:
                    exit_trade = True
                    exit_p = tp_p
                    reason = "TP"
                elif c_high >= sl_p:
                    exit_trade = True
                    exit_p = sl_p
                    reason = "SL" if not be_active else "BE"
                    
                if exit_trade:
                    ret = (entry_p - exit_p) / entry_p
                    
            if exit_trade:
                notional = min(margin_trade, capital * 0.85) * leverage
                net_pnl = notional * ret - (notional * fee_pct * 2)
                capital += net_pnl
                trades.append({"pnl": net_pnl, "ret": ret, "reason": reason, "capital": capital})
                in_pos = False
                pos = {}
                
        if not in_pos and capital > 10.0:
            # LONG ENTRY: Price above EMA slow, EMA fast > slow, pullback to near EMA fast, RSI < rsi_os turned up, bullish candle
            if (c_price > c_es and c_ef > c_es and 
                c_low <= c_ef * 1.004 and # touched near EMA fast
                p_rsi <= rsi_os and c_rsi > p_rsi and c_price > c_open):
                
                sl_dist = max(c_atr * sl_mult, c_price * 0.012)
                tp_dist = max(c_atr * tp_mult, c_price * 0.026)
                in_pos = True
                pos = {
                    "type": "LONG",
                    "entry": c_price,
                    "sl": c_price - sl_dist,
                    "tp": c_price + tp_dist,
                    "be": False
                }
            # SHORT ENTRY: Price below EMA slow, EMA fast < slow, bounce to near EMA fast, RSI > rsi_ob turned down, bearish candle
            elif (c_price < c_es and c_ef < c_es and 
                  c_high >= c_ef * 0.996 and # touched near EMA fast
                  p_rsi >= rsi_ob and c_rsi < p_rsi and c_price < c_open):
                
                sl_dist = max(c_atr * sl_mult, c_price * 0.012)
                tp_dist = max(c_atr * tp_mult, c_price * 0.026)
                in_pos = True
                pos = {
                    "type": "SHORT",
                    "entry": c_price,
                    "sl": c_price + sl_dist,
                    "tp": c_price - tp_dist,
                    "be": False
                }
                
    if not trades:
        return 0, 0, 0, 21.79
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / len(trades) * 100
    ret_pct = (capital - 21.79) / 21.79 * 100
    return len(trades), wr, ret_pct, capital

if __name__ == "__main__":
    md = MarketData("SOLUSDT")
    df = md.fetch_historical_dataset("15m", days=30)
    print(f"Data loaded: {len(df)} candles")
    
    best = None
    for ef in [15, 20, 25]:
        for es in [50, 75, 100]:
            for r_os in [35, 40, 45]:
                for sl in [1.5, 1.8, 2.0]:
                    for tp in [2.5, 3.0, 3.5]:
                        n, wr, ret, cap = run_simulation(df, ema_fast=ef, ema_slow=es, rsi_os=r_os, rsi_ob=100-r_os, sl_mult=sl, tp_mult=tp)
                        if n >= 8:
                            if best is None or ret > best["ret"]:
                                best = {"ef": ef, "es": es, "r_os": r_os, "sl": sl, "tp": tp, "n": n, "wr": wr, "ret": ret, "cap": cap}
                                print(f"New Best: Trades={n}, WR={wr:.1f}%, Return={ret:+.1f}%, Capital=${cap:.2f} (ef={ef}, es={es}, r_os={r_os}, sl={sl}, tp={tp})")
    
    print("\nOPTIMIZATION RESULT:")
    print(best)
