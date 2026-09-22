"""
Backtesting Engine for SOL/USDT 5x Futures.
Evaluates the strategy on historical Binance Futures data.
Calculates net profit, win rate, profit factor, max drawdown, and fee impact.
"""
import sys
import argparse
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from market_data import MarketData
from strategy import TradingStrategy
import config

console = Console()

class Backtester:
    def __init__(
        self,
        symbol: str = "SOLUSDT",
        initial_capital: float = 21.79,
        leverage: int = 5,
        margin_per_trade: float = 18.0,
        stop_loss_pct: float = 0.013,
        take_profit_pct: float = 0.028,
        breakeven_trigger_pct: float = 0.015,
        fee_pct: float = 0.0005 # 0.05% taker fee
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.margin_per_trade = margin_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.breakeven_trigger_pct = breakeven_trigger_pct
        self.fee_pct = fee_pct
        
        self.strategy = TradingStrategy(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct
        )
        self.market_data = MarketData(symbol)

    def run(self, days: int = 30) -> dict:
        console.print(f"[bold cyan]Descargando datos históricos de Binance Futuros ({days} días)...[/bold cyan]")
        df = self.market_data.fetch_historical_dataset(interval="15m", days=days)
        if df.empty or len(df) < 250:
            console.print("[bold red]Error: No se pudieron obtener suficientes velas para el backtest.[/bold red]")
            return {}

        console.print(f"[green]Total velas 15m analizadas: {len(df):,} ({df['timestamp'].iloc[0].strftime('%Y-%m-%d')} a {df['timestamp'].iloc[-1].strftime('%Y-%m-%d')})[/green]")

        # Enrich indicators
        df = self.strategy.enrich_indicators(df)

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown_pct = 0.0
        
        trades = []
        in_position = False
        position = {}

        # Loop through candles starting after warmup period
        warmup = 100
        for i in range(warmup, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            close = curr["close"]
            high = curr["high"]
            low = curr["low"]
            open_p = curr["open"]
            ts = curr["timestamp"]
            atr = curr["atr"] if not np.isnan(curr["atr"]) else close * 0.01

            # Manage open position
            if in_position:
                pos_type = position["type"]
                entry_p = position["entry_price"]
                sl_p = position["stop_loss"]
                tp_p = position["take_profit"]
                be_active = position["breakeven_active"]

                exit_trade = False
                exit_price = None
                exit_reason = ""

                if pos_type == "LONG":
                    # Check breakeven trigger
                    if not be_active and high >= entry_p * (1.0 + self.breakeven_trigger_pct):
                        position["breakeven_active"] = True
                        position["stop_loss"] = entry_p * 1.001 # Breakeven + small fee buffer
                        sl_p = position["stop_loss"]

                    # Check TP and SL
                    if high >= tp_p:
                        exit_trade = True
                        exit_price = tp_p
                        exit_reason = "TAKE_PROFIT"
                    elif low <= sl_p:
                        exit_trade = True
                        exit_price = sl_p
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"

                    if exit_trade:
                        price_change_pct = (exit_price - entry_p) / entry_p
                
                elif pos_type == "SHORT":
                    # Check breakeven trigger
                    if not be_active and low <= entry_p * (1.0 - self.breakeven_trigger_pct):
                        position["breakeven_active"] = True
                        position["stop_loss"] = entry_p * 0.999
                        sl_p = position["stop_loss"]

                    # Check TP and SL
                    if low <= tp_p:
                        exit_trade = True
                        exit_price = tp_p
                        exit_reason = "TAKE_PROFIT"
                    elif high >= sl_p:
                        exit_trade = True
                        exit_price = sl_p
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"

                    if exit_trade:
                        price_change_pct = (entry_p - exit_price) / entry_p

                if exit_trade:
                    # Calculate PnL with leverage and fees
                    margin = min(self.margin_per_trade, capital * 0.85)
                    notional_value = margin * self.leverage
                    
                    gross_pnl = notional_value * price_change_pct
                    fees = notional_value * (self.fee_pct * 2.0) # Entry + exit fees
                    net_pnl = gross_pnl - fees
                    
                    capital += net_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    
                    dd = (peak_capital - capital) / peak_capital * 100.0
                    if dd > max_drawdown_pct:
                        max_drawdown_pct = dd

                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": ts,
                        "type": pos_type,
                        "entry_price": entry_p,
                        "exit_price": exit_price,
                        "reason": exit_reason,
                        "pnl": net_pnl,
                        "return_pct": (net_pnl / margin) * 100.0,
                        "capital_after": capital
                    })
                    in_position = False
                    position = {}

            # If not in position, look for new signal
            if not in_position and capital > 10.0:
                ema_f = curr["ema_fast"]
                ema_s = curr["ema_slow"]
                rsi_curr = curr["rsi"]
                rsi_prev = prev["rsi"]

                sl_dist = max(atr * config.ATR_SL_MULTIPLIER, close * self.stop_loss_pct)
                tp_dist = max(atr * config.ATR_TP_MULTIPLIER, close * self.take_profit_pct)

                # Check Long Pullback
                if (close > ema_s and ema_f > ema_s and
                    low <= ema_f * 1.004 and
                    rsi_prev <= config.RSI_OVERSOLD and 
                    rsi_curr > rsi_prev and 
                    close > open_p):
                    
                    in_position = True
                    position = {
                        "type": "LONG",
                        "entry_time": ts,
                        "entry_price": close,
                        "stop_loss": close - sl_dist,
                        "take_profit": close + tp_dist,
                        "breakeven_active": False
                    }

                # Check Short Pullback
                elif (close < ema_s and ema_f < ema_s and
                      high >= ema_f * 0.996 and
                      rsi_prev >= config.RSI_OVERBOUGHT and 
                      rsi_curr < rsi_prev and 
                      close < open_p):
                    
                    in_position = True
                    position = {
                        "type": "SHORT",
                        "entry_time": ts,
                        "entry_price": close,
                        "stop_loss": close + sl_dist,
                        "take_profit": close - tp_dist,
                        "breakeven_active": False
                    }

        # Calculate statistics
        total_trades = len(trades)
        if total_trades == 0:
            console.print("[yellow]No se ejecutaron trades con los criterios configurados.[/yellow]")
            return {}

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = (len(wins) / total_trades) * 100.0
        
        total_profit = sum(t["pnl"] for t in wins) if wins else 0.0
        total_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 999.0
        net_return_pct = ((capital - self.initial_capital) / self.initial_capital) * 100.0

        # Output results
        self.display_results(
            total_trades, len(wins), len(losses), win_rate,
            profit_factor, self.initial_capital, capital, net_return_pct, max_drawdown_pct, trades
        )

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "initial_capital": self.initial_capital,
            "final_capital": capital,
            "net_return_pct": net_return_pct,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown_pct,
            "trades": trades
        }

    def display_results(self, total, wins, losses, win_rate, pf, initial, final, ret_pct, dd, trades):
        color = "green" if ret_pct >= 0 else "red"
        
        summary = (
            f"[bold]Capital Inicial:[/bold] ${initial:.2f} USDT\n"
            f"[bold]Capital Final:[/bold] [{color}]${final:.2f} USDT[/{color}]\n"
            f"[bold]Rendimiento Neto:[/bold] [{color}]{ret_pct:+.2f}%[/{color}]\n"
            f"[bold]Máximo Drawdown (Retroceso):[/bold] [yellow]{dd:.2f}%[/yellow]\n"
            f"[bold]Total Trades:[/bold] {total} ([green]{wins} Ganadores[/green] / [red]{losses} Perdedores[/red])\n"
            f"[bold]Win Rate:[/bold] {win_rate:.1f}%\n"
            f"[bold]Factor de Beneficio (Profit Factor):[/bold] {pf:.2f}\n"
            f"[bold]Apalancamiento:[/bold] {self.leverage}x (Margen Aislado)"
        )
        console.print(Panel(summary, title="[bold cyan]Resultados del Backtesting SOL/USDT[/bold cyan]", border_style="cyan"))

        # Table of last 10 trades
        table = Table(title="Últimos 10 Trades Simulados")
        table.add_column("Fecha Entrada", style="dim")
        table.add_column("Tipo")
        table.add_column("Precio Entrada")
        table.add_column("Precio Salida")
        table.add_column("Motivo")
        table.add_column("PnL Neto ($)")
        table.add_column("Saldo ($)")

        for t in trades[-10:]:
            pnl_style = "green" if t["pnl"] > 0 else "red"
            t_style = "cyan" if t["type"] == "LONG" else "magenta"
            table.add_row(
                t["entry_time"].strftime("%m-%d %H:%M"),
                f"[{t_style}]{t['type']}[/{t_style}]",
                f"${t['entry_price']:.2f}",
                f"${t['exit_price']:.2f}",
                t["reason"],
                f"[{pnl_style}]${t['pnl']:+.2f}[/{pnl_style}]",
                f"${t['capital_after']:.2f}"
            )
        console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtester SOL/USDT 5x")
    parser.add_argument("--days", type=int, default=30, help="Días de historial a evaluar")
    parser.add_argument("--capital", type=float, default=21.79, help="Capital inicial en USDT")
    parser.add_argument("--leverage", type=int, default=5, help="Apalancamiento")
    args = parser.parse_args()

    bt = Backtester(
        initial_capital=args.capital,
        leverage=args.leverage
    )
    bt.run(days=args.days)
