"""
Operaciones CRUD con la base de datos.
"""
import pandas as pd
import os
from sqlite3 import Error
from datetime import datetime
from utils.logger import logger
import config

def get_last_data_from_db(connection, symbol, limit=200):
    """
    Obtiene los últimos datos históricos de un símbolo desde la base de datos.
    
    Args:
        connection: Conexión a la base de datos
        symbol: Símbolo de la acción
        limit: Número máximo de registros a recuperar
        
    Returns:
        DataFrame con los datos históricos o None
    """
    try:
        if not connection:
            return None
            
        cursor = connection.cursor()
        
        # Verificar si la tabla existe
        cursor.execute(f"""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='datos_historicos'
        """)
        
        if not cursor.fetchone():
            logger.warning("La tabla datos_historicos no existe en la base de datos")
            return None
        
        # Obtener datos ordenados por fecha en orden descendente
        cursor.execute(f'''
        SELECT fecha_hora, precio_open, precio_high, precio_low, precio_close, 
               volumen, bb_inferior, bb_media, bb_superior, macd, macd_signal, rsi, rsi_k
        FROM datos_historicos 
        WHERE simbolo = ?
        ORDER BY fecha_hora DESC
        LIMIT {limit}
        ''', (symbol,))
        
        records = cursor.fetchall()
        
        if not records:
            logger.info(f"No hay datos históricos para {symbol} en la base de datos")
            return None
            
        # Crear DataFrame con los datos
        columns = ['fecha_hora', 'Open', 'High', 'Low', 'Close', 'Volume', 
                  'BB_INFERIOR', 'BB_MEDIA', 'BB_SUPERIOR', 'MACD', 'MACD_SIGNAL', 'RSI', 'RSI_K']
        
        df = pd.DataFrame(records, columns=columns)
        
        # Convertir columna fecha_hora a índice datetime
        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        df.set_index('fecha_hora', inplace=True)
        
        # Ordenar por índice en orden ascendente (primero los más antiguos)
        df = df.sort_index()
        
        return df
        
    except Error as e:
        logger.error(f"Error al recuperar datos históricos de la BD: {e}")
        return None

