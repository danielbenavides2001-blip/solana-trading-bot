"""
Targeted Optimizer for Champion Strategy: Donchian Breakout + EMA 200 Filter.
Finds optimal Channel Period (16-26) and ATR Trailing parameters (1.3 - 2.2).
"""
import pandas as pd
import numpy as np
from market_data import MarketData

md = MarketData("SOLUSDT")
df = md.fetch_historical_dataset("1h", days=60)

close = df["close"]
high = df["high"]
low = df["low"]
df["ema_200"] = close.ewm(span=200, adjust=False).mean()

tr = pd.concat([
    high - low,
    (high - close.shift(1)).abs(),
    (low - close.shift(1)).abs()
], axis=1).max(axis=1)
df["atr"] = tr.rolling(14).mean()

best_config = None

for period in [18, 20, 22, 24]:
    df["h_ch"] = high.rolling(period).max().shift(1)
    df["l_ch"] = low.rolling(period).min().shift(1)
    
    for atr_sl in [1.6, 1.8, 2.0]:
        for atr_trail in [1.3, 1.5, 1.7]:
            cap = 21.79
            trades = []
            in_pos = False
            pos = {}
            peak = cap
            max_dd = 0.0

            for i in range(205, len(df)):
                c_p = close.iloc[i]
                c_h = high.iloc[i]
                c_l = low.iloc[i]
                c_atr = df["atr"].iloc[i]
                e200 = df["ema_200"].iloc[i]
                h_ch = df["h_ch"].iloc[i]
                l_ch = df["l_ch"].iloc[i]

                if in_pos:
                    pt, ep, sl = pos["type"], pos["entry"], pos["sl"]
                    exit_trade = False
                    exit_p = None

                    if pt == "LONG":
                        new_sl = c_p - (atr_trail * c_atr)
                        if new_sl > sl: pos["sl"] = new_sl; sl = new_sl
                        if c_l <= sl:
                            exit_trade = True
                            exit_p = sl
                            ret = (sl - ep) / ep
                    else:
                        new_sl = c_p + (atr_trail * c_atr)
                        if new_sl < sl: pos["sl"] = new_sl; sl = new_sl
                        if c_h >= sl:
                            exit_trade = True
                            exit_p = sl
                            ret = (ep - sl) / ep

                    if exit_trade:
                        margin = min(18.0, cap * 0.85)
                        notional = margin * 5
                        pnl = (notional * ret) - (notional * 0.001)
                        cap += pnl
                        if cap > peak: peak = cap
                        dd = (peak - cap) / peak * 100
                        if dd > max_dd: max_dd = dd
                        trades.append(pnl)
                        in_pos = False
                        pos = {}

                if not in_pos and cap > 10.0 and not np.isnan(c_atr):
                    # Filter: Only Long if price > EMA 200, Only Short if price < EMA 200
                    if c_h > h_ch and c_p > e200:
                        in_pos = True
                        pos = {"type": "LONG", "entry": h_ch, "sl": h_ch - (atr_sl * c_atr)}
                    elif c_l < l_ch and c_p < e200:
                        in_pos = True
                        pos = {"type": "SHORT", "entry": l_ch, "sl": l_ch + (atr_sl * c_atr)}

            if trades:
                wins = len([t for t in trades if t > 0])
                wr = wins / len(trades) * 100
                ret_pct = (cap - 21.79) / 21.79 * 100
                gross_p = sum(t for t in trades if t > 0)
                gross_l = abs(sum(t for t in trades if t <= 0))
                pf = (gross_p / gross_l) if gross_l > 0 else 99
                calmar = (ret_pct / max_dd) if max_dd > 0 else 0

                if best_config is None or ret_pct > best_config["ret_pct"]:
                    best_config = {
                        "period": period,
                        "atr_sl": atr_sl,
                        "atr_trail": atr_trail,
                        "cap": cap,
                        "ret_pct": ret_pct,
                        "wr": wr,
                        "pf": pf,
                        "max_dd": max_dd,
                        "calmar": calmar,
                        "trades": len(trades)
                    }
                    print(f"Mejor hallazgo: Periodo={period}, SL={atr_sl}x, Trail={atr_trail}x -> Saldo=${cap:.2f} ({ret_pct:+.1f}%), PF={pf:.2f}, DD={max_dd:.1f}%")

print("\n--- CAMPEÓN ABSOLUTO ---")
print(best_config)
