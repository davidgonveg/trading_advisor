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
from utils.logger import logger, rotate_logs
from database.connection import create_connection, create_tables
from database.operations import check_data_integrity
from market.utils import is_market_open, format_time_to_market_open
from market.data import get_stock_data
from analysis.detector import analyze_stock_flexible
from analysis.market_type import detect_market_type
from notifications.telegram import send_telegram_alert, send_telegram_test, send_market_status_notification
from notifications.formatter import format_weekly_summary
import config

# Variables globales para controlar el estado del sistema
running = True
sent_alerts = {}  # Registro de alertas enviadas para evitar duplicados

def check_stocks(db_connection=None):
    """
    Verifica todas las acciones en la lista actualizada y envía alertas si se cumplen las condiciones.
    
    Args:
        db_connection: Conexión a la base de datos (opcional)
    """
    # Verificar si el mercado está abierto
    if not is_market_open():
        logger.info("Mercado cerrado. No se realizarán verificaciones.")
        return
    
    logger.info("Verificando acciones...")
    
    # Obtener lista actualizada de acciones
    stocks = config.get_stock_list()
    
    # Usar threads para acelerar las comprobaciones
    threads = []
    results = {}
    
    def analyze_stock_thread(symbol):
        try:
            meets_conditions, message = analyze_stock_flexible(symbol, db_connection)
            results[symbol] = (meets_conditions, message)
        except Exception as e:
            logger.error(f"Error procesando {symbol} en thread: {e}")
            results[symbol] = (False, f"Error: {str(e)}")
    
    # Crear y iniciar threads para cada acción (limitando el número máximo de threads)
    max_threads = min(config.MAX_THREADS, len(stocks))
    
    for i in range(0, len(stocks), max_threads):
        batch = stocks[i:i+max_threads]
        threads = []
        
        for symbol in batch:
            thread = threading.Thread(target=analyze_stock_thread, args=(symbol,))
            threads.append(thread)
            thread.start()
        
        # Esperar a que todos los threads terminen
        for thread in threads:
            thread.join()
    
    # Procesar resultados y enviar alertas
    for symbol, (meets_conditions, message) in results.items():
        if meets_conditions:
            # Verificar si ya enviamos una alerta para este símbolo en la última hora
            current_time = time.time()
            if symbol in sent_alerts:
                last_alert = sent_alerts[symbol]
                # Evitar enviar más de una alerta para el mismo símbolo en 60 minutos
                if current_time - last_alert < 3600:
                    logger.info(f"Alerta para {symbol} ya enviada en la última hora. Omitiendo.")
                    continue
            
            # Enviar alerta vía Telegram
            logger.info(f"Condiciones cumplidas para {symbol}, enviando alerta")
            send_telegram_alert(message, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
            
            # Registrar el tiempo de envío de esta alerta
            sent_alerts[symbol] = current_time
            
            # Como respaldo, guardar en archivo
            from utils.logger import save_alert_to_file
            save_alert_to_file(message)
            
            # Esperar 2 segundos entre cada envío para evitar sobrecargar la API de Telegram
            time.sleep(2)
        else:
            logger.info(f"Condiciones no cumplidas para {symbol}")

def run_continuous_checks(interval_minutes=20):
    """
    Ejecuta verificaciones continuamente en un hilo separado.
    
    Args:
        interval_minutes: Intervalo entre verificaciones en minutos
    """
    # Crear conexión a la base de datos
    connection = create_connection(config.DB_PATH)
    if connection:
        # Crear tablas si no existen
        create_tables(connection)
        logger.info(f"Base de datos inicializada: {config.DB_PATH}")
    else:
        logger.warning("No se pudo crear conexión a la base de datos. Continuando sin BD.")
    
    # Control de verificación de integridad (una vez al día)
    last_integrity_check = 0
    last_log_rotation = 0
    
    # Realizar verificación inicial del estado del mercado
    try:
        # Usar el S&P 500 como referencia para el estado general del mercado
        market_data = get_stock_data('SPY', period='5d', interval='1d')
        if market_data is not None and not market_data.empty:
            market_type = detect_market_type(market_data)
            send_market_status_notification(market_type, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    except Exception as e:
        logger.error(f"Error al verificar estado inicial del mercado: {e}")
    
    while running:
        try:
            start_time = time.time()
            
            # Renovar conexión a BD si es necesario
            if connection:
                try:
                    # Probar si la conexión sigue activa
                    connection.execute("SELECT 1")
                except:
                    logger.warning("Conexión a BD perdida. Reconectando...")
                    connection = create_connection(config.DB_PATH)
                    if connection:
                        logger.info("Reconexión a BD exitosa")
            
            # Verificar rotación de logs (una vez al día)
            if start_time - last_log_rotation > 86400:  # 24 horas en segundos
                rotate_logs(config.LOG_MAX_FILES, config.LOG_ROTATION_DAYS)
                last_log_rotation = start_time
            
            # Verificar integridad de datos (una vez al día)
            if start_time - last_integrity_check > config.INTEGRITY_CHECK_INTERVAL_SECONDS:
                logger.info("Ejecutando verificación periódica de integridad de datos")
                check_data_integrity(connection, config.get_stock_list())
                last_integrity_check = start_time
            
            # Verificación normal de acciones
            check_stocks(connection)
            
            # Calcular cuánto esperar hasta la próxima verificación
            elapsed_time = time.time() - start_time
            wait_time = max(0, interval_minutes * 60 - elapsed_time)
            
            # Verificar si el mercado está abierto antes de esperar
            if not is_market_open():
                logger.info(f"Mercado cerrado. {format_time_to_market_open()}")
                # Si está cerrado, esperar hasta 5 minutos antes de la próxima apertura o el intervalo normal
                wait_time = min(wait_time, calculate_time_to_next_check())
            
            if wait_time > 0:
                logger.info(f"Esperando {wait_time:.1f} segundos hasta la próxima verificación")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Error en el bucle de verificación: {e}")
            # Esperar un minuto antes de reintentar en caso de error
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

def main():
    """
    Función principal del sistema.
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
    interval = handle_command_line()
    
    # Si se ejecutó un comando específico, terminar
    if interval is None or not isinstance(interval, int):
        return
    
    try:
        # Crear directorios necesarios si no existen
        for directory in [config.DATA_DIR, config.LOGS_DIR, config.DB_BACKUP_PATH]:
            os.makedirs(directory, exist_ok=True)
        
        # Crear backup inicial de la base de datos si existe
        if os.path.exists(config.DB_PATH):
            create_database_backup()
        
        # Iniciar verificaciones continuas en un hilo independiente
        check_thread = threading.Thread(
            target=run_continuous_checks,
            args=(interval,),
            daemon=True
        )
        
        check_thread.start()
        
        # Mantener el programa en ejecución
        print("\nSistema en ejecución. Presione Ctrl+C para detener.")
        while check_thread.is_alive():
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nDetención solicitada por el usuario.")
        running = False
        logger.info("Sistema detenido por el usuario")
    except Exception as e:
        print(f"\nError: {e}")
        logger.error(f"Error en el sistema: {e}")
    finally:
        # Asegurar la correcta finalización
        running = False
        print("\nSistema finalizado.")

if __name__ == "__main__":
    main()