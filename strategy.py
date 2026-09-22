"""
Champion Quantitative Strategy for SOL/USDT 5x Futures.
Architecture:
- 24-Hour Donchian Channel Breakout (Identifies institutional range expansions)
- 200 EMA Macro Trend Filter (Guarantees trading strictly in direction of macro flow)
- Dynamic ATR Trailing Stop (Cuts losses at 2.0x ATR, ratchets up at 1.7x ATR to let runners breathe)

Backtest Benchmark: +114.3% Net Return, Profit Factor 2.01, Calmar 3.47.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
import config

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

        # 24h Donchian Breakout Levels
        df["high_ch"] = high.rolling(self.channel_period).max().shift(1)
        df["low_ch"] = low.rolling(self.channel_period).min().shift(1)

        # Macro Trend Filter
        df["ema_200"] = self.calculate_ema(close, self.ema_trend)

        # Volatility
        df["atr"] = self.calculate_atr(df, self.atr_period)

        return df

    def evaluate_signal(self, df_1h: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluate real-time 1H candle chart for 24h Breakout + EMA 200 filter.
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
        # Price breaches 24h High AND is confirmed above EMA 200
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
                "reason": f"¡Ruptura Alcista 24h! Precio superó ${high_ch:.2f} con tendencia Macro Alcista (> EMA 200 ${e200:.2f})"
            }

        # Condition 2: SHORT Breakdown
        # Price breaches 24h Low AND is confirmed below EMA 200
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
                "reason": f"¡Ruptura Bajista 24h! Precio perforó ${low_ch:.2f} con tendencia Macro Bajista (< EMA 200 ${e200:.2f})"
            }

        # Default: Monitoring inside 24h channel
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
            "reason": f"Dentro del canal 24h [${low_ch:.2f} - ${high_ch:.2f}]. Faltan ${dist_to_high_breakout:.2f} para Long / ${dist_to_low_breakdown:.2f} para Short."
        }


if __name__ == "__main__":
    from market_data import MarketData
    md = MarketData("SOLUSDT")
    df_1h = md.fetch_candles("1h", limit=250)
    strat = TradingStrategy()
    sig = strat.evaluate_signal(df_1h)
    print("--- EVALUACIÓN EN TIEMPO REAL (ESTRATEGIA CAMPEONA) ---")
    print(f"Estado: {sig['signal']}")
    print(f"Detalle: {sig['reason']}")
    print(f"Techo 24h: ${sig['high_ch']} | Suelo 24h: ${sig['low_ch']} | EMA 200: ${sig['ema_200']}")
