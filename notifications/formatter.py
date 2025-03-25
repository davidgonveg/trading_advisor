"""
Funciones para formatear mensajes de alerta.
"""
from analysis.market_type import detect_market_type, adapt_parameters_to_market

def generate_alert_message(symbol, data, breakout_index):
    """
    Genera un mensaje de alerta más informativo con niveles de precio recomendados
    y adaptaciones basadas en el tipo de mercado.
    
    Args:
        symbol: Símbolo de la acción
        data: DataFrame con datos e indicadores
        breakout_index: Índice donde se detectó la ruptura
        
    Returns:
        str: Mensaje formateado para la alerta
    """
    row = data.iloc[breakout_index]
    current_price = data['Close'].iloc[-1]
    date_time = data.index[breakout_index]
    
    # Detectar tipo de mercado
    market_type = detect_market_type(data)
    
    # Obtener parámetros adaptados al tipo de mercado
    params = adapt_parameters_to_market(market_type)
    
    # Calcular niveles de precio recomendados
    entry_price = current_price
    stop_loss = round(entry_price * (1 - params["stop_loss_pct"]/100), 2)
    take_profit_1 = round(entry_price * (1 + params["take_profit1_pct"]/100), 2)
    take_profit_2 = round(entry_price * (1 + params["take_profit2_pct"]/100), 2)
    
    # Distancia a la banda media (objetivo potencial)
    middle_band_distance = ((row['BB_MEDIA'] / current_price) - 1) * 100
    
    message = f"🔔 <b>ALERTA TÉCNICA: {symbol}</b>\n\n"
    
    # Añadir tipo de mercado
    message += f"<b>Mercado:</b> {market_type['descripcion']}\n\n"
    
    # Añadir condiciones técnicas que se cumplen
    from indicators.macd import verify_macd_conditions
    _, macd_detail = verify_macd_conditions(data, breakout_index)
    
    from indicators.rsi import check_rsi_conditions
    _, rsi_detail = check_rsi_conditions(data, breakout_index)
    
    message += f"• Precio ({row['Close']:.2f}) por debajo de la Banda de Bollinger inferior ({row['BB_INFERIOR']:.2f})\n"
    message += f"• {rsi_detail}\n"
    message += f"• {macd_detail}"
    
    # Añadir recomendaciones de trading
    message += f"\n\n<b>Datos de Trading:</b>"
    message += f"\nPrecio actual: ${current_price:.2f}"
    message += f"\nStop loss sugerido: ${stop_loss} (-{params['stop_loss_pct']}%)"
    message += f"\nToma de ganancias 1: ${take_profit_1} (+{params['take_profit1_pct']}%)"
    message += f"\nToma de ganancias 2: ${take_profit_2} (+{params['take_profit2_pct']}%)"
    message += f"\nBanda media: ${row['BB_MEDIA']:.2f} ({middle_band_distance:.1f}% desde precio actual)"
    
    # Añadir momento y fortaleza de la señal
    rsi_strength = "FUERTE" if row['RSI_K'] < 10 else "MODERADA"
    message += f"\n\n<b>Fortaleza de la señal:</b> {rsi_strength}"
    
    # Añadir recomendación específica basada en el mercado
    if "recomendacion" in market_type:
        message += f"\n\n⚠️ <b>Consideración:</b> {market_type['recomendacion']}"
    elif market_type["tendencia"] == "bajista":
        message += f"\n\n⚠️ <b>Precaución:</b> Mercado bajista - Considere reducir tamaño de posición y tomar ganancias rápidamente."
    elif market_type["volatilidad"] == "alta":
        message += f"\n\n⚠️ <b>Precaución:</b> Alta volatilidad - Stop loss más amplio y vigilar posible reversión rápida."
    
    # Añadir comentario especial si existe
    if "comentario" in params:
        message += f"\n\n<b>Nota:</b> {params['comentario']}"
    
    # Añadir marcas de tiempo
    message += f"\n\nFecha y hora de la señal: {date_time}"
    message += f"\nFecha y hora actual: {data.index[-1]}"
    
    return message

