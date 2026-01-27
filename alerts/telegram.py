
import logging
import requests
import os
from typing import Optional
from config.settings import SYSTEM_CONFIG, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from core.utils import retry

logger = logging.getLogger("core.alerts.telegram")

class TelegramBot:
    """
    Simple Telegram Bot wrapper for sending notifications.
    """
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram credentials not found. Notifications disabled.")
            
    @retry(Exception, tries=3, delay=2, backoff=2)
    def send_message(self, message: str) -> bool:
        """
        Send a text message to the configured chat.
        """
        if not self.enabled:
            logger.debug("Telegram disabled, skipping message.")
            return False
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram message sent successfully.")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error triggering Telegram API: {e}")
            return False

    def send_signal_alert(self, signal, plan):
        """
        Formats a Signal/Plan into the VWAP Bounce Strategy format.
        """
        if not self.enabled:
            return

        icon = "🟢" if "LONG" in signal.type.value else "🔴"
        direction = signal.type.value
        symbol = signal.symbol
        price = signal.price
        
        # Extract Logic Metadata
        vwap = signal.metadata.get('vwap', 0)
        vol = signal.metadata.get('vol', 0)
        vol_sma = signal.metadata.get('vol_sma', 0)
        
        # Build Message
        msg = f"{icon} *{direction} - {symbol} (1H)*\n\n"
        msg += "📊 *SETUP: VWAP BOUNCE*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"- Precio: ${price:.2f}\n"
        msg += f"- VWAP: ${vwap:.2f} {'✓'}\n"
        msg += f"- Vol: {int(vol)} > Avg ({int(vol_sma)}) {'✓'}\n\n"
        
        if plan:
            msg += "📥 *EJECUCIÓN:*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
            for order in plan.entry_orders:
                msg += f"• {order.tag}: {order.quantity} uds @ {order.price:.2f} ({order.type})\n"
            
            msg += f"\n🛑 *STOP LOSS*: ${plan.stop_loss_price:.2f} (0.4%)\n\n"
            
            msg += "✅ *TAKE PROFIT:*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
            if plan.take_profits:
                for tp in plan.take_profits:
                    pct = 0.8 if tp.tag == "TP1" else 1.2
                    weight = "60%" if tp.tag == "TP1" else "40%"
                    msg += f"• {tp.tag} ({weight}): ${tp.price:.2f} (+{pct}%)\n"
        
        msg += f"\n💰 Riesgo Total: ${plan.risk_amount:.2f}\n"
        
        if plan.warnings:
            msg += "\n⚠️ *ADVERTENCIAS:*\n"
            for warn in plan.warnings:
                msg += f"• {warn}\n"
                
        msg += "⏱️ Time Stop: Cierre de Sesión / 8H"
        
        self.send_message(msg)
    def send_exit_notification(self, symbol: str, outcome: str, pnl_r: float, exit_price: float):
        """
        Sends a notification when a position is closed.
        """
        if not self.enabled:
            return

        icon = "🏁"
        if outcome == "SL": icon = "❌"
        elif outcome == "TP1": icon = "✅"
        elif outcome == "EARLY_EXIT": icon = "⚠️"
        elif outcome == "TIME_STOP": icon = "⏱️"

        msg = f"{icon} *POSICIÓN CERRADA - {symbol}*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"- Resultado: *{outcome}*\n"
        msg += f"- Precio de Salida: ${exit_price:.2f}\n"
        msg += f"- PnL (R): *{pnl_r:+.2f}R*\n\n"
        
        if outcome == "EARLY_EXIT":
            msg += "_Salida temprana por empeoramiento de condiciones._"
            
        self.send_message(msg)
