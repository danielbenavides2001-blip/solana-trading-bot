"""
Telegram Notifications Handler for SOL/USDT Trading Bot.
Sends instant alerts to the user's smartphone on trades, trailing stops, and daily summaries.
"""
import os
import requests
import logging

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

class TelegramNotifier:
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            resp = requests.post(url, json=payload, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logging.error(f"Error sending Telegram notification: {e}")
            return False

    def notify_bot_started(self, capital: float, mode: str, high_ch: float, low_ch: float):
        msg = (
            f"🤖 *BOT SOL/USDT 24/7 EN LÍNEA*\n\n"
            f"💼 *Modo:* `{mode}`\n"
            f"💰 *Capital:* `${capital:.2f} USDT`\n"
            f"⚡ *Apalancamiento:* `5x Aislado`\n"
            f"📊 *Estrategia:* `Donchian 24h + EMA 200 + Trailing ATR`\n\n"
            f"🎯 *Niveles Clave 24h:*\n"
            f"• Techo Long: `${high_ch:.2f}`\n"
            f"• Suelo Short: `${low_ch:.2f}`\n\n"
            f"🚀 _El bot está escaneando el mercado cada 10 segundos._"
        )
        self.send_message(msg)

    def notify_trade_opened(self, trade_type: str, price: float, qty: float, sl: float, margin: float):
        icon = "🟢" if trade_type == "LONG" else "🔴"
        msg = (
            f"{icon} *NUEVA OPERACIÓN APERTURADA*\n\n"
            f"📈 *Posición:* `{trade_type} (5x)`\n"
            f"💵 *Precio Entrada:* `${price:.2f}`\n"
            f"📦 *Cantidad:* `{qty} SOL`\n"
            f"🛡️ *Stop Loss Inicial:* `${sl:.2f}`\n"
            f"💼 *Margen:* `${margin:.2f} USDT`\n\n"
            f"⚙️ _Trailing Stop dinámico activado._"
        )
        self.send_message(msg)

    def notify_trailing_update(self, new_sl: float, current_price: float, trade_type: str):
        msg = (
            f"🛡️ *TRAILING STOP ACTUALIZADO*\n\n"
            f"📈 *Posición:* `{trade_type}`\n"
            f"💵 *Precio Actual:* `${current_price:.2f}`\n"
            f"🔒 *Nuevo Stop Loss:* `${new_sl:.2f}`\n\n"
            f"✅ _Beneficio protegido con volatilidad ATR._"
        )
        self.send_message(msg)

    def notify_trade_closed(self, trade_type: str, exit_price: float, pnl: float, new_capital: float):
        icon = "🎉" if pnl >= 0 else "🛑"
        sign = "+" if pnl >= 0 else ""
        msg = (
            f"{icon} *POSICIÓN CERRADA*\n\n"
            f"📊 *Tipo:* `{trade_type}`\n"
            f"💵 *Precio Salida:* `${exit_price:.2f}`\n"
            f"💰 *Resultado:* `{sign}${pnl:.2f} USDT`\n"
            f"💼 *Nuevo Saldo Total:* `${new_capital:.2f} USDT`\n\n"
            f"🔍 _Buscando nueva oportunidad en el mercado._"
        )
        self.send_message(msg)
