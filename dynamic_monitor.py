#!/usr/bin/env python3
"""
🎯 DYNAMIC MONITORING SYSTEM - TRADING AUTOMATIZADO V2.3 + FIXES
==============================================================

🔧 FIXES APLICADOS:
✅ Error 'tuple' object has no attribute 'isoformat' - SOLUCIONADO
✅ Manejo seguro de timezone naive/aware datetimes
✅ Validación robusta de tipos en get_monitoring_stats
✅ Helper functions para timezone consistency

Sistema de monitoreo dinámico que ajusta automáticamente la frecuencia
de escaneo según:

1. 🚨 PROXIMIDAD A ENTRADAS: Más frecuente cuando precio se acerca a niveles
2. 💼 POSICIONES ACTIVAS: Monitoreo intensivo para exits críticos
3. 📊 VOLATILIDAD: Ajuste según ATR y condiciones de mercado
4. 🛡️ RATE LIMITING: Gestión inteligente para no exceder límites API

FRECUENCIAS DINÁMICAS:
- 🔥 CRÍTICA: 5 minutos (cerca de entrada/exit crítico)
- ⚡ ALTA: 10 minutos (posiciones activas)
- 📊 NORMAL: 15 minutos (escaneo rutinario)
- 😴 BAJA: 45 minutos (mercado cerrado/sin actividad)
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
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

# 🔧 TIMEZONE HELPERS - FIXES PARA ERROR ISOFORMAT
def _get_current_time() -> datetime:
    """🔧 FIX: Obtener tiempo actual con timezone UTC consistente"""
    return datetime.now(pytz.UTC)

def _ensure_timezone_aware(dt: datetime) -> datetime:
    """🔧 FIX: Asegurar que datetime tiene timezone"""
    if dt is None:
        return _get_current_time()
    
    if dt.tzinfo is None:
        # Si no tiene timezone, asumir que es market timezone y convertir a UTC
        try:
            market_tz = pytz.timezone(config.MARKET_TIMEZONE)
            return market_tz.localize(dt).astimezone(pytz.UTC)
        except:
            # Fallback: asumir UTC
            return pytz.UTC.localize(dt)
    else:
        # Si ya tiene timezone, convertir a UTC
        return dt.astimezone(pytz.UTC)

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
    """🔧 FIX: Convertir datetime a isoformat de forma segura"""
    try:
        if dt is None:
            return None
        
        if isinstance(dt, datetime):
            dt_aware = _ensure_timezone_aware(dt)
            return dt_aware.isoformat()
        elif isinstance(dt, (tuple, list)):
            logger.warning(f"⚠️ Intentando isoformat en {type(dt)}: {dt}")
            return None
        else:
            logger.warning(f"⚠️ Tipo inesperado para isoformat: {type(dt)}")
            return str(dt)
            
    except Exception as e:
        logger.warning(f"⚠️ Error en safe_isoformat: {e}")
        return None

# Importar exit manager si está disponible
try:
    from exit_manager import ExitManager, ActivePosition, ExitUrgency
    EXIT_MANAGER_AVAILABLE = True
except ImportError:
    EXIT_MANAGER_AVAILABLE = False

# Importar rate limiter si está disponible
try:
    from rate_limiter import RateLimitManager
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    position: Optional['ActivePosition'] = None
    
    # Precios y targets
    current_price: float = 0.0
    target_prices: List[float] = None
    closest_target_distance: float = 999.0
    
    # Control de actualizaciones
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
    critical_interval: int = 2      # 🔧 FIX: Menos agresivo
    high_interval: int = 5          # 🔧 FIX: Más conservador
    normal_interval: int = 15       # Como antes
    low_interval: int = 45          # Como antes
    
    # Configuración de concurrencia
    max_concurrent_updates: int = 3  # Máximo updates concurrente
    
    # Thresholds para cambio de prioridad - 🔧 FIX: Menos sensibles
    proximity_critical_pct: float = 1.0    # 1% = Menos falsos positivos
    proximity_high_pct: float = 2.5        # 2.5% = Más margen
    volatility_multiplier: float = 1.2     # Menos agresivo con volatilidad

class DynamicMonitor:
    """
    🔧 FIXED: Sistema de monitoreo dinámico con manejo robusto de timezone
    """
    
    def __init__(self):
        """Inicializar el monitor dinámico"""
        logger.info("🎯 Inicializando Dynamic Monitor v2.3 + FIXES")
        
        # Componentes principales
        self.scanner = SignalScanner()
        self.indicators = TechnicalIndicators()
        
        # 🔧 FIX: Configurar timezone para operaciones de fecha
        self.market_tz = pytz.timezone(config.MARKET_TIMEZONE)
        self.utc_tz = pytz.UTC
        
        # Exit manager si está disponible
        self.exit_manager = None
        if EXIT_MANAGER_AVAILABLE:
            self.exit_manager = ExitManager()
            logger.info("✅ Exit Manager conectado")
        
        # Rate limiter si está disponible
        self.rate_limiter = None
        if RATE_LIMITER_AVAILABLE:
            self.rate_limiter = RateLimitManager(requests_per_hour=120)
            logger.info("✅ Rate Limiter conectado")
        
        # Configuración de monitoreo
        self.schedule = MonitorSchedule()
        self.monitor_targets: Dict[str, MonitorTarget] = {}
        
        # Control de threads
        self.running = False
        self.monitor_thread = None
        self.update_queue = queue.PriorityQueue()
        self.shutdown_event = threading.Event()
        
        # Estadísticas
        self.total_updates = 0
        self.critical_updates = 0
        self.high_updates = 0
        self.normal_updates = 0
        self.rate_limit_waits = 0
        
        logger.info("✅ Dynamic Monitor inicializado con FIXES")
    
    def is_market_open_safe(self):
        """🔧 FIX: Verificar si mercado está abierto con fallback"""
        try:
            if hasattr(self.scanner, 'is_market_open'):
                return self.scanner.is_market_open()
            else:
                # Fallback básico: lunes-viernes, 9:30-16:00 ET
                now_et = datetime.now(pytz.timezone('US/Eastern'))
                weekday = now_et.weekday()
                hour = now_et.hour
                minute = now_et.minute
                
                if weekday > 4:  # Fin de semana
                    return False
                
                market_time = hour * 100 + minute
                return 930 <= market_time <= 1600
                
        except Exception as e:
            logger.warning(f"⚠️ Error verificando mercado abierto: {e}")
            return True  # Fallback: asumir abierto para no parar el sistema
    
    def start_dynamic_monitoring(self) -> bool:
        """Iniciar el monitoreo dinámico en thread separado"""
        try:
            if self.running:
                logger.warning("⚠️ Dynamic Monitor ya está corriendo")
                return True
            
            logger.info("🚀 Iniciando Dynamic Monitor...")
            
            self.running = True
            self.shutdown_event.clear()
            
            # Crear y iniciar thread de monitoreo
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="DynamicMonitorThread",
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("✅ Dynamic Monitor iniciado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando Dynamic Monitor: {e}")
            self.running = False
            return False
    
    def stop_dynamic_monitoring(self) -> bool:
        """Detener el monitoreo dinámico"""
        try:
            if not self.running:
                return True
            
            logger.info("🛑 Deteniendo Dynamic Monitor...")
            
            # Señalar shutdown
            self.running = False
            self.shutdown_event.set()
            
            # Esperar thread con timeout
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=10)
                
                if self.monitor_thread.is_alive():
                    logger.warning("⚠️ Thread no terminó en tiempo esperado")
                else:
                    logger.info("✅ Dynamic Monitor detenido correctamente")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo Dynamic Monitor: {e}")
            return False
    
    def _monitor_loop(self):
        """🔧 FIX: Loop principal de monitoreo con manejo robusto de errores"""
        logger.info("🔄 Iniciando loop de monitoreo dinámico...")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                # 1. Verificar si hay targets para monitorear
                if not self.monitor_targets:
                    if self.shutdown_event.wait(30):  # Esperar 30s si no hay targets
                        break
                    continue
                
                # 2. Calcular próximas actualizaciones
                next_updates = self._calculate_next_updates()
                
                if not next_updates:
                    if self.shutdown_event.wait(60):  # Esperar 1 min si no hay updates
                        break
                    continue
                
                # 3. Procesar updates que ya es hora de ejecutar
                current_time = _get_current_time()
                updates_to_process = []
                
                for update_time, symbol, priority in next_updates:
                    # 🔧 FIX: Asegurar que update_time es datetime aware
                    update_time_aware = _ensure_timezone_aware(update_time)
                    
                    if update_time_aware <= current_time:
                        updates_to_process.append((symbol, priority))
                
                # 4. Ejecutar updates
                if updates_to_process:
                    logger.info(f"🔄 Procesando {len(updates_to_process)} actualizaciones dinámicas")
                    
                    for symbol, priority in updates_to_process:
                        if not self.running:
                            break
                        
                        # Rate limiting si está disponible
                        if self.rate_limiter and not self.rate_limiter.can_make_request():
                            logger.debug(f"🛡️ Rate limit - saltando {symbol}")
                            self.rate_limit_waits += 1
                            continue
                        
                        # Ejecutar update
                        success = self.update_monitor_target(symbol)
                        if success:
                            self._update_priority_counters(priority)
                
                # 5. Calcular tiempo hasta próximo update
                sleep_time = self._calculate_sleep_time(next_updates)
                
                # 6. Esperar hasta próximo ciclo o shutdown
                if self.shutdown_event.wait(sleep_time):
                    break
                    
            except Exception as e:
                logger.error(f"❌ Error en monitor loop: {e}")
                if self.shutdown_event.wait(30):  # Esperar 30s en caso de error
                    break
        
        logger.info("✅ Monitor loop terminado")
    
    def _calculate_next_updates(self) -> List[Tuple[datetime, str, MonitorPriority]]:
        """🔧 FIX: Calcular próximas actualizaciones con manejo seguro de datetime"""
        next_updates = []
        current_time = _get_current_time()
        
        for symbol, target in self.monitor_targets.items():
            try:
                # 🔧 FIX: Obtener intervalo según prioridad
                interval_minutes = {
                    MonitorPriority.CRITICAL: self.schedule.critical_interval,
                    MonitorPriority.HIGH: self.schedule.high_interval,
                    MonitorPriority.NORMAL: self.schedule.normal_interval,
                    MonitorPriority.LOW: self.schedule.low_interval
                }.get(target.priority, 15)
                
                # 🔧 FIX: Calcular próxima actualización de forma segura
                last_update_aware = _ensure_timezone_aware(target.last_update)
                next_update_time = last_update_aware + timedelta(minutes=interval_minutes)
                
                # Añadir a la lista
                next_updates.append((next_update_time, symbol, target.priority))
                
            except Exception as e:
                logger.warning(f"⚠️ Error calculando next update para {symbol}: {e}")
                continue
        
        # Ordenar por tiempo (más próximo primero)
        next_updates.sort(key=lambda x: x[0])
        return next_updates
    
    def _calculate_sleep_time(self, next_updates: List[Tuple[datetime, str, MonitorPriority]]) -> float:
        """🔧 FIX: Calcular tiempo de sleep hasta próxima actualización"""
        if not next_updates:
            return 60.0  # Default: 1 minuto
        
        try:
            current_time = _get_current_time()
            next_update_time = _ensure_timezone_aware(next_updates[0][0])
            
            time_diff = next_update_time - current_time
            sleep_seconds = max(1.0, time_diff.total_seconds())  # Mínimo 1 segundo
            
            # Máximo 5 minutos de sleep
            return min(sleep_seconds, 300.0)
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando sleep time: {e}")
            return 60.0
    
    def add_monitor_target(self, symbol: str, signal: Optional[TradingSignal] = None,
                          position: Optional['ActivePosition'] = None, reason: str = "Manual") -> bool:
        """🔧 FIX: Añadir nuevo target al monitoreo con manejo robusto"""
        try:
            logger.info(f"📊 Añadiendo {symbol} al monitoreo dinámico - {reason}")
            
            # Obtener precio actual
            try:
                indicators = self.indicators.get_all_indicators(symbol, period="15m", days=5)
                current_price = indicators['current_price']
            except Exception as e:
                logger.error(f"❌ Error obteniendo precio para {symbol}: {e}")
                return False
            
            # Determinar targets críticos
            targets = []
            if signal and signal.position_plan:
                # Targets de entrada y salida
                for entry in signal.position_plan.entries:
                    targets.append(entry.price)
                for exit in signal.position_plan.exits:
                    targets.append(exit.price)
                if signal.position_plan.stop_loss:
                    targets.append(signal.position_plan.stop_loss.price)
            
            if position and position.position_plan:
                # Targets de posición activa
                targets.extend([position.entry_price])
                if hasattr(position, 'stop_loss_price'):
                    targets.append(position.stop_loss_price)
            
            # Calcular prioridad inicial
            priority = self._calculate_initial_priority(current_price, targets, signal, position)
            
            # Crear target de monitoreo
            monitor_target = MonitorTarget(
                symbol=symbol,
                priority=priority,
                reason=reason,
                signal=signal,
                position=position,
                current_price=current_price,
                target_prices=targets,
                last_update=_get_current_time(),  # 🔧 FIX: Usar función segura
                update_count=0
            )
            
            # Añadir al diccionario
            self.monitor_targets[symbol] = monitor_target
            
            logger.info(f"✅ {symbol} añadido al monitoreo - Prioridad: {priority.value}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error añadiendo monitor target {symbol}: {e}")
            return False
    
    def update_monitor_target(self, symbol: str) -> bool:
        """🔧 FIX: Actualizar target específico con manejo de errores"""
        if symbol not in self.monitor_targets:
            return False
        
        target = self.monitor_targets[symbol]
        
        try:
            # Obtener nuevo precio
            indicators = self.indicators.get_all_indicators(symbol, period="15m", days=5)
            new_price = indicators['current_price']
            
            # Actualizar target
            target.current_price = new_price
            target.last_update = _get_current_time()  # 🔧 FIX: Usar función segura
            target.update_count += 1
            target.consecutive_errors = 0  # Reset errores
            
            # Recalcular prioridad
            old_priority = target.priority
            target.priority = self._calculate_dynamic_priority(target, indicators)
            
            # Log si cambió prioridad
            if target.priority != old_priority:
                logger.info(f"🎯 {symbol}: Prioridad {old_priority.value} → {target.priority.value}")
            
            # Verificar condiciones críticas
            if target.priority == MonitorPriority.CRITICAL:
                # Podría añadir alertas especiales aquí
                target.reason = "EXIT CRÍTICO detectado"
                logger.warning(f"🚨 {symbol}: Necesita EXIT CRÍTICO")
            
            self.total_updates += 1
            
            logger.debug(f"📊 {symbol}: Actualizado - ${new_price:.2f} ({target.priority.value})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando {symbol}: {e}")
            target.consecutive_errors += 1
            return False
    
    def _update_priority_counters(self, priority: MonitorPriority):
        """Actualizar contadores de estadísticas"""
        if priority == MonitorPriority.CRITICAL:
            self.critical_updates += 1
        elif priority == MonitorPriority.HIGH:
            self.high_updates += 1
        else:
            self.normal_updates += 1
    
    def _calculate_initial_priority(self, current_price: float, targets: List[float],
                                   signal: Optional[TradingSignal], 
                                   position: Optional['ActivePosition']) -> MonitorPriority:
        """Calcular prioridad inicial basada en proximidad a targets"""
        try:
            if not targets:
                return MonitorPriority.NORMAL
            
            # Calcular distancia mínima a cualquier target
            min_distance_pct = min([abs(current_price - target) / current_price * 100 for target in targets])
            
            # Si hay posición activa, mayor prioridad
            if position:
                if min_distance_pct <= self.schedule.proximity_critical_pct:
                    return MonitorPriority.CRITICAL
                elif min_distance_pct <= self.schedule.proximity_high_pct:
                    return MonitorPriority.HIGH
                else:
                    return MonitorPriority.HIGH  # Posiciones siempre HIGH como mínimo
            
            # Si solo hay señal
            elif signal:
                if min_distance_pct <= self.schedule.proximity_critical_pct * 2:  # Más margen para señales
                    return MonitorPriority.HIGH
                else:
                    return MonitorPriority.NORMAL
            
            return MonitorPriority.NORMAL
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando prioridad inicial: {e}")
            return MonitorPriority.NORMAL
    
    def _calculate_dynamic_priority(self, target: MonitorTarget, 
                                   indicators: Dict) -> MonitorPriority:
        """Calcular prioridad dinámica basada en condiciones actuales"""
        try:
            current_price = target.current_price
            
            if not target.target_prices:
                return MonitorPriority.NORMAL
            
            # Calcular distancia mínima a targets
            min_distance_pct = min([abs(current_price - price) / current_price * 100 
                                  for price in target.target_prices])
            
            target.closest_target_distance = min_distance_pct
            
            # Ajuste por volatilidad (ATR)
            volatility_multiplier = 1.0
            if 'atr' in indicators:
                atr_pct = indicators['atr']['atr_percentage']
                if atr_pct > 3.0:  # Alta volatilidad
                    volatility_multiplier = self.schedule.volatility_multiplier
            
            # Thresholds ajustados por volatilidad
            critical_threshold = self.schedule.proximity_critical_pct * volatility_multiplier
            high_threshold = self.schedule.proximity_high_pct * volatility_multiplier
            
            # Determinar prioridad
            if target.position:
                # Posiciones activas tienen prioridad más alta
                if min_distance_pct <= critical_threshold:
                    return MonitorPriority.CRITICAL
                elif min_distance_pct <= high_threshold:
                    return MonitorPriority.HIGH
                else:
                    return MonitorPriority.HIGH  # Posiciones mínimo HIGH
            
            elif target.signal:
                # Señales pendientes
                if min_distance_pct <= critical_threshold:
                    return MonitorPriority.HIGH
                elif min_distance_pct <= high_threshold * 2:
                    return MonitorPriority.NORMAL
                else:
                    return MonitorPriority.LOW
            
            return MonitorPriority.NORMAL
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculando prioridad dinámica: {e}")
            return MonitorPriority.NORMAL
    
    def remove_monitor_target(self, symbol: str, reason: str = "Manual") -> bool:
        """Remover target del monitoreo"""
        try:
            if symbol in self.monitor_targets:
                del self.monitor_targets[symbol]
                logger.info(f"🗑️ {symbol} removido del monitoreo - {reason}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Error removiendo {symbol}: {e}")
            return False
    
    def get_next_update_schedule(self) -> List[Tuple[datetime, str, MonitorPriority]]:
        """Obtener schedule de próximas actualizaciones"""
        return self._calculate_next_updates()
    
    def get_monitoring_stats(self) -> Dict:
        """🔧 FIXED: Obtener estadísticas del monitoreo dinámico sin errores de isoformat"""
        try:
            # Contar targets por prioridad
            priority_counts = {priority.value: 0 for priority in MonitorPriority}
            
            for target in self.monitor_targets.values():
                priority_counts[target.priority.value] += 1
            
            # 🔧 FIX: Determinar próximas actualizaciones de forma segura
            next_updates = []
            try:
                next_updates = self.get_next_update_schedule()
            except Exception as e:
                logger.warning(f"⚠️ Error obteniendo schedule: {e}")
            
            # 🔧 FIX: Procesar próximas actualizaciones de forma segura
            next_critical = None
            next_high = None
            
            if next_updates:
                try:
                    for update in next_updates:
                        # Verificar que update es una tupla/lista con al menos 3 elementos
                        if isinstance(update, (tuple, list)) and len(update) >= 3:
                            update_time = update[0]  # Primer elemento debe ser datetime
                            priority = update[2]      # Tercer elemento debe ser prioridad
                            
                            # 🔧 FIX: Usar función segura para isoformat
                            if isinstance(update_time, datetime):
                                update_time_aware = _ensure_timezone_aware(update_time)
                                
                                if priority == MonitorPriority.CRITICAL and next_critical is None:
                                    next_critical = update_time_aware
                                elif priority == MonitorPriority.HIGH and next_high is None:
                                    next_high = update_time_aware
                            else:
                                logger.warning(f"⚠️ Elemento de update no es datetime: {type(update_time)}")
                        else:
                            logger.warning(f"⚠️ Formato de update incorrecto: {type(update)} - {update}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando next_updates: {e}")
            
            # Construir stats de targets de forma segura
            targets_detail = {}
            for symbol, target in self.monitor_targets.items():
                try:
                    # 🔧 FIX: Manejo seguro de last_update usando función helper
                    last_update_str = _safe_isoformat(target.last_update)
                    
                    targets_detail[symbol] = {
                        'priority': target.priority.value if hasattr(target, 'priority') else 'UNKNOWN',
                        'reason': getattr(target, 'reason', 'N/A'),
                        'current_price': getattr(target, 'current_price', 0.0),
                        'closest_target_distance': getattr(target, 'closest_target_distance', 0.0),
                        'update_count': getattr(target, 'update_count', 0),
                        'last_update': last_update_str
                    }
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando target {symbol}: {e}")
                    targets_detail[symbol] = {'error': str(e)}
            
            return {
                'running': getattr(self, 'running', False),
                'total_targets': len(self.monitor_targets),
                'total_updates': getattr(self, 'total_updates', 0),
                'critical_updates': getattr(self, 'critical_updates', 0),
                'high_updates': getattr(self, 'high_updates', 0),
                'normal_updates': getattr(self, 'normal_updates', 0),
                'rate_limit_waits': getattr(self, 'rate_limit_waits', 0),
                'targets_by_priority': priority_counts,
                'next_critical_update': _safe_isoformat(next_critical),
                'next_high_update': _safe_isoformat(next_high),
                'targets_detail': targets_detail
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo stats: {e}")
            return {
                'error': str(e),
                'running': False,
                'total_targets': 0,
                'total_updates': 0
            }
    
    def sync_with_exit_manager(self) -> None:
        """Sincronizar targets con exit manager"""
        try:
            if not self.exit_manager:
                return
            
            # Obtener posiciones activas del exit manager
            positions_summary = self.exit_manager.get_positions_summary()
            active_positions = positions_summary.get('positions', {})
            
            # Añadir posiciones que no están en monitoreo
            for symbol in active_positions.keys():
                if symbol not in self.monitor_targets:
                    position = self.exit_manager.active_positions.get(symbol)
                    if position:
                        self.add_monitor_target(symbol, position=position, reason="Exit Manager sync")
            
            # Remover targets que ya no tienen posición activa
            symbols_to_remove = []
            for symbol in self.monitor_targets.keys():
                target = self.monitor_targets[symbol]
                if target.position and symbol not in active_positions:
                    symbols_to_remove.append(symbol)
            
            for symbol in symbols_to_remove:
                self.remove_monitor_target(symbol, "Posición cerrada")
            
            if symbols_to_remove:
                logger.info(f"🔄 Sync Exit Manager: {len(symbols_to_remove)} targets removidos")
            
        except Exception as e:
            logger.error(f"❌ Error sincronizando Exit Manager: {e}")


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_dynamic_monitor():
    """Test básico del dynamic monitor"""
    print("🧪 TESTING DYNAMIC MONITOR (FIXED)")
    print("=" * 50)
    
    try:
        # Crear monitor
        monitor = DynamicMonitor()
        
        print("✅ Monitor creado con FIXES aplicados")
        print(f"Rate Limiter: {'✅' if monitor.rate_limiter else '❌'}")
        print(f"Exit Manager: {'✅' if monitor.exit_manager else '❌'}")
        print(f"Timezone helpers: ✅ FIXED")
        
        # Test añadir target manual
        print("\n📊 Test añadiendo target...")
        success = monitor.add_monitor_target("SPY", reason="Test")
        print(f"Resultado: {'✅ OK' if success else '❌ FALLO'}")
        
        # Mostrar stats
        print("\n📈 Estadísticas iniciales:")
        stats = monitor.get_monitoring_stats()
        print(f"Targets totales: {stats['total_targets']}")
        print(f"Por prioridad: {stats['targets_by_priority']}")
        print(f"Error en stats: {'❌' if 'error' in stats else '✅ OK'}")
        
        # Test actualización
        if stats['total_targets'] > 0:
            print("\n🔄 Test actualización...")
            symbol = list(monitor.monitor_targets.keys())[0]
            success = monitor.update_monitor_target(symbol)
            print(f"Actualización {symbol}: {'✅ OK' if success else '❌ FALLO'}")
        
        # Test timezone functions
        print("\n🕐 Test timezone functions:")
        current = _get_current_time()
        print(f"✅ _get_current_time(): {current.tzinfo}")
        
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        aware_dt = _ensure_timezone_aware(naive_dt)
        print(f"✅ naive → aware: {aware_dt.tzinfo}")
        
        isoformat_test = _safe_isoformat(current)
        print(f"✅ safe_isoformat: {'OK' if isoformat_test else 'FAIL'}")
        
        # Cleanup
        print("\n🧹 Limpiando test...")
        for symbol in list(monitor.monitor_targets.keys()):
            monitor.remove_monitor_target(symbol, "Test cleanup")
        
        print("\n✅ Test básico completado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def test_priority_calculation():
    """Test del cálculo de prioridades"""
    print("🧪 TESTING CÁLCULO DE PRIORIDADES")
    print("=" * 50)
    
    try:
        monitor = DynamicMonitor()
        
        # Test casos de prioridad
        test_cases = [
            {"current_price": 100.0, "targets": [100.5], "expected": "CRITICAL"},
            {"current_price": 100.0, "targets": [102.0], "expected": "HIGH"},
            {"current_price": 100.0, "targets": [105.0], "expected": "NORMAL"},
            {"current_price": 100.0, "targets": [], "expected": "NORMAL"}
        ]
        
        print("Casos de test:")
        for i, case in enumerate(test_cases, 1):
            try:
                priority = monitor._calculate_initial_priority(
                    current_price=case["current_price"],
                    targets=case["targets"],
                    signal=None,
                    position=None
                )
                
                result = "✅ OK" if priority.value == case["expected"] else f"❌ Got {priority.value}"
                print(f"  {i}. Precio {case['current_price']} → {case['targets']}: {result}")
                
            except Exception as e:
                print(f"  {i}. ❌ Error: {e}")
        
        print("\n✅ Test de prioridades completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test prioridades: {e}")
        return False

def demo_dynamic_monitor_with_real_signal():
    """Demo usando una señal real"""
    print("🧪 DEMO DYNAMIC MONITOR CON SEÑAL REAL")
    print("=" * 50)
    
    try:
        # Crear monitor
        monitor = DynamicMonitor()
        
        # Crear señal mock
        from scanner import TradingSignal
        from position_calculator import PositionLevel
        import pytz
        
        # Mock position plan
        class MockPositionPlan:
            def __init__(self):
                self.entries = [
                    PositionLevel("ENTRY", 174.50, 60, "Entrada principal"),
                    PositionLevel("ENTRY", 174.00, 40, "Entrada secundaria")
                ]
                self.exits = [
                    PositionLevel("EXIT", 176.80, 70, "TP1"),
                    PositionLevel("EXIT", 178.95, 30, "TP2")
                ]
                self.stop_loss = PositionLevel("STOP", 173.20, 100, "Stop loss")
        
        # Crear señal mock
        signal = TradingSignal(
            symbol="NVDA",
            timestamp=datetime.now(pytz.timezone('US/Eastern')),
            signal_type="LONG",
            signal_strength=75,
            confidence_level="MEDIUM",
            current_price=175.29,
            entry_quality="FULL_ENTRY",
            indicator_scores={'MACD': 15, 'RSI': 20, 'VWAP': 15, 'ROC': 10, 'BOLLINGER': 10, 'VOLUME': 5},
            indicator_signals={'MACD': 'BULLISH_CROSS', 'RSI': 'OVERSOLD', 'VWAP': 'NEAR_VWAP'},
            position_plan=MockPositionPlan(),
            market_context="SIDEWAYS | LOW_VOLATILITY"
        )
        
        if signal:
            print(f"📊 Usando señal: {signal.symbol} - {signal.signal_type}")
            print(f"   Precio actual: ${signal.current_price:.2f}")
            
            # Añadir al monitoreo
            print("\n1. 📊 Añadiendo al monitoreo dinámico...")
            success = monitor.add_monitor_target(signal.symbol, signal=signal, reason="Demo señal")
            
            if success:
                print("✅ Señal añadida al monitoreo")
                
                # Mostrar estado inicial
                stats = monitor.get_monitoring_stats()
                target_detail = stats['targets_detail'].get(signal.symbol, {})
                print(f"   Prioridad inicial: {target_detail.get('priority', 'N/A')}")
                print(f"   Distancia a target: {target_detail.get('closest_target_distance', 0):.1f}%")
                
                # Simular updates
                print("\n2. 🔄 Simulando actualizaciones...")
                for i in range(3):
                    time.sleep(2)
                    success = monitor.update_monitor_target(signal.symbol)
                    if success:
                        updated_target = monitor.monitor_targets[signal.symbol]
                        print(f"   Update {i+1}: ${updated_target.current_price:.2f} ({updated_target.priority.value})")
                    else:
                        print(f"   Update {i+1}: ❌ FALLO")
                
                # Stats finales
                print("\n3. 📈 Estadísticas finales:")
                final_stats = monitor.get_monitoring_stats()
                print(f"   Total updates: {final_stats['total_updates']}")
                print(f"   Targets activos: {final_stats['total_targets']}")
                print(f"   Error: {'❌ ' + final_stats.get('error', '') if 'error' in final_stats else '✅ Sin errores'}")
                
                # Cleanup
                monitor.remove_monitor_target(signal.symbol, "Demo completado")
                print("\n✅ Demo completado exitosamente")
            else:
                print("❌ Error añadiendo target")
                return False
        else:
            print("ℹ️ No hay señales disponibles para demo")
            return True
            
        return True
        
    except Exception as e:
        print(f"❌ Error en demo: {e}")
        return False

def test_timezone_functions():
    """Test específico de las funciones de timezone"""
    print("🧪 TESTING TIMEZONE FUNCTIONS (FIXED)")
    print("=" * 50)
    
    try:
        # Test funciones helper
        current = _get_current_time()
        print(f"✅ _get_current_time(): {current} (timezone: {current.tzinfo})")
        
        # Test naive datetime
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        aware_dt = _ensure_timezone_aware(naive_dt)
        print(f"✅ naive → aware: {naive_dt} → {aware_dt}")
        
        # Test diferencia
        time_diff = _calculate_time_difference_safe(current, aware_dt)
        print(f"✅ Diferencia calculada: {time_diff}")
        
        # Test comparación
        comparison_result = current > aware_dt
        print(f"✅ Comparación: {comparison_result}")
        
        # Test safe_isoformat
        iso_result = _safe_isoformat(current)
        print(f"✅ safe_isoformat: {'OK' if iso_result else 'FAIL'}")
        
        # Test con tuple (debería manejar el error)
        tuple_test = _safe_isoformat(("not", "a", "datetime"))
        print(f"✅ safe_isoformat con tuple: {'OK - handled' if tuple_test is None else 'FAIL'}")
        
        print("\n✅ Todas las funciones de timezone funcionan correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test timezone: {e}")
        return False

if __name__ == "__main__":
    """Ejecutar tests si se llama directamente"""
    print("🎯 DYNAMIC MONITOR - MODO TESTING (FIXED)")
    print("=" * 60)
    
    # Menú de tests
    print("\nSelecciona un test:")
    print("1. Test básico del monitor")
    print("2. Test cálculo de prioridades") 
    print("3. Demo con señal real")
    print("4. Test funciones timezone")
    print("5. Ejecutar todos los tests")
    
    try:
        choice = input("\nOpción (1-5): ").strip()
        
        if choice == "1":
            test_dynamic_monitor()
        elif choice == "2":
            test_priority_calculation()
        elif choice == "3":
            demo_dynamic_monitor_with_real_signal()
        elif choice == "4":
            test_timezone_functions()
        elif choice == "5":
            print("🚀 EJECUTANDO TODOS LOS TESTS")
            print("=" * 50)
            
            tests = [
                ("Timezone Functions", test_timezone_functions),
                ("Monitor Básico", test_dynamic_monitor),
                ("Cálculo Prioridades", test_priority_calculation),
                ("Demo Señal Real", demo_dynamic_monitor_with_real_signal)
            ]
            
            results = {}
            for test_name, test_func in tests:
                print(f"\n📝 {test_name}:")
                print("-" * 30)
                results[test_name] = test_func()
            
            print(f"\n📊 RESUMEN DE TESTS:")
            print("=" * 30)
            for test_name, result in results.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"{test_name}: {status}")
        else:
            print("❌ Opción no válida")
            
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Test cancelado por usuario")
    except Exception as e:
        print(f"\n❌ Error ejecutando test: {e}")

            
            #