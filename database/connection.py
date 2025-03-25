"""
Funciones para manejar la conexión a la base de datos SQLite.
"""
import sqlite3
from sqlite3 import Error
from utils.logger import logger

def create_connection(db_path="stock_alerts.db"):
    """
    Crea una conexión a la base de datos SQLite.
    
    Args:
        db_path: Ruta al archivo de la base de datos
        
    Returns:
        Connection: Conexión a la base de datos o None
    """
    connection = None
    try:
        connection = sqlite3.connect(db_path)
        return connection
    except Error as e:
        logger.error(f"Error al conectar a la base de datos: {e}")
        return None

def create_tables(connection):
    """
    Crea las tablas necesarias en la base de datos.
    
    Args:
        connection: Conexión a la base de datos
    """
    try:
        cursor = connection.cursor()
        
        # Tabla para almacenar alertas
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
        
        # Tabla para almacenar datos históricos
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
        logger.info("Tablas creadas correctamente")
    except Error as e:
        logger.error(f"Error al crear las tablas: {e}")