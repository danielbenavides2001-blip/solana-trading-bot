"""
Autonomous Optimizer and Continuous Backtester for SOL/USDT Futures Bot.
Periodically benchmarks strategy candidates on fresh Binance Futures data
and updates active_strategy.json with the champion configuration.
"""
import os
import json
import logging
from datetime import datetime
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table

from market_data import MarketData
import config

console = Console()
ACTIVE_STRATEGY_FILE = "active_strategy.json"

class AutoOptimizer:
    def __init__(self, symbol: str = "SOLUSDT"):
        self.symbol = symbol
        self.market_data = MarketData(symbol)
        self.fee_pct = config.TAKER_FEE
        self.leverage = config.LEVERAGE

    def load_current_active(self) -> dict:
        if os.path.exists(ACTIVE_STRATEGY_FILE):
            try:
                with open(ACTIVE_STRATEGY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_active(self, strategy_data: dict):
        with open(ACTIVE_STRATEGY_FILE, "w") as f:
            json.dump(strategy_data, f, indent=2)

    def prepare_dataset(self, days: int = 45) -> pd.DataFrame:
        df = self.market_data.fetch_historical_dataset("1h", days=days)
        if df.empty or len(df) < 150:
            return pd.DataFrame()

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # EMAs
        df["ema_50"] = close.ewm(span=50, adjust=False).mean()
        df["ema_200"] = close.ewm(span=200, adjust=False).mean()

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        # Donchian Channels for multiple periods (18, 20, 24)
        for p in [18, 20, 24]:
            df[f"high_ch_{p}"] = high.rolling(p).max().shift(1)
            df[f"low_ch_{p}"] = low.rolling(p).min().shift(1)

        # SuperTrend (10, 3)
        st_atr = tr.rolling(10).mean()
        hl2 = (high + low) / 2.0
        up_band = hl2 - (3.0 * st_atr)
        dn_band = hl2 + (3.0 * st_atr)
        supertrend = [True] * len(df)
        f_up, f_dn = up_band.copy(), dn_band.copy()

        for i in range(1, len(df)):
            if up_band.iloc[i] > f_up.iloc[i-1] or close.iloc[i-1] < f_up.iloc[i-1]:
                f_up.iloc[i] = up_band.iloc[i]
            else:
                f_up.iloc[i] = f_up.iloc[i-1]

            if dn_band.iloc[i] < f_dn.iloc[i-1] or close.iloc[i-1] > f_dn.iloc[i-1]:
                f_dn.iloc[i] = dn_band.iloc[i]
            else:
                f_dn.iloc[i] = f_dn.iloc[i-1]

            if close.iloc[i] > f_dn.iloc[i-1]:
                supertrend[i] = True
            elif close.iloc[i] < f_up.iloc[i-1]:
                supertrend[i] = False
            else:
                supertrend[i] = supertrend[i-1]

        df["supertrend_bull"] = supertrend
        return df

    def simulate(self, df: pd.DataFrame, candidate: dict) -> dict:
        period = candidate["channel_period"]
        atr_trail = candidate["atr_trail"]
        atr_sl = candidate["atr_initial_sl"]
        h_col = f"high_ch_{period}"
        l_col = f"low_ch_{period}"

        capital = 21.79
        peak = capital
        max_dd = 0.0
        trades = []
        in_pos = False
        pos = {}

        for i in range(205, len(df)):
            curr = df.iloc[i]
            close = curr["close"]
            high = curr["high"]
            low = curr["low"]
            e200 = curr["ema_200"]
            atr = curr["atr"]
            h_ch = curr[h_col]
            l_ch = curr[l_col]

            if in_pos:
                pt, ep, sl = pos["type"], pos["entry"], pos["sl"]
                exit_trade = False
                exit_p = None

                if pt == "LONG":
                    # 1. Trailing Stop
                    new_sl = close - (atr_trail * atr)
                    if new_sl > sl: pos["sl"] = new_sl; sl = new_sl
                    # 2. Invalidation: Price crosses below EMA 200
                    if close < e200:
                        exit_trade = True; exit_p = close
                    elif low <= sl:
                        exit_trade = True; exit_p = sl
                    if exit_trade:
                        ret = (exit_p - ep) / ep

                else: # SHORT
                    new_sl = close + (atr_trail * atr)
                    if new_sl < sl: pos["sl"] = new_sl; sl = new_sl
                    if close > e200:
                        exit_trade = True; exit_p = close
                    elif high >= sl:
                        exit_trade = True; exit_p = sl
                    if exit_trade:
                        ret = (ep - exit_p) / ep

                if exit_trade:
                    notional = min(18.0, capital * 0.85) * self.leverage
                    net_pnl = (notional * ret) - (notional * self.fee_pct * 2.0)
                    capital += net_pnl
                    if capital > peak: peak = capital
                    dd = (peak - capital) / peak * 100.0
                    if dd > max_dd: max_dd = dd
                    trades.append(net_pnl)
                    in_pos = False
                    pos = {}

            if not in_pos and capital > 10.0 and not np.isnan(atr):
                # Long Breakout
                if high > h_ch and close > e200:
                    in_pos = True
                    pos = {"type": "LONG", "entry": h_ch, "sl": h_ch - (atr_sl * atr)}
                # Short Breakdown
                elif low < l_ch and close < e200:
                    in_pos = True
                    pos = {"type": "SHORT", "entry": l_ch, "sl": l_ch + (atr_sl * atr)}

        total = len(trades)
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        wr = (len(wins) / total * 100.0) if total else 0.0
        ret_pct = ((capital - 21.79) / 21.79) * 100.0
        gross_p = sum(wins) if wins else 0.0
        gross_l = abs(sum(losses)) if losses else 0.0
        pf = (gross_p / gross_l) if gross_l > 0 else 99.0
        calmar = (ret_pct / max_dd) if max_dd > 0 else 0.0

        return {
            "name": candidate["name"],
            "channel_period": period,
            "atr_trail": atr_trail,
            "atr_initial_sl": atr_sl,
            "capital": capital,
            "net_return_pct": ret_pct,
            "profit_factor": pf,
            "win_rate_pct": wr,
            "max_drawdown_pct": max_dd,
            "calmar_ratio": calmar,
            "total_trades": total
        }

    def evaluate_and_update(self, days: int = 45, force: bool = False) -> dict:
        """Run tournament on recent candles and update active_strategy.json."""
        console.print(f"[bold cyan]Ejecutando Auto-Backtesting sobre los últimos {days} días...[/bold cyan]")
        df = self.prepare_dataset(days=days)
        if df.empty:
            logging.warning("AutoOptimizer: Datos insuficientes para correr backtest.")
            return {}

        candidates = [
            {"name": "Donchian 24h + EMA 200 + ATR Trail 1.7x", "channel_period": 24, "atr_trail": 1.7, "atr_initial_sl": 2.0},
            {"name": "Donchian 20h + EMA 200 + ATR Trail 1.5x", "channel_period": 20, "atr_trail": 1.5, "atr_initial_sl": 1.8},
            {"name": "Donchian 18h + EMA 200 + ATR Trail 1.6x", "channel_period": 18, "atr_trail": 1.6, "atr_initial_sl": 1.8},
            {"name": "Donchian 24h Conservador (Trail 1.8x)", "channel_period": 24, "atr_trail": 1.8, "atr_initial_sl": 2.0},
        ]

        scored = []
        for cand in candidates:
            res = self.simulate(df, cand)
            scored.append(res)

        # Sort by Calmar Ratio (Risk-Adjusted Return) and Profit Factor
        scored.sort(key=lambda x: (x["calmar_ratio"], x["profit_factor"]), reverse=True)
        winner = scored[0]

        # Update active_strategy.json
        active_config = {
            "strategy_name": winner["name"],
            "channel_period": winner["channel_period"],
            "ema_trend_period": 200,
            "atr_period": 14,
            "atr_initial_sl": winner["atr_initial_sl"],
            "atr_trail": winner["atr_trail"],
            "breakeven_trigger_pct": 0.015,
            "last_backtest_date": datetime.now().isoformat(),
            "backtest_metrics": {
                "net_return_pct": round(winner["net_return_pct"], 2),
                "profit_factor": round(winner["profit_factor"], 2),
                "win_rate_pct": round(winner["win_rate_pct"], 1),
                "max_drawdown_pct": round(winner["max_drawdown_pct"], 2),
                "calmar_ratio": round(winner["calmar_ratio"], 2),
                "total_trades": winner["total_trades"]
            }
        }
        self.save_active(active_config)
        console.print(f"[bold green]Auto-Backtest completado. Estrategia activa: {winner['name']} (Calmar: {winner['calmar_ratio']:.2f}, Retorno: {winner['net_return_pct']:+.1f}%)[/bold green]")
        return active_config


if __name__ == "__main__":
    opt = AutoOptimizer()
    res = opt.evaluate_and_update(days=45, force=True)
    print("\nConfiguración Activa Actualizada:")
    print(json.dumps(res, indent=2))
