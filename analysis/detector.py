"""
Detección de señales y patrones técnicos en datos de acciones.
"""
import pandas as pd
import numpy as np
from utils.logger import logger
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi
from market.data import get_stock_data
from database.operations import save_historical_data, save_alert_to_db
from .market_type import detect_market_type
from notifications.formatter import generate_flexible_alert_message

def detect_signal_sequence(df, max_window=5):
    """
    Detecta la secuencia apropiada de señales técnicas en una ventana de tiempo flexible.
    Primero busca ruptura de Bollinger y RSI bajo (en cualquier orden pero cerca),
    y luego MACD acercándose a su línea de señal.
    
    Args:
        df: DataFrame con indicadores calculados
        max_window: Número máximo de velas a considerar para la secuencia completa
        
    Returns:
        (bool, dict): Tupla con (secuencia_detectada, información_detallada)
    """
    if df.empty or len(df) < 10:  # Necesitamos suficientes datos para analizar secuencias
        return False, {"mensaje": "Datos insuficientes para analizar secuencia"}
    
    # Analizaremos las últimas 'max_window + 3' velas para tener margen
    # (+3 porque podemos necesitar verificar condiciones que dependen de velas anteriores)
    periods_to_check = min(max_window + 3, len(df) - 2)
    last_candles = df.iloc[-periods_to_check:]
    
    # Variables para detectar eventos
    bollinger_event = None  # Índice donde Bollinger rompe
    low_rsi_event = None    # Índice donde RSI está por debajo de 20
    macd_event = None       # Índice donde MACD comienza a acercarse
    
    # 1. Detectar ruptura de Bollinger (la más reciente)
    for i in range(1, periods_to_check):
        index = -i
        
        # Comprobar ruptura de la Banda de Bollinger inferior
        if (not pd.isna(df['Close'].iloc[index]) and 
            not pd.isna(df['BB_INFERIOR'].iloc[index]) and
            df['Close'].iloc[index] < df['BB_INFERIOR'].iloc[index]):
            
            # Confirmar que es una nueva ruptura
            if index > -len(df) and df['Close'].iloc[index-1] >= df['BB_INFERIOR'].iloc[index-1]:
                bollinger_event = index
                break
    
    # 2. Detectar RSI Estocástico por debajo de 20 (el más reciente)
    for i in range(1, periods_to_check):
        index = -i
        
        if not pd.isna(df['RSI_K'].iloc[index]) and df['RSI_K'].iloc[index] < 20:
            low_rsi_event = index
            break
    
    # Si no tenemos ninguno de los dos primeros eventos, no hay secuencia
    if bollinger_event is None or low_rsi_event is None:
        return False, {"mensaje": "No se detectó ruptura de Bollinger o RSI bajo"}
    
    # 3. Comprobar que ambos eventos (Bollinger y RSI) ocurren cerca en el tiempo
    # Calcular la distancia en velas entre los dos eventos
    events_distance = abs(abs(bollinger_event) - abs(low_rsi_event))
    if events_distance > 3:  # Máximo 3 velas (15 minutos) de diferencia
        return False, {"mensaje": "Ruptura de Bollinger y RSI bajo demasiado distantes"}
    
    # 4. Buscar señal MACD después de los eventos de Bollinger/RSI
    # Determinar cuál de los dos eventos ocurrió más recientemente
    last_event_index = min(abs(bollinger_event), abs(low_rsi_event))
    
    # Buscar MACD acercándose a la señal después del último evento
    for i in range(last_event_index, periods_to_check):
        index = -i
        previous_index = index - 1
        
        if (previous_index < -len(df) or 
            pd.isna(df['MACD'].iloc[index]) or 
            pd.isna(df['MACD_SIGNAL'].iloc[index]) or
            pd.isna(df['MACD'].iloc[previous_index]) or
            pd.isna(df['MACD_SIGNAL'].iloc[previous_index])):
            continue
        
        # Calcular distancias y tendencias en MACD
        current_distance = df['MACD_SIGNAL'].iloc[index] - df['MACD'].iloc[index]
        previous_distance = df['MACD_SIGNAL'].iloc[previous_index] - df['MACD'].iloc[previous_index]
        
        # Condiciones para MACD acercándose
        macd_approaching_condition = (df['MACD'].iloc[index] < df['MACD_SIGNAL'].iloc[index] and 
                                     current_distance < previous_distance and
                                     current_distance > 0)
        
        # Pendiente positiva
        macd_slope_condition = df['MACD'].iloc[index] > df['MACD'].iloc[previous_index]
        
        # Histograma mejorando
        histogram_condition = df['MACD_HIST'].iloc[index] > df['MACD_HIST'].iloc[previous_index]
        
        if macd_approaching_condition and macd_slope_condition and histogram_condition:
            macd_event = index
            break
    
    # Si no hay evento MACD o está demasiado lejos, no hay secuencia completa
    if macd_event is None:
        return False, {"mensaje": "No se detectó MACD favorable después de la ruptura"}
    
    # Comprobar que la secuencia completa ocurre dentro de la ventana máxima
    total_window = abs(macd_event) - min(abs(bollinger_event), abs(low_rsi_event))
    if total_window > max_window:
        return False, {"mensaje": f"La secuencia excede la ventana máxima de {max_window} velas"}
    
    # Calcular distancia al cruce
    if current_distance > 0 and previous_distance > current_distance:
        closing_speed = previous_distance - current_distance
        estimated_candles_to_cross = current_distance / closing_speed if closing_speed > 0 else float('inf')
    else:
        estimated_candles_to_cross = float('inf')
    
    # Preparar información detallada sobre la secuencia
    details = {
        "secuencia_ok": True,
        "indice_bollinger": bollinger_event,
        "indice_rsi": low_rsi_event,
        "indice_macd": macd_event,
        "distancia_bollinger_rsi": events_distance,
        "ventana_total": total_window,
        "velas_para_cruce": estimated_candles_to_cross
    }
    
    return True, details

