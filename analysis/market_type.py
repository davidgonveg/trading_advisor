"""
Análisis del tipo de mercado basado en indicadores técnicos.
"""
import pandas as pd
from utils.logger import logger

def detect_market_type(df):
    """
    Detecta el tipo de mercado actual (lateral, alcista, bajista, alta/baja volatilidad).
    
    Args:
        df: DataFrame con datos e indicadores
        
    Returns:
        dict: Diccionario con tipo de mercado y sus características
    """
    if len(df) < 50:  # Necesitamos suficientes datos para analizar
        return {"tipo": "indeterminado", "descripcion": "Datos insuficientes"}
    
    # Calcular pendiente EMA50 (si ya existe en el DataFrame)
    if 'EMA50' not in df.columns:
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # Obtener datos de las últimas 50 velas
    last_candles = df.iloc[-50:]
    
    # Pendiente de EMA50 (tendencia)
    first_value = last_candles['EMA50'].iloc[0]
    last_value = last_candles['EMA50'].iloc[-1]
    percent_change = ((last_value / first_value) - 1) * 100
    
    # Volatilidad (ancho de las Bandas de Bollinger)
    bands_width = (last_candles['BB_SUPERIOR'] - last_candles['BB_INFERIOR']) / last_candles['Close'] * 100
    avg_volatility = bands_width.mean()
    
    # Analizar tipo de mercado
    market_type = {}
    
    # Análisis de tendencia
    if percent_change > 2:
        market_type["tendencia"] = "alcista"
    elif percent_change < -2:
        market_type["tendencia"] = "bajista"
    else:
        market_type["tendencia"] = "lateral"
    
    # Análisis de volatilidad
    if avg_volatility > 5:  # Umbral para alta volatilidad (ajustar según tus activos)
        market_type["volatilidad"] = "alta"
    elif avg_volatility < 2:  # Umbral para baja volatilidad
        market_type["volatilidad"] = "baja"
    else:
        market_type["volatilidad"] = "moderada"
    
    # Análisis de momento
    momentum = calculate_momentum(last_candles)
    market_type["momentum"] = momentum
    
    # Análisis de fortaleza relativa
    if 'RSI' in last_candles.columns:
        avg_rsi = last_candles['RSI'].iloc[-10:].mean()
        if avg_rsi > 70:
            market_type["fortaleza"] = "sobrecompra"
        elif avg_rsi < 30:
            market_type["fortaleza"] = "sobreventa"
        else:
            market_type["fortaleza"] = "neutral"
    
    # Descripción combinada
    market_type["descripcion"] = f"mercado {market_type['tendencia']} con volatilidad {market_type['volatilidad']}"
    
    # Información adicional específica para el trading
    if market_type["tendencia"] == "bajista" and market_type["volatilidad"] == "alta":
        market_type["recomendacion"] = "Precaución: mercado bajista volátil - posiciones más pequeñas"
    elif market_type["tendencia"] == "lateral" and market_type["volatilidad"] == "baja":
        market_type["recomendacion"] = "Posible consolidación - esperar ruptura para confirmar dirección"
    elif market_type["tendencia"] == "alcista" and market_type["volatilidad"] == "moderada":
        market_type["recomendacion"] = "Entorno favorable para largos - mantener stop loss ajustado"
    
    return market_type

def calculate_momentum(df, period=14):
    """
    Calcula el momento del mercado basado en la velocidad de los movimientos de precio.
    
    Args:
        df: DataFrame con datos de precios
        period: Período para calcular el momento
        
    Returns:
        str: Descripción del momento ("fuerte", "moderado", "débil")
    """
    if len(df) < period:
        return "indeterminado"
    
    # Calcular tasa de cambio porcentual
    roc = ((df['Close'].iloc[-1] / df['Close'].iloc[-period]) - 1) * 100
    
    # Evaluar fuerza del momento
    if abs(roc) > 5:
        momentum = "fuerte"
    elif abs(roc) > 2:
        momentum = "moderado"
    else:
        momentum = "débil"
    
    # Determinar dirección
    direction = "positivo" if roc > 0 else "negativo"
    
    return f"{momentum} {direction}"

def adapt_parameters_to_market(market_type):
    """
    Adapta parámetros de trading según el tipo de mercado.
    
    Args:
        market_type: Diccionario con información del tipo de mercado
        
    Returns:
        dict: Parámetros adaptados al tipo de mercado
    """
    params = {
        "stop_loss_pct": 0.5,
        "take_profit1_pct": 0.5,
        "take_profit2_pct": 1.0,
        "position_size_factor": 1.0,
        "time_horizon": "normal"
    }
    
    # Ajustes basados en la tendencia
    if market_type["tendencia"] == "bajista":
        # En mercado bajista, stop loss más ajustado y toma de ganancias más conservadora
        params["stop_loss_pct"] = 0.4
        params["take_profit1_pct"] = 0.4
        params["take_profit2_pct"] = 0.8
        params["position_size_factor"] = 0.7  # Reducir tamaño de posición en mercado bajista
    
    # Ajustes basados en volatilidad
    if market_type["volatilidad"] == "alta":
        # En mercado volátil, stop loss más amplio y toma de ganancias más ambiciosa
        params["stop_loss_pct"] = 0.7
        params["take_profit1_pct"] = 0.7
        params["take_profit2_pct"] = 1.4
        params["time_horizon"] = "corto"  # Horizonte temporal más corto en mercados volátiles
    elif market_type["volatilidad"] == "baja":
        # En baja volatilidad, necesitamos más paciencia
        params["time_horizon"] = "largo"
    
    # Ajustes basados en momento
    if "fuerte positivo" in market_type.get("momentum", ""):
        params["position_size_factor"] *= 1.2  # Incrementar tamaño en momento fuerte positivo
    
    # Añadir consideraciones especiales para condiciones extremas
    if market_type.get("fortaleza") == "sobreventa" and market_type["tendencia"] == "alcista":
        params["comentario"] = "Posible rebote técnico fuerte"
    elif market_type.get("fortaleza") == "sobrecompra" and market_type["tendencia"] == "bajista":
        params["comentario"] = "Riesgo de corrección a la baja"
    
    return params