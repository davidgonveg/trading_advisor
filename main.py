#!/usr/bin/env python3
"""
Script principal para el sistema de alertas técnicas de acciones.
Inicia el monitoreo continuo del mercado y envía alertas cuando se cumplen
condiciones técnicas específicas.
"""
import time
import threading
import datetime
import argparse
import sqlite3
import os
import pytz
import pandas as pd

# Importar módulos del proyecto
from utils.logger import logger, rotate_logs, save_alert_to_file
from indicators.bollinger import calculate_bollinger
from indicators.macd import calculate_macd
from indicators.rsi import calculate_stochastic_rsi
from database.connection import create_connection, create_tables
from database.operations import check_data_integrity, save_alert_to_db, save_historical_data
from market.utils import is_market_open, format_time_to_market_open
from market.data import get_stock_data
from analysis.detector import analyze_stock_flexible, detect_signal_sequence
from analysis.market_type import detect_market_type
from notifications.telegram import send_telegram_alert, send_telegram_test, send_market_status_notification
from notifications.formatter import format_weekly_summary
import config
from trading212 import integrator as trading212_integrator
# Importar get_last_data_from_db de database.operations
from database.operations import get_last_data_from_db

# Variables globales para controlar el estado del sistema
running = True
sent_alerts = {}  # Registro de alertas enviadas para evitar duplicados

os.makedirs("data/yfinance_cache", exist_ok=True)


def handle_command_line():
    """
    Procesa los argumentos de línea de comandos y ejecuta las acciones correspondientes.
    """
    parser = argparse.ArgumentParser(description='Sistema de Alertas Técnicas para Acciones')
    
    # ... tus argumentos existentes ...
    
    # Nuevos argumentos para Trading212
    parser.add_argument('--trading212', action='store_true', help='Inicializar integración con Trading212')
    parser.add_argument('--trading212-api-key', type=str, help='Clave API para Trading212')
    parser.add_argument('--trading212-simulation', action='store_true', help='Usar modo simulación para Trading212')
    parser.add_argument('--trading212-status', action='store_true', help='Mostrar estado de Trading212')
    
    # ... tu código existente ...
    
    # Procesar argumentos de Trading212
    if args.trading212:
        print("Inicializando integración con Trading212...")
        simulation_mode = args.trading212_simulation or True
        result = trading212_integrator.initialize(api_key=args.trading212_api_key, simulation_mode=simulation_mode)
        
        if result:
            print("✅ Integración con Trading212 inicializada correctamente")
            trading212_integrator.enable_integration()
            print("✅ Integración con Trading212 habilitada")
        else:
            print("❌ Error al inicializar integración con Trading212")
        
        return True
    
    if args.trading212_status:
        if not trading212_integrator.is_initialized():
            print("❌ La integración con Trading212 no está inicializada")
            return False
            
        status = trading212_integrator.get_status()
        print("\nEstado de Trading212:")
        print(status)
        return True



