import pandas as pd


"""
Cálculo de Bandas de Bollinger.
"""
from utils.logger import logger

def calculate_bollinger(df, window=18, deviations=2.25):
    """
    Calcula las Bandas de Bollinger para un DataFrame.
    
    Args:
        df: DataFrame con datos de precios
        window: Período para la media móvil
        deviations: Número de desviaciones estándar
        
    Returns:
        DataFrame con columnas 'BB_MEDIA', 'BB_SUPERIOR', 'BB_INFERIOR'
    """
    if len(df) < window:
        logger.warning(f"Datos insuficientes para calcular Bollinger (se necesitan al menos {window} períodos)")
        return df
    
    # Calcular la media móvil
    df['BB_MEDIA'] = df['Close'].rolling(window=window).mean()
    
    # Calcular la desviación estándar
    rolling_std = df['Close'].rolling(window=window).std()
    
    # Calcular bandas superior e inferior
    df['BB_SUPERIOR'] = df['BB_MEDIA'] + (rolling_std * deviations)
    df['BB_INFERIOR'] = df['BB_MEDIA'] - (rolling_std * deviations)
    
    return df

def detect_bollinger_breakout(df):
    """
    Detecta cuando se rompe la Banda de Bollinger inferior en los últimos 15 minutos (3 períodos de 5 min).
    
    Args:
        df: DataFrame con indicadores calculados
        
    Returns:
        (bool, int): Tupla con (ruptura_detectada, índice_ruptura)
    """
    if df.empty or len(df) < 5:  # Necesitamos al menos algunos períodos
        return False, None
    
    # Comprobar los últimos 3 períodos (15 minutos en intervalos de 5 min)
    periods_to_check = min(3, len(df) - 1)
    
    for i in range(1, periods_to_check + 1):
        index = -i  # Empezando desde el último y yendo hacia atrás
        
        # Comprobar si el precio está por debajo de la banda inferior
        if not pd.isna(df['Close'].iloc[index]) and not pd.isna(df['BB_INFERIOR'].iloc[index]):
            if df['Close'].iloc[index] < df['BB_INFERIOR'].iloc[index]:
                # Si en el período anterior no estaba rota, entonces es una nueva ruptura
                if index > -len(df) and df['Close'].iloc[index-1] >= df['BB_INFERIOR'].iloc[index-1]:
                    return True, index
    
    return False, None