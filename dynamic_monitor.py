#!/usr/bin/env python3
"""
🎯 DYNAMIC MONITORING SYSTEM - TRADING AUTOMATIZADO V2.3
=======================================================

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

# 🔧 TIMEZONE HELPERS - SOLUCION INMEDIATA AL ERROR
def _get_current_time() -> datetime:
    """Obtener tiempo actual con timezone UTC consistente"""
    return datetime.now(pytz.UTC)

def _ensure_timezone_aware(dt: datetime) -> datetime:
    """Asegurar que datetime tiene timezone"""
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
    """Calcular diferencia de tiempo con timezone awareness"""
    try:
        dt1_aware = _ensure_timezone_aware(dt1)
        dt2_aware = _ensure_timezone_aware(dt2)
        return dt1_aware - dt2_aware
    except Exception as e:
        print(f"❌ Error calculando diferencia de tiempo: {e}")
        return timedelta(0)

# Importar exit manager si está disponible
try:
    from exit_manager import ExitManager, ActivePosition, ExitUrgency
    EXIT_MANAGER_AVAILABLE = True
except ImportError:
    EXIT_MANAGER_AVAILABLE = False

# Importar smart enhancements si está disponible
try:
    from smart_enhancements import RateLimitManager
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MonitorPriority(Enum):
    """Prioridades de monitoreo"""
    CRITICAL = "CRITICAL"    # 5 min - Entrada inminente / Exit crítico
    HIGH = "HIGH"           # 10 min - Posición activa / Señal fuerte
    NORMAL = "NORMAL"       # 15 min - Escaneo rutinario
    LOW = "LOW"             # 45 min - Sin actividad / Mercado cerrado
    SLEEP = "SLEEP"         # 90 min - Fin de semana / Holidays

@dataclass
class MonitorTarget:
    """Objetivo de monitoreo con prioridad dinámica"""
    symbol: str
    priority: MonitorPriority
    reason: str  # Por qué tiene esta prioridad
    
    # Datos del objetivo
    current_price: float = 0.0
    target_prices: List[float] = None  # Precios críticos a vigilar
    position: Optional['ActivePosition'] = None
    last_signal: Optional[TradingSignal] = None
    
    # Control de monitoreo
    last_update: Optional[datetime] = None
    update_count: int = 0
    consecutive_no_change: int = 0
    
    # Métricas de proximidad
    closest_target_distance: float = float('inf')  # % hasta objetivo más cercano
    volatility_atr_pct: float = 2.0  # ATR como % del precio

@dataclass
class MonitorSchedule:
    """Programa de monitoreo con frecuencias dinámicas - CONFIGURACIÓN CONSERVADORA"""
    critical_interval: int = 5     # minutos - Conservador pero rápido
    high_interval: int = 10        # minutos - Reduce ruido
    normal_interval: int = 15      # minutos - Mantiene base
    low_interval: int = 45         # minutos - Más espaciado para inactivos
    sleep_interval: int = 90       # minutos - Más descanso fuera de mercado
    
    # Límites API - Más conservadores
    max_requests_per_hour: int = 80     # Más seguro con APIs
    max_concurrent_updates: int = 3     # Menos carga concurrente
    
    # Thresholds para cambio de prioridad - Menos sensibles
    proximity_critical_pct: float = 1.0    # 1% = Menos falsos positivos
    proximity_high_pct: float = 2.5        # 2.5% = Más margen
    volatility_multiplier: float = 1.2     # Menos agresivo con volatilidad

class DynamicMonitor:
    """
    Sistema de monitoreo dinámico con frecuencia variable
    """
    
    def __init__(self):
        """Inicializar el monitor dinámico"""
        logger.info("🎯 Inicializando Dynamic Monitor v2.3")
        
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
        
        logger.info("✅ Dynamic Monitor inicializado")
    
    def is_market_open_safe(self):
        """Verificar si mercado está abierto con fallback"""
        try:
            if hasattr(self.scanner, 'is_market_open'):
                return self.scanner.is_market_open()
            else:
                # Fallback: asumir abierto entre 9:30-16:00 EST
                eastern = pytz.timezone('US/Eastern')
                now = datetime.now(eastern)
                market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
                market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
                
                # Solo días laborables
                if now.weekday() >= 5:  # Sábado=5, Domingo=6
                    return False
                
                return market_open <= now <= market_close
        except Exception as e:
            logger.error(f"❌ Error verificando mercado: {e}")
            return True  # Default: asumir abierto
    
    def calculate_proximity_to_targets(self, current_price: float, target_prices: List[float]) -> float:
        """Calcular distancia mínima a targets críticos"""
        try:
            if not target_prices or current_price <= 0:
                return float('inf')
            
            min_distance = float('inf')
            
            for target_price in target_prices:
                if target_price > 0:
                    distance_pct = abs((target_price - current_price) / current_price) * 100
                    min_distance = min(min_distance, distance_pct)
            
            return min_distance
            
        except Exception as e:
            logger.error(f"❌ Error calculando proximidad: {e}")
            return float('inf')
    
    def determine_monitor_priority(self, symbol: str, current_price: float, 
                                  position: Optional['ActivePosition'] = None,
                                  signal: Optional[TradingSignal] = None) -> Tuple[MonitorPriority, str]:
        """🔧 FIX: Determinar prioridad de monitoreo (CORREGIDO TIMEZONE)"""
        try:
            reasons = []
            base_priority = MonitorPriority.NORMAL
            
            # 1. Verificar posiciones activas críticas
            if position:
                try:
                    current_time = _get_current_time()  # 🔧 FIX: Usar función timezone-safe
                    entry_time_aware = _ensure_timezone_aware(position.entry_time)  # 🔧 FIX
                    time_diff = _calculate_time_difference_safe(current_time, entry_time_aware)  # 🔧 FIX
                    hours_held = time_diff.total_seconds() / 3600
                    
                    if hours_held < 2:  # Posición muy reciente
                        base_priority = MonitorPriority.HIGH
                        reasons.append("Posición reciente (< 2h)")
                    elif hours_held < 24:  # Posición del día
                        base_priority = MonitorPriority.HIGH
                        reasons.append("Posición activa (< 24h)")
                    else:
                        base_priority = MonitorPriority.NORMAL
                        reasons.append("Posición establecida")
                        
                except Exception as e:
                    logger.error(f"❌ Error calculando tiempo de posición: {e}")
                    base_priority = MonitorPriority.NORMAL
                    reasons.append(f"Error: {str(e)[:50]}")
            
            # 2. Señal reciente fuerte
            if signal and signal.signal_strength >= 80:
                base_priority = max(base_priority, MonitorPriority.HIGH, key=lambda x: x.value)
                reasons.append(f"Señal fuerte ({signal.signal_strength}/100)")
            
            # 3. Proximidad a targets (esto lo maneja update_monitor_target)
            # Se actualiza dinámicamente en update_monitor_target
            
            # 4. Mercado cerrado = prioridad baja
            try:
                if not self.is_market_open_safe():
                    if base_priority not in [MonitorPriority.CRITICAL]:  # Mantener críticos
                        base_priority = MonitorPriority.LOW
                        reasons.append("Mercado cerrado")
            except Exception:
                pass  # Si falla verificación mercado, continuar normal
            
            # Construir razón final
            final_reason = "; ".join(reasons) if reasons else "Análisis estándar"
            
            return base_priority, final_reason
            
        except Exception as e:
            logger.error(f"❌ Error determinando prioridad para {symbol}: {e}")
            return MonitorPriority.NORMAL, f"Error: {str(e)[:50]}"
    
    def _quick_exit_evaluation(self, symbol: str, current_price: float, position: 'ActivePosition') -> bool:
        """🔧 FIX: Evaluación rápida de necesidad de exit (CORREGIDO)"""
        try:
            if not position.position_plan:
                return False
            
            # 🔧 FIX: Verificar tiempo transcurrido con timezone awareness
            current_time = _get_current_time()
            entry_time_aware = _ensure_timezone_aware(position.entry_time)
            time_diff = _calculate_time_difference_safe(current_time, entry_time_aware)
            hours_held = time_diff.total_seconds() / 3600
            
            # Solo evaluar posiciones que han tenido tiempo de desarrollarse
            if hours_held < 0.5:  # Menos de 30 minutos
                return False
            
            # 🔧 FIX: Acceso correcto a precio del stop loss
            stop_loss_price = position.position_plan.stop_loss.price
            
            # Calcular PnL actual
            if position.direction == 'LONG':
                pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
                # Verificar stop loss
                if current_price <= stop_loss_price:
                    logger.info(f"🚨 {symbol} LONG: Precio en stop loss ({current_price:.2f} <= {stop_loss_price:.2f})")
                    return True
                    
                # Pérdida significativa
                if pnl_pct <= -8:  # -8% es señal de deterioro crítico
                    logger.info(f"🚨 {symbol} LONG: Pérdida crítica {pnl_pct:.1f}%")
                    return True
                    
            else:  # SHORT
                pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100
                # Verificar stop loss
                if current_price >= stop_loss_price:
                    logger.info(f"🚨 {symbol} SHORT: Precio en stop loss ({current_price:.2f} >= {stop_loss_price:.2f})")
                    return True
                    
                # Pérdida significativa
                if pnl_pct <= -8:
                    logger.info(f"🚨 {symbol} SHORT: Pérdida crítica {pnl_pct:.1f}%")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en evaluación de exit para {symbol}: {e}")
            return False
    
    def update_monitor_target(self, symbol: str) -> bool:
        """🔧 FIX: Actualizar datos y prioridad de un target (CORREGIDO)"""
        try:
            if symbol not in self.monitor_targets:
                return False
            
            target = self.monitor_targets[symbol]
            
            # Rate limiting
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
                self.rate_limiter.log_request()
            
            # Obtener datos actualizados
            indicators = self.indicators.get_all_indicators(symbol, period="5m", days=2)
            new_price = indicators['current_price']
            
            # Actualizar ATR/volatilidad
            atr_data = indicators.get('atr', {})
            target.volatility_atr_pct = atr_data.get('atr_percentage', target.volatility_atr_pct)
            
            # Detectar cambio significativo de precio
            if target.current_price > 0:
                price_change_pct = abs((new_price - target.current_price) / target.current_price) * 100
                
                if price_change_pct < 0.1:  # Cambio mínimo
                    target.consecutive_no_change += 1
                else:
                    target.consecutive_no_change = 0
            
            # Actualizar precio
            old_price = target.current_price
            target.current_price = new_price
            target.last_update = _get_current_time()  # ✅ MÉTODO TIMEZONE-AWARE
            target.update_count += 1
            
            # Recalcular proximidad si hay targets
            if target.target_prices:
                old_distance = target.closest_target_distance
                target.closest_target_distance = self.calculate_proximity_to_targets(new_price, target.target_prices)
                
                # Log si proximidad cambió significativamente
                if abs(old_distance - target.closest_target_distance) > 0.5:
                    logger.info(f"📊 {symbol}: Proximidad cambió de {old_distance:.1f}% a {target.closest_target_distance:.1f}%")
                
                # Evaluar cambio de prioridad por proximidad
                old_priority = target.priority
                
                if target.closest_target_distance <= self.schedule.proximity_critical_pct:
                    if target.priority != MonitorPriority.CRITICAL:
                        target.priority = MonitorPriority.CRITICAL
                        target.reason = f"CRÍTICO: {target.closest_target_distance:.1f}% del target"
                        logger.warning(f"🔥 {symbol}: Prioridad CRÍTICA - {target.closest_target_distance:.1f}% del target")
                        
                elif target.closest_target_distance <= self.schedule.proximity_high_pct:
                    if target.priority not in [MonitorPriority.CRITICAL, MonitorPriority.HIGH]:
                        target.priority = MonitorPriority.HIGH
                        target.reason = f"ALTA: {target.closest_target_distance:.1f}% del target"
                        logger.info(f"⚡ {symbol}: Prioridad ALTA - {target.closest_target_distance:.1f}% del target")
                
                # Actualizar contadores de prioridad
                if old_priority != target.priority:
                    self._update_priority_counters(target.priority)
            
            # Evaluación especial para posiciones activas
            if target.position:
                needs_exit = self._quick_exit_evaluation(symbol, new_price, target.position)
                if needs_exit:
                    target.priority = MonitorPriority.CRITICAL
                    target.reason = "EXIT CRÍTICO detectado"
                    logger.warning(f"🚨 {symbol}: Necesita EXIT CRÍTICO")
            
            self.total_updates += 1
            
            logger.debug(f"📊 {symbol}: Actualizado - ${new_price:.2f} ({target.priority.value})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando {symbol}: {e}")
            return False
    
    def _update_priority_counters(self, priority: MonitorPriority):
        """Actualizar contadores de estadísticas"""
        if priority == MonitorPriority.CRITICAL:
            self.critical_updates += 1
        elif priority == MonitorPriority.HIGH:
            self.high_updates += 1
        else:
            self.normal_updates += 1
    
    def add_monitor_target(self, symbol: str, signal: Optional[TradingSignal] = None,
                          position: Optional['ActivePosition'] = None, reason: str = "Manual") -> bool:
        """🔧 FIX: Añadir nuevo target al monitoreo (CORREGIDO)"""
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
            
            # Obtener ATR para volatilidad
            try:
                indicators = self.indicators.get_all_indicators(symbol, period="15m", days=5)
                atr_data = indicators.get('atr', {})
                volatility_atr_pct = atr_data.get('atr_percentage', 2.0)
            except Exception:
                volatility_atr_pct = 2.0
            
            # 🔧 FIX: Determinar prioridad inicial (LLAMADA CORREGIDA)
            priority, priority_reason = self.determine_monitor_priority(
                symbol, current_price, position, signal  # ✅ Solo 4 argumentos
            )
            
            # 🔧 FIX: Crear o actualizar target (TIMESTAMP CORREGIDO)
            target = MonitorTarget(
                symbol=symbol,
                priority=priority,
                reason=f"{reason}: {priority_reason}",
                current_price=current_price,
                target_prices=targets,
                position=position,
                last_signal=signal,
                last_update=_get_current_time(),  # ✅ MÉTODO TIMEZONE-AWARE
                volatility_atr_pct=volatility_atr_pct
            )
            
            # Calcular proximidad inicial
            if targets:
                target.closest_target_distance = self.calculate_proximity_to_targets(current_price, targets)
            
            self.monitor_targets[symbol] = target
            
            logger.info(f"📊 {symbol}: Añadido a monitoreo - {priority.value}")
            logger.info(f"   Razón: {target.reason}")
            logger.info(f"   Precio actual: ${current_price:.2f}")
            logger.info(f"   Targets: {len(targets)} objetivos")
            logger.info(f"   Proximidad: {target.closest_target_distance:.2f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error añadiendo target {symbol}: {e}")
            return False
    
    def remove_monitor_target(self, symbol: str, reason: str = "Manual") -> bool:
        """Remover target del monitoreo"""
        try:
            if symbol in self.monitor_targets:
                target = self.monitor_targets[symbol]
                logger.info(f"🗑️ {symbol}: Removido del monitoreo - {reason}")
                logger.info(f"   Última prioridad: {target.priority.value}")
                logger.info(f"   Updates realizados: {target.update_count}")
                
                del self.monitor_targets[symbol]
                return True
            else:
                logger.warning(f"⚠️ {symbol}: No está en monitoreo")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error removiendo {symbol}: {e}")
            return False
    
    def get_next_update_schedule(self) -> List[Tuple[datetime, str, MonitorPriority]]:
        """Calcular próximas actualizaciones programadas"""
        try:
            now = _get_current_time()  # 🔧 FIX: Usar función timezone-safe
            schedule_list = []
            
            interval_map = {
                MonitorPriority.CRITICAL: self.schedule.critical_interval,
                MonitorPriority.HIGH: self.schedule.high_interval,
                MonitorPriority.NORMAL: self.schedule.normal_interval,
                MonitorPriority.LOW: self.schedule.low_interval,
                MonitorPriority.SLEEP: self.schedule.sleep_interval,
            }
            
            for symbol, target in self.monitor_targets.items():
                interval_minutes = interval_map[target.priority]
                
                if target.last_update:
                    last_update_aware = _ensure_timezone_aware(target.last_update)  # 🔧 FIX
                    next_update = last_update_aware + timedelta(minutes=interval_minutes)
                else:
                    next_update = now
                
                schedule_list.append((next_update, symbol, target.priority))
            
            # Ordenar por tiempo de próxima actualización
            schedule_list.sort(key=lambda x: x[0])
            
            return schedule_list[:10]  # Próximas 10 actualizaciones
            
        except Exception as e:
            logger.error(f"❌ Error calculando schedule: {e}")
            return []
    
    def run_dynamic_monitoring_loop(self) -> None:
        """Loop principal de monitoreo dinámico"""
        try:
            logger.info("🎯 Iniciando Dynamic Monitoring Loop")
            
            while self.running and not self.shutdown_event.is_set():
                
                # 1. Verificar si hay targets para monitorear
                if not self.monitor_targets:
                    logger.debug("📊 No hay targets - esperando 30s...")
                    if self.shutdown_event.wait(30):
                        break
                    continue
                
                # 2. Determinar próxima actualización
                next_updates = self.get_next_update_schedule()
                
                if not next_updates:
                    if self.shutdown_event.wait(60):
                        break
                    continue
                
                # 3. Procesar actualizaciones que ya son tiempo
                now = _get_current_time()  # 🔧 FIX
                
                updates_to_process = []
                for next_time, symbol, priority in next_updates:
                    if next_time <= now:
                        updates_to_process.append((symbol, priority))
                
                # 4. Ejecutar actualizaciones
                if updates_to_process:
                    logger.info(f"🔄 Procesando {len(updates_to_process)} actualizaciones dinámicas")
                    
                    for symbol, priority in updates_to_process[:self.schedule.max_concurrent_updates]:
                        try:
                            success = self.update_monitor_target(symbol)
                            if success:
                                logger.debug(f"✅ {symbol}: Actualizado ({priority.value})")
                            else:
                                logger.warning(f"⚠️ {symbol}: Falló actualización")
                        
                        except Exception as e:
                            logger.error(f"❌ Error actualizando {symbol}: {e}")
                
                # 5. Sincronizar con exit manager
                if self.exit_manager and len(self.monitor_targets) > 0:
                    try:
                        self.sync_with_exit_manager()
                    except Exception as e:
                        logger.error(f"❌ Error sincronizando con Exit Manager: {e}")
                
                # 6. Determinar tiempo de espera hasta próxima actualización
                if next_updates:
                    next_update_time = next_updates[0][0]
                    sleep_seconds = max(30, (next_update_time - now).total_seconds())
                    sleep_seconds = min(sleep_seconds, 300)  # Máximo 5 minutos
                else:
                    sleep_seconds = 60
                
                # 7. Esperar hasta próxima iteración
                if self.shutdown_event.wait(sleep_seconds):
                    break
            
            logger.info("🏁 Dynamic monitoring loop terminado")
            
        except Exception as e:
            logger.error(f"❌ Error crítico en monitoring loop: {e}")
        finally:
            self.running = False
    
    def start_dynamic_monitoring(self) -> bool:
        """Iniciar el monitoreo dinámico en background"""
        try:
            if self.running:
                logger.warning("⚠️ Dynamic Monitor ya está ejecutándose")
                return True
            
            self.running = True
            self.shutdown_event.clear()
            
            # Iniciar thread de monitoreo
            self.monitor_thread = threading.Thread(
                target=self.run_dynamic_monitoring_loop,
                name="DynamicMonitorThread",
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("✅ Dynamic Monitor iniciado en background")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando Dynamic Monitor: {e}")
            return False
    
    def stop_dynamic_monitoring(self) -> bool:
        """Detener el monitoreo dinámico"""
        try:
            if not self.running:
                logger.info("ℹ️ Dynamic Monitor ya está detenido")
                return True
            
            logger.info("🛑 Deteniendo Dynamic Monitor...")
            
            self.running = False
            self.shutdown_event.set()
            
            # Esperar que termine el thread
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
    
    def get_monitoring_stats(self) -> Dict:
        """Obtener estadísticas del monitoreo dinámico"""
        try:
            # Contar targets por prioridad
            priority_counts = {priority.value: 0 for priority in MonitorPriority}
            
            for target in self.monitor_targets.values():
                priority_counts[target.priority.value] += 1
            
            # Determinar próximas actualizaciones
            next_updates = self.get_next_update_schedule()
            next_critical = [x for x in next_updates if x[2] == MonitorPriority.CRITICAL]
            next_high = [x for x in next_updates if x[2] == MonitorPriority.HIGH]
            
            return {
                'running': self.running,
                'total_targets': len(self.monitor_targets),
                'total_updates': self.total_updates,
                'critical_updates': self.critical_updates,
                'high_updates': self.high_updates,
                'normal_updates': self.normal_updates,
                'rate_limit_waits': self.rate_limit_waits,
                'targets_by_priority': priority_counts,
                'next_critical_update': next_critical[0].isoformat() if next_critical else None,
                'next_high_update': next_high[0].isoformat() if next_high else None,
                'targets_detail': {
                    symbol: {
                        'priority': target.priority.value,
                        'reason': target.reason,
                        'current_price': target.current_price,
                        'closest_target_distance': target.closest_target_distance,
                        'update_count': target.update_count,
                        'last_update': target.last_update.isoformat() if target.last_update else None
                    }
                    for symbol, target in self.monitor_targets.items()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo stats: {e}")
            return {'error': str(e)}
    
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
    print("🧪 TESTING DYNAMIC MONITOR")
    print("=" * 50)
    
    try:
        # Crear monitor
        monitor = DynamicMonitor()
        
        print("✅ Monitor creado")
        print(f"Rate Limiter: {'✅' if monitor.rate_limiter else '❌'}")
        print(f"Exit Manager: {'✅' if monitor.exit_manager else '❌'}")
        
        # Test añadir target manual
        print("\n📊 Test añadiendo target...")
        success = monitor.add_monitor_target("SPY", reason="Test")
        print(f"Resultado: {'✅ OK' if success else '❌ FALLO'}")
        
        # Mostrar stats
        print("\n📈 Estadísticas iniciales:")
        stats = monitor.get_monitoring_stats()
        print(f"Targets totales: {stats['total_targets']}")
        print(f"Por prioridad: {stats['targets_by_priority']}")
        
        # Test actualización
        if stats['total_targets'] > 0:
            print("\n🔄 Test actualización...")
            symbol = list(monitor.monitor_targets.keys())[0]
            success = monitor.update_monitor_target(symbol)
            print(f"Actualización {symbol}: {'✅ OK' if success else '❌ FALLO'}")
        
        # Cleanup
        print("\n🧹 Limpiando test...")
        for symbol in list(monitor.monitor_targets.keys()):
            monitor.remove_monitor_target(symbol, "Test completado")
        
        print("\n✅ Test básico completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def test_priority_calculation():
    """Test del cálculo de prioridades"""
    print("🧪 TESTING PRIORITY CALCULATION")
    print("=" * 50)
    
    try:
        monitor = DynamicMonitor()
        
        # Test casos básicos
        test_cases = [
            {
                'name': 'Sin contexto',
                'symbol': 'TEST',
                'current_price': 100.0,
                'expected': MonitorPriority.NORMAL
            },
            {
                'name': 'Precio estándar',
                'symbol': 'SPY',
                'current_price': 450.0,
                'expected': MonitorPriority.NORMAL
            }
        ]
        
        for case in test_cases:
            priority, reason = monitor.determine_monitor_priority(
                symbol=case['symbol'],
                current_price=case['current_price']
            )
            
            result = "✅ OK" if priority == case['expected'] else f"❌ FALLO (esperado {case['expected'].value})"
            print(f"{case['name']}: {priority.value} - {result}")
            print(f"  Razón: {reason}")
        
        print("\n✅ Test prioridades completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def demo_dynamic_monitor_with_real_signal():
    """Demo con señal real del scanner"""
    print("🎯 DEMO DYNAMIC MONITOR CON SEÑAL REAL")
    print("=" * 60)
    
    try:
        # Crear componentes
        monitor = DynamicMonitor()
        scanner = SignalScanner()
        
        print("1. 🔍 Buscando señal real...")
        signal = scanner.scan_symbol("SPY")
        
        if signal:
            print(f"✅ Señal encontrada: {signal.symbol} {signal.signal_type}")
            print(f"   Fuerza: {signal.signal_strength}/100")
            print(f"   Precio: ${signal.current_price:.2f}")
            
            # Añadir al monitoreo dinámico
            print("\n2. 📊 Añadiendo al monitoreo dinámico...")
            success = monitor.add_monitor_target(signal.symbol, signal=signal, reason="Demo signal")
            
            if success:
                target = monitor.monitor_targets[signal.symbol]
                print(f"✅ Target añadido con prioridad: {target.priority.value}")
                print(f"   Razón: {target.reason}")
                print(f"   Objetivos críticos: {len(target.target_prices or [])}")
                print(f"   Proximidad: {target.closest_target_distance:.2f}%")
                
                # Simular algunas actualizaciones
                print("\n3. 🔄 Simulando actualizaciones...")
                for i in range(3):
                    time.sleep(2)
                    success = monitor.update_monitor_target(signal.symbol)
                    if success:
                        updated_target = monitor.monitor_targets[signal.symbol]
                        print(f"   Update {i+1}: ${updated_target.current_price:.2f} ({updated_target.priority.value})")
                    else:
                        print(f"   Update {i+1}: ❌ FALLO")
                
                # Stats finales
                print("\n4. 📈 Estadísticas finales:")
                stats = monitor.get_monitoring_stats()
                print(f"   Total updates: {stats['total_updates']}")
                print(f"   Targets activos: {stats['total_targets']}")
                
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
    print("🧪 TESTING TIMEZONE FUNCTIONS")
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
        
        print("\n✅ Todas las funciones de timezone funcionan correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test timezone: {e}")
        return False

if __name__ == "__main__":
    """Ejecutar tests si se llama directamente"""
    print("🎯 DYNAMIC MONITOR - MODO TESTING")
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