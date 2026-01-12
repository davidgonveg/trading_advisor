
import logging
import requests
import os
from typing import Optional
from config.settings import SYSTEM_CONFIG, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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
        Formats a Signal/Plan into the Strategy's specific markdown format.
        """
        if not self.enabled:
            return

        icon = "🟢" if "LONG" in signal.type.value else "🔴"
        direction = signal.type.value
        symbol = signal.symbol
        price = signal.price
        
        # Extract Logic Metadata
        rsi = signal.metadata.get('rsi', 0)
        adx = signal.metadata.get('adx', 0)
        vwap = signal.metadata.get('vwap', 0)
        sma = signal.metadata.get('sma_50', 0)
        
        # Build Message
        msg = f"{icon} *{direction} - {symbol} (1H)*\n\n"
        msg += "📊 *SETUP: Mean Reversion*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"- RSI(14): {rsi:.1f} {'✓' if (rsi<35 or rsi>65) else ''}\n"
        msg += f"- Precio: ${price:.2f}\n"
        msg += f"- VWAP: ${vwap:.2f}\n"
        msg += f"- ADX: {adx:.1f}\n"
        msg += f"- SMA(50): ${sma:.2f}\n\n"
        
        if plan:
            msg += "📥 *ENTRADA ESCALONADA:*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
            for order in plan.entry_orders:
                msg += f"• {order.tag}: {order.quantity} uds @ {order.price if order.price else 'MKT'}\n"
            
            msg += f"\n🛑 *STOP LOSS*: ${plan.stop_loss_price:.2f}\n\n"
            
            msg += "✅ *TAKE PROFIT:*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
            if plan.take_profits:
                msg += f"• TP1: ${plan.take_profits[0].price:.2f}\n"
                msg += f"• TP2: ${plan.take_profits[1].price:.2f}\n"
                msg += f"• TP3: ${plan.take_profits[2].price:.2f}\n"
        
        msg += f"\n💰 Riesgo: ${plan.risk_amount:.2f} (1.5%)\n"
        msg += "⏱️ Time Stop: 48h"
        
        self.send_message(msg)
