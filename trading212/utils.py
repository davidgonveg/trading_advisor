"""
Utilidades mejoradas para el módulo Trading212.
"""
import time
import pandas as pd
import random
from utils.logger import logger

def format_currency(amount, decimals=2):
    """
    Formatea un valor monetario con el número especificado de decimales.
    
    Args:
        amount: Cantidad monetaria
        decimals: Número de decimales (por defecto: 2)
        
    Returns:
        str: Valor formateado con símbolo de dólar
    """
    try:
        return f"${float(amount):.{decimals}f}"
    except (ValueError, TypeError):
        return f"${0:.{decimals}f}"

def generate_test_alert_message(symbol, data, details):
    """
    Genera un mensaje de alerta de prueba para uso en el módulo Trading212.
    Esta versión es robusta ante datos faltantes o mal formateados.
    
    Args:
        symbol: Símbolo de la acción
        data: DataFrame con datos e indicadores
        details: Diccionario con detalles de la secuencia detectada
        
    Returns:
        str: Mensaje formateado para la alerta
    """
    # Versión robusta para pruebas
    message = f"🔔 ALERTA TÉCNICA: {symbol}\n\n"
    
    # Añadir detalles básicos de la secuencia
    bollinger_index = details.get("indice_bollinger", -1)
    rsi_index = details.get("indice_rsi", -1)
    macd_index = details.get("indice_macd", -1)
    
    # Obtener precio actual de manera segura
    try:
        current_price = float(data['Close'].iloc[-1])
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        current_price = 100.0  # Valor predeterminado para pruebas
    
    # Detalles de Bollinger
    if bollinger_index:
        try:
            bollinger_time = data.index[bollinger_index] if hasattr(data, 'index') else "N/A"
            bollinger_price = safe_get_value(data, 'Close', bollinger_index)
            bb_inferior = safe_get_value(data, 'BB_INFERIOR', bollinger_index)
            message += f"• Ruptura de Bollinger: Precio ({bollinger_price:.2f}) < BB Inferior ({bb_inferior:.2f})\n"
        except Exception as e:
            message += f"• Ruptura de Bollinger detectada\n"
    
    # Detalles de RSI
    if rsi_index:
        try:
            rsi_time = data.index[rsi_index] if hasattr(data, 'index') else "N/A"
            rsi_k = safe_get_value(data, 'RSI_K', rsi_index)
            message += f"• RSI Estocástico: RSI-K ({rsi_k:.2f}) por debajo de 20\n"
        except Exception as e:
            message += f"• RSI Estocástico bajo detectado\n"
    
    # Detalles de MACD
    if macd_index:
        try:
            macd_time = data.index[macd_index] if hasattr(data, 'index') else "N/A"
            macd = safe_get_value(data, 'MACD', macd_index)
            macd_signal = safe_get_value(data, 'MACD_SIGNAL', macd_index)
            message += f"• MACD: MACD ({macd:.4f}) acercándose a Señal ({macd_signal:.4f})\n"
        except Exception as e:
            message += f"• MACD acercándose a su línea de señal\n"
    
    # Datos de trading
    message += f"\nPrecio actual: ${current_price:.2f}"
    
    # Stop loss y tomas de ganancia
    stop_loss = current_price * 0.99
    take_profit1 = current_price * 1.01
    take_profit2 = current_price * 1.02
    
    message += f"\nStop loss sugerido: ${stop_loss:.2f} (-1.0%)"
    message += f"\nToma de ganancias 1: ${take_profit1:.2f} (+1.0%)"
    message += f"\nToma de ganancias 2: ${take_profit2:.2f} (+2.0%)"
    
    # Fortaleza de la señal
    rsi_strength = "FUERTE" if is_strong_signal(data) else "MODERADA"
    message += f"\n\n<b>Fortaleza de la señal:</b> {rsi_strength}"
    
    return message

def safe_get_value(df, column, index, default=0.0):
    """
    Obtiene un valor de un DataFrame de manera segura.
    
    Args:
        df: DataFrame
        column: Nombre de la columna
        index: Índice
        default: Valor por defecto
        
    Returns:
        float: Valor en la posición especificada o valor por defecto
    """
    try:
        return float(df[column].iloc[index])
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        return default

def is_strong_signal(data):
    """
    Determina si la señal es fuerte basándose en indicadores múltiples.
    
    Args:
        data: DataFrame con datos e indicadores
        
    Returns:
        bool: True si la señal es fuerte
    """
    try:
        # Verificar si RSI_K está por debajo de 10
        if 'RSI_K' in data.columns and data['RSI_K'].iloc[-1] < 10:
            return True
        
        # Verificar si el precio está muy por debajo de la banda inferior
        if ('Close' in data.columns and 'BB_INFERIOR' in data.columns and
            (data['BB_INFERIOR'].iloc[-1] - data['Close'].iloc[-1]) / data['Close'].iloc[-1] > 0.02):
            return True
        
        # Verificar divergencia MACD pronunciada
        if ('MACD' in data.columns and 'MACD_SIGNAL' in data.columns and
            (data['MACD_SIGNAL'].iloc[-1] - data['MACD'].iloc[-1]) > 0.1):
            return True
        
        return False
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        # En caso de error, retornar un valor aleatorio para propósitos de prueba
        return random.choice([True, False])

def wait_for_rate_limit(last_call_time, endpoint_limit=1.0, 
                        base_wait_time=1.0, max_jitter=0.5):
    """
    Espera de manera inteligente para respetar los límites de tasa.
    
    Args:
        last_call_time: Tiempo de la última llamada
        endpoint_limit: Límite específico para el endpoint (segundos)
        base_wait_time: Tiempo base de espera
        max_jitter: Máximo tiempo aleatorio añadido
        
    Returns:
        float: Tiempo actual después de la espera
    """
    current_time = time.time()
    elapsed = current_time - last_call_time
    
    if elapsed < endpoint_limit:
        wait_time = endpoint_limit - elapsed
        # Añadir jitter aleatorio para evitar sincronización
        wait_time += random.uniform(0, max_jitter)
        logger.debug(f"Esperando {wait_time:.2f} segundos para respetar límites de tasa...")
        time.sleep(wait_time)
        
    return time.time()

def parse_ticker(ticker):
    """
    Analiza un ticker y extrae componentes importantes.
    
    Args:
        ticker: Ticker en formato Trading212 (ej: AAPL_US_EQ)
        
    Returns:
        dict: Componentes del ticker
    """
    parts = ticker.split('_')
    
    result = {
        'symbol': parts[0],
        'region': parts[1] if len(parts) > 1 else None,
        'type': parts[2] if len(parts) > 2 else None,
        'original': ticker
    }
    
    return result

def get_yfinance_symbol(ticker):
    """
    Convierte un ticker de Trading212 a símbolo de YFinance.
    
    Args:
        ticker: Ticker en formato Trading212
        
    Returns:
        str: Símbolo en formato YFinance
    """
    from .config import REVERSE_TICKER_MAPPING
    
    # Si está en el mapeo inverso, usar directamente
    if ticker in REVERSE_TICKER_MAPPING:
        return REVERSE_TICKER_MAPPING[ticker]
    
    # Si no, extraer el símbolo base
    components = parse_ticker(ticker)
    return components['symbol']