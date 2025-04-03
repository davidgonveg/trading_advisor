"""
Utilidades para el módulo Trading212.
"""
import pandas as pd
from utils.logger import logger

def generate_test_alert_message(symbol, data, details):
    """
    Genera un mensaje de alerta de prueba para uso en el módulo Trading212.
    Esta versión es independiente para evitar importaciones circulares.
    
    Args:
        symbol: Símbolo de la acción
        data: DataFrame con datos e indicadores
        details: Diccionario con detalles de la secuencia detectada
        
    Returns:
        str: Mensaje formateado para la alerta
    """
    # Versión simplificada para pruebas
    message = f"🔔 ALERTA TÉCNICA: {symbol}\n\n"
    
    # Añadir detalles básicos de la secuencia
    bollinger_index = details.get("indice_bollinger", -1)
    rsi_index = details.get("indice_rsi", -1)
    macd_index = details.get("indice_macd", -1)
    
    if bollinger_index:
        try:
            bollinger_time = data.index[bollinger_index]
            bollinger_price = data['Close'].iloc[bollinger_index]
            bb_inferior = data['BB_INFERIOR'].iloc[bollinger_index]
            message += f"• Ruptura de Bollinger: Precio ({bollinger_price:.2f}) < BB Inferior ({bb_inferior:.2f})\n"
        except:
            message += f"• Ruptura de Bollinger detectada\n"
    
    if rsi_index:
        try:
            rsi_time = data.index[rsi_index]
            rsi_k = data['RSI_K'].iloc[rsi_index]
            message += f"• RSI Estocástico: RSI-K ({rsi_k:.2f}) por debajo de 20\n"
        except:
            message += f"• RSI Estocástico bajo detectado\n"
    
    if macd_index:
        try:
            macd_time = data.index[macd_index]
            macd = data['MACD'].iloc[macd_index]
            macd_signal = data['MACD_SIGNAL'].iloc[macd_index]
            message += f"• MACD: MACD ({macd:.4f}) acercándose a Señal ({macd_signal:.4f})\n"
        except:
            message += f"• MACD acercándose a su línea de señal\n"
    
    # Precio actual
    current_price = data['Close'].iloc[-1]
    message += f"\nPrecio actual: ${current_price:.2f}"
    
    # Stop loss sugerido (1%)
    stop_loss = current_price * 0.99
    message += f"\nStop loss sugerido: ${stop_loss:.2f} (-1.0%)"
    
    return message