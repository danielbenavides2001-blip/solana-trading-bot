"""
Champion Quantitative Strategy for SOL/USDT 5x Futures.
Architecture:
- Dynamic Config: Auto-loads latest optimized parameters from active_strategy.json
- 24-Hour Donchian Channel Breakout (Identifies institutional range expansions)
- 200 EMA Macro Trend Filter (Guarantees trading strictly in direction of macro flow)
- 4 Transparent Exit Conditions:
  1. Trailing Stop (Locks in gains dynamically based on ATR)
  2. Stop Loss Inicial (Limits maximum loss to 2.0x ATR ~$1.20)
  3. Invalidez Macro (Emergency close if price violently crosses EMA 200)
  4. Breakeven Lock-in (Risk zero once +1.5% profit is reached)
"""
import os
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
import config

ACTIVE_STRATEGY_FILE = "active_strategy.json"

class TradingStrategy:
    def __init__(
        self,
        channel_period: int = config.CHANNEL_PERIOD,
        ema_trend: int = config.EMA_TREND_PERIOD,
        atr_period: int = config.ATR_PERIOD,
        atr_initial_sl: float = config.ATR_INITIAL_SL,
        atr_trail: float = config.ATR_TRAIL
    ):
        self.channel_period = channel_period
        self.ema_trend = ema_trend
        self.atr_period = atr_period
        self.atr_initial_sl = atr_initial_sl
        self.atr_trail = atr_trail
        self.strategy_name = "Donchian 24h + EMA 200 + ATR Trailing"
        self.breakeven_trigger_pct = 0.015
        
        # Load latest auto-optimized parameters if present
        self.reload_strategy_config()

    def reload_strategy_config(self):
        """Reload hyperparameters from active_strategy.json on the fly."""
        if os.path.exists(ACTIVE_STRATEGY_FILE):
            try:
                with open(ACTIVE_STRATEGY_FILE, "r") as f:
                    data = json.load(f)
                    self.channel_period = data.get("channel_period", self.channel_period)
                    self.ema_trend = data.get("ema_trend_period", self.ema_trend)
                    self.atr_initial_sl = data.get("atr_initial_sl", self.atr_initial_sl)
                    self.atr_trail = data.get("atr_trail", self.atr_trail)
                    self.strategy_name = data.get("strategy_name", self.strategy_name)
                    self.breakeven_trigger_pct = data.get("breakeven_trigger_pct", 0.015)
            except Exception:
                pass

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close_prev = df["close"].shift(1)
        
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def enrich_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enrich candlestick dataframe with Champion indicators."""
        df = df.copy()
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Breakout Levels
        df["high_ch"] = high.rolling(self.channel_period).max().shift(1)
        df["low_ch"] = low.rolling(self.channel_period).min().shift(1)

        # Macro Trend Filter
        df["ema_200"] = self.calculate_ema(close, self.ema_trend)

        # Volatility
        df["atr"] = self.calculate_atr(df, self.atr_period)

        return df

    def evaluate_signal(self, df_1h: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluate real-time 1H candle chart for Breakout + EMA 200 filter.
        """
        if len(df_1h) < max(self.ema_trend, self.channel_period) + 5:
            return {"signal": "HOLD", "reason": "Cargando velas suficientes para EMA 200"}

        enriched = self.enrich_indicators(df_1h)
        curr = enriched.iloc[-1]
        
        close = curr["close"]
        high = curr["high"]
        low = curr["low"]
        high_ch = curr["high_ch"]
        low_ch = curr["low_ch"]
        e200 = curr["ema_200"]
        atr = curr["atr"] if not np.isnan(curr["atr"]) else close * 0.015

        macro_bias = "BULLISH" if close > e200 else "BEARISH"
        dist_to_high_breakout = round(high_ch - close, 2)
        dist_to_low_breakdown = round(close - low_ch, 2)

        # Condition 1: LONG Breakout
        # Price breaches channel High AND is confirmed above EMA 200
        if high > high_ch and close > e200:
            sl_price = round(high_ch - (self.atr_initial_sl * atr), 2)
            return {
                "signal": "LONG",
                "entry_price": high_ch,
                "stop_loss": sl_price,
                "atr": round(atr, 2),
                "atr_trail": self.atr_trail,
                "macro_bias": macro_bias,
                "ema_200": round(e200, 2),
                "high_ch": round(high_ch, 2),
                "low_ch": round(low_ch, 2),
                "strategy_name": self.strategy_name,
                "reason": f"¡Ruptura Alcista! Precio superó ${high_ch:.2f} con tendencia Macro Alcista (> EMA 200 ${e200:.2f})"
            }

        # Condition 2: SHORT Breakdown
        # Price breaches channel Low AND is confirmed below EMA 200
        elif low < low_ch and close < e200:
            sl_price = round(low_ch + (self.atr_initial_sl * atr), 2)
            return {
                "signal": "SHORT",
                "entry_price": low_ch,
                "stop_loss": sl_price,
                "atr": round(atr, 2),
                "atr_trail": self.atr_trail,
                "macro_bias": macro_bias,
                "ema_200": round(e200, 2),
                "high_ch": round(high_ch, 2),
                "low_ch": round(low_ch, 2),
                "strategy_name": self.strategy_name,
                "reason": f"¡Ruptura Bajista! Precio perforó ${low_ch:.2f} con tendencia Macro Bajista (< EMA 200 ${e200:.2f})"
            }

        # Default: Monitoring inside channel
        return {
            "signal": "HOLD",
            "current_price": close,
            "macro_bias": macro_bias,
            "ema_200": round(e200, 2),
            "high_ch": round(high_ch, 2),
            "low_ch": round(low_ch, 2),
            "dist_to_long": dist_to_high_breakout,
            "dist_to_short": dist_to_low_breakdown,
            "atr": round(atr, 2),
            "strategy_name": self.strategy_name,
            "reason": f"Dentro del canal [{self.channel_period}h: ${low_ch:.2f} - ${high_ch:.2f}]. Faltan ${dist_to_high_breakout:.2f} para Long / ${dist_to_low_breakdown:.2f} para Short."
        }

    def evaluate_exit(self, pos: dict, current_price: float, atr: float, ema_200: float) -> dict:
        """
        Evaluate all 4 transparent exit rules:
        1. Trailing Stop (Dynamic ATR ratchet)
        2. Initial Stop Loss
        3. Macro Invalidation (Price crosses adverse side of EMA 200)
        4. Breakeven (+1.5% profit reached)
        """
        pos_type = pos["type"]
        entry_p = pos["entry_price"]
        current_sl = pos["stop_loss"]

        exit_triggered = False
        exit_price = None
        exit_reason = ""
        new_sl = current_sl

        if pos_type == "LONG":
            # 1. Trailing Stop ratchet upward
            calculated_trail = current_price - (self.atr_trail * atr)
            if calculated_trail > current_sl:
                new_sl = round(calculated_trail, 2)

            # 2. Breakeven Lock-in (+1.5% profit reached moves SL to protect capital + fees)
            if (current_price - entry_p) / entry_p >= self.breakeven_trigger_pct:
                be_level = round(entry_p + 0.10, 2)
                if new_sl < be_level:
                    new_sl = be_level

            # 3. Check Macro Invalidation (Emergency exit if trend collapses below EMA 200)
            if current_price < ema_200:
                exit_triggered = True
                exit_price = current_price
                exit_reason = "MACRO_INVALIDATION (Precio perdió EMA 200)"
            # 4. Check Trailing / Hard Stop
            elif current_price <= new_sl:
                exit_triggered = True
                exit_price = new_sl
                exit_reason = "TRAILING_STOP" if new_sl > entry_p else "STOP_LOSS"

        elif pos_type == "SHORT":
            # 1. Trailing Stop ratchet downward
            calculated_trail = current_price + (self.atr_trail * atr)
            if calculated_trail < current_sl:
                new_sl = round(calculated_trail, 2)

            # 2. Breakeven Lock-in (+1.5% profit reached moves SL to protect capital + fees)
            if (entry_p - current_price) / entry_p >= self.breakeven_trigger_pct:
                be_level = round(entry_p - 0.10, 2)
                if new_sl > be_level:
                    new_sl = be_level

            # 3. Check Macro Invalidation (Emergency exit if trend spikes above EMA 200)
            if current_price > ema_200:
                exit_triggered = True
                exit_price = current_price
                exit_reason = "MACRO_INVALIDATION (Precio superó EMA 200)"
            # 4. Check Trailing / Hard Stop
            elif current_price >= new_sl:
                exit_triggered = True
                exit_price = new_sl
                exit_reason = "TRAILING_STOP" if new_sl < entry_p else "STOP_LOSS"

        return {
            "exit": exit_triggered,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "updated_sl": new_sl
        }


if __name__ == "__main__":
    from market_data import MarketData
    md = MarketData("SOLUSDT")
    df_1h = md.fetch_candles("1h", limit=250)
    strat = TradingStrategy()
    sig = strat.evaluate_signal(df_1h)
    print(f"--- ESTRATEGIA ADAPTATIVA ({strat.strategy_name}) ---")
    print(f"Estado: {sig['signal']}")
    print(f"Detalle: {sig['reason']}")
