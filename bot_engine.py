"""
Main Execution Engine for SOL/USDT 5x Futures Trading Bot (Champion Strategy).
Supports both Paper Trading (live simulation) and Live Binance API trading.
Strategy: 24h Donchian Breakout + EMA 200 Macro Filter + ATR Dynamic Trailing Stop.
Includes:
- Telegram Notifications (Real-time smartphone alerts)
- Lightweight HTTP Health-Check Server (For Render / Railway / PaaS 24/7 hosting)
"""
import os
import time
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from typing import Optional, Dict, Any

import ccxt
from rich.console import Console

import config
from market_data import MarketData
from strategy import TradingStrategy
from notifications import TelegramNotifier

# Logging configuration (Output to both bot.log and stdout for Railway live logs)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
console = Console()

STATE_FILE = "portfolio_state.json"

class HealthHandler(BaseHTTPRequestHandler):
    bot_instance = None
    
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        
        state_data = {
            "status": "online",
            "bot": "SOL/USDT Champion Trading Bot (5x Futures)",
            "mode": self.bot_instance.mode if self.bot_instance else "UNKNOWN",
            "capital_usdt": round(self.bot_instance.state.get("current_capital", 0.0), 2) if self.bot_instance else 0.0,
            "in_position": self.bot_instance.state.get("in_position", False) if self.bot_instance else False,
            "position": self.bot_instance.state.get("position") if self.bot_instance else None,
            "total_trades": self.bot_instance.state.get("total_trades", 0) if self.bot_instance else 0,
            "winning_trades": self.bot_instance.state.get("winning_trades", 0) if self.bot_instance else 0,
            "losing_trades": self.bot_instance.state.get("losing_trades", 0) if self.bot_instance else 0,
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(state_data, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        pass # Silence HTTP console noise

def start_health_server(bot, port: int):
    try:
        HealthHandler.bot_instance = bot
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logging.info(f"Health-check HTTP server listening on port {port}")
    except Exception as e:
        logging.warning(f"Could not bind HTTP health server on port {port}: {e}")


class BotEngine:
    def __init__(self, mode: str = "PAPER"):
        self.mode = mode.upper()
        self.symbol = config.SYMBOL
        self.futures_symbol = config.FUTURES_SYMBOL
        self.leverage = config.LEVERAGE
        self.market_data = MarketData(self.futures_symbol)
        self.strategy = TradingStrategy()
        self.notifier = TelegramNotifier()
        
        # Load or initialize state
        self.state = self.load_state()
        self.save_state()
        
        # Live exchange client
        self.exchange = None
        if self.mode == "LIVE":
            self.init_live_exchange()

        # Start health check server for PaaS hosting (Render / Railway)
        port = int(os.getenv("PORT", 8080))
        start_health_server(self, port)

        # Notify Telegram on start
        try:
            df_1h = self.market_data.fetch_candles("1h", limit=30)
            sig = self.strategy.evaluate_signal(df_1h) if len(df_1h) > 25 else {}
            h_ch = sig.get("high_ch", 0.0)
            l_ch = sig.get("low_ch", 0.0)
            self.notifier.notify_bot_started(self.state["current_capital"], self.mode, h_ch, l_ch)
        except Exception as e:
            logging.warning(f"Note on initial telegram notify: {e}")

    def load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "initial_capital": config.INITIAL_CAPITAL,
            "current_capital": config.INITIAL_CAPITAL,
            "in_position": False,
            "position": None,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "history": []
        }

    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def init_live_exchange(self):
        """Initialize CCXT Binance Futures client with API keys."""
        if not config.BINANCE_API_KEY or not config.BINANCE_API_SECRET:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env for LIVE mode.")
        
        self.exchange = ccxt.binanceusdm({
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True
            }
        })
        
        if config.USE_TESTNET:
            self.exchange.set_sandbox_mode(True)

        try:
            self.exchange.set_leverage(self.leverage, self.symbol)
            self.exchange.set_margin_mode(config.MARGIN_MODE, self.symbol)
            console.print(f"[green]Binance Futures inicializado: {self.symbol} a {self.leverage}x ({config.MARGIN_MODE})[/green]")
        except Exception as e:
            logging.warning(f"Note setting leverage/margin mode: {e}")

    def get_live_balance(self) -> float:
        if self.mode == "PAPER":
            return self.state["current_capital"]
        try:
            balance = self.exchange.fetch_balance()
            return float(balance["USDT"]["free"])
        except Exception as e:
            logging.error(f"Error fetching live balance: {e}")
            return self.state["current_capital"]

    def execute_trade(self, signal: dict, current_price: float):
        """Open a position based on Champion Breakout signal."""
        sig_type = signal["signal"]
        balance = self.get_live_balance()
        
        if balance < 10.0:
            console.print(f"[bold red]Saldo insuficiente (${balance:.2f} USDT) para abrir posición.[/bold red]")
            return

        margin = min(config.MAX_MARGIN_PER_TRADE, balance * 0.85)
        notional = margin * self.leverage
        qty_sol = round(notional / current_price, 2)
        if qty_sol <= 0.01:
            qty_sol = 0.02

        sl_price = signal["stop_loss"]
        atr = signal.get("atr", 1.5)

        console.print(f"[bold yellow]¡DISPARO DE ORDEN {sig_type} en {self.symbol}![/bold yellow]")
        console.print(f"  Precio Entrada: ${current_price:.2f} | Cantidad: {qty_sol} SOL (~${notional:.2f} notional)")
        console.print(f"  Margen asignado: ${margin:.2f} USDT | Stop Inicial: ${sl_price:.2f} | ATR: ${atr:.2f}")

        if self.mode == "LIVE":
            try:
                side = "buy" if sig_type == "LONG" else "sell"
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type="market",
                    side=side,
                    amount=qty_sol
                )
                logging.info(f"Live order executed: {order['id']}")
            except Exception as e:
                console.print(f"[bold red]Error enviando orden a Binance: {e}[/bold red]")
                logging.error(f"Order error: {e}")
                return

        self.state["in_position"] = True
        self.state["position"] = {
            "type": sig_type,
            "entry_price": current_price,
            "stop_loss": sl_price,
            "atr": atr,
            "margin": margin,
            "quantity": qty_sol,
            "open_time": datetime.now().isoformat()
        }
        self.save_state()

        # Send Telegram alert
        self.notifier.notify_trade_opened(sig_type, current_price, qty_sol, sl_price, margin)

    def check_position_exit(self, current_price: float, atr: float):
        """Dynamic ATR Trailing Stop management."""
        if not self.state["in_position"] or not self.state["position"]:
            return

        pos = self.state["position"]
        pos_type = pos["type"]
        entry_p = pos["entry_price"]
        sl_p = pos["stop_loss"]
        margin = pos["margin"]
        notional = margin * self.leverage

        exit_trade = False
        exit_price = None

        if pos_type == "LONG":
            new_sl = current_price - (config.ATR_TRAIL * atr)
            if new_sl > sl_p:
                pos["stop_loss"] = new_sl
                sl_p = new_sl
                logging.info(f"Trailing Stop subió a ${sl_p:.2f} (Precio: ${current_price:.2f})")
                self.notifier.notify_trailing_update(sl_p, current_price, pos_type)

            if current_price <= sl_p:
                exit_trade = True
                exit_price = sl_p
                price_ret = (sl_p - entry_p) / entry_p

        elif pos_type == "SHORT":
            new_sl = current_price + (config.ATR_TRAIL * atr)
            if new_sl < sl_p:
                pos["stop_loss"] = new_sl
                sl_p = new_sl
                logging.info(f"Trailing Stop bajó a ${sl_p:.2f} (Precio: ${current_price:.2f})")
                self.notifier.notify_trailing_update(sl_p, current_price, pos_type)

            if current_price >= sl_p:
                exit_trade = True
                exit_price = sl_p
                price_ret = (entry_p - sl_p) / entry_p

        if exit_trade:
            fees = notional * (config.TAKER_FEE * 2)
            net_pnl = (notional * price_ret) - fees

            if self.mode == "LIVE":
                try:
                    close_side = "sell" if pos_type == "LONG" else "buy"
                    self.exchange.create_order(
                        symbol=self.symbol,
                        type="market",
                        side=close_side,
                        amount=pos["quantity"],
                        params={"reduceOnly": True}
                    )
                except Exception as e:
                    logging.error(f"Error closing live position: {e}")

            self.state["current_capital"] += net_pnl
            self.state["total_trades"] += 1
            if net_pnl > 0:
                self.state["winning_trades"] += 1
            else:
                self.state["losing_trades"] += 1

            style = "green" if net_pnl > 0 else "red"
            console.print(f"[bold {style}]Posición {pos_type} cerrada por Trailing Stop: PnL ${net_pnl:+.2f} USDT | Saldo: ${self.state['current_capital']:.2f}[/bold {style}]")

            self.state["history"].append({
                "type": pos_type,
                "entry": entry_p,
                "exit": exit_price,
                "reason": "TRAILING_STOP",
                "pnl": round(net_pnl, 2),
                "closed_at": datetime.now().isoformat()
            })
            self.state["in_position"] = False
            self.state["position"] = None
            self.save_state()

            # Send Telegram alert
            self.notifier.notify_trade_closed(pos_type, exit_price, net_pnl, self.state["current_capital"])

    def run_step(self):
        """Single evaluation step of the Champion Bot."""
        curr_price = self.market_data.get_current_price()
        df_1h = self.market_data.fetch_candles("1h", limit=250)
        signal = self.strategy.evaluate_signal(df_1h)
        atr = signal.get("atr", 1.5)
        
        # If in position, manage trailing stop exit
        if self.state["in_position"]:
            pos = self.state["position"]
            logging.info(f"Posición activa {pos['type']} | Entrada: ${pos['entry_price']:.2f} | Actual: ${curr_price:.2f} | Trailing SL: ${pos['stop_loss']:.2f}")
            self.check_position_exit(curr_price, atr)
            return

        # If not in position, check for 24h channel breakout
        if signal["signal"] in ("LONG", "SHORT"):
            logging.info(f"SEÑAL CAMPEONA DETECTADA: {signal['signal']} @ ${curr_price:.2f} | Razón: {signal['reason']}")
            self.execute_trade(signal, curr_price)
        else:
            logging.info(f"Monitoreo 24h: SOL=${curr_price:.2f} | Techo 24h: ${signal.get('high_ch')} | Suelo 24h: ${signal.get('low_ch')} | Macro EMA200: ${signal.get('ema_200')} | Estado: {signal.get('reason')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SOL/USDT Champion Trading Bot")
    parser.add_argument("--mode", choices=["PAPER", "LIVE"], default="PAPER", help="Modo de ejecución")
    parser.add_argument("--step", action="store_true", help="Ejecutar un solo paso")
    args = parser.parse_args()

    bot = BotEngine(mode=args.mode)
    if args.step:
        bot.run_step()
    else:
        console.print(f"[bold green]Iniciando Bot de Trading Campeón en modo {args.mode}... (Presiona Ctrl+C para detener)[/bold green]")
        while True:
            try:
                bot.run_step()
                time.sleep(10)
            except KeyboardInterrupt:
                console.print("\n[yellow]Bot detenido por el usuario.[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error en ciclo del bot: {e}[/red]")
                time.sleep(10)
