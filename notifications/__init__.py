"""
Paquete para funciones de notificación y alertas.
"""
from .telegram import send_telegram_alert, send_telegram_test, sanitize_html_message
from .formatter import generate_alert_message, generate_flexible_alert_message