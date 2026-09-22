import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from market_data import MarketData

console = Console()
md = MarketData("SOLUSDT")

# Fetch 750 hours (~31 days of 1-hour candles)
df = md.fetch_candles("1h", limit=750)
console.print(f"[bold cyan]Analizando {len(df)} velas de 1 Hora (1H) de Solana...[/bold cyan]")

close = df["close"]
high = df["high"]
low = df["low"]
open_p = df["open"]

# 1H Indicators
ema_20 = close.ewm(span=20, adjust=False).mean()
ema_50 = close.ewm(span=50, adjust=False).mean()

delta = close.diff()
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
ag = gain.ewm(alpha=1/14, adjust=False).mean()
al = loss.ewm(alpha=1/14, adjust=False).mean()
rsi = 100 - (100 / (1 + (ag / (al + 1e-9))))

cap = 21.79
initial = cap
leverage = 5
trades = []
in_pos = False
pos = {}

# Strategy on 1H:
# SL: 1.8% | TP: 4.5% (Asymmetric R:R = 1:2.5) | Breakeven at +2.0%
sl_pct = 0.018
tp_pct = 0.045
be_pct = 0.020

for i in range(50, len(df)):
    c_p = close.iloc[i]
    c_h = high.iloc[i]
    c_l = low.iloc[i]
    c_o = open_p.iloc[i]
    c_r = rsi.iloc[i]
    p_r = rsi.iloc[i-1]
    ts = df["timestamp"].iloc[i]
    
    if in_pos:
        pt = pos["type"]
        ep = pos["entry"]
        sl = pos["sl"]
        tp = pos["tp"]
        be = pos["be"]
        exit_p = None
        reason = ""
        
        if pt == "LONG":
            if not be and c_h >= ep * (1.0 + be_pct):
                pos["be"] = True
                pos["sl"] = ep * 1.002
                sl = pos["sl"]
            if c_h >= tp:
                exit_p = tp
                reason = "TAKE_PROFIT"
                ret = (tp - ep) / ep
            elif c_l <= sl:
                exit_p = sl
                reason = "BREAKEVEN" if be else "STOP_LOSS"
                ret = (sl - ep) / ep
        else:
            if not be and c_l <= ep * (1.0 - be_pct):
                pos["be"] = True
                pos["sl"] = ep * 0.998
                sl = pos["sl"]
            if c_l <= tp:
                exit_p = tp
                reason = "TAKE_PROFIT"
                ret = (ep - tp) / ep
            elif c_h >= sl:
                exit_p = sl
                reason = "BREAKEVEN" if be else "STOP_LOSS"
                ret = (ep - sl) / ep
                
        if exit_p:
            notional = min(18.0, cap * 0.85) * leverage
            fees = notional * 0.001
            net_pnl = (notional * ret) - fees
            cap += net_pnl
            trades.append({
                "time": ts,
                "type": pt,
                "entry": ep,
                "exit": exit_p,
                "reason": reason,
                "pnl": net_pnl,
                "cap": cap
            })
            in_pos = False
            pos = {}
            
    if not in_pos and cap > 10.0:
        # Long: 1H Trend Uptrend (EMA 20 > EMA 50, price > EMA 50), Pullback RSI <= 45 bounced up
        if ema_20.iloc[i] > ema_50.iloc[i] and c_p > ema_50.iloc[i] and p_r <= 45 and c_r > p_r and c_p > c_o:
            in_pos = True
            pos = {"type": "LONG", "entry": c_p, "sl": c_p * (1.0 - sl_pct), "tp": c_p * (1.0 + tp_pct), "be": False}
        # Short: 1H Trend Downtrend (EMA 20 < EMA 50, price < EMA 50), Bounce RSI >= 55 turned down
        elif ema_20.iloc[i] < ema_50.iloc[i] and c_p < ema_50.iloc[i] and p_r >= 55 and c_r < p_r and c_p < c_o:
            in_pos = True
            pos = {"type": "SHORT", "entry": c_p, "sl": c_p * (1.0 + sl_pct), "tp": c_p * (1.0 - tp_pct), "be": False}

total = len(trades)
wins = len([t for t in trades if t["pnl"] > 0])
losses = total - wins
wr = (wins / total * 100) if total else 0
ret_pct = ((cap - initial) / initial) * 100

summary = (
    f"[bold]Capital Inicial:[/bold] ${initial:.2f} USDT\n"
    f"[bold]Capital Final (1H):[/bold] [bold green]${cap:.2f} USDT[/bold green]\n"
    f"[bold]Rendimiento Neto:[/bold] [bold green]{ret_pct:+.2f}%[/bold green]\n"
    f"[bold]Total Trades:[/bold] {total} ([green]{wins} Ganadores[/green] / [red]{losses} Perdedores[/red])\n"
    f"[bold]Win Rate:[/bold] {wr:.1f}%\n"
    f"[bold]Apalancamiento:[/bold] 5x Margen Aislado\n"
    f"[bold]Ratio Riesgo/Beneficio:[/bold] 1:2.5 (Arriesga 1.8% para ganar 4.5%)"
)
console.print(Panel(summary, title="[bold green]Resultados Backtest 1H (Velas de 1 Hora)[/bold green]", border_style="green"))

table = Table(title="Detalle de Trades en 1H")
table.add_column("Fecha", style="dim")
table.add_column("Tipo")
table.add_column("Entrada")
table.add_column("Salida")
table.add_column("Motivo")
table.add_column("PnL ($)")
table.add_column("Saldo ($)")

for t in trades:
    p_style = "green" if t["pnl"] > 0 else "red"
    t_style = "cyan" if t["type"] == "LONG" else "magenta"
    table.add_row(
        t["time"].strftime("%m-%d %H:%M"),
        f"[{t_style}]{t['type']}[/{t_style}]",
        f"${t['entry']:.2f}",
        f"${t['exit']:.2f}",
        t["reason"],
        f"[{p_style}]${t['pnl']:+.2f}[/{p_style}]",
        f"${t['cap']:.2f}"
    )
console.print(table)
