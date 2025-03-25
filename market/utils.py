"""
Utilidades relacionadas con el mercado de valores.
"""
import datetime
import pytz
from utils.logger import logger

def is_market_open():
    """
    Verifica si el mercado estadounidense está actualmente abierto o dentro 
    de los 45 minutos antes de la apertura.
    
    Returns:
        bool: True si el mercado está abierto o a punto de abrir, False en caso contrario
    """
    # Zona horaria de Nueva York (mercado estadounidense)
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    
    # Comprobar si es fin de semana (0 es lunes, 6 es domingo)
    if now.weekday() >= 5:  # Sábado o domingo
        return False
    
    # Horario regular del mercado (9:30 AM - 4:00 PM ET)
    opening_time = datetime.time(9, 30)
    closing_time = datetime.time(16, 0)
    
    # Hora para empezar a monitorizar (45 minutos antes de la apertura)
    pre_market_time = datetime.time(8, 45)  # 9:30 - 0:45 = 8:45 AM
    
    current_time = now.time()
    
    # Comprobar si estamos en horario de mercado o en los 45 minutos anteriores
    return pre_market_time <= current_time <= closing_time

def get_next_market_open():
    """
    Calcula la próxima apertura del mercado.
    
    Returns:
        datetime: Fecha y hora de la próxima apertura del mercado
    """
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    
    # Hora de apertura del mercado (9:30 AM ET)
    market_open = datetime.time(9, 30)
    
    # Calcular la próxima fecha de apertura
    next_day = now.date()
    
    # Si ya pasó la hora de apertura, avanzar al siguiente día
    if now.time() >= market_open:
        next_day += datetime.timedelta(days=1)
    
    # Ajustar para skip fines de semana
    day_of_week = next_day.weekday()  # 0 es lunes, 6 es domingo
    
    # Si es sábado, avanzar 2 días al lunes
    if day_of_week == 5:  # Sábado
        next_day += datetime.timedelta(days=2)
    # Si es domingo, avanzar 1 día al lunes
    elif day_of_week == 6:  # Domingo
        next_day += datetime.timedelta(days=1)
    
    # Combinar fecha y hora
    next_open = datetime.datetime.combine(next_day, market_open)
    next_open = ny_tz.localize(next_open)
    
    return next_open

def get_market_hours_today():
    """
    Obtiene las horas de apertura y cierre del mercado para hoy.
    
    Returns:
        tuple: (datetime de apertura, datetime de cierre) o (None, None) si hoy está cerrado
    """
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    
    # Comprobar si es fin de semana
    if now.weekday() >= 5:  # Sábado o domingo
        return None, None
    
    # Horario regular del mercado (9:30 AM - 4:00 PM ET)
    today = now.date()
    opening_time = datetime.time(9, 30)
    closing_time = datetime.time(16, 0)
    
    # Crear datetime para apertura y cierre de hoy
    market_open = ny_tz.localize(datetime.datetime.combine(today, opening_time))
    market_close = ny_tz.localize(datetime.datetime.combine(today, closing_time))
    
    return market_open, market_close

def format_time_to_market_open():
    """
    Formatea el tiempo restante hasta la próxima apertura del mercado.
    
    Returns:
        str: Mensaje formateado con el tiempo restante
    """
    next_open = get_next_market_open()
    now = datetime.datetime.now(pytz.timezone('America/New_York'))
    
    time_to_open = next_open - now
    
    # Formatear el tiempo restante
    days = time_to_open.days
    hours, remainder = divmod(time_to_open.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    if days > 0:
        return f"{days} día(s), {hours} hora(s) y {minutes} minuto(s) hasta la apertura del mercado"
    else:
        return f"{hours} hora(s) y {minutes} minuto(s) hasta la apertura del mercado"