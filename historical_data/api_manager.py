#!/usr/bin/env python3
"""
🔄 API MANAGER - SISTEMA DE ROTACIÓN INTELIGENTE V3.0
==================================================

Sistema que gestiona múltiples APIs de datos financieros:
- Yahoo Finance (sin límites)
- Alpha Vantage (500 requests/día)
- Twelve Data (800 requests/día)  
- Polygon.io (100 requests/día)

CARACTERÍSTICAS:
- Rotación automática si una API falla
- Rate limiting inteligente por API
- Tracking de uso diario
- Retry automático con backoff exponencial
- Performance monitoring en tiempo real
"""

import sys
import os
import time
import json
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
from dataclasses import dataclass, asdict
from enum import Enum

# =============================================================================
# 🔧 SOLUCION DE IMPORTS - COMPATIBLE STANDALONE Y MÓDULO
# =============================================================================
def setup_imports():
    """Configurar imports para funcionar standalone y como módulo"""
    # Obtener directorio actual del script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Agregar directorio historical_data al path si no está
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # Agregar directorio padre (trading_system) al path
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

# Ejecutar setup de imports
setup_imports()

# Importar configuración con fallback
try:
    # Intentar import relativo (cuando se usa como módulo)
    from . import config
except ImportError:
    try:
        # Import absoluto desde historical_data
        import config
    except ImportError:
        # Fallback: cargar desde directorio actual
        import sys
        import importlib.util
        config_path = os.path.join(os.path.dirname(__file__), 'config.py')
        spec = importlib.util.spec_from_file_location("config", config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)

# =============================================================================
# 🔄 CONFIGURACION DE RATE LIMITS COMPARTIDOS
# =============================================================================

# Rate limits compartidos entre sistema principal e histórico
RATE_LIMITS_SHARED = {
    'YAHOO': 1.0,           # 1 seg entre requests (conservador para datos históricos)
    'ALPHA_VANTAGE': 13.0,  # 13 seg = ~5 requests/min (respeta límite oficial)
    'TWELVE_DATA': 2.0,     # 2 seg = 30 requests/min (muy conservador)
    'POLYGON': 15.0,        # 15 seg = 4 requests/min (ultra conservador)
}

# Configurar logging con fallback seguro
try:
    log_level = getattr(logging, config.LOGGING_CONFIG.get('level', 'INFO'), logging.INFO)
except (AttributeError, KeyError):
    log_level = logging.INFO

logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

class APIStatus(Enum):
    """Estados de las APIs"""
    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    QUOTA_EXCEEDED = "quota_exceeded"
    UNAVAILABLE = "unavailable"

@dataclass
class APIUsage:
    """Tracking de uso de API por día"""
    api_name: str
    date: str  # YYYY-MM-DD
    requests_made: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    total_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    status: APIStatus = APIStatus.AVAILABLE
    
    @property
    def avg_response_time(self) -> float:
        """Tiempo promedio de respuesta"""
        if self.requests_made > 0:
            return self.total_response_time / self.requests_made
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """Tasa de éxito"""
        if self.requests_made > 0:
            return (self.requests_successful / self.requests_made) * 100
        return 0.0
    
    def can_make_request(self) -> bool:
        """¿Puede hacer más requests hoy?"""
        daily_limit = config.DAILY_LIMITS.get(self.api_name.upper(), 0)
        if daily_limit == 0:  # Sin límite (como Yahoo)
            return True
        return self.requests_made < daily_limit
    
    def time_until_next_request(self) -> float:
        """Segundos hasta que puede hacer próximo request (rate limit compartido)"""
        if not self.last_request_time:
            return 0.0
        
        rate_limit = RATE_LIMITS_SHARED.get(self.api_name.upper(), 1.0)
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        return max(0.0, rate_limit - elapsed)