def save_alert_to_db(connection, symbol, data, index, message, alert_type="sequence"):
    """
    Guarda una alerta en la base de datos.
    
    Args:
        connection: Conexión a la base de datos
        symbol: Símbolo de la acción
        data: DataFrame con los datos
        index: Índice de la alerta en el DataFrame
        message: Mensaje de la alerta
        alert_type: Tipo de alerta generada
        
    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    try:
        if not connection:
            logger.warning("No hay conexión a la base de datos para guardar la alerta")
            return False
            
        cursor = connection.cursor()
        
        # Verificar si la tabla existe
        cursor.execute(f"""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='alertas'
        """)
        
        if not cursor.fetchone():
            logger.warning("La tabla alertas no existe en la base de datos. Creándola...")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simbolo TEXT NOT NULL,
                precio REAL NOT NULL,
                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_alerta TEXT,
                mensaje TEXT,
                bb_inferior REAL,
                bb_media REAL,
                macd REAL,
                macd_signal REAL,
                rsi_k REAL
            )
            ''')
            connection.commit()
        
        row = data.iloc[index]
        
        # Preparar datos para inserción
        alert_data = (
            symbol,
            float(row['Close']),
            str(data.index[index]),
            alert_type,
            message,
            float(row['BB_INFERIOR']) if 'BB_INFERIOR' in row and pd.notna(row['BB_INFERIOR']) else None,
            float(row['BB_MEDIA']) if 'BB_MEDIA' in row and pd.notna(row['BB_MEDIA']) else None,
            float(row['MACD']) if 'MACD' in row and pd.notna(row['MACD']) else None,
            float(row['MACD_SIGNAL']) if 'MACD_SIGNAL' in row and pd.notna(row['MACD_SIGNAL']) else None,
            float(row['RSI_K']) if 'RSI_K' in row and pd.notna(row['RSI_K']) else None
        )
        
        cursor.execute('''
        INSERT INTO alertas 
        (simbolo, precio, fecha_hora, tipo_alerta, mensaje, bb_inferior, bb_media, macd, macd_signal, rsi_k)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', alert_data)
        
        connection.commit()
        logger.info(f"Alerta para {symbol} guardada en la base de datos")
        return True
    except Error as e:
        logger.error(f"Error al guardar la alerta en la base de datos: {e}")
        return False

def save_historical_data(connection, symbol, data):
    """
    Guarda datos históricos en la base de datos.
    
    Args:
        connection: Conexión a la base de datos
        symbol: Símbolo de la acción
        data: DataFrame con los datos
        
    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    try:
        if data.empty:
            logger.warning(f"No hay datos para guardar de {symbol}")
            return False
            
        if not connection:
            logger.warning("No hay conexión a la base de datos para guardar datos históricos")
            return False
            
        cursor = connection.cursor()
        
        # Verificar si la tabla existe
        cursor.execute(f"""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='datos_historicos'
        """)
        
        if not cursor.fetchone():
            logger.warning("La tabla datos_historicos no existe en la base de datos. Creándola...")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS datos_historicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simbolo TEXT NOT NULL,
                fecha_hora TIMESTAMP,
                precio_open REAL,
                precio_high REAL,
                precio_low REAL,
                precio_close REAL,
                volumen INTEGER,
                bb_inferior REAL,
                bb_media REAL,
                bb_superior REAL,
                macd REAL,
                macd_signal REAL,
                rsi REAL,
                rsi_k REAL
            )
            ''')
            connection.commit()
        
        # Para mejorar el rendimiento, usar transacción para múltiples inserciones
        inserted_count = 0
        errors_count = 0
        
        for idx, row in data.iterrows():
            try:
                # Comprobar si ya existe un registro para este símbolo y fecha
                cursor.execute('''
                SELECT id FROM datos_historicos 
                WHERE simbolo = ? AND fecha_hora = ?
                ''', (symbol, str(idx)))
                
                exists = cursor.fetchone()
                
                if exists:
                    continue  # Omitir si ya existe
                
                # Preparar datos para inserción
                hist_data = (
                    symbol,
                    str(idx),
                    float(row['Open']) if 'Open' in row and pd.notna(row['Open']) else None,
                    float(row['High']) if 'High' in row and pd.notna(row['High']) else None,
                    float(row['Low']) if 'Low' in row and pd.notna(row['Low']) else None,
                    float(row['Close']) if 'Close' in row and pd.notna(row['Close']) else None,
                    int(row['Volume']) if 'Volume' in row and pd.notna(row['Volume']) else 0,
                    float(row['BB_INFERIOR']) if 'BB_INFERIOR' in row and pd.notna(row['BB_INFERIOR']) else None,
                    float(row['BB_MEDIA']) if 'BB_MEDIA' in row and pd.notna(row['BB_MEDIA']) else None,
                    float(row['BB_SUPERIOR']) if 'BB_SUPERIOR' in row and pd.notna(row['BB_SUPERIOR']) else None,
                    float(row['MACD']) if 'MACD' in row and pd.notna(row['MACD']) else None,
                    float(row['MACD_SIGNAL']) if 'MACD_SIGNAL' in row and pd.notna(row['MACD_SIGNAL']) else None,
                    float(row['RSI']) if 'RSI' in row and pd.notna(row['RSI']) else None,
                    float(row['RSI_K']) if 'RSI_K' in row and pd.notna(row['RSI_K']) else None
                )
                
                cursor.execute('''
                INSERT INTO datos_historicos 
                (simbolo, fecha_hora, precio_open, precio_high, precio_low, precio_close, 
                 volumen, bb_inferior, bb_media, bb_superior, macd, macd_signal, rsi, rsi_k)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', hist_data)
                
                inserted_count += 1
                
            except Exception as e:
                logger.error(f"Error insertando registro para {symbol} en {idx}: {e}")
                errors_count += 1
        
        connection.commit()
        
        if inserted_count > 0:
            logger.info(f"Datos históricos para {symbol}: {inserted_count} registros insertados, {errors_count} errores")
            return True
        else:
            logger.info(f"No se insertaron nuevos registros para {symbol}")
            return False
    except Error as e:
        logger.error(f"Error al guardar datos históricos en la base de datos: {e}")
        return False