def generate_flexible_alert_message(symbol, data, sequence_details):
    """
    Genera un mensaje de alerta adaptado a la secuencia flexible.
    
    Args:
        symbol: Símbolo de la acción
        data: DataFrame con datos e indicadores
        sequence_details: Diccionario con detalles de la secuencia detectada
        
    Returns:
        str: Mensaje formateado para la alerta
    """
    # Extraer índices de secuencia
    bollinger_index = sequence_details["indice_bollinger"]
    rsi_index = sequence_details["indice_rsi"]
    macd_index = sequence_details["indice_macd"]
    
    # Usar el evento más reciente para información de precio actual
    current_price = data['Close'].iloc[-1]
    
    # Datos para cada evento
    bollinger_data = data.iloc[bollinger_index]
    rsi_data = data.iloc[rsi_index]
    macd_data = data.iloc[macd_index]
    
    # Velas hasta cruce - Convertir explícitamente a float si es numpy.float64
    candles_to_cross = float(sequence_details.get("velas_para_cruce", float('inf')))
    imminent_cross = candles_to_cross < 5
    
    # Detectar tipo de mercado
    market_type = detect_market_type(data)
    
    # Obtener parámetros adaptados al tipo de mercado
    params = adapt_parameters_to_market(market_type)
    
    # Calcular niveles de precio
    stop_loss = round(current_price * (1 - params["stop_loss_pct"]/100), 2)
    take_profit_1 = round(current_price * (1 + params["take_profit1_pct"]/100), 2)
    take_profit_2 = round(current_price * (1 + params["take_profit2_pct"]/100), 2)
    
    # Distancia a la banda media (objetivo potencial)
    middle_band_distance = ((bollinger_data['BB_MEDIA'] / current_price) - 1) * 100
    
    # Construir mensaje con símbolos < y > correctamente escapados
    message = f"🔔 <b>ALERTA TÉCNICA: {symbol}</b>\n\n"
    message += f"<b>Mercado:</b> {market_type['descripcion']}\n\n"
    message += f"<b>Secuencia de Señal Detectada:</b>\n"
    
    # 1. Ruptura de Bollinger - IMPORTANTE: Escapar manualmente símbolo <
    bollinger_time = data.index[bollinger_index]
    message += f"• Ruptura de Bollinger: {bollinger_time.strftime('%H:%M')} - Precio ({bollinger_data['Close']:.2f}) &lt; BB Inferior ({bollinger_data['BB_INFERIOR']:.2f})\n"
    
    # 2. RSI Estocástico bajo
    rsi_time = data.index[rsi_index]
    message += f"• RSI Estocástico: {rsi_time.strftime('%H:%M')} - RSI-K ({rsi_data['RSI_K']:.2f}) por debajo de 20\n"
    
    # 3. MACD acercándose
    macd_time = data.index[macd_index]
    message += f"• MACD: {macd_time.strftime('%H:%M')} - MACD ({macd_data['MACD']:.4f}) acercándose a Señal ({macd_data['MACD_SIGNAL']:.4f})\n"
    
    # Resto del mensaje...
    if imminent_cross:
        message += f"\n⚠️ <b>CRUCE INMINENTE</b> - Aprox. {candles_to_cross:.1f} velas hasta cruce de MACD\n"
    
    message += f"\n<b>Datos de Trading:</b>"
    message += f"\nPrecio actual: ${current_price:.2f}"
    message += f"\nStop loss sugerido: ${stop_loss} (-{params['stop_loss_pct']}%)"
    message += f"\nToma de ganancias 1: ${take_profit_1} (+{params['take_profit1_pct']}%)"
    message += f"\nToma de ganancias 2: ${take_profit_2} (+{params['take_profit2_pct']}%)"
    message += f"\nBanda media: ${bollinger_data['BB_MEDIA']:.2f} ({middle_band_distance:.1f}% desde precio actual)"
    
    rsi_strength = "FUERTE" if rsi_data['RSI_K'] < 10 else "MODERADA"
    message += f"\n\n<b>Fortaleza de la señal:</b> {rsi_strength}"
    
    if "recomendacion" in market_type:
        message += f"\n\n⚠️ <b>Consideración:</b> {market_type['recomendacion']}"
    elif market_type["tendencia"] == "bajista":
        message += f"\n\n⚠️ <b>Precaución:</b> Mercado bajista - Considere reducir tamaño de posición y tomar ganancias rápidamente."
    elif market_type["volatilidad"] == "alta":
        message += f"\n\n⚠️ <b>Precaución:</b> Alta volatilidad - Stop loss más amplio y vigilar posible reversión rápida."
    
    # Añadir comentario especial si existe
    if "comentario" in params:
        message += f"\n\n<b>Nota:</b> {params['comentario']}"
    
    message += f"\n\nFecha y hora actual: {data.index[-1]}"
    
    return message

def format_weekly_summary(symbols_data, period_days=7):
    """
    Genera un resumen semanal de las señales detectadas y rendimiento.
    
    Args:
        symbols_data: Diccionario con datos para cada símbolo
        period_days: Período de días para el resumen
        
    Returns:
        str: Mensaje formateado con el resumen
    """
    import datetime
    
    today = datetime.datetime.now()
    start_date = today - datetime.timedelta(days=period_days)
    
    message = f"📊 <b>RESUMEN DE TRADING ({start_date.strftime('%d/%m/%Y')} - {today.strftime('%d/%m/%Y')})</b>\n\n"
    
    # Estadísticas generales
    total_signals = sum(len(data.get('signals', [])) for symbol, data in symbols_data.items())
    successful_signals = sum(len([s for s in data.get('signals', []) if s.get('success')]) 
                            for symbol, data in symbols_data.items())
    
    success_rate = (successful_signals / total_signals * 100) if total_signals > 0 else 0
    
    message += f"<b>Estadísticas Generales:</b>\n"
    message += f"• Señales totales: {total_signals}\n"
    message += f"• Señales exitosas: {successful_signals}\n"
    message += f"• Tasa de éxito: {success_rate:.1f}%\n\n"
    
    # Top 3 mejores señales
    message += f"<b>Mejores Señales:</b>\n"
    all_signals = []
    for symbol, data in symbols_data.items():
        for signal in data.get('signals', []):
            if signal.get('performance'):
                all_signals.append({
                    'symbol': symbol,
                    'date': signal.get('date'),
                    'performance': signal.get('performance'),
                    'price': signal.get('price')
                })
    
    # Ordenar por rendimiento
    all_signals.sort(key=lambda x: x['performance'], reverse=True)
    
    # Mostrar top 3 (o menos si no hay suficientes)
    for i, signal in enumerate(all_signals[:3]):
        if i < len(all_signals):
            message += f"#{i+1}: {signal['symbol']} ({signal['date'].strftime('%d/%m')}) - {signal['performance']:.2f}%\n"
    
    # Resumen del tipo de mercado actual
    message += f"\n<b>Análisis de Mercado Actual:</b>\n"
    # Aquí se podría añadir un análisis más detallado del mercado actual
    
    message += f"\n<i>El sistema continúa monitorizando para detectar nuevas oportunidades.</i>"
    
    return message