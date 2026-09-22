"""
Donchian Trend Breakout Backtester for SOL/USDT 5x Futures.
Implements 20-period High/Low Breakout with Dynamic ATR Trailing Stop.
"""
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from market_data import MarketData

console = Console()

class BreakoutBacktester:
    def __init__(
        self,
        symbol: str = "SOLUSDT",
        initial_capital: float = 21.79,
        leverage: int = 5,
        margin_per_trade: float = 18.0,
        channel_period: int = 20,
        atr_period: int = 14,
        atr_initial_sl: float = 2.0,
        atr_trail: float = 1.5,
        fee_pct: float = 0.0005 # 0.05% taker fee
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.margin_per_trade = margin_per_trade
        self.channel_period = channel_period
        self.atr_period = atr_period
        self.atr_initial_sl = atr_initial_sl
        self.atr_trail = atr_trail
        self.fee_pct = fee_pct
        self.market_data = MarketData(symbol)

    def run(self, hours: int = 750) -> dict:
        console.print(f"[bold cyan]Descargando {hours} velas de 1 Hora de Binance Futuros...[/bold cyan]")
        df = self.market_data.fetch_candles("1h", limit=hours)
        if df.empty or len(df) < 50:
            console.print("[red]Error: Datos insuficientes.[/red]")
            return {}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Donchian Channel (Highest High and Lowest Low of last 20 candles, shifted by 1)
        df["high_ch"] = high.rolling(self.channel_period).max().shift(1)
        df["low_ch"] = low.rolling(self.channel_period).min().shift(1)

        # ATR (Average True Range)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(self.atr_period).mean()

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0
        
        trades = []
        in_pos = False
        pos = {}

        for i in range(self.channel_period + 5, len(df)):
            c_p = close.iloc[i]
            c_h = high.iloc[i]
            c_l = low.iloc[i]
            c_atr = df["atr"].iloc[i]
            h_ch = df["high_ch"].iloc[i]
            l_ch = df["low_ch"].iloc[i]
            ts = df["timestamp"].iloc[i]

            if in_pos:
                pt = pos["type"]
                ep = pos["entry"]
                sl = pos["sl"]
                exit_trade = False
                exit_price = None

                if pt == "LONG":
                    # Ratchet trailing stop up
                    new_sl = c_p - (self.atr_trail * c_atr)
                    if new_sl > pos["sl"]:
                        pos["sl"] = new_sl
                        sl = new_sl

                    # Trigger stop
                    if c_l <= sl:
                        exit_trade = True
                        exit_price = sl
                        price_ret = (sl - ep) / ep

                elif pt == "SHORT":
                    # Ratchet trailing stop down
                    new_sl = c_p + (self.atr_trail * c_atr)
                    if new_sl < pos["sl"]:
                        pos["sl"] = new_sl
                        sl = new_sl

                    if c_h >= sl:
                        exit_trade = True
                        exit_price = sl
                        price_ret = (ep - sl) / ep

                if exit_trade:
                    margin = min(self.margin_per_trade, capital * 0.85)
                    notional = margin * self.leverage
                    gross_pnl = notional * price_ret
                    fees = notional * (self.fee_pct * 2.0)
                    net_pnl = gross_pnl - fees
                    capital += net_pnl

                    if capital > peak_capital:
                        peak_capital = capital
                    dd = (peak_capital - capital) / peak_capital * 100.0
                    if dd > max_drawdown:
                        max_drawdown = dd

                    trades.append({
                        "entry_time": pos["entry_time"],
                        "exit_time": ts,
                        "type": pt,
                        "entry_price": ep,
                        "exit_price": exit_price,
                        "pnl": net_pnl,
                        "return_pct": (net_pnl / margin) * 100.0,
                        "capital_after": capital
                    })
                    in_pos = False
                    pos = {}

            # Check new entry if not in position
            if not in_pos and capital > 10.0 and not np.isnan(c_atr):
                # Breakout LONG
                if c_h > h_ch:
                    in_pos = True
                    pos = {
                        "type": "LONG",
                        "entry_time": ts,
                        "entry": h_ch,
                        "sl": h_ch - (self.atr_initial_sl * c_atr)
                    }
                # Breakout SHORT
                elif c_l < l_ch:
                    in_pos = True
                    pos = {
                        "type": "SHORT",
                        "entry_time": ts,
                        "entry": l_ch,
                        "sl": l_ch + (self.atr_initial_sl * c_atr)
                    }

        total = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        wr = (len(wins) / total * 100.0) if total else 0.0
        ret_pct = ((capital - self.initial_capital) / self.initial_capital) * 100.0

        # Summary
        color = "green" if ret_pct >= 0 else "red"
        summary = (
            f"[bold]Estrategia:[/bold] Donchian Breakout + ATR Trailing Stop (1H)\n"
            f"[bold]Capital Inicial:[/bold] ${self.initial_capital:.2f} USDT\n"
            f"[bold]Capital Final:[/bold] [{color}]${capital:.2f} USDT[/{color}]\n"
            f"[bold]Rendimiento Neto:[/bold] [{color}]{ret_pct:+.2f}%[/{color}]\n"
            f"[bold]Máximo Drawdown (Retroceso):[/bold] [yellow]{max_drawdown:.2f}%[/yellow]\n"
            f"[bold]Total Operaciones:[/bold] {total} ([green]{len(wins)} Ganadores[/green] / [red]{len(losses)} Perdedores[/red])\n"
            f"[bold]Win Rate:[/bold] {wr:.1f}%\n"
            f"[bold]Apalancamiento:[/bold] {self.leverage}x (Margen Aislado)"
        )
        console.print(Panel(summary, title="[bold green]Reporte Oficial de Backtesting SOL/USDT[/bold green]", border_style="green"))

        # Table of last 12 trades
        table = Table(title="Últimos 12 Trades Históricos Simulados")
        table.add_column("Fecha Entrada", style="dim")
        table.add_column("Tipo")
        table.add_column("Precio Entrada")
        table.add_column("Precio Salida")
        table.add_column("PnL Neto ($)")
        table.add_column("Rentabilidad")
        table.add_column("Saldo ($)")

        for t in trades[-12:]:
            pnl_style = "green" if t["pnl"] > 0 else "red"
            t_style = "cyan" if t["type"] == "LONG" else "magenta"
            table.add_row(
                t["entry_time"].strftime("%m-%d %H:%M"),
                f"[{t_style}]{t['type']}[/{t_style}]",
                f"${t['entry_price']:.2f}",
                f"${t['exit_price']:.2f}",
                f"[{pnl_style}]${t['pnl']:+.2f}[/{pnl_style}]",
                f"[{pnl_style}]{t['return_pct']:+.1f}%[/{pnl_style}]",
                f"${t['capital_after']:.2f}"
            )
        console.print(table)
        return {"capital": capital, "return_pct": ret_pct, "win_rate": wr, "trades": trades}


if __name__ == "__main__":
    bt = BreakoutBacktester()
    bt.run(hours=750)