def check_stocks_spaced(db_connection=None):
    """
    Verificación optimizada de acciones con mejor manejo de límites de tasa.
    """
    # Verificar si el mercado está abierto
    if not is_market_open():
        logger.info("Mercado cerrado. No se realizarán verificaciones.")
        return
    
    logger.info("Iniciando verificación espaciada de acciones...")
    
    # Obtener lista actualizada de acciones
    stocks = config.get_stock_list()
    results = {}
    
    # Verificar si hay un número adecuado de acciones para analizar
    if not stocks:
        logger.warning("Lista de acciones vacía. No hay nada que verificar.")
        return results
    
    # Inicializar el optimizador de solicitudes si aún no está inicializado
    try:
        from yfinance_rate_limiter import initialize, get_queue_stats
        initialize(db_connection=db_connection)
        logger.info("Optimizador de solicitudes inicializado correctamente")
        
        # Mostrar estadísticas iniciales
        stats = get_queue_stats()
        if stats:
            logger.info(f"Estado inicial de la cola: {stats['queue_size']} pendientes, {stats['active_requests']} activas")
    except Exception as e:
        logger.warning(f"Error al inicializar optimizador de solicitudes: {e}")
    
    # Calcular retardo entre símbolos para espaciar verificaciones
    total_available_time = config.CHECK_INTERVAL_MINUTES * 60 * 0.8  # en segundos
    delay_between_stocks = max(config.RATE_LIMIT_THROTTLE, total_available_time / len(stocks))
    
    logger.info(f"Procesando {len(stocks)} acciones con {delay_between_stocks:.2f} seg entre cada una")
    
    # Implementar verificación por lotes
    batch_size = min(config.MAX_SYMBOLS_PER_BATCH, len(stocks))
    batch_count = (len(stocks) + batch_size - 1) // batch_size
    
    logger.info(f"Procesando en {batch_count} lotes de hasta {batch_size} acciones cada uno")
    
    # Procesar en lotes para mayor eficiencia
    for batch_index in range(batch_count):
        start_idx = batch_index * batch_size
        end_idx = min(start_idx + batch_size, len(stocks))
        current_batch = stocks[start_idx:end_idx]
        
        logger.info(f"Procesando lote {batch_index+1}/{batch_count}: {len(current_batch)} acciones")
        
        for i, symbol in enumerate(current_batch):
            try:
                logger.info(f"Analizando {symbol} ({start_idx+i+1}/{len(stocks)})...")
                
                # Analizar la acción
                meets_conditions, message = analyze_stock_flexible_thread_safe(symbol, config.DB_PATH)
                
                # Procesar resultado y enviar alerta si es necesario
                if meets_conditions:
                    # Verificar si ya enviamos una alerta para este símbolo en los últimos 20 minutos
                    current_time = time.time()
                    if symbol in sent_alerts:
                        last_alert = sent_alerts[symbol]
                        if current_time - last_alert < 1200:  # 20 minutos en segundos
                            logger.info(f"Ya se envió una alerta para {symbol} en los últimos 20 minutos. Ignorando.")
                            results[symbol] = (False, "Alerta enviada recientemente")
                            continue
                    
                    # Enviar alerta vía Telegram
                    logger.info(f"Se cumplen las condiciones para {symbol}, enviando alerta")
                    send_telegram_alert(message, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
                    
                    # Registrar el envío de esta alerta
                    sent_alerts[symbol] = current_time
                    
                    # Como respaldo, guardar en archivo
                    save_alert_to_file(message)
                    
                    # Enviar alerta a Trading212 si está inicializado
                    if trading212_integrator.is_initialized():
                        logger.info(f"Enviando alerta para {symbol} a Trading212")
                        trading212_result = trading212_integrator.process_alert(symbol, message)
                        
                        if trading212_result:
                            logger.info(f"Alerta para {symbol} procesada por Trading212")
                        else:
                            logger.warning(f"Error al procesar alerta para {symbol} en Trading212")
                    
                    results[symbol] = (True, message)
                else:
                    logger.info(f"No se cumplen las condiciones para {symbol}")
                    results[symbol] = (False, "No se cumplen las condiciones")
                
                # Esperar antes de procesar la siguiente acción, a menos que sea la última del lote
                if i < len(current_batch) - 1:
                    logger.debug(f"Esperando {delay_between_stocks:.2f} seg antes de analizar la siguiente acción")
                    time.sleep(delay_between_stocks)
                    
            except Exception as e:
                logger.error(f"Error al procesar {symbol}: {e}")
                results[symbol] = (False, f"Error: {str(e)}")
        
        # Verificar si es necesario esperar entre lotes (solo si no es el último lote)
        if batch_index < batch_count - 1:
            # Mostrar estadísticas de la cola
            try:
                from yfinance_rate_limiter import get_queue_stats
                stats = get_queue_stats()
                if stats:
                    logger.info(f"Estado de la cola: {stats['queue_size']} pendientes, {stats['active_requests']} activas")
                    
                    # Ajustar el tiempo de espera entre lotes según el estado de la cola
                    if stats['in_cooldown']:
                        batch_delay = 10.0  # Esperar más si estamos en enfriamiento
                        logger.info(f"En período de enfriamiento. Esperando {batch_delay} segundos antes del siguiente lote...")
                    else:
                        batch_delay = 3.0  # Esperar lo normal
                        logger.info(f"Lote {batch_index+1} completado. Esperando {batch_delay} segundos antes del siguiente lote...")
                    
                    time.sleep(batch_delay)
            except Exception as e:
                batch_delay = 3.0  # Fallback
                logger.info(f"Lote {batch_index+1} completado. Esperando {batch_delay} segundos antes del siguiente lote...")
                time.sleep(batch_delay)
    
    logger.info(f"Verificación completa de {len(stocks)} acciones finalizada.")
    
    # Mostrar estadísticas finales
    try:
        from yfinance_rate_limiter import get_queue_stats
        stats = get_queue_stats()
        if stats:
            logger.info(f"Estadísticas finales: {stats['cache_hits']} hits, {stats['cache_misses']} misses, {stats['error_count']} errores")
    except:
        pass
        
    return results

# Modificación para main.py
# Esta versión incluye más validaciones y mensajes de depuración

def analyze_stock_flexible_thread_safe(symbol, main_db_path=None):
    """
    A thread-safe version of analyze_stock_flexible that creates its own database connection.
    Optimizada para minimizar llamadas a API cuando se reducen los intervalos de tiempo.
    
    Args:
        symbol: Stock symbol to analyze
        main_db_path: Path to the database file
        
    Returns:
        (bool, str): Tuple with (alert_generated, alert_message)
    """
    # Importar get_last_data_from_db de database.operations
    from database.operations import get_last_data_from_db

    # Create a new connection specific to this thread
    db_connection = None
    if main_db_path:
        try:
            db_connection = create_connection(main_db_path)
        except Exception as e:
            logger.error(f"Error al crear la conexión a la base de datos. {symbol}: {e}")
    
    try:
        # Comprobar si hay datos recientes en la base de datos antes de solicitar nuevos
        if db_connection:
            from_db = True
            last_data = get_last_data_from_db(db_connection, symbol, limit=200)
            
            # Si hay datos en la BD y son recientes (menos de 5 minutos), prioritizar esos datos
            if last_data is not None and not last_data.empty:
                last_data_time = last_data.index[-1]
                current_time = pd.Timestamp.now(tz=last_data_time.tz)
                data_age = (current_time - last_data_time).total_seconds() / 60
                
                if data_age < 5:  # Datos de menos de 5 minutos
                    logger.info(f"Usando datos recientes de BD para {symbol} (de hace {data_age:.1f} minutos)")
                    data = last_data
                    from_db = True
                else:
                    logger.info(f"Datos de BD para {symbol} demasiado antiguos ({data_age:.1f} min). Obteniendo nuevos datos.")
                    from_db = False
            else:
                logger.info(f"No hay datos recientes en BD para {symbol}. Obteniendo nuevos datos.")
                from_db = False
        else:
            from_db = False
        
        # Si no hay datos recientes en BD, obtener nuevos datos
        if not from_db:
            # Get data combining historical and new if possible
            logger.info(f"Obteniendo datos para {symbol}...")
            data = get_stock_data(symbol, period='1d', interval='5m', 
                                db_connection=db_connection, 
                                only_new=(db_connection is not None))
        
        if data is None or data.empty or len(data) < 22:
            logger.warning(f"Datos insuficientes para analizar {symbol}")
            return False, f"Datos insuficientes de {symbol}"
        
        logger.info(f"Datos obtenidos para {symbol}: {len(data)} registros")
        
        # Check if we already have all calculated indicators
        complete_indicators = all(col in data.columns for col in 
                                ['BB_INFERIOR', 'BB_MEDIA', 'BB_SUPERIOR', 
                                 'MACD', 'MACD_SIGNAL', 'MACD_HIST', 
                                 'RSI', 'RSI_K', 'RSI_D'])
        
        # If indicators are missing, calculate all
        if not complete_indicators:
            logger.info(f"Calculando indicadores técnicos para {symbol}...")
            data = calculate_bollinger(data, window=config.BOLLINGER_WINDOW, deviations=config.BOLLINGER_DEVIATIONS)
            data = calculate_macd(data, fast=config.MACD_FAST, slow=config.MACD_SLOW, signal=config.MACD_SIGNAL)
            data = calculate_stochastic_rsi(data, rsi_period=config.RSI_PERIOD, 
                                          k_period=config.STOCH_RSI_K_PERIOD, 
                                          d_period=config.STOCH_RSI_D_PERIOD, 
                                          smooth=config.STOCH_RSI_SMOOTH)
            logger.info(f"Indicadores calculados para {symbol}")
        
        # Save historical data if there's a DB connection and we have new data
        if db_connection and not from_db:
            save_historical_data(db_connection, symbol, data)
        
        # Detect flexible sequence of signals (maximum 5 candles or 25 minutes between first and last)
        logger.info(f"Detectando secuencia de señales para {symbol}...")
        sequence_detected, details = detect_signal_sequence(data, max_window=5)
        
        if sequence_detected:
            logger.info(f"Detección de señal para {symbol}: {details}")
            
            # Import here to avoid circular imports
            from notifications.formatter import generate_flexible_alert_message
            
            # Use the MACD index (the last signal) to generate the alert
            logger.info(f"Generando mensaje de alerta para {symbol}...")
            message = generate_flexible_alert_message(symbol, data, details)
            
            # Save alert to the database if there's a connection
            if db_connection:
                macd_index = details.get("indice_macd", -1)
                save_alert_to_db(db_connection, symbol, data, macd_index, message, "sequence")
            
            # Verificar integración con Trading212
            if trading212_integrator.is_initialized():
                logger.info(f"Enviando alerta para {symbol} a Trading212...")
                trading_result = trading212_integrator.process_alert(symbol, message)
                
                if trading_result:
                    logger.info(f"Alerta para {symbol} procesada por Trading212")
                else:
                    logger.warning(f"Error al procesar alerta para {symbol} en Trading212")
            else:
                logger.debug(f"Integración con Trading212 no inicializada, no se procesa alerta para {symbol}")
            
            return True, message
        else:
            logger.info(f"Secuencia no detectada para {symbol}: {details.get('mensaje', '')}")
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Error analyzing {symbol}: {str(e)}"
    finally:
        # Always close the connection when done
        if db_connection:
            try:
                db_connection.close()
                logger.debug(f"Closed database connection for {symbol}")
            except Exception as e:
                logger.error(f"Error closing database connection for {symbol}: {e}")


def run_continuous_checks(interval_minutes=None):
    """
    Runs checks continuously in a separate thread.
    Optimizada para intervalos más cortos sin sobrecarga de API.
    
    Args:
        interval_minutes: Interval between checks in minutes (usa el valor de config si es None)
    """
    # Si no se especifica un intervalo, usar el valor predeterminado de config
    if interval_minutes is None:
        interval_minutes = config.CHECK_INTERVAL_MINUTES
    
    # Variables para control de integridad y rotación de logs
    last_integrity_check = 0
    last_log_rotation = 0
    
    # Variables para adaptarse a la carga
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    logger.info(f"Iniciando verificaciones periódicas cada {interval_minutes:.2f} minutos")
    
    while running:
        try:
            start_time = time.time()
            
            # Create a fresh connection for each check cycle
            connection = create_connection(config.DB_PATH)
            if connection:
                logger.debug(f"Database connection created for this check cycle")
                # Create tables if they don't exist
                create_tables(connection)
            
            # Check log rotation (once a day)
            if start_time - last_log_rotation > 86400:  # 24 hours in seconds
                rotate_logs(config.LOG_MAX_FILES, config.LOG_ROTATION_DAYS)
                last_log_rotation = start_time
            
            # Verify data integrity (once a day)
            if start_time - last_integrity_check > config.INTEGRITY_CHECK_INTERVAL_SECONDS:
                logger.info("Running periodic data integrity check")
                # Use a separate connection for integrity check
                integrity_connection = create_connection(config.DB_PATH)
                if integrity_connection:
                    # Solo verificar un subconjunto aleatorio de acciones para no sobrecargar
                    import random
                    full_list = config.get_stock_list()
                    check_symbols = random.sample(full_list, min(10, len(full_list)))
                    check_data_integrity(integrity_connection, check_symbols)
                    integrity_connection.close()
                last_integrity_check = start_time
            
            # Normal stock check with spacing
            check_result = check_stocks_spaced(connection)
            
            # Si hay resultado exitoso, resetear contador de errores
            if check_result:
                consecutive_errors = 0
            
            # Close connection after checks
            if connection:
                connection.close()
                connection = None
                logger.debug("Database connection closed after check cycle")
            
            # Calculate how long to wait until the next check
            elapsed_time = time.time() - start_time
            wait_time = max(0, interval_minutes * 60 - elapsed_time)
            
            # Adaptar el intervalo si hay muchas acciones para verificar o si hay carga alta
            stock_count = len(config.get_stock_list())
            
            # Si el ciclo duró demasiado tiempo en relación al intervalo deseado, adaptar
            if elapsed_time > interval_minutes * 60 * 0.8:
                logger.warning(f"Ciclo de verificación demasiado largo ({elapsed_time:.1f} seg). Ajustando...")
                # Añadir un tiempo mínimo de espera para no sobrecalentar el sistema
                wait_time = max(wait_time, 30)  # Al menos 30 segundos de espera
            
            # Check if the market is open before waiting
            if not is_market_open():
                logger.info(f"Market closed. {format_time_to_market_open()}")
                # If closed, wait until 5 minutes before next opening or the normal interval
                wait_time = min(wait_time, calculate_time_to_next_check())
            
            if wait_time > 0:
                logger.info(f"Ciclo completado en {elapsed_time:.1f} seg. Esperando {wait_time:.1f} segundos hasta el siguiente ciclo")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Error in the check loop: {e}")
            # Close connection if there was an error
            if connection:
                try:
                    connection.close()
                except:
                    pass
                connection = None
            
            # Incrementar contador de errores consecutivos
            consecutive_errors += 1
            
            # Si hay muchos errores consecutivos, incrementar tiempo de espera
            error_wait = 60 * min(consecutive_errors, max_consecutive_errors)
            logger.warning(f"Error #{consecutive_errors}. Esperando {error_wait} segundos antes de reintentar...")
            time.sleep(error_wait)

def calculate_time_to_next_check():
    """
    Calcula el tiempo hasta la próxima verificación, considerando los horarios del mercado.
    
    Returns:
        float: Tiempo en segundos hasta la próxima verificación
    """
    from market.utils import get_next_market_open
    
    next_open = get_next_market_open()
    now = datetime.datetime.now(pytz.timezone('America/New_York'))
    
    # Si el mercado abrirá en más de 8 horas, esperar en intervalos más largos
    time_to_open = (next_open - now).total_seconds()
    
    if time_to_open > 28800:  # 8 horas en segundos
        return 3600  # Verificar cada hora si falta mucho para la apertura
    elif time_to_open > 1800:  # 30 minutos en segundos
        return 900   # Verificar cada 15 minutos si está cerca de la apertura
    else:
        return 300   # Verificar cada 5 minutos si está muy cerca de la apertura

def create_database_backup():
    """
    Crea una copia de seguridad de la base de datos.
    """
    try:
        import shutil
        from datetime import datetime
        
        if not os.path.exists(config.DB_PATH):
            logger.warning("No se puede crear backup, la base de datos no existe.")
            return False
        
        # Crear nombre de archivo con fecha
        backup_file = os.path.join(
            config.DB_BACKUP_PATH, 
            f"stock_alerts_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        
        # Crear directorio de backup si no existe
        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
        
        # Copiar el archivo
        shutil.copy2(config.DB_PATH, backup_file)
        
        logger.info(f"Backup de base de datos creado: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"Error al crear backup de la base de datos: {e}")
        return False

def handle_command_line():
    """
    Procesa los argumentos de línea de comandos y ejecuta las acciones correspondientes.
    """
    parser = argparse.ArgumentParser(description='Sistema de Alertas Técnicas para Acciones')
    
    parser.add_argument('--test', action='store_true', help='Enviar mensaje de prueba a Telegram')
    parser.add_argument('--backup', action='store_true', help='Crear backup de la base de datos')
    parser.add_argument('--symbol', type=str, help='Analizar un símbolo específico')
    parser.add_argument('--interval', type=int, default=config.CHECK_INTERVAL_MINUTES, 
                        help=f'Intervalo de verificación en minutos (default: {config.CHECK_INTERVAL_MINUTES})')
    
    args = parser.parse_args()
    
    # Enviar mensaje de prueba a Telegram
    if args.test:
        logger.info("Enviando mensaje de prueba a Telegram...")
        result = send_telegram_test("SISTEMA DE ALERTAS TÉCNICAS ACTIVADO", 
                                  config.TELEGRAM_BOT_TOKEN, 
                                  config.TELEGRAM_CHAT_ID)
        if result:
            print("✅ Mensaje de prueba enviado correctamente")
        else:
            print("❌ Error al enviar mensaje de prueba")
        return result
    
    # Crear backup de la base de datos
    if args.backup:
        logger.info("Creando backup de la base de datos...")
        result = create_database_backup()
        if result:
            print("✅ Backup creado correctamente")
        else:
            print("❌ Error al crear backup")
        return result
    
    # Analizar un símbolo específico
    if args.symbol:
        logger.info(f"Analizando símbolo específico: {args.symbol}")
        connection = create_connection(config.DB_PATH)
        if connection:
            create_tables(connection)
        
        meets_conditions, message = analyze_stock_flexible(args.symbol, connection)
        
        if meets_conditions:
            print(f"✅ Se detectó señal para {args.symbol}")
            print("\nDetalles de la señal:")
            print(message)
            
            # Preguntar si se quiere enviar la alerta
            send_alert = input("\n¿Desea enviar esta alerta a Telegram? (s/n): ").lower()
            if send_alert == 's':
                send_telegram_alert(message, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
                print("✅ Alerta enviada")
        else:
            print(f"❌ No se detectó señal para {args.symbol}")
        
        if connection:
            connection.close()
        
        return
    
    # Si no hay argumentos específicos, iniciar el sistema completo
    logger.info(f"Iniciando sistema con intervalo de verificación de {args.interval} minutos")
    return args.interval


# Modificar la función main para inicializar Trading212
def main():
    """
    Main function of the system.
    """
    global running
    
    print("=" * 60)
    print(" SISTEMA DE ALERTAS TÉCNICAS PARA ACCIONES ")
    print("=" * 60)
    print(f"• Versión: 1.0.0")
    print(f"• Fecha: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"• Acciones monitoreadas: {len(config.get_stock_list())}")
    print("-" * 60)
    
    # Procesar argumentos de línea de comandos
    try:
        interval = 15.1  # Valor por defecto
        
        # Crear directorios necesarios
        for directory in [config.DATA_DIR, config.LOGS_DIR, config.DB_BACKUP_PATH]:
            os.makedirs(directory, exist_ok=True)
        
        # Crear copia de seguridad inicial de la base de datos si existe
        if os.path.exists(config.DB_PATH):
            create_database_backup()
            
        # Inicializar Trading212 con la API Key desde config
        api_key = config.TRADING212_API_KEY
        api_url = config.TRADING212_API_URL
        simulation_mode = config.SIMULATION_MODE  # Usar el valor de config

        if api_key:
            logger.info(f"Inicializando integración con Trading212 (URL: {api_url}, Modo: {'SIMULACIÓN' if simulation_mode else 'REAL'})")
            
            # Inicializar el módulo Trading212
            init_result = trading212_integrator.initialize(
                api_key=api_key, 
                api_url=api_url,
                simulation_mode=simulation_mode
            )
            
            if init_result:
                logger.info("Integración con Trading212 inicializada correctamente")
                
                # La integración ya se habilita automáticamente en el nuevo código
                logger.info("Integración con Trading212 habilitada")
            else:
                logger.error("No se pudo inicializar la integración con Trading212")
        else:
            logger.warning("No se ha configurado API_KEY para Trading212, integración deshabilitada")
        
        # Iniciar verificaciones continuas en un hilo independiente
        check_thread = threading.Thread(
            target=run_continuous_checks,
            args=(interval,),
            daemon=True
        )
        
        check_thread.start()
        
        # Mantener el programa en ejecución
        print("\nEl sistema está en funcionamiento. Presione Ctrl+C para detener.")
        
        # Bucle para mantener el programa en ejecución
        while True:
            time.sleep(60)  # Esperar 1 minuto
            
    except KeyboardInterrupt:
        print("\nDetención solicitada por el usuario.")
        running = False
        logger.info("Sistema detenido por el usuario")
        
        # Detener procesos de Trading212
        if trading212_integrator.is_initialized():
            trading212_integrator.stop_all_processes()
            logger.info("Procesos de Trading212 detenidos")


if __name__ == "__main__":
    main()