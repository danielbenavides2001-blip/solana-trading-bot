"""
Live Market Monitor & Real-Time Dashboard for SOL/USDT Futures (Champion Strategy).
Displays real-time prices, 24h channel bounds, EMA 200 trend, ATR volatility, and position status.
"""
import time
import os
import sys
from datetime import datetime
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

from market_data import MarketData
from strategy import TradingStrategy
import config

console = Console()

class LiveMarketMonitor:
    def __init__(self, symbol: str = "SOLUSDT", initial_capital: float = 21.79):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.market_data = MarketData(symbol)
        self.strategy = TradingStrategy()
        
        self.active_position = None
        self.trade_history = []

    def fetch_market_state(self) -> dict:
        """Fetch latest candles, ticker stats, and evaluate Champion strategy."""
        current_price = self.market_data.get_current_price()
        stats = self.market_data.get_24h_stats()
        df_1h = self.market_data.fetch_candles("1h", limit=250)
        signal_info = self.strategy.evaluate_signal(df_1h)
        
        return {
            "price": current_price,
            "stats": stats,
            "signal": signal_info,
            "timestamp": datetime.now()
        }

    def update_paper_position(self, state: dict):
        """Simulate trade execution and ATR trailing stop in Paper Trading mode."""
        curr_p = state["price"]
        sig = state["signal"]
        atr = sig.get("atr", 1.5)

        if self.active_position:
            pos = self.active_position
            pos_type = pos["type"]
            entry_p = pos["entry"]
            sl_p = pos["sl"]
            margin = pos["margin"]
            notional = margin * config.LEVERAGE

            # Ratchet trailing stop
            if pos_type == "LONG":
                new_sl = curr_p - (config.ATR_TRAIL * atr)
                if new_sl > sl_p:
                    pos["sl"] = new_sl
                    sl_p = new_sl
                # Check exit
                if curr_p <= sl_p:
                    ret_pct = (sl_p - entry_p) / entry_p
                    net_pnl = (notional * ret_pct) - (notional * config.TAKER_FEE * 2)
                    self.capital += net_pnl
                    self.trade_history.append({"type": "LONG", "pnl": net_pnl, "reason": "TRAILING_STOP", "price": sl_p})
                    self.active_position = None
                    return
                else:
                    ret_pct = (curr_p - entry_p) / entry_p
                    pos["unrealized_pnl"] = notional * ret_pct
                    pos["unrealized_pct"] = ret_pct * config.LEVERAGE * 100.0

            elif pos_type == "SHORT":
                new_sl = curr_p + (config.ATR_TRAIL * atr)
                if new_sl < sl_p:
                    pos["sl"] = new_sl
                    sl_p = new_sl
                if curr_p >= sl_p:
                    ret_pct = (entry_p - sl_p) / entry_p
                    net_pnl = (notional * ret_pct) - (notional * config.TAKER_FEE * 2)
                    self.capital += net_pnl
                    self.trade_history.append({"type": "SHORT", "pnl": net_pnl, "reason": "TRAILING_STOP", "price": sl_p})
                    self.active_position = None
                    return
                else:
                    ret_pct = (entry_p - curr_p) / entry_p
                    pos["unrealized_pnl"] = notional * ret_pct
                    pos["unrealized_pct"] = ret_pct * config.LEVERAGE * 100.0

        else:
            # Check for new entry signal
            if sig["signal"] in ("LONG", "SHORT") and self.capital >= 10.0:
                margin = min(config.MAX_MARGIN_PER_TRADE, self.capital * 0.85)
                self.active_position = {
                    "type": sig["signal"],
                    "entry": sig["entry_price"],
                    "sl": sig["stop_loss"],
                    "margin": margin,
                    "unrealized_pnl": 0.0,
                    "unrealized_pct": 0.0,
                    "open_time": datetime.now()
                }

    def generate_dashboard(self, state: dict) -> Layout:
        """Construct the Rich terminal layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=7)
        )
        layout["body"].split_row(
            Layout(name="market_status", ratio=1),
            Layout(name="position_status", ratio=1)
        )

        # Header
        stats = state["stats"]
        chg = stats["priceChangePercent"]
        chg_color = "green" if chg >= 0 else "red"
        curr_p = state["price"]
        
        header_text = (
            f"[bold yellow]SOL/USDT FUTURES[/bold yellow] | "
            f"Precio: [bold white]${curr_p:.2f}[/bold white] | "
            f"24h: [{chg_color}]{chg:+.2f}%[/{chg_color}] (Alto: ${stats['highPrice']:.2f} / Bajo: ${stats['lowPrice']:.2f}) | "
            f"Volumen 24h: ${stats['quoteVolume']/1e6:.1f}M USDT\n"
            f"[dim]Estrategia: Donchian 24h + EMA 200 + ATR Trailing Stop | Actualizado: {state['timestamp'].strftime('%H:%M:%S')} (5x Aislado)[/dim]"
        )
        layout["header"].update(Panel(header_text, style="bold cyan", border_style="cyan"))

        # Market Analysis Table
        sig = state["signal"]
        macro_b = sig.get("macro_bias", "NEUTRAL")
        macro_c = "green" if macro_b == "BULLISH" else "red"
        
        m_table = Table(box=None, expand=True)
        m_table.add_column("Métrica Cuantitativa", style="bold")
        m_table.add_column("Valor Actual", justify="right")
        
        m_table.add_row("Régimen Macro (EMA 200)", f"[{macro_c} bold]{macro_b} (${sig.get('ema_200', 0):.2f})[/{macro_c} bold]")
        m_table.add_row("Techo de Ruptura (24h High)", f"[cyan bold]${sig.get('high_ch', 0):.2f}[/cyan bold]")
        m_table.add_row("Suelo de Ruptura (24h Low)", f"[magenta bold]${sig.get('low_ch', 0):.2f}[/magenta bold]")
        m_table.add_row("Distancia para LONG", f"${sig.get('dist_to_long', 0):.2f}")
        m_table.add_row("Distancia para SHORT", f"${sig.get('dist_to_short', 0):.2f}")
        m_table.add_row("Volatilidad ATR (1h)", f"${sig.get('atr', 0):.2f}")
        
        sig_type = sig["signal"]
        sig_col = "green" if sig_type == "LONG" else ("red" if sig_type == "SHORT" else "yellow")
        m_table.add_row("Estado de Entrada", f"[{sig_col} bold]{sig_type}[/{sig_col} bold]")
        
        layout["market_status"].update(Panel(m_table, title="[bold]Estrategia Campeona: Niveles de Rotura 24h[/bold]", border_style="blue"))

        # Position & Account Table
        p_table = Table(box=None, expand=True)
        p_table.add_column("Concepto", style="bold")
        p_table.add_column("Estado", justify="right")

        total_ret = ((self.capital - self.initial_capital) / self.initial_capital) * 100.0
        cap_color = "green" if self.capital >= self.initial_capital else "red"
        
        p_table.add_row("Capital Inicial", f"${self.initial_capital:.2f} USDT")
        p_table.add_row("Saldo Disponible", f"[{cap_color} bold]${self.capital:.2f} USDT[/{cap_color} bold]")
        p_table.add_row("Rendimiento Neto", f"[{cap_color}]{total_ret:+.2f}%[/{cap_color}]")
        
        if self.active_position:
            pos = self.active_position
            pnl = pos["unrealized_pnl"]
            pnl_c = "green" if pnl >= 0 else "red"
            pos_style = "green" if pos["type"] == "LONG" else "red"
            
            p_table.add_row("Posición Activa", f"[{pos_style} bold]{pos['type']} (5x)[/{pos_style} bold]")
            p_table.add_row("Precio Entrada", f"${pos['entry']:.2f}")
            p_table.add_row("Trailing Stop Actual", f"[yellow]${pos['sl']:.2f}[/yellow]")
            p_table.add_row("PnL no realizado", f"[{pnl_c}]${pnl:+.2f} ({pos['unrealized_pct']:+.1f}%)[/{pnl_c}]")
        else:
            p_table.add_row("Posición Activa", "[dim]Sin posición abierta[/dim]")
            p_table.add_row("Modo de Operación", "[green]Esperando ruptura de canal 24h[/green]")
            p_table.add_row("Gestión de Salida", "Trailing Stop ATR (1.7x)")

        layout["position_status"].update(Panel(p_table, title="[bold]Gestión de Cuenta & Posición[/bold]", border_style="green"))

        # Footer
        f_table = Table(box=None, expand=True)
        f_table.add_column("Historial Reciente", style="bold")
        f_table.add_column("Tipo")
        f_table.add_column("Precio Salida")
        f_table.add_column("Motivo")
        f_table.add_column("PnL ($)", justify="right")
        
        if not self.trade_history:
            f_table.add_row("[dim]Aún no se han ejecutado trades en esta sesión[/dim]", "-", "-", "-", "-")
        else:
            for t in self.trade_history[-3:]:
                p_col = "green" if t["pnl"] > 0 else "red"
                f_table.add_row(
                    "Cerrado",
                    t["type"],
                    f"${t['price']:.2f}",
                    t["reason"],
                    f"[{p_col}]${t['pnl']:+.2f}[/{p_col}]"
                )

        layout["footer"].update(Panel(f_table, title="[bold]Registro de Órdenes[/bold]", border_style="magenta"))
        return layout

    def run_live(self, poll_interval: int = 5, max_ticks: int = None):
        """Run real-time monitoring loop."""
        console.print("[bold green]Iniciando Monitor en Tiempo Real de SOL/USDT...[/bold green]")
        ticks = 0
        
        with Live(console=console, refresh_per_second=2, screen=False) as live:
            while True:
                try:
                    state = self.fetch_market_state()
                    self.update_paper_position(state)
                    dashboard = self.generate_dashboard(state)
                    live.update(dashboard)
                    
                    ticks += 1
                    if max_ticks and ticks >= max_ticks:
                        break
                        
                    time.sleep(poll_interval)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    time.sleep(poll_interval)


if __name__ == "__main__":
    monitor = LiveMarketMonitor()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        state = monitor.fetch_market_state()
        monitor.update_paper_position(state)
        layout = monitor.generate_dashboard(state)
        console.print(layout)
    else:
        monitor.run_live(poll_interval=5)