def save_current_quote(connection, symbol, quote_data):
    """
    Guarda una cotización actual en la base de datos.
    
    Args:
        connection: Conexión a la base de datos
        symbol: Símbolo de la acción
        quote_data: Datos de la cotización de Finnhub
        
    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    try:
        if not connection:
            logger.warning("No hay conexión a la base de datos para guardar la cotización")
            return False
            
        cursor = connection.cursor()
        
        # Verificar si la tabla existe
        cursor.execute(f"""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='{symbol}_quotes'
        """)
        
        if not cursor.fetchone():
            logger.info(f"Creando tabla para cotizaciones de {symbol}...")
            cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {symbol}_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                current_price REAL,
                change REAL,
                change_percent REAL,
                low_price REAL,
                high_price REAL,
                timestamp DATETIME
            )
            ''')
            connection.commit()
        
        # Insertar datos
        cursor.execute(f'''
        INSERT INTO {symbol}_quotes 
        (current_price, change, change_percent, low_price, high_price, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            quote_data['c'],  # current price
            quote_data.get('d', 0),  # change
            quote_data.get('dp', 0),  # change percent
            quote_data.get('l', 0),  # low price
            quote_data.get('h', 0),  # high price
            datetime.now()  # timestamp
        ))
        
        connection.commit()
        logger.info(f"Cotización de {symbol} guardada en la base de datos")
        return True
    except Error as e:
        logger.error(f"Error al guardar la cotización en la base de datos: {e}")
        return False

def get_quotes_from_db(connection, symbol, limit=10):
    """
    Obtiene las últimas cotizaciones de un símbolo desde la base de datos.
    
    Args:
        connection: Conexión a la base de datos
        symbol: Símbolo de la acción
        limit: Número máximo de registros a recuperar
        
    Returns:
        list: Lista de cotizaciones o [] si hay error
    """
    try:
        if not connection:
            return []
            
        cursor = connection.cursor()
        
        # Verificar si la tabla existe
        cursor.execute(f"""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='{symbol}_quotes'
        """)
        
        if not cursor.fetchone():
            logger.warning(f"No existe la tabla {symbol}_quotes en la base de datos")
            return []
        
        # Obtener datos ordenados por fecha en orden descendente
        cursor.execute(f'''
        SELECT id, current_price, change, change_percent, low_price, high_price, timestamp
        FROM {symbol}_quotes
        ORDER BY timestamp DESC
        LIMIT {limit}
        ''')
        
        records = cursor.fetchall()
        
        if not records:
            logger.info(f"No hay cotizaciones para {symbol} en la base de datos")
            return []
            
        # Convertir a lista de diccionarios
        quotes = []
        for record in records:
            quotes.append({
                'id': record[0],
                'current_price': record[1],
                'change': record[2],
                'change_percent': record[3],
                'low_price': record[4],
                'high_price': record[5],
                'timestamp': record[6]
            })
        
        return quotes
        
    except Error as e:
        logger.error(f"Error al recuperar cotizaciones de la BD: {e}")
        return []

def check_data_integrity(connection, symbols):
    """
    Verifica la integridad de los datos históricos para detectar y corregir gaps.
    
    Args:
        connection: Conexión a la base de datos
        symbols: Lista de símbolos a verificar
    """
    if not connection:
        logger.warning("No hay conexión a la base de datos para verificar integridad")
        return
        
    logger.info("Iniciando verificación de integridad de datos...")
    
    for symbol in symbols:
        try:
            logger.info(f"Verificando integridad de datos para {symbol}")
            
            # Obtener datos históricos
            data = get_last_data_from_db(connection, symbol, limit=1000)
            
            if data is None or data.empty:
                logger.info(f"No hay datos históricos para {symbol}")
                continue
                
            # Verificar gaps durante las horas de mercado
            import pandas as pd
            dates = data.index
            
            # Crear una serie de tiempo ideal con intervalo de 5 minutos durante horas de mercado
            import datetime
            import pytz
            
            # Determinar el rango de fechas a verificar (último mes)
            start_date = dates.min()
            end_date = dates.max()
            
            # Limitar a 30 días para evitar sobrecarga
            if (end_date - start_date).days > 30:
                start_date = end_date - datetime.timedelta(days=30)
            
            # Crear un rango de fechas ideales durante horas de mercado
            ideal_dates = []
            current_date = start_date
            
            while current_date <= end_date:
                # Solo días laborables (0=Lunes, 4=Viernes)
                if current_date.weekday() < 5:
                    # Horas de mercado (9:30 AM - 4:00 PM ET)
                    start_hour = datetime.time(9, 30)
                    end_hour = datetime.time(16, 0)
                    
                    # Generar intervalos de 5 minutos
                    current_hour = datetime.datetime.combine(current_date.date(), start_hour)
                    current_hour = pytz.timezone('America/New_York').localize(current_hour)
                    
                    while current_hour.time() <= end_hour:
                        ideal_dates.append(current_hour)
                        current_hour += datetime.timedelta(minutes=5)
                
                current_date += datetime.timedelta(days=1)
            
            # Convertir a DataFrame para comparación
            ideal_df = pd.DataFrame(index=ideal_dates)
            
            # Identificar fechas faltantes (gaps)
            missing_dates = ideal_df.index.difference(dates)
            
            if len(missing_dates) > 0:
                # Agrupar fechas faltantes por día para el informe
                days_with_gaps = set([date.date() for date in missing_dates])
                
                logger.warning(f"Detectados {len(missing_dates)} posibles gaps para {symbol} en {len(days_with_gaps)} días diferentes")
                
                # Si hay muchos gaps, podríamos programar una recarga completa de datos
                if len(missing_dates) > 20:
                    logger.info(f"Programando recarga completa de datos para {symbol}")
                    # Aquí podríamos marcar el símbolo para recarga completa
                    # o implementar la recarga directamente
                
            else:
                logger.info(f"No se detectaron gaps significativos para {symbol}")
                
        except Exception as e:
            logger.error(f"Error al verificar integridad de datos para {symbol}: {e}")