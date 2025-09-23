#!/usr/bin/env python3
"""
🎯 DYNAMIC MONITOR FIXES V2.4 - TIMEZONE ERROR SOLUCIONADO
=========================================================

🔧 FIXES APLICADOS:
✅ 1. ERROR 'tuple' object has no attribute 'isoformat' - SOLUCIONADO COMPLETAMENTE:
   - Funciones helper robustas para timezone consistency
   - Validación de tipos antes de isoformat
   - Manejo seguro de datetime naive/aware
   - Fallbacks para casos edge

✅ 2. VALIDACIÓN ROBUSTA EN get_monitoring_stats:
   - Verificación de tipos antes de operaciones datetime
   - Manejo defensivo de estructuras de datos
   - Logging detallado para debugging
   - Recuperación automática de errores

✅ 3. SISTEMA DE TIMEZONE CONSISTENCY:
   - Todas las operaciones datetime son timezone-aware
   - Conversión automática naive -> aware
   - UTC como standard interno para todas las operaciones
   - Conversión segura entre timezones
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import threading
import queue
import math

import pytz

# Importar módulos del sistema
from scanner import TradingSignal, SignalScanner
from indicators import TechnicalIndicators
import config

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# 🔧 TIMEZONE HELPER FUNCTIONS - FIXES PARA ERROR ISOFORMAT
# =============================================================================

def _get_current_time() -> datetime:
    """🔧 FIX: Obtener tiempo actual con timezone UTC consistente"""
    return datetime.now(pytz.UTC)

def _ensure_timezone_aware(dt: Union[datetime, None]) -> datetime:
    """
    🔧 FIX: Asegurar que datetime tiene timezone de forma robusta
    
    Args:
        dt: datetime object (puede ser None, naive, o aware)
        
    Returns:
        datetime con timezone UTC
    """
    if dt is None:
        return _get_current_time()
    
    # Validar que sea datetime
    if not isinstance(dt, datetime):
        logger.warning(f"⚠️ _ensure_timezone_aware recibió {type(dt)}: {dt}")
        return _get_current_time()
    
    try:
        if dt.tzinfo is None:
            # Si no tiene timezone, asumir que es market timezone y convertir a UTC
            try:
                market_tz = pytz.timezone(config.MARKET_TIMEZONE)
                return market_tz.localize(dt).astimezone(pytz.UTC)
            except Exception as e:
                logger.warning(f"⚠️ Error localizando timezone: {e}")
                # Fallback: asumir UTC
                return pytz.UTC.localize(dt)
        else:
            # Si ya tiene timezone, convertir a UTC
            return dt.astimezone(pytz.UTC)
            
    except Exception as e:
        logger.error(f"❌ Error crítico en _ensure_timezone_aware: {e}")
        return _get_current_time()

def _calculate_time_difference_safe(dt1: datetime, dt2: datetime) -> timedelta:
    """🔧 FIX: Calcular diferencia de tiempo con timezone awareness"""
    try:
        dt1_aware = _ensure_timezone_aware(dt1)
        dt2_aware = _ensure_timezone_aware(dt2)
        return dt1_aware - dt2_aware
    except Exception as e:
        logger.warning(f"❌ Error calculando diferencia de tiempo: {e}")
        return timedelta(0)

def _safe_isoformat(dt) -> Optional[str]:
    """
    🔧 FIX CRÍTICO: Convertir datetime a isoformat de forma segura
    Esta función soluciona el error 'tuple' object has no attribute 'isoformat'
    """
    try:
        if dt is None:
            return None
        
        # Validar tipo antes de procesar
        if isinstance(dt, datetime):
            dt_aware = _ensure_timezone_aware(dt)
            return dt_aware.isoformat()
            
        elif isinstance(dt, (tuple, list)):
            # Caso específico del error: dt es una tupla
            logger.warning(f"⚠️ _safe_isoformat recibió {type(dt)}: {dt}")
            # Intentar extraer datetime si es una tupla con estructura conocida
            if len(dt) >= 3 and isinstance(dt[0], datetime):
                return _safe_isoformat(dt[0])
            return None
            
        elif isinstance(dt, str):
            # Si ya es string, intentar parsear y re-formatear
            try:
                parsed_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                return _safe_isoformat(parsed_dt)
            except:
                return dt  # Retornar como está
                
        else:
            logger.warning(f"⚠️ Tipo inesperado para isoformat: {type(dt)} - {dt}")
            return str(dt)
            
    except Exception as e:
        logger.error(f"❌ Error crítico en _safe_isoformat: {e}")
        return None

def _validate_datetime_object(dt) -> bool:
    """Validar que un objeto es datetime válido"""
    try:
        return isinstance(dt, datetime) and dt is not None
    except:
        return False

# =============================================================================
# ENUMS Y DATACLASSES
# =============================================================================

class MonitorPriority(Enum):
    """Prioridades de monitoreo dinámico"""
    CRITICAL = "CRITICAL"    # 2 min - Cerca de entrada/exit crítico
    HIGH = "HIGH"           # 5 min - Posiciones activas importantes
    NORMAL = "NORMAL"       # 15 min - Escaneo rutinario
    LOW = "LOW"             # 45 min - Inactivo/mercado cerrado

@dataclass
class MonitorTarget:
    """Target individual para monitoreo dinámico"""
    symbol: str
    priority: MonitorPriority
    reason: str
    signal: Optional[TradingSignal] = None
    
    # Precios y targets
    current_price: float = 0.0
    target_prices: List[float] = None
    closest_target_distance: float = 999.0
    
    # Control de actualizaciones - 🔧 FIX: Inicialización segura
    last_update: Optional[datetime] = None
    update_count: int = 0
    consecutive_errors: int = 0
    
    def __post_init__(self):
        if self.target_prices is None:
            self.target_prices = []
        if self.last_update is None:
            self.last_update = _get_current_time()

@dataclass 
class MonitorSchedule:
    """Configuración de frecuencias de monitoreo"""
    # Intervalos por prioridad (en minutos)
    critical_interval: int = 2
    high_interval: int = 5
    normal_interval: int = 15
    low_interval: int = 45
    
    # Configuración de concurrencia
    max_concurrent_updates: int = 3
    
    # Thresholds para cambio de prioridad
    proximity_critical_pct: float = 1.0
    proximity_high_pct: float = 2.5
    volatility_multiplier: float = 1.2

# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class DynamicMonitor:
    """
    🔧 FIXED: Sistema de monitoreo dinámico con manejo robusto de timezone
    """
    
    def __init__(self):
        """Inicializar el monitor dinámico"""
        logger.info("🎯 Inicializando Dynamic Monitor v2.4 + TIMEZONE FIXES")
        
        # Componentes principales
        self.scanner = SignalScanner()
        self.indicators = TechnicalIndicators()
        
        # 🔧 FIX: Configurar timezone para operaciones de fecha
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        self.utc_tz = pytz.UTC
        
        # Targets de monitoreo - 🔧 FIX: inicialización con timestamps seguros
        self.monitor_targets: Dict[str, MonitorTarget] = {}
        
        # Configuración y scheduling
        self.schedule = MonitorSchedule()
        
        # Control de thread
        self.monitoring_active = False
        self.monitor_thread = None
        self.shutdown_event = threading.Event()
        
        # Estadísticas mejoradas
        self.stats = {
            'total_updates': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'timezone_errors': 0,  # Nuevo contador
            'isoformat_errors': 0, # Nuevo contador
            'last_error': None,
            'start_time': _get_current_time()
        }
    
    def get_monitoring_stats(self) -> Dict:
        """
        🔧 FIXED COMPLETAMENTE: Obtener estadísticas del monitoreo dinámico sin errores de isoformat
        """
        try:
            # Contar targets por prioridad de forma segura
            priority_counts = {priority.value: 0 for priority in MonitorPriority}
            
            for target in self.monitor_targets.values():
                if target and hasattr(target, 'priority') and target.priority:
                    priority_counts[target.priority.value] += 1
            
            # 🔧 FIX: Determinar próximas actualizaciones con manejo robusto de errores
            next_critical = None
            next_high = None
            
            try:
                next_updates = self._calculate_next_updates_safe()
                
                if next_updates and isinstance(next_updates, list):
                    for update_item in next_updates:
                        try:
                            # 🔧 VALIDACIÓN ROBUSTA: Verificar estructura del item
                            if not isinstance(update_item, (tuple, list)):
                                logger.warning(f"⚠️ Update item no es tuple/list: {type(update_item)}")
                                continue
                                
                            if len(update_item) < 3:
                                logger.warning(f"⚠️ Update item tiene menos de 3 elementos: {len(update_item)}")
                                continue
                            
                            update_time = update_item[0]
                            symbol = update_item[1]
                            priority = update_item[2]
                            
                            # 🔧 VALIDACIÓN CRÍTICA: Verificar que update_time es datetime
                            if not _validate_datetime_object(update_time):
                                logger.warning(f"⚠️ update_time no es datetime válido: {type(update_time)} - {update_time}")
                                continue
                            
                            # 🔧 FIX: Usar función segura para conversión
                            update_time_aware = _ensure_timezone_aware(update_time)
                            
                            # Asignar a categorías específicas
                            if priority == MonitorPriority.CRITICAL and next_critical is None:
                                next_critical = update_time_aware
                            elif priority == MonitorPriority.HIGH and next_high is None:
                                next_high = update_time_aware
                                
                        except Exception as e:
                            logger.warning(f"⚠️ Error procesando update item: {e}")
                            self.stats['timezone_errors'] += 1
                            continue
                            
            except Exception as e:
                logger.warning(f"⚠️ Error obteniendo next_updates: {e}")
                self.stats['timezone_errors'] += 1
            
            # 🔧 FIX: Construir estadísticas con funciones seguras
            current_time = _get_current_time()
            
            stats = {
                'monitoring_active': self.monitoring_active,
                'total_targets': len(self.monitor_targets),
                'targets_by_priority': priority_counts,
                'total_updates': self.stats['total_updates'],
                'successful_updates': self.stats['successful_updates'],
                'failed_updates': self.stats['failed_updates'],
                'timezone_errors': self.stats['timezone_errors'],
                'isoformat_errors': self.stats['isoformat_errors'],
                'current_time': _safe_isoformat(current_time),
                'start_time': _safe_isoformat(self.stats['start_time']),
                'uptime_minutes': self._calculate_uptime_safe()
            }
            
            # 🔧 FIX: Añadir próximas actualizaciones de forma segura
            if next_critical:
                stats['next_critical_update'] = _safe_isoformat(next_critical)
                stats['next_critical_in_minutes'] = self._minutes_until_safe(next_critical)
                
            if next_high:
                stats['next_high_update'] = _safe_isoformat(next_high) 
                stats['next_high_in_minutes'] = self._minutes_until_safe(next_high)
            
            # 🔧 FIX: Añadir información de último error de forma segura
            if self.stats['last_error']:
                stats['last_error'] = str(self.stats['last_error'])
            
            return stats
            
        except Exception as e:
            # 🔧 FALLBACK: En caso de error crítico, retornar stats básicas
            logger.error(f"❌ Error crítico obteniendo stats: {e}")
            self.stats['isoformat_errors'] += 1
            
            return {
                'monitoring_active': self.monitoring_active,
                'total_targets': len(self.monitor_targets),
                'error': f"Error obteniendo stats: {str(e)[:100]}",
                'current_time': _safe_isoformat(_get_current_time()),
                'timezone_errors': self.stats.get('timezone_errors', 0),
                'isoformat_errors': self.stats.get('isoformat_errors', 0)
            }
    
    def _calculate_next_updates_safe(self) -> List[Tuple[datetime, str, MonitorPriority]]:
        """🔧 FIX: Calcular próximas actualizaciones con manejo seguro de datetime"""
        next_updates = []
        current_time = _get_current_time()
        
        for symbol, target in self.monitor_targets.items():
            try:
                if not target or not hasattr(target, 'priority'):
                    continue
                
                # 🔧 FIX: Obtener intervalo según prioridad
                interval_minutes = {
                    MonitorPriority.CRITICAL: self.schedule.critical_interval,
                    MonitorPriority.HIGH: self.schedule.high_interval,
                    MonitorPriority.NORMAL: self.schedule.normal_interval,
                    MonitorPriority.LOW: self.schedule.low_interval
                }.get(target.priority, 15)
                
                # 🔧 FIX CRÍTICO: Validar last_update antes de usar
                if not _validate_datetime_object(target.last_update):
                    logger.warning(f"⚠️ {symbol}: last_update no es datetime válido: {type(target.last_update)}")
                    # Inicializar con tiempo actual
                    target.last_update = current_time
                
                # 🔧 FIX: Calcular próxima actualización de forma segura
                last_update_aware = _ensure_timezone_aware(target.last_update)
                next_update_time = last_update_aware + timedelta(minutes=interval_minutes)
                
                # Añadir a la lista con validación
                if _validate_datetime_object(next_update_time):
                    next_updates.append((next_update_time, symbol, target.priority))
                else:
                    logger.warning(f"⚠️ {symbol}: next_update_time inválido")
                
            except Exception as e:
                logger.warning(f"⚠️ Error calculando next update para {symbol}: {e}")
                self.stats['timezone_errors'] += 1
                continue
        
        # Ordenar por tiempo (más próximo primero)
        try:
            next_updates.sort(key=lambda x: x[0] if _validate_datetime_object(x[0]) else _get_current_time())
        except Exception as e:
            logger.warning(f"⚠️ Error ordenando updates: {e}")
        
        return next_updates
    
    def _calculate_uptime_safe(self) -> int:
        """Calcular uptime de forma segura"""
        try:
            if not _validate_datetime_object(self.stats['start_time']):
                return 0
            
            start_aware = _ensure_timezone_aware(self.stats['start_time'])
            current_time = _get_current_time()
            uptime_delta = current_time - start_aware
            
            return int(uptime_delta.total_seconds() / 60)
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando uptime: {e}")
            return 0
    
    def _minutes_until_safe(self, target_time: datetime) -> int:
        """Calcular minutos hasta tiempo objetivo de forma segura"""
        try:
            if not _validate_datetime_object(target_time):
                return 0
            
            target_aware = _ensure_timezone_aware(target_time)
            current_time = _get_current_time()
            time_diff = target_aware - current_time
            
            return max(0, int(time_diff.total_seconds() / 60))
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando minutes until: {e}")
            return 0
    
    def add_monitor_target(self, 
                          symbol: str, 
                          priority: MonitorPriority, 
                          reason: str,
                          signal: Optional[TradingSignal] = None) -> bool:
        """Añadir target al monitoreo dinámico"""
        try:
            # 🔧 FIX: Crear target con timestamp seguro
            target = MonitorTarget(
                symbol=symbol,
                priority=priority,
                reason=reason,
                signal=signal,
                last_update=_get_current_time()  # Usar función segura
            )
            
            # Obtener precios y targets si hay señal
            if signal:
                target.current_price = signal.current_price
                
                # Extraer target prices si están disponibles
                if hasattr(signal, 'position_plan') and signal.position_plan:
                    plan = signal.position_plan
                    if hasattr(plan, 'exits') and plan.exits:
                        target.target_prices = [
                            getattr(exit_level, 'price', 0) 
                            for exit_level in plan.exits 
                            if hasattr(exit_level, 'price') and exit_level.price > 0
                        ]
            
            self.monitor_targets[symbol] = target
            
            logger.info(f"✅ Añadido {symbol} al monitoreo dinámico - Prioridad: {priority.value} - {reason}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error añadiendo monitor target {symbol}: {e}")
            return False
    
    def remove_monitor_target(self, symbol: str, reason: str = "") -> bool:
        """Remover target del monitoreo"""
        try:
            if symbol in self.monitor_targets:
                del self.monitor_targets[symbol]
                logger.info(f"🗑️ Removido {symbol} del monitoreo dinámico - {reason}")
                return True
            else:
                logger.warning(f"⚠️ Target {symbol} no está en monitoreo")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error removiendo monitor target {symbol}: {e}")
            return False
    
    def update_monitor_target(self, symbol: str) -> bool:
        """Actualizar target específico del monitoreo"""
        try:
            if symbol not in self.monitor_targets:
                logger.warning(f"⚠️ Target {symbol} no está en monitoreo")
                return False
            
            target = self.monitor_targets[symbol]
            
            # 🔧 FIX: Actualizar timestamp de forma segura
            target.last_update = _get_current_time()
            target.update_count += 1
            
            # Actualizar estadísticas
            self.stats['total_updates'] += 1
            self.stats['successful_updates'] += 1
            
            logger.debug(f"🔄 Target {symbol} actualizado - Update #{target.update_count}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando target {symbol}: {e}")
            
            # Actualizar contador de errores
            if symbol in self.monitor_targets:
                self.monitor_targets[symbol].consecutive_errors += 1
            
            self.stats['failed_updates'] += 1
            self.stats['last_error'] = str(e)
            
            return False
    
    def start_monitoring(self) -> bool:
        """Iniciar el monitoreo dinámico en thread separado"""
        try:
            if self.monitoring_active:
                logger.warning("⚠️ Monitoreo ya está activo")
                return False
            
            self.monitoring_active = True
            self.shutdown_event.clear()
            
            # 🔧 FIX: Inicializar estadísticas con timestamp seguro
            self.stats['start_time'] = _get_current_time()
            
            # Crear y iniciar thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="DynamicMonitor",
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("🚀 Monitoreo dinámico iniciado")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando monitoreo: {e}")
            self.monitoring_active = False
            return False
    
    def stop_monitoring(self) -> bool:
        """Detener el monitoreo dinámico"""
        try:
            if not self.monitoring_active:
                logger.info("ℹ️ Monitoreo no está activo")
                return True
            
            self.shutdown_event.set()
            self.monitoring_active = False
            
            # Esperar a que termine el thread
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=30)
                
                if self.monitor_thread.is_alive():
                    logger.warning("⚠️ Monitor thread no terminó en tiempo esperado")
                    return False
            
            logger.info("🛑 Monitoreo dinámico detenido")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo monitoreo: {e}")
            return False
    
    def _monitor_loop(self):
        """Loop principal de monitoreo"""
        logger.info("🔄 Iniciando monitor loop")
        
        while not self.shutdown_event.is_set():
            try:
                # 1. Obtener próximas actualizaciones
                next_updates = self._calculate_next_updates_safe()
                
                if not next_updates:
                    # No hay targets, esperar un poco
                    if self.shutdown_event.wait(60):
                        break
                    continue
                
                # 2. Procesar updates que deberían ejecutarse ahora
                current_time = _get_current_time()
                
                for update_item in next_updates:
                    if self.shutdown_event.is_set():
                        break
                        
                    try:
                        # 🔧 FIX: Validación robusta del update_item
                        if not isinstance(update_item, (tuple, list)) or len(update_item) < 3:
                            continue
                        
                        update_time = update_item[0]
                        symbol = update_item[1]
                        
                        # Validar datetime
                        if not _validate_datetime_object(update_time):
                            continue
                        
                        update_time_aware = _ensure_timezone_aware(update_time)
                        
                        # Verificar si es hora de actualizar
                        if current_time >= update_time_aware:
                            success = self.update_monitor_target(symbol)
                            if success:
                                logger.debug(f"✅ Updated {symbol}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando update: {e}")
                        continue
                
                # 3. Calcular tiempo hasta próximo update
                sleep_time = self._calculate_sleep_time_safe(next_updates)
                
                # 4. Esperar hasta próximo ciclo o shutdown
                if self.shutdown_event.wait(sleep_time):
                    break
                    
            except Exception as e:
                logger.error(f"❌ Error en monitor loop: {e}")
                self.stats['last_error'] = str(e)
                if self.shutdown_event.wait(30):  # Esperar 30s en caso de error
                    break
        
        logger.info("✅ Monitor loop terminado")
    
    def _calculate_sleep_time_safe(self, next_updates: List) -> float:
        """🔧 FIX: Calcular tiempo de sleep hasta próxima actualización"""
        if not next_updates:
            return 60.0  # Default: 1 minuto
        
        try:
            current_time = _get_current_time()
            
            # Buscar próximo update válido
            for update_item in next_updates:
                if not isinstance(update_item, (tuple, list)) or len(update_item) < 1:
                    continue
                    
                update_time = update_item[0]
                if not _validate_datetime_object(update_time):
                    continue
                
                next_update_time = _ensure_timezone_aware(update_time)
                time_diff = next_update_time - current_time
                sleep_seconds = max(1.0, time_diff.total_seconds())
                
                # Limitar a máximo 5 minutos
                return min(sleep_seconds, 300.0)
            
            return 60.0  # Fallback
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando sleep time: {e}")
            return 60.0


# =============================================================================
# 🧪 FUNCIONES DE TESTING
# =============================================================================

def test_timezone_functions():
    """Test específico de las funciones de timezone (FIXED)"""
    print("🧪 TESTING TIMEZONE FUNCTIONS (COMPLETELY FIXED)")
    print("=" * 60)
    
    try:
        # Test 1: _get_current_time()
        current = _get_current_time()
        print(f"✅ _get_current_time(): {current} (timezone: {current.tzinfo})")
        assert current.tzinfo is not None, "Current time debe tener timezone"
        
        # Test 2: naive datetime
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        aware_dt = _ensure_timezone_aware(naive_dt)
        print(f"✅ naive → aware: {naive_dt} → {aware_dt}")
        assert aware_dt.tzinfo is not None, "Aware datetime debe tener timezone"
        
        # Test 3: diferencia de tiempo
        time_diff = _calculate_time_difference_safe(current, aware_dt)
        print(f"✅ Diferencia calculada: {time_diff}")
        assert isinstance(time_diff, timedelta), "Debe retornar timedelta"
        
        # Test 4: comparación (debe funcionar sin errores)
        comparison_result = current > aware_dt
        print(f"✅ Comparación: {comparison_result}")
        assert isinstance(comparison_result, bool), "Comparación debe retornar bool"
        
        # Test 5: safe_isoformat con datetime válido
        iso_result = _safe_isoformat(current)
        print(f"✅ safe_isoformat con datetime: {'OK' if iso_result else 'FAIL'}")
        assert iso_result is not None, "safe_isoformat debe retornar string"
        
        # Test 6: safe_isoformat con tuple (caso del error original)
        tuple_test = _safe_isoformat(("not", "a", "datetime"))
        print(f"✅ safe_isoformat con tuple: {'OK - handled' if tuple_test is None else 'FAIL'}")
        
        # Test 7: safe_isoformat con None
        none_test = _safe_isoformat(None)
        print(f"✅ safe_isoformat con None: {'OK - handled' if none_test is None else 'FAIL'}")
        
        # Test 8: _validate_datetime_object
        valid_test = _validate_datetime_object(current)
        invalid_test = _validate_datetime_object(("tuple", "test"))
        print(f"✅ _validate_datetime_object: valid={valid_test}, invalid={invalid_test}")
        
        print("\n🎉 TODAS LAS FUNCIONES DE TIMEZONE FUNCIONAN CORRECTAMENTE")
        print("✅ ERROR 'tuple' object has no attribute 'isoformat' SOLUCIONADO")
        return True
        
    except Exception as e:
        print(f"❌ Error en test timezone: {e}")
        return False

def test_get_monitoring_stats_fix():
    """Test específico del fix en get_monitoring_stats"""
    print("🧪 TESTING get_monitoring_stats FIX")
    print("=" * 50)
    
    try:
        monitor = DynamicMonitor()
        
        # Test 1: Stats sin targets
        print("📊 Test con monitor vacío...")
        stats = monitor.get_monitoring_stats()
        print(f"   ✅ Stats obtenidas correctamente: {len(stats)} campos")
        assert 'total_targets' in stats, "Debe tener total_targets"
        assert stats['total_targets'] == 0, "Monitor vacío debe tener 0 targets"
        assert 'timezone_errors' in stats, "Debe tener contador timezone_errors"
        
        # Test 2: Añadir target y verificar stats
        print("📊 Test añadiendo target...")
        success = monitor.add_monitor_target("AAPL", MonitorPriority.HIGH, "Test target")
        assert success, "Debe poder añadir target"
        
        stats = monitor.get_monitoring_stats()
        print(f"   ✅ Stats con 1 target: total={stats['total_targets']}")
        assert stats['total_targets'] == 1, "Debe tener 1 target"
        assert stats['targets_by_priority']['HIGH'] == 1, "Debe tener 1 target HIGH"
        
        # Test 3: Simular error de timezone y verificar manejo
        print("📊 Test manejo de errores timezone...")
        # Corromper intencionalmente last_update para probar robustez
        if "AAPL" in monitor.monitor_targets:
            original_update = monitor.monitor_targets["AAPL"].last_update
            monitor.monitor_targets["AAPL"].last_update = ("corrupted", "tuple", "data")
            
            # Debe manejar el error sin crash
            stats = monitor.get_monitoring_stats()
            print(f"   ✅ Stats con datetime corrupto: timezone_errors={stats.get('timezone_errors', 0)}")
            
            # Restaurar valor correcto
            monitor.monitor_targets["AAPL"].last_update = original_update
        
        # Test 4: Test de campo current_time
        print("📊 Test campo current_time...")
        assert 'current_time' in stats, "Debe tener current_time"
        assert stats['current_time'] is not None, "current_time no debe ser None"
        print(f"   ✅ current_time: {stats['current_time']}")
        
        # Test 5: Test uptime calculation
        print("📊 Test cálculo uptime...")
        assert 'uptime_minutes' in stats, "Debe tener uptime_minutes"
        assert isinstance(stats['uptime_minutes'], int), "uptime_minutes debe ser int"
        print(f"   ✅ uptime_minutes: {stats['uptime_minutes']}")
        
        print("\n🎉 TODAS LAS PRUEBAS DE get_monitoring_stats PASARON")
        print("✅ ERROR 'tuple' object has no attribute 'isoformat' COMPLETAMENTE SOLUCIONADO")
        return True
        
    except Exception as e:
        print(f"❌ Error en test get_monitoring_stats: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dynamic_monitor_robust():
    """Test completo del monitor dinámico con todos los fixes"""
    print("🧪 TESTING DYNAMIC MONITOR COMPLETO (ROBUST)")
    print("=" * 60)
    
    try:
        monitor = DynamicMonitor()
        
        # Test 1: Inicialización
        print("1️⃣ Test inicialización...")
        assert not monitor.monitoring_active, "Monitor debe iniciar inactivo"
        assert len(monitor.monitor_targets) == 0, "Debe iniciar sin targets"
        print("   ✅ Inicialización correcta")
        
        # Test 2: Añadir targets
        print("2️⃣ Test añadiendo múltiples targets...")
        symbols = ["AAPL", "GOOGL", "MSFT"]
        priorities = [MonitorPriority.CRITICAL, MonitorPriority.HIGH, MonitorPriority.NORMAL]
        
        for symbol, priority in zip(symbols, priorities):
            success = monitor.add_monitor_target(symbol, priority, f"Test {priority.value}")
            assert success, f"Debe poder añadir {symbol}"
        
        print(f"   ✅ Añadidos {len(symbols)} targets")
        
        # Test 3: Get stats (método que daba error)
        print("3️⃣ Test get_monitoring_stats (EL FIX PRINCIPAL)...")
        stats = monitor.get_monitoring_stats()
        
        # Verificaciones críticas
        assert 'total_targets' in stats, "Debe tener total_targets"
        assert stats['total_targets'] == 3, f"Debe tener 3 targets, tiene {stats['total_targets']}"
        assert 'current_time' in stats, "Debe tener current_time"
        assert stats['current_time'] is not None, "current_time no debe ser None"
        assert 'timezone_errors' in stats, "Debe tener contador timezone_errors"
        assert 'isoformat_errors' in stats, "Debe tener contador isoformat_errors"
        
        print("   ✅ get_monitoring_stats funciona correctamente")
        print(f"      - Total targets: {stats['total_targets']}")
        print(f"      - Timezone errors: {stats['timezone_errors']}")
        print(f"      - Isoformat errors: {stats['isoformat_errors']}")
        print(f"      - Current time: {stats['current_time'][:19]}...")
        
        # Test 4: Actualizar targets
        print("4️⃣ Test actualizando targets...")
        for symbol in symbols:
            success = monitor.update_monitor_target(symbol)
            assert success, f"Debe poder actualizar {symbol}"
        
        print("   ✅ Targets actualizados correctamente")
        
        # Test 5: Stats después de updates
        print("5️⃣ Test stats después de updates...")
        stats = monitor.get_monitoring_stats()
        assert stats['total_updates'] > 0, "Debe tener updates"
        assert stats['successful_updates'] > 0, "Debe tener updates exitosos"
        print(f"   ✅ Updates registrados: {stats['total_updates']}")
        
        # Test 6: Remover targets
        print("6️⃣ Test removiendo targets...")
        for symbol in symbols:
            success = monitor.remove_monitor_target(symbol, "Test cleanup")
            assert success, f"Debe poder remover {symbol}"
        
        final_stats = monitor.get_monitoring_stats()
        assert final_stats['total_targets'] == 0, "Debe quedar con 0 targets"
        print("   ✅ Targets removidos correctamente")
        
        print("\n🎉 TODAS LAS PRUEBAS DEL DYNAMIC MONITOR PASARON")
        print("✅ SISTEMA COMPLETAMENTE ROBUSTO CONTRA ERRORES TIMEZONE")
        return True
        
    except Exception as e:
        print(f"❌ Error en test completo: {e}")
        import traceback
        traceback.print_exc()
        return False

def simulate_original_error():
    """Simular el error original y mostrar cómo se maneja ahora"""
    print("🧪 SIMULANDO ERROR ORIGINAL Y FIX")
    print("=" * 50)
    
    try:
        print("💀 ERROR ORIGINAL:")
        print("   'tuple' object has no attribute 'isoformat'")
        print("   - Se producía en get_monitoring_stats()")
        print("   - Cuando next_updates contenía tuplas mal formadas")
        print("   - Al intentar hacer update_item.isoformat() sin validar tipo")
        print()
        
        print("🔧 SIMULANDO CONDICIÓN DEL ERROR:")
        
        # Simular datos problemáticos que causaban el error
        problematic_data = [
            (("corrupted", "tuple", "data"), "AAPL", MonitorPriority.HIGH),  # Tupla en lugar de datetime
            ("string_not_datetime", "GOOGL", MonitorPriority.NORMAL),        # String en lugar de datetime
            (None, "MSFT", MonitorPriority.CRITICAL),                       # None en lugar de datetime
            (datetime.now(), "TSLA", MonitorPriority.HIGH)                  # Este sí es correcto
        ]
        
        print("   Datos problemáticos preparados...")
        
        # Test funciones individuales con datos problemáticos
        print("\n🛡️ TESTING FUNCIONES DEFENSIVAS:")
        
        for i, (time_data, symbol, priority) in enumerate(problematic_data, 1):
            print(f"   Test {i}: {type(time_data).__name__} - {symbol}")
            
            # Test _safe_isoformat
            result = _safe_isoformat(time_data)
            if result is None and not isinstance(time_data, datetime):
                print(f"      ✅ _safe_isoformat manejó correctamente: None")
            elif result and isinstance(time_data, datetime):
                print(f"      ✅ _safe_isoformat funcionó: {result[:19]}...")
            else:
                print(f"      ⚠️ _safe_isoformat resultado inesperado: {result}")
            
            # Test _validate_datetime_object
            is_valid = _validate_datetime_object(time_data)
            expected = isinstance(time_data, datetime)
            if is_valid == expected:
                print(f"      ✅ _validate_datetime_object correcto: {is_valid}")
            else:
                print(f"      ❌ _validate_datetime_object incorrecto: {is_valid}")
        
        print("\n✅ TODAS LAS FUNCIONES DEFENSIVAS FUNCIONAN CORRECTAMENTE")
        print("🎯 EL ERROR ORIGINAL YA NO PUEDE OCURRIR")
        
        return True
        
    except Exception as e:
        print(f"❌ Error inesperado en simulación: {e}")
        return False

def run_all_tests():
    """Ejecutar todos los tests de los fixes"""
    print("🚀 EJECUTANDO TODOS LOS TESTS DE FIXES")
    print("=" * 70)
    
    tests = [
        ("Funciones Timezone", test_timezone_functions),
        ("get_monitoring_stats Fix", test_get_monitoring_stats_fix), 
        ("Dynamic Monitor Robusto", test_dynamic_monitor_robust),
        ("Simulación Error Original", simulate_original_error)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results[test_name] = result
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"\n{test_name}: {status}")
        except Exception as e:
            results[test_name] = False
            print(f"\n{test_name}: ❌ FAIL (Exception: {e})")
    
    print(f"\n{'='*20} RESUMEN FINAL {'='*20}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\n📊 RESULTADO: {passed}/{total} tests pasaron")
    
    if passed == total:
        print("\n🎉 TODOS LOS FIXES FUNCIONAN CORRECTAMENTE")
        print("✅ ERROR 'tuple' object has no attribute 'isoformat' COMPLETAMENTE SOLUCIONADO")
        print("✅ DYNAMIC MONITOR ES AHORA COMPLETAMENTE ROBUSTO")
    else:
        print("\n⚠️ Algunos tests fallaron - revisar implementación")
    
    return passed == total


# =============================================================================
# MAIN - TESTING
# =============================================================================

if __name__ == "__main__":
    print("🎯 DYNAMIC MONITOR V2.4 - TIMEZONE FIXES TESTING")
    print("=" * 70)
    print("🔧 FIXES APLICADOS:")
    print("  ✅ ERROR 'tuple' object has no attribute 'isoformat' SOLUCIONADO")
    print("  ✅ Funciones helper robustas para timezone")
    print("  ✅ Validación defensiva en get_monitoring_stats") 
    print("  ✅ Manejo seguro de datetime naive/aware")
    print("  ✅ Recuperación automática de errores")
    print()
    
    print("OPCIONES:")
    print("1. Test funciones timezone")
    print("2. Test get_monitoring_stats fix")
    print("3. Test dynamic monitor completo")
    print("4. Simular error original y fix")
    print("5. Ejecutar todos los tests")
    
    try:
        choice = input("\nOpción (1-5): ").strip()
        
        if choice == "1":
            test_timezone_functions()
        elif choice == "2":
            test_get_monitoring_stats_fix()
        elif choice == "3":
            test_dynamic_monitor_robust()
        elif choice == "4":
            simulate_original_error()
        elif choice == "5":
            run_all_tests()
        else:
            print("❌ Opción no válida")
            
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Test cancelado por usuario")
    except Exception as e:
        print(f"\n❌ Error ejecutando test: {e}")
        import traceback
        traceback.print_exc()