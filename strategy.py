"""
Champion Quantitative Strategy for SOL/USDT 5x Futures.
Architecture (Opción 4 - Momentum Institucional + TP Fijo + Anti-Rango):
- 24-Hour Donchian Channel Breakout (Identifies institutional range expansions)
- 200 EMA Macro Trend Filter (Guarantees trading strictly in direction of macro flow)
- ADX Trend Strength Filter (> 20.0 eliminates sideways chop and false fakeouts)
- Target Take Profit (+1.6% ~ $1.35-$1.45 USDT profit per trade)
- 4 Transparent Exit Conditions:
  1. Target Take Profit (+1.6% target hit, locks in cash immediately)
  2. Trailing Stop (Dynamic ATR ratchet to protect profits on runners)
  3. Stop Loss Inicial (1.8x ATR protection)
  4. Macro Invalidation (Emergency close if price violently crosses adverse side of EMA 200)
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
        atr_trail: float = config.ATR_TRAIL,
        tp_pct: float = config.TP_TARGET_PCT,
        adx_min: float = config.ADX_MIN,
        adx_period: int = config.ADX_PERIOD
    ):
        self.channel_period = channel_period
        self.ema_trend = ema_trend
        self.atr_period = atr_period
        self.atr_initial_sl = atr_initial_sl
        self.atr_trail = atr_trail
        self.tp_pct = tp_pct
        self.adx_min = adx_min
        self.adx_period = adx_period
        self.strategy_name = "Donchian 24h + ADX 20 + TP Fijo (+1.6%)"
        self.breakeven_trigger_pct = 0.012
        
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
                    self.tp_pct = data.get("tp_pct", self.tp_pct)
                    self.adx_min = data.get("adx_min", self.adx_min)
                    self.strategy_name = data.get("strategy_name", self.strategy_name)
                    self.breakeven_trigger_pct = data.get("breakeven_trigger_pct", 0.012)
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

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index (ADX) with exponential smoothing."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        close_prev = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        tr_smooth = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
        plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
        minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
        
        plus_di = 100 * (plus_dm_smooth / (tr_smooth + 1e-9))
        minus_di = 100 * (minus_dm_smooth / (tr_smooth + 1e-9))
        
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
        adx = dx.ewm(alpha=1/period, adjust=False).mean()
        return adx

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

        # ADX Trend Strength Filter
        df["adx"] = self.calculate_adx(df, self.adx_period)

        return df

    def evaluate_signal(self, df_1h: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluate real-time 1H candle chart for Breakout + EMA 200 + ADX strength.
        """
        min_required = max(self.ema_trend, self.channel_period, self.adx_period * 2) + 5
        if len(df_1h) < min_required:
            return {"signal": "HOLD", "reason": "Cargando velas suficientes para indicadores"}

        enriched = self.enrich_indicators(df_1h)
        curr = enriched.iloc[-1]
        
        close = curr["close"]
        high = curr["high"]
        low = curr["low"]
        high_ch = curr["high_ch"]
        low_ch = curr["low_ch"]
        e200 = curr["ema_200"]
        atr = curr["atr"] if not np.isnan(curr["atr"]) else close * 0.015
        adx = curr["adx"] if not np.isnan(curr["adx"]) else 25.0

        macro_bias = "BULLISH" if close > e200 else "BEARISH"
        dist_to_high_breakout = round(high_ch - close, 2)
        dist_to_low_breakdown = round(close - low_ch, 2)

        # Anti-Whipsaw Penetration Buffer (0.2% ~ $0.24 on SOL to filter fakeout wicks)
        min_breakout_long = round(high_ch * (1.0 + 0.002), 2)
        min_breakdown_short = round(low_ch * (1.0 - 0.002), 2)

        # Check ADX Strength Filter
        has_momentum = adx >= self.adx_min

        # Condition 1: LONG Breakout
        # Price breaches channel High with real penetration AND is confirmed above EMA 200
        if high >= min_breakout_long and close > e200:
            if not has_momentum:
                return {
                    "signal": "HOLD",
                    "current_price": close,
                    "macro_bias": macro_bias,
                    "ema_200": round(e200, 2),
                    "high_ch": round(high_ch, 2),
                    "low_ch": round(low_ch, 2),
                    "adx": round(adx, 2),
                    "atr": round(atr, 2),
                    "strategy_name": self.strategy_name,
                    "reason": f"Filtro ADX Activo: Ruptura detectada pero mercado sin fuerza/momentum institucional (ADX {adx:.1f} < {self.adx_min:.1f}). Evitando trampa de rango."
                }

            sl_price = round(min_breakout_long - (self.atr_initial_sl * atr), 2)
            tp_price = round(min_breakout_long * (1.0 + self.tp_pct), 2)
            return {
                "signal": "LONG",
                "entry_price": min_breakout_long,
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "tp_pct": self.tp_pct,
                "atr": round(atr, 2),
                "adx": round(adx, 2),
                "atr_trail": self.atr_trail,
                "macro_bias": macro_bias,
                "ema_200": round(e200, 2),
                "high_ch": round(high_ch, 2),
                "low_ch": round(low_ch, 2),
                "strategy_name": self.strategy_name,
                "reason": f"¡Ruptura Alcista Confirmada con Momentum! Precio > ${min_breakout_long:.2f} con ADX {adx:.1f} > {self.adx_min} y tendencia Macro Alcista (> EMA 200 ${e200:.2f}). TP Objetivo: ${tp_price:.2f} (+{self.tp_pct*100:.1f}%)"
            }

        # Condition 2: SHORT Breakdown
        # Price breaches channel Low with real penetration AND is confirmed below EMA 200
        elif low <= min_breakdown_short and close < e200:
            if not has_momentum:
                return {
                    "signal": "HOLD",
                    "current_price": close,
                    "macro_bias": macro_bias,
                    "ema_200": round(e200, 2),
                    "high_ch": round(high_ch, 2),
                    "low_ch": round(low_ch, 2),
                    "adx": round(adx, 2),
                    "atr": round(atr, 2),
                    "strategy_name": self.strategy_name,
                    "reason": f"Filtro ADX Activo: Ruptura detectada pero mercado sin fuerza/momentum institucional (ADX {adx:.1f} < {self.adx_min:.1f}). Evitando trampa de rango."
                }

            sl_price = round(min_breakdown_short + (self.atr_initial_sl * atr), 2)
            tp_price = round(min_breakdown_short * (1.0 - self.tp_pct), 2)
            return {
                "signal": "SHORT",
                "entry_price": min_breakdown_short,
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "tp_pct": self.tp_pct,
                "atr": round(atr, 2),
                "adx": round(adx, 2),
                "atr_trail": self.atr_trail,
                "macro_bias": macro_bias,
                "ema_200": round(e200, 2),
                "high_ch": round(high_ch, 2),
                "low_ch": round(low_ch, 2),
                "strategy_name": self.strategy_name,
                "reason": f"¡Ruptura Bajista Confirmada con Momentum! Precio < ${min_breakdown_short:.2f} con ADX {adx:.1f} > {self.adx_min} y tendencia Macro Bajista (< EMA 200 ${e200:.2f}). TP Objetivo: ${tp_price:.2f} (-{self.tp_pct*100:.1f}%)"
            }

        # Default: Monitoring inside channel
        return {
            "signal": "HOLD",
            "current_price": close,
            "macro_bias": macro_bias,
            "ema_200": round(e200, 2),
            "high_ch": round(high_ch, 2),
            "low_ch": round(low_ch, 2),
            "adx": round(adx, 2),
            "dist_to_long": dist_to_high_breakout,
            "dist_to_short": dist_to_low_breakdown,
            "atr": round(atr, 2),
            "strategy_name": self.strategy_name,
            "reason": f"Dentro del canal [{self.channel_period}h: ${low_ch:.2f} - ${high_ch:.2f} | ADX: {adx:.1f}]. Faltan ${dist_to_high_breakout:.2f} para Long / ${dist_to_low_breakdown:.2f} para Short."
        }

    def evaluate_exit(self, pos: dict, current_price: float, atr: float, ema_200: float) -> dict:
        """
        Evaluate 4 transparent exit rules:
        1. Fixed Target Take Profit (+1.6% target hit, cash out immediately)
        2. Trailing Stop (Dynamic ATR ratchet to protect profits on runners)
        3. Hard Stop Loss (1.8x ATR)
        4. Macro Invalidation (Emergency exit if trend collapses past EMA 200)
        """
        pos_type = pos["type"]
        entry_p = pos["entry_price"]
        current_sl = pos["stop_loss"]
        tp_price = pos.get("take_profit")

        exit_triggered = False
        exit_price = None
        exit_reason = ""
        new_sl = current_sl

        if pos_type == "LONG":
            # 1. Check Fixed Target Take Profit
            if tp_price and current_price >= tp_price:
                return {
                    "exit": True,
                    "exit_price": tp_price,
                    "exit_reason": f"TAKE_PROFIT (+{self.tp_pct*100:.1f}%)",
                    "updated_sl": new_sl
                }

            # 2. Trailing Stop ratchet upward
            calculated_trail = current_price - (self.atr_trail * atr)
            if calculated_trail > current_sl:
                new_sl = round(calculated_trail, 2)

            # 3. Breakeven Lock-in (+1.2% profit reached moves SL to protect capital + fees)
            if (current_price - entry_p) / entry_p >= self.breakeven_trigger_pct:
                be_level = round(entry_p + 0.10, 2)
                if new_sl < be_level:
                    new_sl = be_level

            # 4. Check Macro Invalidation
            if current_price < ema_200:
                exit_triggered = True
                exit_price = current_price
                exit_reason = "MACRO_INVALIDATION (Precio perdió EMA 200)"
            # 5. Check Trailing / Hard Stop
            elif current_price <= new_sl:
                exit_triggered = True
                exit_price = new_sl
                exit_reason = "TRAILING_STOP" if new_sl > entry_p else "STOP_LOSS"

        elif pos_type == "SHORT":
            # 1. Check Fixed Target Take Profit
            if tp_price and current_price <= tp_price:
                return {
                    "exit": True,
                    "exit_price": tp_price,
                    "exit_reason": f"TAKE_PROFIT (+{self.tp_pct*100:.1f}%)",
                    "updated_sl": new_sl
                }

            # 2. Trailing Stop ratchet downward
            calculated_trail = current_price + (self.atr_trail * atr)
            if calculated_trail < current_sl:
                new_sl = round(calculated_trail, 2)

            # 3. Breakeven Lock-in (+1.2% profit reached moves SL to protect capital + fees)
            if (entry_p - current_price) / entry_p >= self.breakeven_trigger_pct:
                be_level = round(entry_p - 0.10, 2)
                if new_sl > be_level:
                    new_sl = be_level

            # 4. Check Macro Invalidation
            if current_price > ema_200:
                exit_triggered = True
                exit_price = current_price
                exit_reason = "MACRO_INVALIDATION (Precio superó EMA 200)"
            # 5. Check Trailing / Hard Stop
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
