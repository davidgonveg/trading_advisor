"""
Paquete para manejo de la base de datos SQLite del sistema de alertas de acciones.
"""
from .connection import create_connection, create_tables
from .operations import (
    get_last_data_from_db, 
    save_alert_to_db, 
    save_historical_data,
    check_data_integrity
)