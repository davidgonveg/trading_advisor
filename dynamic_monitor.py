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
- 🔥 CRÍTICA: 1-2 minutos (cerca de entrada/exit crítico)
- ⚡ ALTA: 5 minutos (posiciones activas)
- 📊 NORMAL: 15 minutos (escaneo rutinario)
- 😴 BAJA: 30+ minutos (mercado cerrado/sin actividad)
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
    CRITICAL = "CRITICAL"    # 1-2 min - Entrada inminente / Exit crítico
    HIGH = "HIGH"           # 5 min - Posición activa / Señal fuerte
    NORMAL = "NORMAL"       # 15 min - Escaneo rutinario
    LOW = "LOW"             # 30+ min - Sin actividad / Mercado cerrado
    SLEEP = "SLEEP"         # 60+ min - Fin de semana / Holidays

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
    critical_interval: int = 5     # minutos (antes 2) - Más conservador pero sigue siendo rápido
    high_interval: int = 10        # minutos (antes 5) - Reduce ruido
    normal_interval: int = 15      # minutos (igual) - Mantiene base
    low_interval: int = 45         # minutos (antes 30) - Más espaciado para inactivos
    sleep_interval: int = 90       # minutos (antes 60) - Más descanso fuera de mercado
    
    # Límites API - Más conservadores
    max_requests_per_hour: int = 80     # (antes 120) - Más seguro con APIs
    max_concurrent_updates: int = 3     # (antes 5) - Menos carga concurrente
    
    # Thresholds para cambio de prioridad - Menos sensibles
    proximity_critical_pct: float = 1.0    # (antes 0.5%) - 1% = Menos falsos positivos
    proximity_high_pct: float = 2.5        # (antes 1.5%) - 2.5% = Más margen
    volatility_multiplier: float = 1.2     # (antes 1.5) - Menos agresivo con volatilidad

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
    
    # 🔧 FIX: Métodos helper para timezone
    def _get_current_time(self) -> datetime:
        """Obtener tiempo actual con timezone consistente"""
        return datetime.now(self.utc_tz)
    
    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Asegurar que datetime tiene timezone"""
        if dt is None:
            return self._get_current_time()
        
        if dt.tzinfo is None:
            # Si no tiene timezone, asumir que es market timezone
            return self.market_tz.localize(dt).astimezone(self.utc_tz)
        else:
            # Si ya tiene timezone, convertir a UTC
            return dt.astimezone(self.utc_tz)
    
    def _calculate_time_difference(self, dt1: datetime, dt2: datetime) -> timedelta:
        """Calcular diferencia de tiempo con timezone awareness"""
        try:
            dt1_aware = self._ensure_timezone_aware(dt1)
            dt2_aware = self._ensure_timezone_aware(dt2)
            return dt1_aware - dt2_aware
        except Exception as e:
            logger.error(f"❌ Error calculando diferencia de tiempo: {e}")
            return timedelta(0)
    
    def is_market_open_safe(self):
        """Verificar si mercado está abierto con fallback"""
        try:
            if hasattr(self.scanner, 'is_market_open'):
                return self.scanner.is_market_open()
            else:
                # Fallback: asumir abierto entre 9:30-16:00 EST
                eastern = pytz.timezone('US/Eastern')
                now = datetime.now(eastern)
                market_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
                market_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
                return market_start <= now <= market_end and now.weekday() < 5
        except Exception:
            return True  # Default: asumir abierto
    
    def calculate_target_prices(self, signal: TradingSignal) -> List[float]:
        """Calcular precios críticos para monitoreo"""
        try:
            targets = []
            
            if signal.position_plan:
                # Precios de entrada
                for entry in signal.position_plan.entries:
                    targets.append(entry.price)
                
                # Stop loss
                targets.append(signal.position_plan.stop_loss.price)
                
                # Take profits
                for tp in signal.position_plan.exits:
                    targets.append(tp.price)
            
            return sorted(set(targets))  # Eliminar duplicados y ordenar
            
        except Exception as e:
            logger.error(f"❌ Error calculando targets: {e}")
            return [signal.current_price]
    
    def calculate_proximity_to_targets(self, current_price: float, targets: List[float]) -> float:
        """Calcular distancia mínima a objetivos críticos (en %)"""
        if not targets:
            return float('inf')
        
        min_distance = float('inf')
        
        for target in targets:
            distance_pct = abs((target - current_price) / current_price) * 100
            min_distance = min(min_distance, distance_pct)
        
        return min_distance
    
    def determine_monitor_priority(self, symbol: str, current_price: float, 
                          position: Optional['ActivePosition'] = None,
                          last_signal: Optional[TradingSignal] = None) -> Tuple[MonitorPriority, str]:
        """🔧 FIX: Determinar prioridad de monitoreo para un símbolo (VERSIÓN CORREGIDA)"""
        try:
            # Prioridad base
            base_priority = MonitorPriority.NORMAL
            reasons = []
            
            # 1. Verificar posiciones activas críticas
            if position:
                try:
                    current_time = self._get_current_time()
                    entry_time_aware = self._ensure_timezone_aware(position.entry_time)
                    time_diff = current_time - entry_time_aware
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
            
            # 2. 🔧 FIX: Proximidad a niveles críticos (CORREGIDO)
            if position and position.position_plan and position.position_plan.exits and position.position_plan.stop_loss:
                try:
                    # Usar primer exit como take_profit
                    take_profit_price = position.position_plan.exits[0].price
                    stop_loss_price = position.position_plan.stop_loss.price
                    
                    # Calcular distancias a targets (CORREGIDO)
                    if position.direction == 'LONG':
                        target_distance = ((take_profit_price - current_price) / current_price) * 100
                        stop_distance = ((current_price - stop_loss_price) / current_price) * 100
                    else:  # SHORT
                        target_distance = ((current_price - take_profit_price) / current_price) * 100
                        stop_distance = ((stop_loss_price - current_price) / current_price) * 100
                    
                    # Verificar proximidad crítica
                    if abs(target_distance) < self.schedule.proximity_critical_pct or abs(stop_distance) < self.schedule.proximity_critical_pct:
                        base_priority = MonitorPriority.CRITICAL
                        reasons.append(f"Precio a {min(abs(target_distance), abs(stop_distance)):.1f}% de objetivo crítico")
                    elif abs(target_distance) < self.schedule.proximity_high_pct or abs(stop_distance) < self.schedule.proximity_high_pct:
                        base_priority = max(base_priority, MonitorPriority.HIGH)
                        reasons.append(f"Precio a {min(abs(target_distance), abs(stop_distance)):.1f}% de objetivo")
                        
                except Exception as e:
                    logger.error(f"❌ Error calculando proximidad: {e}")
                    reasons.append(f"Error proximidad: {str(e)[:30]}")
            
            # 3. Señal reciente
            if last_signal:
                try:
                    current_time = self._get_current_time()
                    signal_time_aware = self._ensure_timezone_aware(last_signal.timestamp)
                    time_diff = current_time - signal_time_aware
                    hours_since_signal = time_diff.total_seconds() / 3600
                    
                    if hours_since_signal < 1:  # Señal muy reciente
                        base_priority = max(base_priority, MonitorPriority.HIGH)
                        reasons.append("Señal reciente (< 1h)")
                    elif hours_since_signal < 4:  # Señal del día
                        base_priority = max(base_priority, MonitorPriority.HIGH)
                        reasons.append("Señal del día (< 4h)")
                        
                except Exception as e:
                    logger.error(f"❌ Error calculando tiempo de señal: {e}")
                    reasons.append(f"Error señal: {str(e)[:30]}")
            
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
            current_time = self._get_current_time()
            entry_time_aware = self._ensure_timezone_aware(position.entry_time)
            time_diff = self._calculate_time_difference(current_time, entry_time_aware)
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
                    logger.info(f"🚨 {symbol}: LONG cerca de stop loss - {pnl_pct:+.2f}%")
                    return True
            else:  # SHORT
                pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100
                # Verificar stop loss
                if current_price >= stop_loss_price:
                    logger.info(f"🚨 {symbol}: SHORT cerca de stop loss - {pnl_pct:+.2f}%")
                    return True
            
            # Verificar pérdidas significativas (> 3%)
            if pnl_pct < -3.0:
                logger.info(f"🚨 {symbol}: Pérdidas significativas - {pnl_pct:+.2f}%")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en quick exit evaluation: {e}")
            return False
    
    def add_monitor_target(self, symbol: str, 
                          signal: TradingSignal = None, 
                          position: 'ActivePosition' = None,
                          reason: str = "Manual") -> bool:
        """🔧 FIX: Añadir objetivo al monitoreo dinámico (CORREGIDO)"""
        try:
            # Obtener precio actual
            current_price = signal.current_price if signal else position.current_price if position else 0
            
            if current_price == 0:
                # Obtener precio actual desde API
                try:
                    indicators = self.indicators.get_all_indicators(symbol, period="1m", days=1)
                    current_price = indicators['current_price']
                except Exception as e:
                    logger.error(f"❌ Error obteniendo precio {symbol}: {e}")
                    return False
            
            # Calcular targets y volatilidad
            targets = []
            volatility_atr_pct = 2.0
            
            if signal and signal.position_plan:
                targets = self.calculate_target_prices(signal)
            
            if position:
                # Targets básicos para posición existente
                targets = [position.entry_price]
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
                last_update=self._get_current_time(),  # ✅ MÉTODO TIMEZONE-AWARE
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
            target.last_update = self._get_current_time()  # ✅ MÉTODO TIMEZONE-AWARE
            target.update_count += 1
            
            # Recalcular proximidad si hay targets
            if target.target_prices:
                old_distance = target.closest_target_distance
                target.closest_target_distance = self.calculate_proximity_to_targets(new_price, target.target_prices)
                
                # Log si proximidad cambió significativamente
                if abs(old_distance - target.closest_target_distance) > 0.5:
                    logger.info(f"📊 {symbol}: Proximidad cambió {old_distance:.2f}% → {target.closest_target_distance:.2f}%")
            
            # 🔧 FIX: Recalcular prioridad (LLAMADA CORREGIDA)
            old_priority = target.priority
            new_priority, new_reason = self.determine_monitor_priority(
                symbol, new_price, target.position, target.last_signal  # ✅ Solo 4 argumentos
            )
            
            # Actualizar prioridad si cambió
            if new_priority != old_priority:
                target.priority = new_priority
                target.reason = new_reason
                
                logger.info(f"🔄 {symbol}: Prioridad cambió {old_priority.value} → {new_priority.value}")
                logger.info(f"   Razón: {new_reason}")
            
            # Actualizar contadores
            self.total_updates += 1
            if target.priority == MonitorPriority.CRITICAL:
                self.critical_updates += 1
            elif target.priority == MonitorPriority.HIGH:
                self.high_updates += 1
            elif target.priority == MonitorPriority.NORMAL:
                self.normal_updates += 1
            
            # Log cambio de precio significativo
            if old_price > 0 and abs((new_price - old_price) / old_price) * 100 > 0.5:
                logger.info(f"💹 {symbol}: ${old_price:.2f} → ${new_price:.2f} ({((new_price - old_price) / old_price) * 100:+.2f}%)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando {symbol}: {e}")
            return False
    
    def remove_monitor_target(self, symbol: str, reason: str = "Manual") -> bool:
        """Remover objetivo del monitoreo"""
        try:
            if symbol in self.monitor_targets:
                target = self.monitor_targets[symbol]
                
                logger.info(f"🗑️ {symbol}: Removido del monitoreo - {reason}")
                logger.info(f"   Updates realizados: {target.update_count}")
                logger.info(f"   Última prioridad: {target.priority.value}")
                
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
            now = datetime.now()
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
                    next_update = target.last_update + timedelta(minutes=interval_minutes)
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
                
                # 3. Procesar actualizaciones que ya toca hacer
                now = datetime.now()
                updates_to_process = []
                
                for next_time, symbol, priority in next_updates:
                    if next_time <= now:
                        updates_to_process.append((symbol, priority))
                    else:
                        break  # La lista está ordenada, no hay más por ahora
                
                # 4. Ejecutar actualizaciones
                if updates_to_process:
                    # Ordenar por prioridad (CRITICAL primero)
                    priority_order = {
                        MonitorPriority.CRITICAL: 0,
                        MonitorPriority.HIGH: 1,
                        MonitorPriority.NORMAL: 2,
                        MonitorPriority.LOW: 3,
                        MonitorPriority.SLEEP: 4
                    }
                    
                    updates_to_process.sort(key=lambda x: priority_order[x[1]])
                    
                    # Procesar máximo N símbolos concurrentemente
                    max_concurrent = min(len(updates_to_process), self.schedule.max_concurrent_updates)
                    
                    for symbol, priority in updates_to_process[:max_concurrent]:
                        try:
                            logger.debug(f"🔄 Actualizando {symbol} ({priority.value})")
                            success = self.update_monitor_target(symbol)
                            
                            if not success:
                                logger.warning(f"⚠️ Fallo actualizando {symbol}")
                            
                            # Delay entre actualizaciones para rate limiting
                            time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"❌ Error procesando {symbol}: {e}")
                            continue
                
                # 5. Calcular próximo sleep
                if next_updates:
                    next_time = next_updates[0][0]
                    sleep_seconds = max(10, (next_time - datetime.now()).total_seconds())
                    sleep_seconds = min(sleep_seconds, 300)  # Max 5 min sleep
                else:
                    sleep_seconds = 60
                
                logger.debug(f"⏳ Próxima actualización en {sleep_seconds:.0f}s")
                
                if self.shutdown_event.wait(sleep_seconds):
                    break
            
            logger.info("🏁 Dynamic Monitoring Loop terminado")
            
        except Exception as e:
            logger.error(f"❌ Error crítico en monitoring loop: {e}")
    
    def start_dynamic_monitoring(self) -> bool:
        """Iniciar monitoreo dinámico en thread separado"""
        try:
            if self.running:
                logger.warning("⚠️ Monitoreo ya está ejecutándose")
                return False
            
            logger.info("🚀 Iniciando Dynamic Monitoring System")
            
            self.running = True
            
            self.monitor_thread = threading.Thread(
                target=self.run_dynamic_monitoring_loop,
                name="DynamicMonitoringLoop",
                daemon=False
            )
            
            self.monitor_thread.start()
            
            logger.info("✅ Dynamic Monitoring iniciado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando monitoring: {e}")
            return False
    
    def stop_dynamic_monitoring(self) -> bool:
        """Detener monitoreo dinámico"""
        try:
            logger.info("🛑 Deteniendo Dynamic Monitoring...")
            
            self.running = False
            self.shutdown_event.set()
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                logger.info("⏳ Esperando thread...")
                self.monitor_thread.join(timeout=10)
                
                if self.monitor_thread.is_alive():
                    logger.warning("⚠️ Thread no terminó en tiempo esperado")
            
            logger.info("✅ Dynamic Monitoring detenido")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo monitoring: {e}")
            return False
    
    def get_monitoring_stats(self) -> Dict:
        """Obtener estadísticas del monitoreo dinámico"""
        try:
            # Contar targets por prioridad
            priority_counts = {}
            for priority in MonitorPriority:
                priority_counts[priority.value] = 0
            
            for target in self.monitor_targets.values():
                priority_counts[target.priority.value] += 1
            
            # Próximas actualizaciones
            next_updates = self.get_next_update_schedule()
            next_critical = next((u for u in next_updates if u[2] == MonitorPriority.CRITICAL), None)
            next_high = next((u for u in next_updates if u[2] == MonitorPriority.HIGH), None)
            
            return {
                'running': self.running,
                'total_targets': len(self.monitor_targets),
                'targets_by_priority': priority_counts,
                'total_updates': self.total_updates,
                'critical_updates': self.critical_updates,
                'high_updates': self.high_updates,
                'normal_updates': self.normal_updates,
                'rate_limit_waits': self.rate_limit_waits,
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
                    print(f"   Actualización {i+1}...")
                    success = monitor.update_monitor_target(signal.symbol)
                    if success:
                        target = monitor.monitor_targets[signal.symbol]
                        print(f"   Precio: ${target.current_price:.2f} | Prioridad: {target.priority.value}")
                    time.sleep(2)  # Esperar 2 segundos
                
                # Mostrar estadísticas finales
                print("\n4. 📈 Estadísticas finales:")
                stats = monitor.get_monitoring_stats()
                print(f"   Updates totales: {stats['total_updates']}")
                print(f"   Críticos: {stats['critical_updates']}")
                print(f"   Altos: {stats['high_updates']}")
                print(f"   Normales: {stats['normal_updates']}")
                
                # Mostrar próximas actualizaciones
                next_updates = monitor.get_next_update_schedule()
                if next_updates:
                    print("\n5. ⏰ Próximas actualizaciones:")
                    for next_time, symbol, priority in next_updates[:3]:
                        time_diff = (next_time - datetime.now()).total_seconds() / 60
                        print(f"   {symbol}: {priority.value} en {time_diff:.1f} min")
                
                # Cleanup
                print("\n6. 🧹 Limpiando demo...")
                monitor.remove_monitor_target(signal.symbol, "Demo completado")
                
            else:
                print("❌ Error añadiendo target")
        else:
            print("📊 No hay señales disponibles para demo")
            print("   Probando con símbolo fijo...")
            
            # Demo con símbolo fijo
            success = monitor.add_monitor_target("SPY", reason="Demo fijo")
            if success:
                print("✅ Demo básico completado con SPY")
                monitor.remove_monitor_target("SPY", "Demo completado")
        
        print("\n✅ Demo completado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en demo: {e}")
        return False

if __name__ == "__main__":
    # Menú interactivo para testing
    print("🎯 DYNAMIC MONITOR V2.3 - MODO TESTING")
    print("=" * 60)
    print("Selecciona un test:")
    print("1. Test básico del monitor")
    print("2. Test cálculo de prioridades")
    print("3. Demo con señal real")
    print("")
    
    try:
        choice = input("Elige una opción (1-3): ").strip()
        print("")
        
        if choice == "1":
            test_dynamic_monitor()
        
        elif choice == "2":
            test_priority_calculation()
        
        elif choice == "3":
            demo_dynamic_monitor_with_real_signal()
        
        else:
            print("❌ Opción no válida")
            
    except KeyboardInterrupt:
        print("\n👋 Tests interrumpidos por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando tests: {e}")
    
    print("\n🏁 Tests completados!")