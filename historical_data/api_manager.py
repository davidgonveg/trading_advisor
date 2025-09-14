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
import os

# Importar configuración local
from . import config

# Configurar logging
logging.basicConfig(level=getattr(logging, config.LOGGING_CONFIG['level']))
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
    
    def get_best_api_for_request(self, prefer_fast: bool = False) -> Optional[str]:
        """
        Seleccionar mejor API para próximo request
        
        Args:
            prefer_fast: Preferir APIs más rápidas vs más confiables
            
        Returns:
            Nombre de API o None si ninguna disponible
        """
        available_apis = self.get_available_apis()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Filtrar APIs que pueden hacer requests
        usable_apis = []
        for api in available_apis:
            stats_key = f"{api}_{today}"
            usage = self.usage_stats.get(stats_key)
            
            if usage and usage.can_make_request():
                # Verificar si puede hacer request ahora (rate limiting)
                if usage.time_until_next_request() == 0:
                    usable_apis.append((api, usage))
        
        if not usable_apis:
            return None
        
        # Estrategia de selección
        if prefer_fast:
            # Ordenar por velocidad (menor tiempo de respuesta)
            usable_apis.sort(key=lambda x: x[1].avg_response_time)
        else:
            # Ordenar por prioridad y confiabilidad
            usable_apis.sort(key=lambda x: (
                config.API_PRIORITY.index(x[0]),  # Prioridad en config
                -x[1].success_rate  # Mayor tasa de éxito
            ))
        
        return usable_apis[0][0]
    
    def wait_for_rate_limit(self, api_name: str) -> None:
        """Esperar si es necesario por rate limiting"""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_key = f"{api_name}_{today}"
        usage = self.usage_stats.get(stats_key)
        
        if usage:
            wait_time = usage.time_until_next_request()
            if wait_time > 0:
                logger.info(f"⏳ {api_name}: Esperando {wait_time:.1f}s por rate limit...")
                time.sleep(wait_time)
    
    def record_request(self, api_name: str, success: bool, response_time: float, 
                      error: Optional[str] = None):
        """Registrar resultado de request"""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_key = f"{api_name}_{today}"
        
        # Crear stats si no existen
        if stats_key not in self.usage_stats:
            self.usage_stats[stats_key] = APIUsage(api_name, today)
        
        usage = self.usage_stats[stats_key]
        usage.requests_made += 1
        usage.total_response_time += response_time
        usage.last_request_time = datetime.now()
        
        if success:
            usage.requests_successful += 1
            # Reset status si estaba fallando
            if self.api_status.get(api_name) == APIStatus.FAILED:
                self.api_status[api_name] = APIStatus.AVAILABLE
                logger.info(f"✅ {api_name}: Recuperada - funcionando nuevamente")
        else:
            usage.requests_failed += 1
            
            # Analizar tipo de error
            if error and "rate limit" in error.lower():
                self.api_status[api_name] = APIStatus.RATE_LIMITED
                logger.warning(f"🚫 {api_name}: Rate limit alcanzado")
            elif usage.success_rate < 50 and usage.requests_made > 3:
                self.api_status[api_name] = APIStatus.FAILED
                logger.error(f"❌ {api_name}: Marcada como fallida (tasa éxito: {usage.success_rate:.1f}%)")
        
        # Guardar stats automáticamente cada 10 requests
        if usage.requests_made % 10 == 0:
            self.save_usage_stats()
    
    def make_request(self, api_name: str, url: str, params: Dict[str, Any], 
                    timeout: int = 30) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Hacer request a API específica con manejo completo
        
        Returns:
            Tuple[success, data, error_message]
        """
        start_time = time.time()
        
        try:
            # Verificar si API está disponible
            if not config.is_api_available(api_name):
                return False, None, f"{api_name} no configurada"
            
            # Esperar por rate limiting
            self.wait_for_rate_limit(api_name)
            
            logger.debug(f"🌐 {api_name}: {url}")
            
            # Hacer request
            response = requests.get(url, params=params, timeout=timeout)
            response_time = time.time() - start_time
            
            # Verificar status
            if response.status_code == 200:
                try:
                    data = response.json()
                    self.record_request(api_name, True, response_time)
                    return True, data, None
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
    
    def get_yahoo_data(self, symbol: str, interval: str, period: str) -> Tuple[bool, Optional[Dict], str]:
        """Obtener datos de Yahoo Finance"""
        url = f"{config.API_ENDPOINTS['YAHOO']}{symbol}"
        params = {
            'interval': interval,
            'period': period,
            'includePrePost': 'false'
        }
        
        success, data, error = self.make_request('YAHOO', url, params)
        return success, data, 'YAHOO' if success else error
    
    def get_alpha_vantage_data(self, symbol: str, interval: str = '15min') -> Tuple[bool, Optional[Dict], str]:
        """Obtener datos de Alpha Vantage"""
        function = 'TIME_SERIES_INTRADAY' if interval != '1d' else 'TIME_SERIES_DAILY'
        
        params = {
            'function': function,
            'symbol': symbol,
            'apikey': config.API_KEYS['ALPHA_VANTAGE']
        }
        
        if function == 'TIME_SERIES_INTRADAY':
            params['interval'] = interval
            params['outputsize'] = 'full'
        
        success, data, error = self.make_request('ALPHA_VANTAGE', config.API_ENDPOINTS['ALPHA_VANTAGE'], params)
        return success, data, 'ALPHA_VANTAGE' if success else error
    
    def get_twelve_data(self, symbol: str, interval: str) -> Tuple[bool, Optional[Dict], str]:
        """Obtener datos de Twelve Data"""
        url = f"{config.API_ENDPOINTS['TWELVE_DATA']}time_series"
        
        params = {
            'symbol': symbol,
            'interval': interval,
            'apikey': config.API_KEYS['TWELVE_DATA'],
            'outputsize': 5000  # Máximo permitido
        }
        
        success, data, error = self.make_request('TWELVE_DATA', url, params)
        return success, data, 'TWELVE_DATA' if success else error
    
    def get_polygon_data(self, symbol: str, timespan: str = 'minute', multiplier: int = 15) -> Tuple[bool, Optional[Dict], str]:
        """Obtener datos de Polygon.io"""
        from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        
        url = f"{config.API_ENDPOINTS['POLYGON']}{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        
        params = {
            'apikey': config.API_KEYS['POLYGON']
        }
        
        success, data, error = self.make_request('POLYGON', url, params)
        return success, data, 'POLYGON' if success else error
    
    def get_market_data_with_fallback(self, symbol: str, interval: str = '15m', 
                                    period: str = '1mo') -> Tuple[bool, Optional[Dict], str]:
        """
        Obtener datos con fallback automático entre todas las APIs
        
        Args:
            symbol: Símbolo bursátil
            interval: Intervalo (15m, 1h, 1d)
            period: Período (1mo, 3mo, 1y, 2y)
            
        Returns:
            Tuple[success, data, source_api]
        """
        logger.info(f"📊 Obteniendo {symbol} - {interval} - {period}")
        
        # Preparar configuraciones para cada API
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
            params = {
                'function': function,
                'symbol': symbol,
                'apikey': config.API_KEYS['ALPHA_VANTAGE']
            }
            if function == 'TIME_SERIES_INTRADAY':
                params['interval'] = interval
                params['outputsize'] = 'full'
            
            url_configs['ALPHA_VANTAGE'] = (config.API_ENDPOINTS['ALPHA_VANTAGE'], params)
        
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
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """Obtener resumen diario de uso de APIs"""
        today = datetime.now().strftime('%Y-%m-%d')
        summary = {}
        
        for api in config.API_PRIORITY:
            stats_key = f"{api}_{today}"
            usage = self.usage_stats.get(stats_key)
            
            if usage:
                daily_limit = DAILY_LIMITS_SHARED.get(api.upper(), 0)
                summary[api] = {
                    'requests_made': usage.requests_made,
                    'requests_successful': usage.requests_successful,
                    'requests_failed': usage.requests_failed,
                    'success_rate': f"{usage.success_rate:.1f}%",
                    'avg_response_time': f"{usage.avg_response_time:.2f}s",
                    'daily_limit': daily_limit if daily_limit > 0 else "Unlimited",
                    'usage_percentage': f"{(usage.requests_made/daily_limit*100):.1f}%" if daily_limit > 0 else "N/A",
                    'status': usage.status.value
                }
            else:
                summary[api] = {
                    'requests_made': 0,
                    'status': self.api_status.get(api, APIStatus.UNAVAILABLE).value
                }
        
        return summary
    
    def print_status_report(self):
        """Imprimir reporte detallado del estado actual"""
        print("\n🔄 API MANAGER - ESTADO ACTUAL")
        print("=" * 60)
        
        summary = self.get_daily_summary()
        
        for api, stats in summary.items():
            status_emoji = {
                'available': '✅',
                'rate_limited': '⏳', 
                'failed': '❌',
                'quota_exceeded': '🚫',
                'unavailable': '⚪'
            }.get(stats['status'], '❓')
            
            print(f"{status_emoji} {api}:")
            print(f"   Requests: {stats['requests_made']}")
            if 'success_rate' in stats:
                print(f"   Éxito: {stats['success_rate']}")
                print(f"   Tiempo promedio: {stats['avg_response_time']}")
                print(f"   Límite diario: {stats['daily_limit']}")
                if stats.get('usage_percentage') != 'N/A':
                    print(f"   Uso: {stats['usage_percentage']}")
            print()
        
        available_apis = self.get_available_apis()
        print(f"🚀 APIs disponibles ahora: {', '.join(available_apis) if available_apis else 'Ninguna'}")
        print("=" * 60)

# =============================================================================
# 🧪 FUNCIONES DE TESTING
# =============================================================================

def test_api_manager():
    """Test básico del API Manager"""
    print("🧪 TESTING API MANAGER")
    print("=" * 50)
    
    try:
        # Crear manager
        manager = APIManager()
        
        # Mostrar estado inicial
        manager.print_status_report()
        
        # Test request a Yahoo Finance (símbolo simple)
        print("📊 Testeando Yahoo Finance con AAPL...")
        success, data, source = manager.get_yahoo_data('AAPL', '1d', '5d')
        
        if success:
            print(f"✅ Yahoo Finance funcionando - Source: {source}")
            print(f"   Datos recibidos: {len(data.get('chart', {}).get('result', []))} series")
        else:
            print(f"❌ Yahoo Finance falló: {source}")
        
        # Mostrar estado final
        print("\n📊 Estado después del test:")
        manager.print_status_report()
        
        print("✅ Test completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def test_api_fallback():
    """Test del sistema de fallback"""
    print("🧪 TESTING SISTEMA DE FALLBACK")
    print("=" * 50)
    
    try:
        manager = APIManager()
        
        # Test con múltiples APIs
        print("📊 Testeando fallback con AAPL...")
        success, data, source_api = manager.get_market_data_with_fallback('AAPL', '15m', '1mo')
        
        if success:
            print(f"✅ Datos obtenidos exitosamente")
            print(f"   Fuente: {source_api}")
            print(f"   Tipo de datos: {type(data)}")
        else:
            print(f"❌ Todas las APIs fallaron: {source_api}")
        
        return success
        
    except Exception as e:
        print(f"❌ Error en test fallback: {e}")
        return False

if __name__ == "__main__":
    print("🔄 API MANAGER V3.0 - MODO TESTING")
    print("=" * 60)
    
    # Test básico
    print("1️⃣ Test básico...")
    basic_success = test_api_manager()
    
    if basic_success:
        print("\n2️⃣ Test sistema de fallback...")
        fallback_success = test_api_fallback()
        
        if fallback_success:
            print("\n🎉 ¡Todos los tests pasaron!")
        else:
            print("\n⚠️ Test de fallback falló")
    else:
        print("\n❌ Test básico falló")
    
    print("\n🏁 Tests completados")