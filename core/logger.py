import logging
import sys
from pathlib import Path
from config.settings import SYSTEM_CONFIG, LOG_DIR

def setup_logger(name: str, log_file: str = "system.log") -> logging.Logger:
    """
    Configure and return a logger instance.
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers
    if logger.hasHandlers():
        return logger
        
    level = getattr(logging, SYSTEM_CONFIG["LOG_LEVEL"].upper(), logging.INFO)
    logger.setLevel(level)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    file_path = LOG_DIR / log_file
    file_handler = logging.FileHandler(file_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger
