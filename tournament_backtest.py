"""
Comprehensive Strategy Tournament for SOL/USDT 5x Futures.
Evaluates 6 classic & modern quantitative strategies over extended Binance Futures history:
1. Donchian Breakout (20) + ATR Trailing Stop (Benchmark)
2. Donchian Breakout + EMA 200 Trend Filter (Filtered Breakout)
3. SuperTrend (10, 3.0) + EMA 50 Filter
4. Bollinger Band Squeeze & Volatility Breakout
5. Keltner Channel + Chandelier ATR Exit
6. EMA Triple Cross (9 / 21 / 55) + Trailing Stop
"""
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from market_data import MarketData

console = Console()

class StrategyTournament:
    def __init__(self, symbol="SOLUSDT", initial_capital=21.79, leverage=5, fee_pct=0.0005):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.fee_pct = fee_pct
        self.market_data = MarketData(symbol)

    def prepare_data(self, days=60):
        console.print(f"[bold cyan]Descargando {days} días de velas de 1 Hora de Binance Futuros ({days * 24} velas)...[/bold cyan]")
        df = self.market_data.fetch_historical_dataset("1h", days=days)
        if df.empty or len(df) < 200:
            raise ValueError("No se pudieron descargar suficientes velas.")
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]

        # 1. EMAs
        df["ema_9"] = close.ewm(span=9, adjust=False).mean()
        df["ema_20"] = close.ewm(span=20, adjust=False).mean()
        df["ema_21"] = close.ewm(span=21, adjust=False).mean()
        df["ema_50"] = close.ewm(span=50, adjust=False).mean()
        df["ema_55"] = close.ewm(span=55, adjust=False).mean()
        df["ema_200"] = close.ewm(span=200, adjust=False).mean()

        # 2. Donchian Channels (15 and 20)
        df["donch_h20"] = high.rolling(20).max().shift(1)
        df["donch_l20"] = low.rolling(20).min().shift(1)
        df["donch_h15"] = high.rolling(15).max().shift(1)
        df["donch_l15"] = low.rolling(15).min().shift(1)

        # 3. ATR
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        # 4. Bollinger Bands (20, 2)
        df["sma_20"] = close.rolling(20).mean()
        df["std_20"] = close.rolling(20).std()
        df["bb_upper"] = df["sma_20"] + (df["std_20"] * 2.0)
        df["bb_lower"] = df["sma_20"] - (df["std_20"] * 2.0)
        df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / df["sma_20"]

        # 5. Keltner Channels
        df["kelt_upper"] = df["ema_20"] + (df["atr"] * 1.5)
        df["kelt_lower"] = df["ema_20"] - (df["atr"] * 1.5)

        # 6. SuperTrend (10, 3.0)
        st_atr = tr.rolling(10).mean()
        hl2 = (high + low) / 2.0
        up_band = hl2 - (3.0 * st_atr)
        dn_band = hl2 + (3.0 * st_atr)
        
        supertrend = [True] * len(df) # True = Bullish, False = Bearish
        final_up = up_band.copy()
        final_dn = dn_band.copy()

        for i in range(1, len(df)):
            if up_band.iloc[i] > final_up.iloc[i-1] or close.iloc[i-1] < final_up.iloc[i-1]:
                final_up.iloc[i] = up_band.iloc[i]
            else:
                final_up.iloc[i] = final_up.iloc[i-1]

            if dn_band.iloc[i] < final_dn.iloc[i-1] or close.iloc[i-1] > final_dn.iloc[i-1]:
                final_dn.iloc[i] = dn_band.iloc[i]
            else:
                final_dn.iloc[i] = final_dn.iloc[i-1]

            if close.iloc[i] > final_dn.iloc[i-1]:
                supertrend[i] = True
            elif close.iloc[i] < final_up.iloc[i-1]:
                supertrend[i] = False
            else:
                supertrend[i] = supertrend[i-1]

        df["supertrend_bull"] = supertrend
        df["st_stop"] = [final_up.iloc[i] if supertrend[i] else final_dn.iloc[i] for i in range(len(df))]

        return df

    def simulate_engine(self, df, name, entry_signal_fn, exit_fn):
        """Standardized simulation loop for any strategy."""
        capital = self.initial_capital
        peak_capital = capital
        max_dd = 0.0
        trades = []
        in_pos = False
        pos = {}

        warmup = 205
        for i in range(warmup, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            close = curr["close"]
            high = curr["high"]
            low = curr["low"]
            ts = curr["timestamp"]

            if in_pos:
                exit_res = exit_fn(pos, curr, prev)
                if exit_res["exit"]:
                    ret = exit_res["return"]
                    margin = min(18.0, capital * 0.85)
                    notional = margin * self.leverage
                    net_pnl = (notional * ret) - (notional * self.fee_pct * 2.0)
                    capital += net_pnl

                    if capital > peak_capital:
                        peak_capital = capital
                    dd = (peak_capital - capital) / peak_capital * 100.0
                    if dd > max_dd:
                        max_dd = dd

                    trades.append({"pnl": net_pnl, "return_pct": (net_pnl / margin) * 100.0})
                    in_pos = False
                    pos = {}

            if not in_pos and capital > 10.0:
                sig = entry_signal_fn(curr, prev)
                if sig:
                    in_pos = True
                    pos = sig

        total = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        wr = (len(wins) / total * 100.0) if total else 0.0
        ret_pct = ((capital - self.initial_capital) / self.initial_capital) * 100.0
        
        gross_prof = sum(t["pnl"] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.0
        profit_factor = (gross_prof / gross_loss) if gross_loss > 0 else 99.0
        calmar = (ret_pct / max_dd) if max_dd > 0 else 0.0

        return {
            "name": name,
            "capital": capital,
            "ret_pct": ret_pct,
            "trades": total,
            "win_rate": wr,
            "profit_factor": profit_factor,
            "max_dd": max_dd,
            "calmar": calmar
        }

    def run_all(self, days=60):
        df = self.prepare_data(days=days)
        results = []

        # ---------------------------------------------------------
        # Estrategia 1: Donchian Breakout 20 + ATR Trailing Stop (1.5x)
        # ---------------------------------------------------------
        def s1_entry(c, p):
            if c["high"] > c["donch_h20"]:
                return {"type": "LONG", "entry": c["donch_h20"], "sl": c["donch_h20"] - (2.0 * c["atr"])}
            elif c["low"] < c["donch_l20"]:
                return {"type": "SHORT", "entry": c["donch_l20"], "sl": c["donch_l20"] + (2.0 * c["atr"])}
            return None

        def s1_exit(pos, c, p):
            pt, ep, sl = pos["type"], pos["entry"], pos["sl"]
            atr = c["atr"]
            if pt == "LONG":
                new_sl = c["close"] - (1.5 * atr)
                if new_sl > sl: pos["sl"] = new_sl; sl = new_sl
                if c["low"] <= sl: return {"exit": True, "return": (sl - ep) / ep}
            else:
                new_sl = c["close"] + (1.5 * atr)
                if new_sl < sl: pos["sl"] = new_sl; sl = new_sl
                if c["high"] >= sl: return {"exit": True, "return": (ep - sl) / ep}
            return {"exit": False}

        results.append(self.simulate_engine(df, "1. Donchian 20 + ATR Trail", s1_entry, s1_exit))

        # ---------------------------------------------------------
        # Estrategia 2: Donchian 20 + Filtro Tendencia EMA 200
        # ---------------------------------------------------------
        def s2_entry(c, p):
            e200 = c["ema_200"]
            if c["high"] > c["donch_h20"] and c["close"] > e200:
                return {"type": "LONG", "entry": c["donch_h20"], "sl": c["donch_h20"] - (1.8 * c["atr"])}
            elif c["low"] < c["donch_l20"] and c["close"] < e200:
                return {"type": "SHORT", "entry": c["donch_l20"], "sl": c["donch_l20"] + (1.8 * c["atr"])}
            return None

        results.append(self.simulate_engine(df, "2. Donchian 20 + Filtro EMA 200", s2_entry, s1_exit))

        # ---------------------------------------------------------
        # Estrategia 3: SuperTrend (10, 3) + Filtro EMA 50
        # ---------------------------------------------------------
        def s3_entry(c, p):
            st_now = c["supertrend_bull"]
            st_prev = p["supertrend_bull"]
            # Bullish flip
            if st_now and not st_prev and c["close"] > c["ema_50"]:
                return {"type": "LONG", "entry": c["close"], "sl": c["close"] - (2.0 * c["atr"])}
            # Bearish flip
            elif not st_now and st_prev and c["close"] < c["ema_50"]:
                return {"type": "SHORT", "entry": c["close"], "sl": c["close"] + (2.0 * c["atr"])}
            return None

        def s3_exit(pos, c, p):
            pt, ep, sl = pos["type"], pos["entry"], pos["sl"]
            atr = c["atr"]
            if pt == "LONG":
                new_sl = c["close"] - (1.8 * atr)
                if new_sl > sl: pos["sl"] = new_sl; sl = new_sl
                if not c["supertrend_bull"] or c["low"] <= sl:
                    exit_p = min(c["close"], sl)
                    return {"exit": True, "return": (exit_p - ep) / ep}
            else:
                new_sl = c["close"] + (1.8 * atr)
                if new_sl < sl: pos["sl"] = new_sl; sl = new_sl
                if c["supertrend_bull"] or c["high"] >= sl:
                    exit_p = max(c["close"], sl)
                    return {"exit": True, "return": (ep - exit_p) / ep}
            return {"exit": False}

        results.append(self.simulate_engine(df, "3. SuperTrend (10,3) + EMA 50", s3_entry, s3_exit))

        # ---------------------------------------------------------
        # Estrategia 4: Keltner Channel Breakout + Chandelier ATR Exit
        # ---------------------------------------------------------
        def s4_entry(c, p):
            if c["close"] > c["kelt_upper"] and p["close"] <= p["kelt_upper"] and c["close"] > c["ema_50"]:
                return {"type": "LONG", "entry": c["close"], "sl": c["close"] - (1.8 * c["atr"])}
            elif c["close"] < c["kelt_lower"] and p["close"] >= p["kelt_lower"] and c["close"] < c["ema_50"]:
                return {"type": "SHORT", "entry": c["close"], "sl": c["close"] + (1.8 * c["atr"])}
            return None

        results.append(self.simulate_engine(df, "4. Keltner Channel + Chandelier", s4_entry, s1_exit))

        # ---------------------------------------------------------
        # Estrategia 5: EMA Triple Cross (9 / 21 / 55)
        # ---------------------------------------------------------
        def s5_entry(c, p):
            e9, e21, e55 = c["ema_9"], c["ema_21"], c["ema_55"]
            pe9, pe21 = p["ema_9"], p["ema_21"]
            if e9 > e21 and pe9 <= pe21 and e21 > e55:
                return {"type": "LONG", "entry": c["close"], "sl": c["close"] - (1.8 * c["atr"])}
            elif e9 < e21 and pe9 >= pe21 and e21 < e55:
                return {"type": "SHORT", "entry": c["close"], "sl": c["close"] + (1.8 * c["atr"])}
            return None

        results.append(self.simulate_engine(df, "5. EMA Triple Cross (9/21/55)", s5_entry, s1_exit))

        # ---------------------------------------------------------
        # Estrategia 6: Donchian Ágil (15 periodos) + ATR Trailing Stop
        # ---------------------------------------------------------
        def s6_entry(c, p):
            if c["high"] > c["donch_h15"]:
                return {"type": "LONG", "entry": c["donch_h15"], "sl": c["donch_h15"] - (1.8 * c["atr"])}
            elif c["low"] < c["donch_l15"]:
                return {"type": "SHORT", "entry": c["donch_l15"], "sl": c["donch_l15"] + (1.8 * c["atr"])}
            return None

        results.append(self.simulate_engine(df, "6. Donchian Ágil (15) + ATR Trail", s6_entry, s1_exit))

        # Sort by Net Return descending
        results.sort(key=lambda x: x["ret_pct"], reverse=True)
        self.display_tournament(results, len(df))
        return results

    def display_tournament(self, results, candles_count):
        table = Table(title=f"TORNEO CUANTITATIVO SOL/USDT (Binance Futuros 5x - {candles_count} Velas 1H)")
        table.add_column("Estrategia", style="bold")
        table.add_column("Capital Final", justify="right")
        table.add_column("Rendimiento", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Trades", justify="right")
        table.add_column("Profit Factor", justify="right")
        table.add_column("Max Drawdown", justify="right")
        table.add_column("Ratio Calmar", justify="right")

        for r in results:
            color = "green" if r["ret_pct"] >= 0 else "red"
            table.add_row(
                r["name"],
                f"[{color}]${r['capital']:.2f}[/{color}]",
                f"[{color}]{r['ret_pct']:+.2f}%[/{color}]",
                f"{r['win_rate']:.1f}%",
                f"{r['trades']}",
                f"{r['profit_factor']:.2f}",
                f"[yellow]{r['max_dd']:.1f}%[/yellow]",
                f"{r['calmar']:.2f}"
            )
        console.print(table)


if __name__ == "__main__":
    st = StrategyTournament()
    st.run_all(days=60)
