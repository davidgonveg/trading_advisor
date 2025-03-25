"""
Cálculo de indicadores RSI (Relative Strength Index) y RSI Estocástico.
"""
import numpy as np
import pandas as pd
from utils.logger import logger

def calculate_rsi(df, period=14, column='Close'):
    """
    Calcula el RSI (Relative Strength Index) para un DataFrame.
    
    Args:
        df: DataFrame con datos de precios
        period: Período para el cálculo del RSI
        column: Columna de precio a utilizar
        
    Returns:
        Series con valores RSI
    """
    delta = df[column].diff()
    
    # Separar ganancias (up) y pérdidas (down)
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    down = down.abs()
    
    # Calcular la media móvil exponencial de ups y downs
    avg_up = up.ewm(com=period-1, adjust=False).mean()
    avg_down = down.ewm(com=period-1, adjust=False).mean()
    
    # Calcular RS y RSI
    rs = avg_up / avg_down
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_stochastic_rsi(df, rsi_period=14, k_period=14, d_period=3, smooth=3, column='Close'):
    """
    Calcula el RSI Estocástico para un DataFrame.
    
    Args:
        df: DataFrame con datos de precios
        rsi_period: Período para RSI
        k_period: Período para %K
        d_period: Período para %D
        smooth: Suavizado para %K
        column: Columna de precio a utilizar
        
    Returns:
        DataFrame con columnas 'RSI', 'RSI_K' y 'RSI_D'
    """
    if len(df) < max(rsi_period, k_period, d_period, smooth):
        logger.warning(f"Datos insuficientes para calcular RSI Estocástico")
        return df
    
    # Calcular RSI
    df['RSI'] = calculate_rsi(df, period=rsi_period, column=column)
    
    # Calcular RSI Estocástico
    # Usar mínimo y máximo de RSI en lugar de precios
    df['RSI_MIN'] = df['RSI'].rolling(window=k_period).min()
    df['RSI_MAX'] = df['RSI'].rolling(window=k_period).max()
    
    # Calcular %K (equivalente a estocástico pero aplicado al RSI)
    # Evitar división por cero
    denominator = df['RSI_MAX'] - df['RSI_MIN']
    denominator = denominator.replace(0, np.nan)  # Reemplazar ceros con NaN
    
    df['RSI_K_RAW'] = 100 * ((df['RSI'] - df['RSI_MIN']) / denominator)
    df['RSI_K_RAW'] = df['RSI_K_RAW'].fillna(0)  # Reemplazar NaN con 0
    
    # Aplicar suavizado a %K
    df['RSI_K'] = df['RSI_K_RAW'].rolling(window=smooth).mean()
    
    # Calcular %D (media móvil de %K)
    df['RSI_D'] = df['RSI_K'].rolling(window=d_period).mean()
    
    return df

def check_rsi_conditions(df, index, threshold=20):
    """
    Verifica si el RSI Estocástico está por debajo del umbral especificado.
    
    Args:
        df: DataFrame con indicadores calculados
        index: Índice a verificar (-1 para la última fila)
        threshold: Umbral para considerar el RSI bajo (sobreventa)
        
    Returns:
        (bool, str): Tupla con (condiciones_cumplidas, mensaje_detalle)
    """
    if df.empty or abs(index) > len(df):
        return False, "Datos insuficientes para analizar"
    
    # Obtener la fila de datos en el índice especificado
    row = df.iloc[index]
    
    # Verificar si hay valores NaN en los indicadores que necesitamos
    if pd.isna(row['RSI_K']):
        return False, "Datos incompletos para análisis de RSI"
    
    # Condición: RSI Estocástico por debajo del umbral
    rsi_condition = row['RSI_K'] < threshold
    
    # Determinar la fuerza de la señal
    signal_strength = "FUERTE" if row['RSI_K'] < 10 else "MODERADA"
    
    # Mensaje con detalles
    detail_message = f"RSI Estocástico ({row['RSI_K']:.2f}) por debajo de {threshold} - Señal {signal_strength}"
    
    return rsi_condition, detail_message