class APIManager:
    """
    Gestor principal de APIs con rotación inteligente
    """
    
    def __init__(self):
        """Inicializar API Manager"""
        self.usage_stats: Dict[str, APIUsage] = {}
        self.api_status: Dict[str, APIStatus] = {}
        self.usage_file = "historical_data/logs/api_usage.json"
        
        # Asegurar que directorio de logs existe
        os.makedirs(os.path.dirname(self.usage_file), exist_ok=True)
        
        # Cargar estadísticas previas
        self.load_usage_stats()
        
        # Inicializar estado de APIs
        self.initialize_api_status()
        
        logger.info("🔄 API Manager inicializado")
        logger.info(f"📊 APIs disponibles: {self.get_available_apis()}")
    
    def initialize_api_status(self):
        """Inicializar estado de todas las APIs"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        for api_name in config.API_PRIORITY:
            # Verificar si API está configurada
            if config.is_api_available(api_name):
                self.api_status[api_name] = APIStatus.AVAILABLE
            else:
                self.api_status[api_name] = APIStatus.UNAVAILABLE
                logger.warning(f"⚠️ {api_name}: No configurada (falta API key)")
            
            # Crear stats del día si no existen
            stats_key = f"{api_name}_{today}"
            if stats_key not in self.usage_stats:
                self.usage_stats[stats_key] = APIUsage(api_name, today)
    
    def get_available_apis(self) -> List[str]:
        """Obtener lista de APIs disponibles ordenada por prioridad"""
        available = []
        for api in config.API_PRIORITY:
            if (api in self.api_status and 
                self.api_status[api] in [APIStatus.AVAILABLE, APIStatus.RATE_LIMITED]):
                available.append(api)
        return available
    
    def get_best_api(self) -> Optional[str]:
        """Obtener la mejor API disponible"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        best_api = None
        best_score = -1
        
        for api_name in self.get_available_apis():
            stats_key = f"{api_name}_{today}"
            usage = self.usage_stats.get(stats_key)
            
            if not usage or not usage.can_make_request():
                continue
            
            # Calcular score basado en success rate y response time
            score = usage.success_rate - (usage.avg_response_time * 10)
            
            # Bonus para Yahoo (sin límites)
            if api_name == 'YAHOO':
                score += 50
            
            if score > best_score:
                best_score = score
                best_api = api_name
        
        return best_api
    
    def record_request(self, api_name: str, success: bool, response_time: float, 
                      error_msg: str = None):
        """Registrar resultado de request"""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_key = f"{api_name}_{today}"
        
        if stats_key not in self.usage_stats:
            self.usage_stats[stats_key] = APIUsage(api_name, today)
        
        usage = self.usage_stats[stats_key]
        usage.requests_made += 1
        usage.total_response_time += response_time
        usage.last_request_time = datetime.now()
        
        if success:
            usage.requests_successful += 1
            usage.status = APIStatus.AVAILABLE
        else:
            usage.requests_failed += 1
            
            # Analizar tipo de error
            if error_msg and ("rate" in error_msg.lower() or "limit" in error_msg.lower()):
                usage.status = APIStatus.RATE_LIMITED
                self.api_status[api_name] = APIStatus.RATE_LIMITED
            elif error_msg and ("quota" in error_msg.lower() or "exceeded" in error_msg.lower()):
                usage.status = APIStatus.QUOTA_EXCEEDED
                self.api_status[api_name] = APIStatus.QUOTA_EXCEEDED
            else:
                usage.status = APIStatus.FAILED
                
        # Guardar stats periódicamente
        if usage.requests_made % 10 == 0:
            self.save_usage_stats()
    
    def make_request(self, api_name: str, url: str, params: Dict, 
                    timeout: int = 30) -> Tuple[bool, Optional[Dict], str]:
        """
        Hacer request a una API específica con rate limiting
        
        Returns:
            Tuple[success, data, error_message]
        """
        today = datetime.now().strftime('%Y-%m-%d')
        stats_key = f"{api_name}_{today}"
        
        # Verificar si puede hacer request
        usage = self.usage_stats.get(stats_key)
        if usage and not usage.can_make_request():
            error_msg = f"Cuota diaria excedida para {api_name}"
            return False, None, error_msg
        
        # Aplicar rate limiting
        if usage:
            wait_time = usage.time_until_next_request()
            if wait_time > 0:
                logger.info(f"⏳ Rate limit {api_name}: esperando {wait_time:.1f}s")
                time.sleep(wait_time)
        
        start_time = time.time()
        
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    self.record_request(api_name, True, response_time)
                    return True, data, ""
                    
                except json.JSONDecodeError as e:
                    error_msg = f"Error parsing JSON: {e}"
                    self.record_request(api_name, False, response_time, error_msg)
                    return False, None, error_msg
            
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                self.record_request(api_name, False, response_time, error_msg)
                return False, None, error_msg
                
        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            error_msg = f"Timeout después de {timeout}s"
            self.record_request(api_name, False, response_time, error_msg)
            return False, None, error_msg
            
        except requests.exceptions.ConnectionError as e:
            response_time = time.time() - start_time
            error_msg = f"Error de conexión: {str(e)[:100]}"
            self.record_request(api_name, False, response_time, error_msg)
            return False, None, error_msg
            
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = f"Error inesperado: {str(e)[:100]}"
            self.record_request(api_name, False, response_time, error_msg)
            return False, None, error_msg
    
    def make_request_with_fallback(self, url_configs: Dict[str, Tuple[str, Dict]], 
                                  timeout: int = 30, max_attempts: int = 3) -> Tuple[bool, Optional[Dict], str]:
        """
        Hacer request con fallback automático entre APIs
        
        Args:
            url_configs: Dict {api_name: (url, params)}
            timeout: Timeout por request
            max_attempts: Intentos máximos por API
            
        Returns:
            Tuple[success, data, source_api_used]
        """
        available_apis = self.get_available_apis()
        
        for api_name in available_apis:
            if api_name not in url_configs:
                continue
                
            url, params = url_configs[api_name]
            
            # Intentar con esta API
            for attempt in range(max_attempts):
                success, data, error = self.make_request(api_name, url, params, timeout)
                
                if success:
                    logger.info(f"✅ Request exitoso con {api_name} (intento {attempt + 1})")
                    return True, data, api_name
                
                # Si falló, esperar antes del próximo intento
                if attempt < max_attempts - 1:
                    wait_time = 2 ** attempt  # Backoff exponencial: 1s, 2s, 4s
                    logger.warning(f"⚠️ {api_name} intento {attempt + 1} falló: {error}")
                    logger.info(f"⏳ Esperando {wait_time}s antes del próximo intento...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ {api_name}: Todos los intentos fallaron")
        
        logger.error("💥 Todas las APIs fallaron")
        return False, None, "ALL_APIS_FAILED"
    
    def get_data(self, symbol: str, interval: str = '15m', period: str = '1mo') -> Tuple[bool, Optional[Dict], str]:
        """
        Obtener datos con fallback automático entre todas las APIs disponibles
        
        Args:
            symbol: Símbolo a consultar (ej: 'AAPL')
            interval: Intervalo (15m, 1h, 1d, etc.)
            period: Período (1d, 5d, 1mo, 3mo, 1y, etc.)
            
        Returns:
            Tuple[success, data, source_api_used]
        """
        # Configurar URLs para cada API
        url_configs = {}
        
        # Yahoo Finance
        if config.is_api_available('YAHOO'):
            url_configs['YAHOO'] = (
                f"{config.API_ENDPOINTS['YAHOO']}{symbol}",
                {
                    'interval': interval,
                    'period': period,
                    'includePrePost': 'false'
                }
            )
        
        # Alpha Vantage
        if config.is_api_available('ALPHA_VANTAGE'):
            function = 'TIME_SERIES_INTRADAY' if interval != '1d' else 'TIME_SERIES_DAILY'
            av_params = {
                'function': function,
                'symbol': symbol,
                'apikey': config.API_KEYS['ALPHA_VANTAGE']
            }
            if function == 'TIME_SERIES_INTRADAY':
                av_params['interval'] = interval
                av_params['outputsize'] = 'full'
            
            url_configs['ALPHA_VANTAGE'] = (
                config.API_ENDPOINTS['ALPHA_VANTAGE'],
                av_params
            )
        
        # Twelve Data
        if config.is_api_available('TWELVE_DATA'):
            url_configs['TWELVE_DATA'] = (
                f"{config.API_ENDPOINTS['TWELVE_DATA']}time_series",
                {
                    'symbol': symbol,
                    'interval': interval,
                    'apikey': config.API_KEYS['TWELVE_DATA'],
                    'outputsize': 5000
                }
            )
        
        # Usar fallback automático
        return self.make_request_with_fallback(url_configs)
    
    def save_usage_stats(self):
        """Guardar estadísticas de uso en archivo"""
        try:
            # Convertir a formato serializable
            stats_dict = {}
            for key, usage in self.usage_stats.items():
                stats_dict[key] = asdict(usage)
                # Convertir datetime a string
                if stats_dict[key]['last_request_time']:
                    stats_dict[key]['last_request_time'] = usage.last_request_time.isoformat()
                # Convertir enum a string
                stats_dict[key]['status'] = usage.status.value
            
            with open(self.usage_file, 'w') as f:
                json.dump(stats_dict, f, indent=2)
                
            logger.debug(f"💾 Stats guardadas en {self.usage_file}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando stats: {e}")
    
    def load_usage_stats(self):
        """Cargar estadísticas de uso desde archivo"""
        try:
            if not os.path.exists(self.usage_file):
                return
            
            with open(self.usage_file, 'r') as f:
                stats_dict = json.load(f)
            
            # Convertir de vuelta a objetos APIUsage
            for key, data in stats_dict.items():
                # Convertir string de datetime de vuelta
                if data['last_request_time']:
                    data['last_request_time'] = datetime.fromisoformat(data['last_request_time'])
                
                # Convertir string de status a enum
                data['status'] = APIStatus(data['status'])
                
                self.usage_stats[key] = APIUsage(**data)
            
            logger.info(f"📂 Stats cargadas desde {self.usage_file}")
            
        except Exception as e:
            logger.warning(f"⚠️ Error cargando stats (empezando limpio): {e}")
            self.usage_stats = {}
    
    def get_daily_summary(self) -> Dict[str, Dict]:
        """Obtener resumen diario de uso de APIs"""
        today = datetime.now().strftime('%Y-%m-%d')
        summary = {}
        
        for api_name in config.API_PRIORITY:
            stats_key = f"{api_name}_{today}"
            usage = self.usage_stats.get(stats_key)
            
            if usage:
                summary[api_name] = {
                    'requests_made': usage.requests_made,
                    'success_rate': usage.success_rate,
                    'avg_response_time': usage.avg_response_time,
                    'status': usage.status.value,
                    'can_make_request': usage.can_make_request()
                }
            else:
                summary[api_name] = {
                    'requests_made': 0,
                    'success_rate': 0.0,
                    'avg_response_time': 0.0,
                    'status': self.api_status.get(api_name, APIStatus.UNAVAILABLE).value,
                    'can_make_request': config.is_api_available(api_name)
                }
        
        return summary

# =============================================================================
# 🧪 TESTING Y DEBUGGING
# =============================================================================

def test_api_manager():
    """Test del API Manager"""
    print("🧪 Testing API Manager...")
    
    # Crear instancia
    manager = APIManager()
    
    # Mostrar APIs disponibles
    print(f"📊 APIs disponibles: {manager.get_available_apis()}")
    
    # Test simple con AAPL
    print("\n🔍 Testing request para AAPL...")
    success, data, source = manager.get_data('AAPL', interval='1d', period='5d')
    
    if success:
        print(f"✅ Request exitoso usando {source}")
        print(f"📈 Datos obtenidos: {len(data) if isinstance(data, dict) else 'N/A'} elementos")
    else:
        print(f"❌ Request falló: {source}")
    
    # Mostrar resumen del día
    print("\n📋 Resumen diario:")
    summary = manager.get_daily_summary()
    for api, stats in summary.items():
        print(f"  {api}: {stats['requests_made']} requests, "
              f"{stats['success_rate']:.1f}% éxito, "
              f"{stats['avg_response_time']:.2f}s promedio")

if __name__ == "__main__":
    test_api_manager()