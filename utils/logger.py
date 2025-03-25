"""
Configuración del sistema de logging.
"""
import logging
import codecs
import re
import time
import os
from datetime import datetime

# Asegurar que el directorio de logs existe
logs_dir = 'logs'
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# Configuración básica del logger
def setup_logger():
    """
    Configura y devuelve el logger para la aplicación.
    """
    # Crear formato para el logger
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Crear el logger con nivel INFO
    local_logger = logging.getLogger('stock_alerts')
    local_logger.setLevel(logging.INFO)
    
    # Evitar duplicación de handlers
    if not local_logger.handlers:
        # Handler para la consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        local_logger.addHandler(console_handler)
        
        # Handler para archivo de log
        log_file = os.path.join(logs_dir, f'stock_alerts_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        local_logger.addHandler(file_handler)
    
    return local_logger

# Crear y obtener el logger
logger = setup_logger()

def save_alert_to_file(message, filename=None):
    """
    Guarda una alerta en un archivo (como respaldo).
    
    Args:
        message: Contenido del mensaje
        filename: Nombre del archivo (opcional)
        
    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    try:
        # Si no se especifica un nombre de archivo, usar la fecha actual
        if filename is None:
            filename = os.path.join(logs_dir, f"alerts_{datetime.now().strftime('%Y%m%d')}.log")
        
        # Crear el directorio si no existe
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        
        # Usar codecs para abrir el archivo con codificación UTF-8
        with codecs.open(filename, "a", "utf-8") as file:
            file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        
        logger.info(f"Alerta guardada en archivo: {filename}")
        return True
    except Exception as e:
        logger.error(f"Error al guardar la alerta en el archivo: {e}")
        
        # Si falla, intentar guardar una versión simplificada sin emojis o HTML
        try:
            simple_message = re.sub(r'<[^>]*>', '', message)  # Eliminar HTML
            simple_message = re.sub(r'[^\x00-\x7F]+', '', simple_message)  # Eliminar no-ASCII
            
            with open(filename, "a") as file:
                file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [SIMPLIFICADO] {simple_message}\n")
            
            logger.info(f"Versión simplificada de la alerta guardada en archivo: {filename}")
            return True
        except Exception as e2:
            logger.error(f"También falló al guardar la versión simplificada: {e2}")
            return False

def rotate_logs(max_files=10, max_days=30):
    """
    Rota los archivos de log para mantener el espacio en disco.
    Elimina logs más antiguos que max_days y mantiene solo max_files.
    
    Args:
        max_files: Número máximo de archivos de log a mantener
        max_days: Edad máxima en días de los archivos de log
    """
    try:
        files = []
        for file in os.listdir(logs_dir):
            if file.endswith('.log'):
                full_path = os.path.join(logs_dir, file)
                creation_time = os.path.getctime(full_path)
                files.append((full_path, creation_time))
        
        # Ordenar por tiempo de creación (el más antiguo primero)
        files.sort(key=lambda x: x[1])
        
        # Eliminar archivos más antiguos que max_days
        current_time = time.time()
        for file_path, creation_time in files:
            # Si el archivo tiene más de max_days días
            if (current_time - creation_time) / (60*60*24) > max_days:
                os.remove(file_path)
                logger.info(f"Log antiguo eliminado: {file_path}")
        
        # Si todavía hay más archivos que max_files, eliminar los más antiguos
        files = []
        for file in os.listdir(logs_dir):
            if file.endswith('.log'):
                full_path = os.path.join(logs_dir, file)
                creation_time = os.path.getctime(full_path)
                files.append((full_path, creation_time))
        
        files.sort(key=lambda x: x[1])
        
        if len(files) > max_files:
            files_to_delete = files[:len(files) - max_files]
            for file_path, _ in files_to_delete:
                os.remove(file_path)
                logger.info(f"Log excedente eliminado: {file_path}")
        
    except Exception as e:
        logger.error(f"Error en la rotación de logs: {e}")