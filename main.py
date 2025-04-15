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

# Variables globales para controlar el estado del sistema
running = True
sent_alerts = {}  # Registro de alertas enviadas para evitar duplicados


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
    Verifies all stocks in the list with calls spaced over time to avoid API rate limits.
    
    Args:
        db_connection: Database connection (optional)
    """
    # Verify if the market is open
    if not is_market_open():
        logger.info("Mercado cerrado. No se realizarán verificaciones.")
        return
    
    logger.info("Iniciando verificación espaciada de acciones...")
    
    # Get updated list of stocks
    stocks = config.get_stock_list()
    results = {}
    
    # Calculate delay between stocks to spread checks across the interval
    # Use 75% of the interval to ensure we finish before the next check
    total_available_time = config.CHECK_INTERVAL_MINUTES * 60 * 0.75  # in seconds
    delay_between_stocks = total_available_time / len(stocks)
    
    logger.info(f"Espaciando verificaciones de acciones con {delay_between_stocks:.1f} segundos entre cada acción")
    
    for i, symbol in enumerate(stocks):
        try:
            logger.info(f"Analizando {symbol} ({i+1}/{len(stocks)})...")
            meets_conditions, message = analyze_stock_flexible_thread_safe(symbol, config.DB_PATH)
            
            if meets_conditions:
                # Check if we already sent an alert for this symbol in the last hour
                current_time = time.time()
                if symbol in sent_alerts:
                    last_alert = sent_alerts[symbol]
                    # Avoid sending more than one alert for the same symbol in 60 minutes
                    if current_time - last_alert < 3600:
                        logger.info(f"Alert for {symbol} already sent in the last hour. Skipping.")
                        results[symbol] = (False, "Alert already sent recently")
                        continue
                
                # Send alert via Telegram
                logger.info(f"Conditions met for {symbol}, sending alert")
                send_telegram_alert(message, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
                
                # Record the sending time of this alert
                sent_alerts[symbol] = current_time
                
                # As backup, save to file
                save_alert_to_file(message)
                
                # NUEVO: Enviar alerta a Trading212 si está inicializado
                if trading212_integrator.is_initialized():
                    logger.info(f"Enviando alerta para {symbol} a Trading212")
                    trading212_result = trading212_integrator.process_alert(symbol, message)
                    
                    if trading212_result:
                        logger.info(f"Alerta para {symbol} procesada por Trading212")
                    else:
                        logger.warning(f"Error al procesar alerta para {symbol} en Trading212")
                
                results[symbol] = (True, message)
            else:
                logger.info(f"Conditions not met for {symbol}")
                results[symbol] = (False, "Conditions not met")
                
            # Wait before checking the next stock, unless it's the last one
            if i < len(stocks) - 1:
                logger.info(f"Waiting {delay_between_stocks:.1f} seconds before checking next stock")
                time.sleep(delay_between_stocks)
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            results[symbol] = (False, f"Error: {str(e)}")
    
    return results


# Modificación para main.py
# Esta versión incluye más validaciones y mensajes de depuración

def analyze_stock_flexible_thread_safe(symbol, main_db_path=None):
    """
    A thread-safe version of analyze_stock_flexible that creates its own database connection.
    
    Args:
        symbol: Stock symbol to analyze
        main_db_path: Path to the database file
        
    Returns:
        (bool, str): Tuple with (alert_generated, alert_message)
    """
    # Create a new connection specific to this thread
    db_connection = None
    if main_db_path:
        try:
            db_connection = create_connection(main_db_path)
        except Exception as e:
            logger.error(f"Error al crear la conexión a la base de datos. {symbol}: {e}")
    
    try:
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
            data = calculate_bollinger(data, window=18, deviations=2.25)
            data = calculate_macd(data, fast=8, slow=21, signal=9)
            data = calculate_stochastic_rsi(data, rsi_period=14, k_period=14, d_period=3, smooth=3)
            logger.info(f"Indicadores calculados para {symbol}")
        
        # Save historical data if there's a DB connection
        if db_connection:
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
                logger.warning(f"Integración con Trading212 no inicializada, no se procesa alerta para {symbol}")
            
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


def run_continuous_checks(interval_minutes=20):
    """
    Runs checks continuously in a separate thread.
    
    Args:
        interval_minutes: Interval between checks in minutes
    """
    # Create database connection
    connection = None  # We'll create a new connection for each check
    
    # Integrity check control (once a day)
    last_integrity_check = 0
    last_log_rotation = 0
    
    while running:
        try:
            start_time = time.time()
            
            # Create a fresh connection for each check cycle
            connection = create_connection(config.DB_PATH)
            if connection:
                logger.info(f"Database connection created for this check cycle")
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
                    check_data_integrity(integrity_connection, config.get_stock_list())
                    integrity_connection.close()
                last_integrity_check = start_time
            
            # Normal stock check with spacing
            check_stocks_spaced(connection)
            
            # Close connection after checks
            if connection:
                connection.close()
                connection = None
                logger.info("Database connection closed after check cycle")
            
            # Calculate how long to wait until the next check
            elapsed_time = time.time() - start_time
            wait_time = max(0, interval_minutes * 60 - elapsed_time)
            
            # Check if the market is open before waiting
            if not is_market_open():
                logger.info(f"Market closed. {format_time_to_market_open()}")
                # If closed, wait until 5 minutes before next opening or the normal interval
                wait_time = min(wait_time, calculate_time_to_next_check())
            
            if wait_time > 0:
                logger.info(f"Waiting {wait_time:.1f} seconds until next check cycle")
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
            # Wait one minute before retrying in case of error
            time.sleep(60)

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
        
        if api_key:
            logger.info(f"Inicializando integración con Trading212 usando API URL: {api_url}")
            init_result = trading212_integrator.initialize(api_key=api_key)
            
            if init_result:
                logger.info("Integración con Trading212 inicializada correctamente")
                # Solo habilitar si se inicializó correctamente
                enable_result = trading212_integrator.enable_integration()
                if enable_result:
                    logger.info("Integración con Trading212 habilitada correctamente")
                else:
                    logger.error("No se pudo habilitar la integración con Trading212")
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