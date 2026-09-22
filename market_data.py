"""
Market data handler for SOL/USDT on Binance Futures.
Uses public REST API endpoints (no API keys required for market observation).
"""
import time
import requests
import pandas as pd
from typing import Optional, Tuple

BINANCE_FUTURES_BASE = "https://fapi.binance.com"

class MarketData:
    def __init__(self, symbol: str = "SOLUSDT"):
        self.symbol = symbol.replace("/", "").upper()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SolanaTradingBot/1.0",
            "Accept": "application/json"
        })

    def get_current_price(self) -> float:
        """Fetch current mark/ticker price for SOL/USDT futures."""
        url = f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/price"
        params = {"symbol": self.symbol}
        resp = self.session.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data["price"])

    def get_24h_stats(self) -> dict:
        """Fetch 24-hour ticker statistics."""
        url = f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr"
        params = {"symbol": self.symbol}
        resp = self.session.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {
            "priceChangePercent": float(data.get("priceChangePercent", 0.0)),
            "highPrice": float(data.get("highPrice", 0.0)),
            "lowPrice": float(data.get("lowPrice", 0.0)),
            "volume": float(data.get("volume", 0.0)),
            "quoteVolume": float(data.get("quoteVolume", 0.0)),
            "lastPrice": float(data.get("lastPrice", 0.0))
        }

    def fetch_candles(self, interval: str = "15m", limit: int = 250) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data from Binance Futures.
        Intervals: '1m', '5m', '15m', '1h', '4h', '1d'
        """
        url = f"{BINANCE_FUTURES_BASE}/fapi/v1/klines"
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit
        }
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        # Columns: Open time, Open, High, Low, Close, Volume, Close time, Quote volume, Trades, Taker buy base, Taker buy quote, Ignore
        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ]
        df = pd.DataFrame(raw, columns=cols)
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        for num_col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[num_col] = df[num_col].astype(float)
        
        df = df[["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]]
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def fetch_historical_dataset(self, interval: str = "15m", days: int = 30) -> pd.DataFrame:
        """
        Fetch extended historical dataset by batching requests backwards.
        """
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        all_frames = []
        current_start = start_time
        
        while current_start < end_time:
            url = f"{BINANCE_FUTURES_BASE}/fapi/v1/klines"
            params = {
                "symbol": self.symbol,
                "interval": interval,
                "startTime": current_start,
                "limit": 1000
            }
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                
                cols = [
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
                ]
                batch_df = pd.DataFrame(data, columns=cols)
                batch_df["timestamp"] = pd.to_datetime(batch_df["open_time"], unit="ms")
                for num_col in ["open", "high", "low", "close", "volume"]:
                    batch_df[num_col] = batch_df[num_col].astype(float)
                
                all_frames.append(batch_df[["timestamp", "open", "high", "low", "close", "volume"]])
                
                # Move start time forward
                last_time = int(data[-1][0])
                if last_time <= current_start:
                    break
                current_start = last_time + 1
                time.sleep(0.1) # Respect rate limits
            except Exception as e:
                print(f"Error fetching batch: {e}")
                break

        if not all_frames:
            return pd.DataFrame()
        
        full_df = pd.concat(all_frames, ignore_index=True)
        full_df.drop_duplicates(subset=["timestamp"], inplace=True)
        full_df.sort_values("timestamp", inplace=True)
        full_df.reset_index(drop=True, inplace=True)
        return full_df


if __name__ == "__main__":
    md = MarketData()
    price = md.get_current_price()
    print(f"Current SOL/USDT Futures Price: ${price:.2f}")
    df_15m = md.fetch_candles("15m", limit=10)
    print(f"Latest 15m candle close: ${df_15m['close'].iloc[-1]:.2f}")