def analyze_stock_flexible(symbol, db_connection=None):
    """
    Analiza una acción usando la detección de secuencia flexible.
    
    Args:
        symbol: Símbolo de la acción a analizar
        db_connection: Conexión a la base de datos (opcional)
        
    Returns:
        (bool, str): Tupla con (alerta_generada, mensaje_alerta)
    """
    try:
        # Obtener datos combinando históricos y nuevos si es posible
        data = get_stock_data(symbol, period='1d', interval='5m', 
                             db_connection=db_connection, 
                             only_new=(db_connection is not None))
        
        if data is None or data.empty or len(data) < 22:
            logger.warning(f"Datos insuficientes para analizar {symbol}")
            return False, f"Datos insuficientes para {symbol}"
        
        # Comprobar si ya tenemos todos los indicadores calculados
        complete_indicators = all(col in data.columns for col in 
                                 ['BB_INFERIOR', 'BB_MEDIA', 'BB_SUPERIOR', 
                                  'MACD', 'MACD_SIGNAL', 'MACD_HIST', 
                                  'RSI', 'RSI_K', 'RSI_D'])
        
        # Si faltan indicadores, calcular todos
        if not complete_indicators:
            data = calculate_bollinger(data, window=18, deviations=2.25)
            data = calculate_macd(data, fast=8, slow=21, signal=9)
            data = calculate_stochastic_rsi(data, rsi_period=14, k_period=14, d_period=3, smooth=3)
        
        # Guardar datos históricos si hay conexión a la BD
        if db_connection:
            save_historical_data(db_connection, symbol, data)
        
        # Detectar secuencia flexible de señales (máximo 5 velas o 25 minutos entre primera y última)
        sequence_detected, details = detect_signal_sequence(data, max_window=5)
        
        if sequence_detected:
            logger.info(f"Secuencia de señal detectada para {symbol}: {details}")
            
            # Usar el índice MACD (la última señal) para generar la alerta
            message = generate_flexible_alert_message(symbol, data, details)
            
            # Guardar alerta en la base de datos si hay conexión
            if db_connection:
                macd_index = details.get("indice_macd", -1)
                save_alert_to_db(db_connection, symbol, data, macd_index, message, "sequence")
            
            return True, message
        else:
            logger.info(f"Secuencia completa no detectada para {symbol}: {details.get('mensaje', '')}")
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error al analizar {symbol}: {e}")
        return False, f"Error al analizar {symbol}: {str(e)}"

def analyze_stock(symbol):
    """
    Analiza una acción para verificar si cumple las condiciones técnicas optimizadas.
    
    Args:
        symbol: Símbolo de la acción a analizar
        
    Returns:
        (bool, str): Tupla con (alerta_generada, mensaje_alerta)
    """
    try:
        # Obtener datos con intervalo de 5 minutos para el último día
        data = get_stock_data(symbol, period='1d', interval='5m')
        
        if data is None or data.empty or len(data) < 22:
            logger.warning(f"Datos insuficientes para analizar {symbol}")
            return False, f"Datos insuficientes para {symbol}"
        
        # Calcular indicadores
        data = calculate_bollinger(data, window=18, deviations=2.25)
        data = calculate_macd(data, fast=8, slow=21, signal=9)
        data = calculate_stochastic_rsi(data, rsi_period=14, k_period=14, d_period=3, smooth=3)
        
        # Paso 1: Detectar ruptura de Banda de Bollinger en los últimos 15 minutos
        from indicators.bollinger import detect_bollinger_breakout
        breakout_detected, breakout_index = detect_bollinger_breakout(data)
        
        if breakout_detected:
            logger.info(f"Ruptura de Bollinger detectada para {symbol} en período {breakout_index}")
            
            # Paso 2: Verificar MACD y RSI en el mismo período que la ruptura
            from indicators.macd import verify_macd_conditions
            macd_conditions_met, macd_details = verify_macd_conditions(data, breakout_index)
            
            from indicators.rsi import check_rsi_conditions
            rsi_conditions_met, rsi_details = check_rsi_conditions(data, breakout_index)
            
            # Combinación de todas las condiciones
            all_conditions_met = macd_conditions_met and rsi_conditions_met
            
            if all_conditions_met:
                # Si se cumplen todas las condiciones, generar alerta con mensaje mejorado
                from notifications.formatter import generate_alert_message
                message = generate_alert_message(symbol, data, breakout_index)
                return True, message
            else:
                logger.info(f"Ruptura de Bollinger detectada para {symbol}, pero otras condiciones no se cumplen")
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error al analizar {symbol}: {e}")
        return False, f"Error al analizar {symbol}: {str(e)}"