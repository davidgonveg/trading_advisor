import pandas as pd

"""
Cálculo del indicador MACD (Moving Average Convergence Divergence).
"""
from utils.logger import logger

def calculate_macd(df, fast=8, slow=21, signal=9, column='Close'):
    """
    Calcula el MACD para un DataFrame.
    
    Args:
        df: DataFrame con datos de precios
        fast: Período para la media móvil rápida
        slow: Período para la media móvil lenta
        signal: Período para la línea de señal
        column: Columna de precio a utilizar
        
    Returns:
        DataFrame con columnas 'MACD', 'MACD_SIGNAL' y 'MACD_HIST'
    """
    if len(df) < max(fast, slow, signal):
        logger.warning(f"Datos insuficientes para calcular MACD")
        return df
    
    # Calcular EMAs (Exponential Moving Averages)
    df['EMA_RAPIDA'] = df[column].ewm(span=fast, adjust=False).mean()
    df['EMA_LENTA'] = df[column].ewm(span=slow, adjust=False).mean()
    
    # Calcular línea MACD
    df['MACD'] = df['EMA_RAPIDA'] - df['EMA_LENTA']
    
    # Calcular línea de señal (EMA del MACD)
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    
    # Calcular histograma
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']
    
    return df

def verify_macd_conditions(df, index):
    """
    Verifica si se cumplen condiciones específicas del MACD.
    Optimizado para alertar ANTES de que el MACD cruce hacia arriba.
    
    Args:
        df: DataFrame con indicadores calculados
        index: Índice a verificar (-1 para la última fila)
        
    Returns:
        (bool, str): Tupla con (condiciones_cumplidas, mensaje_detalle)
    """
    if df.empty or abs(index) > len(df):
        return False, "Datos insuficientes para analizar"
    
    # Obtener la fila de datos en el índice especificado
    row = df.iloc[index]
    previous_row = df.iloc[index-1] if abs(index) < len(df) else None
    
    # Verificar si hay valores NaN en los indicadores que necesitamos
    required_indicators = ['MACD', 'MACD_SIGNAL', 'MACD_HIST']
    if any(pd.isna(row[ind]) for ind in required_indicators):
        return False, "Datos incompletos para análisis"
    
    # Condición MACD: Por debajo de la señal pero acercándose
    # Verificar si el MACD se está acercando a la línea de señal
    if previous_row is not None and not pd.isna(previous_row['MACD']) and not pd.isna(previous_row['MACD_SIGNAL']):
        # Calcular distancia actual y anterior entre MACD y Señal
        current_distance = row['MACD_SIGNAL'] - row['MACD']
        previous_distance = previous_row['MACD_SIGNAL'] - previous_row['MACD']
        
        # MACD está por debajo de la señal pero acercándose (la distancia disminuye)
        macd_approaching_condition = (row['MACD'] < row['MACD_SIGNAL'] and 
                                     current_distance < previous_distance and
                                     current_distance > 0)
        
        # Adicionalmente, verificar pendiente positiva del MACD
        macd_slope_condition = row['MACD'] > previous_row['MACD']
        
        # El histograma debe estar aumentando (volviéndose menos negativo)
        histogram_condition = row['MACD_HIST'] > previous_row['MACD_HIST']
        
        # Combinar condiciones del MACD
        macd_condition = macd_approaching_condition and macd_slope_condition and histogram_condition
        
        # Calcular distancia al cruce (predicción)
        prediction_message = ""
        if macd_condition:
            # Estimar cuántas velas faltan para el cruce según la velocidad actual
            if current_distance > 0 and previous_distance > current_distance and previous_distance != current_distance:
                closing_speed = previous_distance - current_distance
                estimated_candles_to_cross = current_distance / closing_speed if closing_speed > 0 else float('inf')
                
                if estimated_candles_to_cross < 5:  # Si estimamos menos de 5 velas para el cruce
                    prediction_message = f"⚠️ CRUCE INMINENTE - Aprox. {estimated_candles_to_cross:.1f} velas hasta el cruce del MACD"
        
        # Mensaje con detalles
        detail_message = f"MACD ({row['MACD']:.4f}) acercándose a la Señal ({row['MACD_SIGNAL']:.4f})"
        if prediction_message:
            detail_message += f", {prediction_message}"
        
        return macd_condition, detail_message
    else:
        return False, "Datos insuficientes para análisis de MACD"