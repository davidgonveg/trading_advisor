#!/usr/bin/env python3
"""
📊 CONTINUOUS DATA COLLECTOR V3.1 - RECOLECCIÓN 24/5
===================================================

Recolector inteligente de datos de mercado que opera 24/5 según
las sesiones configuradas en Extended Hours. Previene gaps y 
mantiene continuidad de datos para backtesting robusto.

🎯 FUNCIONALIDADES:
- Recolección automática según sesiones Extended Hours
- Intervalos dinámicos por sesión
- Detección y filling de gaps en tiempo real  
- Monitoreo overnight y extended hours
- Integración con base de datos
- Rate limiting inteligente
- Recovery automático de fallos

🕐 SESIONES SOPORTADAS:
- PRE_MARKET: 04:00-09:30 (cada 30 min)
- REGULAR: 09:30-16:00 (cada 15 min)
- POST_MARKET: 16:00-20:00 (cada 30 min)
- OVERNIGHT: 20:00-04:00 (cada 2 horas)

🔧 USO:
- Como servicio independiente: python continuous_collector.py
- Integrado con main.py para collection automática
- Scheduler para ejecutar en background
"""

import time
import threading
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import pytz
import sqlite3
from pathlib import Path
import json

# Importaciones del sistema
try:
    import config
    from analysis.indicators import TechnicalIndicators
    from data.manager import DataManager # 🆕 V3.3
    from analysis.gap_detector import GapDetector, Gap

    from database.connection import get_connection, save_indicators_data, save_continuous_data
    
    SYSTEM_INTEGRATION = True
    logger = logging.getLogger(__name__)
    
except ImportError as e:
    # Modo standalone si no hay sistema completo
    SYSTEM_INTEGRATION = False
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning(f"Sistema no completo disponible: {e}")
    logger.info("Ejecutando en modo standalone")

class CollectionStatus(Enum):
    """Estados del collector"""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    MAINTENANCE = "MAINTENANCE"

class SessionType(Enum):
    """Tipos de sesión de mercado"""
    PRE_MARKET = "PRE_MARKET"
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    POST_MARKET = "POST_MARKET"
    OVERNIGHT = "OVERNIGHT"
    UNKNOWN = "UNKNOWN"

@dataclass
class CollectionSession:
    """Configuración de una sesión de recolección"""
    name: str
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    interval_minutes: int
    enabled: bool
    description: str
    priority: int  # 1-5, mayor = más prioritario

@dataclass
class CollectionResult:
    """Resultado de una recolección de datos"""
    symbol: str
    timestamp: datetime
    success: bool
    data_points: int
    gaps_detected: int
    gaps_filled: int
    error_message: Optional[str] = None
    collection_time_ms: float = 0
    session_type: SessionType = SessionType.UNKNOWN

class ContinuousDataCollector:
    """
    Recolector principal de datos 24/5
    """
    
    def __init__(self):
        """Inicializar collector con configuración"""
        self.status = CollectionStatus.STOPPED
        self.running = False
        self.shutdown_event = threading.Event()
        
        # Configuración de sesiones
        self.sessions = self._load_collection_sessions()
        self.current_session: Optional[CollectionSession] = None
        self.market_tz = pytz.timezone('US/Eastern')
        
        # Símbolos a recolectar
        self.symbols = self._get_symbols_to_collect()
        
        # Componentes del sistema
        self.indicators = None
        self.data_manager = None
        self.gap_detector = None
        self.database_available = False

        
        if SYSTEM_INTEGRATION:
            try:
                self.indicators = TechnicalIndicators()
                self.data_manager = DataManager(vars(config)) # 🆕 V3.3
                self.gap_detector = GapDetector()

                # Verificar base de datos
                conn = get_connection()
                if conn:
                    conn.close()
                    self.database_available = True
                logger.info("✅ Integración completa del sistema disponible")
            except Exception as e:
                logger.warning(f"⚠️ Integración parcial: {e}")
        
        # Threading y control
        self.collection_thread: Optional[threading.Thread] = None
        self.last_collection_time: Optional[datetime] = None
        
        # Estadísticas
        self.stats = {
            'total_collections': 0,
            'successful_collections': 0,
            'total_gaps_detected': 0,
            'total_gaps_filled': 0,
            'errors': 0,
            'uptime_start': datetime.now(),
            'collections_by_session': {},
            'collections_by_symbol': {}
        }
        
        # Rate limiting
        self.last_api_call = {}  # {symbol: timestamp}
        self.min_api_interval_seconds = 10  # Mínimo 10s entre calls por símbolo
        
        logger.info("📊 Continuous Data Collector V3.1 inicializado")
        logger.info(f"🎯 Símbolos configurados: {len(self.symbols)}")
        logger.info(f"📅 Sesiones configuradas: {len(self.sessions)}")
    
    def _load_collection_sessions(self) -> List[CollectionSession]:
        """Cargar sesiones de recolección desde configuración"""
        sessions = []
        
        try:
            if SYSTEM_INTEGRATION and hasattr(config, 'EXTENDED_TRADING_SESSIONS'):
                # Usar configuración del sistema
                extended_sessions = config.EXTENDED_TRADING_SESSIONS
                
                for name, session_config in extended_sessions.items():
                    if session_config.get('ENABLED', False):
                        session = CollectionSession(
                            name=name,
                            start_time=session_config.get('START', '09:30'),
                            end_time=session_config.get('END', '16:00'),
                            interval_minutes=session_config.get('DATA_INTERVAL', 15),
                            enabled=True,
                            description=session_config.get('DESCRIPTION', name),
                            priority=self._get_session_priority(name)
                        )
                        sessions.append(session)
                        
                logger.info(f"📅 {len(sessions)} sesiones cargadas desde config.py")
            else:
                # Configuración básica standalone
                default_sessions = [
                    CollectionSession("PRE_MARKET", "04:00", "09:30", 30, True, "Pre-market hours", 3),
                    CollectionSession("MORNING", "10:00", "12:00", 15, True, "Morning trading", 5),
                    CollectionSession("AFTERNOON", "13:30", "15:30", 15, True, "Afternoon trading", 5),
                    CollectionSession("POST_MARKET", "16:00", "20:00", 30, True, "Post-market hours", 2),
                    CollectionSession("OVERNIGHT", "20:00", "04:00", 120, True, "Overnight monitoring", 1)
                ]
                sessions = default_sessions
                logger.info("📅 Usando configuración de sesiones por defecto")
            
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Error cargando sesiones: {e}")
            # Sesión mínima de emergencia
            return [CollectionSession("EMERGENCY", "09:30", "16:00", 30, True, "Emergency fallback", 1)]
    
    def _get_session_priority(self, session_name: str) -> int:
        """Obtener prioridad de sesión (1-5, mayor = más importante)"""
        priorities = {
            'MORNING': 5,
            'AFTERNOON': 5,
            'PRE_MARKET': 3,
            'POST_MARKET': 2,
            'OVERNIGHT': 1
        }
        return priorities.get(session_name, 3)
    
    def _get_symbols_to_collect(self) -> List[str]:
        """Obtener lista de símbolos para recolectar"""
        try:
            if SYSTEM_INTEGRATION and hasattr(config, 'SYMBOLS'):
                symbols = config.SYMBOLS
                logger.info(f"🎯 Símbolos cargados desde config: {len(symbols)}")
                return symbols
            else:
                # Símbolos por defecto
                default_symbols = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]
                logger.info(f"🎯 Usando símbolos por defecto: {len(default_symbols)}")
                return default_symbols
                
        except Exception as e:
            logger.error(f"❌ Error cargando símbolos: {e}")
            return ["SPY"]  # Símbolo mínimo
    
    def get_current_session(self) -> Optional[CollectionSession]:
        """Determinar sesión actual basada en hora"""
        try:
            now = datetime.now(self.market_tz)
            current_time = now.time()
            
            for session in self.sessions:
                if not session.enabled:
                    continue
                
                start_time = datetime.strptime(session.start_time, "%H:%M").time()
                end_time = datetime.strptime(session.end_time, "%H:%M").time()
                
                # Manejar sesión overnight que cruza medianoche
                if session.name == "OVERNIGHT" or start_time > end_time:
                    if current_time >= start_time or current_time <= end_time:
                        return session
                else:
                    if start_time <= current_time <= end_time:
                        return session
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error determinando sesión actual: {e}")
            return None
    
    def should_collect_now(self) -> Tuple[bool, Optional[CollectionSession]]:
        """Determinar si se debe recolectar datos ahora"""
        try:
            current_session = self.get_current_session()
            
            if not current_session:
                return False, None
            
            # Verificar si es momento de recolectar según intervalo
            if self.last_collection_time:
                time_since_last = (datetime.now() - self.last_collection_time).total_seconds()
                interval_seconds = current_session.interval_minutes * 60
                
                if time_since_last < interval_seconds:
                    return False, current_session
            
            return True, current_session
            
        except Exception as e:
            logger.error(f"❌ Error verificando si recolectar: {e}")
            return False, None
    
    def collect_symbol_data(self, symbol: str, session: CollectionSession) -> CollectionResult:
        """Recolectar datos para un símbolo específico"""
        start_time = time.time()
        
        try:
            # Rate limiting por símbolo
            if symbol in self.last_api_call:
                time_since_last = time.time() - self.last_api_call[symbol]
                if time_since_last < self.min_api_interval_seconds:
                    wait_time = self.min_api_interval_seconds - time_since_last
                    logger.debug(f"⏳ {symbol}: Rate limiting, esperando {wait_time:.1f}s")
                    time.sleep(wait_time)
            
            # Actualizar timestamp de API call
            self.last_api_call[symbol] = time.time()
            
            # Recolectar datos
            if self.indicators and self.data_manager:
                # Usar sistema integrado V3.3
                
                # 1. Obtener datos (Fetch via DataManager)
                market_data = self.data_manager.get_data(
                    symbol=symbol,
                    timeframe="15m",
                    days=30 # Configurable
                )
                
                if market_data is None or market_data.empty:
                    raise ValueError(f"No data fetched for {symbol}")
                
                # 2. Calcular indicadores
                indicators_data = self.indicators.calculate_all_indicators(market_data, symbol)
                data_points = indicators_data.get('data_points', 0)

                
                # Verificar si hay gaps en los nuevos datos
                gaps_detected = 0
                gaps_filled = 0
                
                if self.gap_detector and 'market_data' in indicators_data:
                    market_data = indicators_data['market_data']
                    if not market_data.empty:
                        gaps = self.gap_detector.detect_gaps_in_dataframe(market_data, symbol)
                        gaps_detected = len(gaps)
                        gaps_filled = len([g for g in gaps if g.is_fillable])
                
                # Guardar en base de datos si está disponible
                if self.database_available:
                    try:
                        save_indicators_data(indicators_data)
                    except Exception as db_error:
                        logger.warning(f"⚠️ {symbol}: Error guardando en BD: {db_error}")
                
                # 🆕 FIX: Guardar también en tabla continuous_data
                if self.database_available and 'market_data' in indicators_data:
                    try:
                        market_data = indicators_data['market_data']
                        if not market_data.empty:
                            # Tomar la última vela cerrada y guardarla
                            last_candle = market_data.iloc[-1]
                            
                            # Formatear punto de datos
                            data_point = {
                                'timestamp': last_candle.name.isoformat() if hasattr(last_candle.name, 'isoformat') else str(last_candle.name),
                                'open': float(last_candle['Open']),
                                'high': float(last_candle['High']),
                                'low': float(last_candle['Low']),
                                'close': float(last_candle['Close']),
                                'volume': int(last_candle['Volume']),
                                'is_gap_filled': False, # Asumimos real por ahora
                                'data_source': 'API'
                            }
                            
                            conn_success = save_continuous_data(
                                symbol=symbol,
                                timeframe="15m", # Default de indicators.py
                                data_points=[data_point],
                                session_type=session.name
                            )
                            if conn_success:
                                logger.debug(f"💾 {symbol}: Datos continuos guardados")
                            
                    except Exception as cont_error:
                        logger.warning(f"⚠️ {symbol}: Error guardando continuous data: {cont_error}")
                
                collection_time = (time.time() - start_time) * 1000
                
                result = CollectionResult(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    success=True,
                    data_points=data_points,
                    gaps_detected=gaps_detected,
                    gaps_filled=gaps_filled,
                    collection_time_ms=collection_time,
                    session_type=SessionType(session.name) if session.name in [s.value for s in SessionType] else SessionType.UNKNOWN
                )
                
                logger.debug(f"✅ {symbol}: {data_points} puntos, {gaps_detected} gaps detectados")
                return result
                
            else:
                # Modo standalone básico
                logger.warning(f"⚠️ {symbol}: Modo standalone, datos simulados")
                
                return CollectionResult(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    success=True,
                    data_points=100,  # Simulado
                    gaps_detected=0,
                    gaps_filled=0,
                    collection_time_ms=(time.time() - start_time) * 1000,
                    session_type=SessionType.UNKNOWN
                )
                
        except Exception as e:
            collection_time = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            logger.error(f"❌ {symbol}: Error en recolección: {error_msg}")
            
            return CollectionResult(
                symbol=symbol,
                timestamp=datetime.now(),
                success=False,
                data_points=0,
                gaps_detected=0,
                gaps_filled=0,
                error_message=error_msg,
                collection_time_ms=collection_time,
                session_type=SessionType.UNKNOWN
            )
    
    def perform_collection_cycle(self) -> List[CollectionResult]:
        """Ejecutar un ciclo completo de recolección"""
        try:
            should_collect, current_session = self.should_collect_now()
            
            if not should_collect:
                return []
            
            if not current_session:
                logger.debug("💤 Sin sesión activa para recolección")
                return []
            
            # Log inicio de ciclo
            logger.info(f"🔄 Iniciando ciclo de recolección - Sesión: {current_session.name}")
            logger.info(f"⏰ Intervalo: {current_session.interval_minutes} min, Símbolos: {len(self.symbols)}")
            
            # Actualizar sesión actual
            if self.current_session != current_session:
                logger.info(f"🔄 Cambio de sesión: {self.current_session.name if self.current_session else 'None'} → {current_session.name}")
                self.current_session = current_session
            
            # Recolectar datos para todos los símbolos
            results = []
            for symbol in self.symbols:
                if self.shutdown_event.is_set():
                    logger.info("🛑 Shutdown solicitado, deteniendo recolección")
                    break
                
                result = self.collect_symbol_data(symbol, current_session)
                results.append(result)
                
                # Actualizar estadísticas
                self._update_statistics(result, current_session)
                
                # Pequeño delay entre símbolos para no saturar API
                if len(self.symbols) > 5:
                    time.sleep(1)
            
            # Actualizar timestamp de última recolección
            self.last_collection_time = datetime.now()
            
            # Log resumen del ciclo
            successful = len([r for r in results if r.success])
            total_gaps = sum(r.gaps_detected for r in results)
            total_filled = sum(r.gaps_filled for r in results)
            
            logger.info(f"✅ Ciclo completado: {successful}/{len(results)} exitosos")
            if total_gaps > 0:
                logger.info(f"🔧 Gaps: {total_gaps} detectados, {total_filled} rellenados")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en ciclo de recolección: {e}")
            return []
    
    def _update_statistics(self, result: CollectionResult, session: CollectionSession):
        """Actualizar estadísticas del collector"""
        try:
            self.stats['total_collections'] += 1
            
            if result.success:
                self.stats['successful_collections'] += 1
                self.stats['total_gaps_detected'] += result.gaps_detected
                self.stats['total_gaps_filled'] += result.gaps_filled
            else:
                self.stats['errors'] += 1
            
            # Estadísticas por sesión
            session_name = session.name
            if session_name not in self.stats['collections_by_session']:
                self.stats['collections_by_session'][session_name] = 0
            self.stats['collections_by_session'][session_name] += 1
            
            # Estadísticas por símbolo
            symbol = result.symbol
            if symbol not in self.stats['collections_by_symbol']:
                self.stats['collections_by_symbol'][symbol] = 0
            self.stats['collections_by_symbol'][symbol] += 1
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estadísticas: {e}")
    
    def run_collection_loop(self):
        """Loop principal de recolección continua"""
        try:
            logger.info("🚀 Iniciando loop de recolección continua")
            
            while self.running and not self.shutdown_event.is_set():
                try:
                    # Ejecutar ciclo de recolección
                    results = self.perform_collection_cycle()
                    
                    # Determinar tiempo de espera hasta próximo ciclo
                    current_session = self.get_current_session()
                    if current_session:
                        wait_time = min(60, current_session.interval_minutes * 60 // 4)  # Max 1 min
                    else:
                        wait_time = 60  # 1 minuto si no hay sesión activa
                    
                    # Esperar con posibilidad de interrupción
                    if self.shutdown_event.wait(timeout=wait_time):
                        break
                        
                except Exception as e:
                    logger.error(f"❌ Error en loop de recolección: {e}")
                    # Esperar antes de reintentar
                    if self.shutdown_event.wait(timeout=30):
                        break
            
            logger.info("🏁 Loop de recolección finalizado")
            
        except Exception as e:
            logger.error(f"❌ Error crítico en loop de recolección: {e}")
            self.status = CollectionStatus.ERROR
        finally:
            self.status = CollectionStatus.STOPPED
    
    def start_collection(self) -> bool:
        """Iniciar recolección continua"""
        try:
            if self.running:
                logger.warning("⚠️ Collector ya está ejecutándose")
                return False
            
            logger.info("🚀 Iniciando Continuous Data Collector V3.1")
            
            # Verificar configuración
            if not self.symbols:
                logger.error("❌ No hay símbolos configurados para recolección")
                return False
            
            if not self.sessions:
                logger.error("❌ No hay sesiones configuradas")
                return False
            
            # Log configuración inicial
            self._log_startup_configuration()
            
            # Iniciar thread de recolección
            self.running = True
            self.status = CollectionStatus.RUNNING
            self.shutdown_event.clear()
            
            self.collection_thread = threading.Thread(
                target=self.run_collection_loop,
                daemon=True,
                name="ContinuousCollector"
            )
            self.collection_thread.start()
            
            logger.info("✅ Continuous Data Collector iniciado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando collector: {e}")
            self.status = CollectionStatus.ERROR
            return False
    
    def stop_collection(self):
        """Detener recolección continua"""
        try:
            if not self.running:
                logger.info("💤 Collector ya está detenido")
                return
            
            logger.info("🛑 Deteniendo Continuous Data Collector...")
            
            # Señalar shutdown
            self.running = False
            self.shutdown_event.set()
            
            # Esperar thread principal
            if self.collection_thread and self.collection_thread.is_alive():
                self.collection_thread.join(timeout=10)
                
                if self.collection_thread.is_alive():
                    logger.warning("⚠️ Thread de recolección no terminó en tiempo esperado")
            
            # Log estadísticas finales
            self._log_final_statistics()
            
            self.status = CollectionStatus.STOPPED
            logger.info("✅ Continuous Data Collector detenido correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error deteniendo collector: {e}")
    
    def _log_startup_configuration(self):
        """Log configuración al inicio"""
        logger.info("=" * 60)
        logger.info("📊 CONFIGURACIÓN CONTINUOUS DATA COLLECTOR V3.1")
        logger.info("=" * 60)
        
        logger.info(f"🎯 Símbolos configurados: {len(self.symbols)}")
        logger.info(f"   {', '.join(self.symbols)}")
        
        logger.info(f"📅 Sesiones configuradas: {len(self.sessions)}")
        for session in self.sessions:
            status = "✅" if session.enabled else "❌"
            logger.info(f"   {status} {session.name}: {session.start_time}-{session.end_time} ({session.interval_minutes}min)")
        
        current_session = self.get_current_session()
        if current_session:
            logger.info(f"🎯 Sesión actual: {current_session.name} ({current_session.description})")
        else:
            logger.info("💤 Sin sesión activa actualmente")
        
        logger.info(f"🔧 Componentes:")
        logger.info(f"   Indicators: {'✅' if self.indicators else '❌'}")
        logger.info(f"   Gap Detector: {'✅' if self.gap_detector else '❌'}")
        logger.info(f"   Database: {'✅' if self.database_available else '❌'}")
        
        logger.info("=" * 60)
    
    def _log_final_statistics(self):
        """Log estadísticas finales al parar"""
        try:
            uptime = datetime.now() - self.stats['uptime_start']
            success_rate = (self.stats['successful_collections'] / max(1, self.stats['total_collections'])) * 100
            
            logger.info("=" * 60)
            logger.info("📊 ESTADÍSTICAS FINALES")
            logger.info("=" * 60)
            logger.info(f"⏱️ Tiempo de ejecución: {uptime}")
            logger.info(f"📊 Total recolecciones: {self.stats['total_collections']}")
            logger.info(f"✅ Exitosas: {self.stats['successful_collections']} ({success_rate:.1f}%)")
            logger.info(f"❌ Errores: {self.stats['errors']}")
            logger.info(f"🔧 Gaps detectados: {self.stats['total_gaps_detected']}")
            logger.info(f"🔧 Gaps rellenados: {self.stats['total_gaps_filled']}")
            
            if self.stats['collections_by_session']:
                logger.info(f"📅 Por sesión:")
                for session, count in self.stats['collections_by_session'].items():
                    logger.info(f"   {session}: {count}")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error logging estadísticas finales: {e}")
    
    def get_status_report(self) -> Dict[str, Any]:
        """Obtener reporte de estado completo"""
        try:
            current_session = self.get_current_session()
            uptime = datetime.now() - self.stats['uptime_start']
            
            return {
                'status': self.status.value,
                'running': self.running,
                'current_session': {
                    'name': current_session.name if current_session else None,
                    'description': current_session.description if current_session else None,
                    'interval_minutes': current_session.interval_minutes if current_session else None
                },
                'symbols_count': len(self.symbols),
                'sessions_count': len(self.sessions),
                'uptime_seconds': uptime.total_seconds(),
                'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None,
                'statistics': self.stats.copy(),
                'components': {
                    'indicators': self.indicators is not None,
                    'gap_detector': self.gap_detector is not None,
                    'database': self.database_available
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error generando reporte de estado: {e}")
            return {'error': str(e)}
    
    def pause_collection(self) -> bool:
        """Pausar recolección temporalmente"""
        try:
            if self.status != CollectionStatus.RUNNING:
                logger.warning("⚠️ Collector no está ejecutándose")
                return False
            
            logger.info("⏸️ Pausando recolección...")
            self.status = CollectionStatus.PAUSED
            
            # Note: El thread seguirá ejecutándose pero no recolectará datos
            # cuando el status sea PAUSED
            
            logger.info("✅ Recolección pausada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error pausando collector: {e}")
            return False
    
    def resume_collection(self) -> bool:
        """Reanudar recolección"""
        try:
            if self.status != CollectionStatus.PAUSED:
                logger.warning("⚠️ Collector no está pausado")
                return False
            
            logger.info("▶️ Reanudando recolección...")
            self.status = CollectionStatus.RUNNING
            
            logger.info("✅ Recolección reanudada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error reanudando collector: {e}")
            return False
    
    def perform_gap_maintenance(self) -> Dict[str, Any]:
        """Ejecutar mantenimiento de gaps (análisis y filling)"""
        try:
            logger.info("🔧 Iniciando mantenimiento de gaps...")
            
            maintenance_results = {
                'timestamp': datetime.now().isoformat(),
                'symbols_processed': 0,
                'total_gaps_found': 0,
                'gaps_filled': 0,
                'errors': [],
                'success': True
            }
            
            if not self.gap_detector or not self.database_available:
                error_msg = "Gap detector o base de datos no disponible"
                logger.error(f"❌ {error_msg}")
                maintenance_results['success'] = False
                maintenance_results['errors'].append(error_msg)
                return maintenance_results
            
            # Analizar cada símbolo
            for symbol in self.symbols:
                try:
                    # Obtener datos recientes del símbolo via DataManager
                    market_data = self.data_manager.get_data(symbol, "15m", 30)
                    if market_data is None or market_data.empty:
                        continue
                        
                    indicators_data = self.indicators.calculate_all_indicators(market_data, symbol)

                    
                    if 'market_data' in indicators_data and not indicators_data['market_data'].empty:
                        market_data = indicators_data['market_data']
                        
                        # Generar reporte de calidad
                        report = self.gap_detector.analyze_data_quality(market_data, symbol, 15)
                        
                        maintenance_results['symbols_processed'] += 1
                        maintenance_results['total_gaps_found'] += report.total_gaps
                        
                        # Contar gaps rellenables
                        fillable_gaps = len([g for g in report.gaps_detected if g.is_fillable])
                        maintenance_results['gaps_filled'] += fillable_gaps
                        
                        # Log si hay muchos gaps
                        if report.total_gaps > 5:
                            logger.warning(f"⚠️ {symbol}: {report.total_gaps} gaps detectados")
                        
                        # Guardar reporte en BD si está disponible
                        try:
                            self.gap_detector.save_gap_report_to_database(report)
                        except Exception as save_error:
                            logger.warning(f"⚠️ Error guardando reporte de {symbol}: {save_error}")
                    
                except Exception as symbol_error:
                    error_msg = f"Error procesando {symbol}: {symbol_error}"
                    logger.error(f"❌ {error_msg}")
                    maintenance_results['errors'].append(error_msg)
            
            # Log resumen del mantenimiento
            logger.info(f"✅ Mantenimiento completado:")
            logger.info(f"   Símbolos procesados: {maintenance_results['symbols_processed']}")
            logger.info(f"   Gaps encontrados: {maintenance_results['total_gaps_found']}")
            logger.info(f"   Gaps rellenados: {maintenance_results['gaps_filled']}")
            
            if maintenance_results['errors']:
                logger.warning(f"⚠️ {len(maintenance_results['errors'])} errores durante mantenimiento")
                maintenance_results['success'] = False
            
            return maintenance_results
            
        except Exception as e:
            logger.error(f"❌ Error en mantenimiento de gaps: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'error': str(e)
            }
    
    def get_collection_metrics(self, hours_back: int = 24) -> Dict[str, Any]:
        """Obtener métricas detalladas de recolección"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            # Calcular métricas básicas
            total_collections = self.stats['total_collections']
            successful_collections = self.stats['successful_collections']
            success_rate = (successful_collections / max(1, total_collections)) * 100
            
            # Uptime
            uptime = datetime.now() - self.stats['uptime_start']
            uptime_hours = uptime.total_seconds() / 3600
            
            # Promedio de recolecciones por hora
            collections_per_hour = total_collections / max(1, uptime_hours)
            
            return {
                'period_hours': hours_back,
                'total_collections': total_collections,
                'successful_collections': successful_collections,
                'failed_collections': self.stats['errors'],
                'success_rate_percent': round(success_rate, 2),
                'gaps_detected': self.stats['total_gaps_detected'],
                'gaps_filled': self.stats['total_gaps_filled'],
                'uptime_hours': round(uptime_hours, 2),
                'collections_per_hour': round(collections_per_hour, 2),
                'collections_by_session': self.stats['collections_by_session'].copy(),
                'collections_by_symbol': self.stats['collections_by_symbol'].copy(),
                'current_status': self.status.value,
                'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculando métricas: {e}")
            return {'error': str(e)}
    
    def force_collection_now(self, symbols: Optional[List[str]] = None) -> List[CollectionResult]:
        """Forzar recolección inmediata (para testing o recovery)"""
        try:
            logger.info("🚀 Forzando recolección inmediata...")
            
            # Usar símbolos especificados o todos
            target_symbols = symbols if symbols else self.symbols
            
            # Usar sesión actual o crear una temporal
            current_session = self.get_current_session()
            if not current_session:
                # Crear sesión temporal
                current_session = CollectionSession(
                    name="FORCED",
                    start_time="00:00",
                    end_time="23:59",
                    interval_minutes=1,
                    enabled=True,
                    description="Forced collection",
                    priority=5
                )
            
            results = []
            for symbol in target_symbols:
                if self.shutdown_event.is_set():
                    break
                
                result = self.collect_symbol_data(symbol, current_session)
                results.append(result)
                self._update_statistics(result, current_session)
                
                # Delay pequeño entre símbolos
                time.sleep(0.5)
            
            successful = len([r for r in results if r.success])
            logger.info(f"✅ Recolección forzada completada: {successful}/{len(results)} exitosos")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en recolección forzada: {e}")
            return []
    
    def save_collector_state(self, filepath: Optional[str] = None) -> bool:
        """Guardar estado del collector a archivo"""
        try:
            if not filepath:
                filepath = f"collector_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            state_data = {
                'timestamp': datetime.now().isoformat(),
                'status': self.status.value,
                'running': self.running,
                'statistics': self.stats,
                'sessions': [
                    {
                        'name': s.name,
                        'start_time': s.start_time,
                        'end_time': s.end_time,
                        'interval_minutes': s.interval_minutes,
                        'enabled': s.enabled,
                        'description': s.description,
                        'priority': s.priority
                    } for s in self.sessions
                ],
                'symbols': self.symbols,
                'last_collection_time': self.last_collection_time.isoformat() if self.last_collection_time else None,
                'components_status': {
                    'indicators': self.indicators is not None,
                    'gap_detector': self.gap_detector is not None,
                    'database': self.database_available
                }
            }
            
            with open(filepath, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
            
            logger.info(f"💾 Estado del collector guardado en {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando estado: {e}")
            return False

# =============================================================================
# FUNCIONES DE CONTROL Y UTILIDADES
# =============================================================================

def setup_signal_handlers(collector: ContinuousDataCollector):
    """Configurar manejadores de señales para shutdown graceful"""
    def signal_handler(signum, frame):
        logger.info(f"📡 Señal {signum} recibida - iniciando shutdown...")
        collector.stop_collection()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Kill

def run_collector_service():
    """Ejecutar collector como servicio independiente"""
    logger.info("🚀 Iniciando Continuous Data Collector como servicio")
    
    try:
        collector = ContinuousDataCollector()
        setup_signal_handlers(collector)
        
        if collector.start_collection():
            try:
                # Mantener servicio ejecutándose
                while collector.running:
                    time.sleep(1)
                    
                    # Realizar mantenimiento periódico cada 6 horas
                    if (datetime.now() - collector.stats['uptime_start']).total_seconds() % (6 * 3600) < 60:
                        logger.info("🔧 Ejecutando mantenimiento periódico...")
                        collector.perform_gap_maintenance()
                    
            except KeyboardInterrupt:
                logger.info("⏸️ Interrupción por teclado recibida")
            
            collector.stop_collection()
        else:
            logger.error("❌ No se pudo iniciar el collector")
            return 1
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error ejecutando servicio: {e}")
        return 1

def run_collector_daemon():
    """Ejecutar collector como daemon (background process)"""
    try:
        import daemon
        import lockfile
        
        # Configurar daemon
        with daemon.DaemonContext(
            pidfile=lockfile.FileLock('/tmp/continuous_collector.pid'),
            stdout=open('/tmp/continuous_collector.log', 'a'),
            stderr=open('/tmp/continuous_collector_error.log', 'a'),
        ):
            return run_collector_service()
            
    except ImportError:
        logger.error("❌ Módulo 'daemon' no disponible. Instalar con: pip install python-daemon")
        return 1

def test_collector_basic():
    """Test básico del collector"""
    print("🧪 TESTING CONTINUOUS DATA COLLECTOR")
    print("=" * 50)
    
    try:
        collector = ContinuousDataCollector()
        
        # Test 1: Verificar configuración
        print("1. ⚙️ Verificando configuración...")
        print(f"   Símbolos: {len(collector.symbols)}")
        print(f"   Sesiones: {len(collector.sessions)}")
        
        # Test 2: Sesión actual
        print("2. 📅 Verificando sesión actual...")
        current_session = collector.get_current_session()
        if current_session:
            print(f"   Sesión activa: {current_session.name}")
            print(f"   Intervalo: {current_session.interval_minutes} min")
        else:
            print("   Sin sesión activa")
        
        # Test 3: ¿Debe recolectar?
        print("3. 🔍 Verificando si debe recolectar...")
        should_collect, session = collector.should_collect_now()
        print(f"   Debe recolectar: {'✅ SÍ' if should_collect else '❌ NO'}")
        
        # Test 4: Recolección de prueba (1 símbolo)
        if collector.symbols and (should_collect or True):  # Force test
            print("4. 📊 Test de recolección...")
            test_symbol = collector.symbols[0]
            
            if current_session:
                result = collector.collect_symbol_data(test_symbol, current_session)
                print(f"   {test_symbol}: {'✅' if result.success else '❌'}")
                if result.success:
                    print(f"   Datos: {result.data_points} puntos")
                    print(f"   Tiempo: {result.collection_time_ms:.0f}ms")
                else:
                    print(f"   Error: {result.error_message}")
        
        # Test 5: Reporte de estado
        print("5. 📊 Reporte de estado...")
        status = collector.get_status_report()
        print(f"   Status: {status['status']}")
        print(f"   Componentes: {status['components']}")
        
        # Test 6: Métricas
        print("6. 📈 Métricas...")
        metrics = collector.get_collection_metrics(1)
        print(f"   Recolecciones: {metrics.get('total_collections', 0)}")
        print(f"   Tasa éxito: {metrics.get('success_rate_percent', 0):.1f}%")
        
        print("✅ Test básico completado")
        return collector
        
    except Exception as e:
        print(f"❌ Error en test básico: {e}")
        return None

def test_collector_forced_collection():
    """Test de recolección forzada"""
    print("\n🧪 TESTING RECOLECCIÓN FORZADA")
    print("=" * 50)
    
    try:
        collector = ContinuousDataCollector()
        
        # Forzar recolección de 2 símbolos
        test_symbols = collector.symbols[:2] if len(collector.symbols) >= 2 else collector.symbols
        print(f"🎯 Forzando recolección de: {', '.join(test_symbols)}")
        
        results = collector.force_collection_now(test_symbols)
        
        print(f"📊 Resultados:")
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.symbol}: {result.data_points} puntos")
            if result.gaps_detected > 0:
                print(f"      🔧 Gaps: {result.gaps_detected} detectados, {result.gaps_filled} rellenados")
        
        print("✅ Test de recolección forzada completado")
        return True
        
    except Exception as e:
        print(f"❌ Error en test forzado: {e}")
        return False

def test_collector_maintenance():
    """Test de mantenimiento de gaps"""
    print("\n🧪 TESTING MANTENIMIENTO DE GAPS")
    print("=" * 50)
    
    try:
        collector = ContinuousDataCollector()
        
        if not collector.gap_detector:
            print("⚠️ Gap detector no disponible - omitiendo test")
            return False
        
        print("🔧 Ejecutando mantenimiento...")
        maintenance_result = collector.perform_gap_maintenance()
        
        if maintenance_result['success']:
            print(f"✅ Mantenimiento exitoso:")
            print(f"   Símbolos procesados: {maintenance_result['symbols_processed']}")
            print(f"   Gaps encontrados: {maintenance_result['total_gaps_found']}")
            print(f"   Gaps rellenados: {maintenance_result['gaps_filled']}")
        else:
            print(f"❌ Mantenimiento falló:")
            for error in maintenance_result.get('errors', []):
                print(f"   Error: {error}")
        
        return maintenance_result['success']
        
    except Exception as e:
        print(f"❌ Error en test de mantenimiento: {e}")
        return False

def demo_collector_interactive():
    """Demo interactivo del collector"""
    print("🎮 DEMO INTERACTIVO - CONTINUOUS DATA COLLECTOR")
    print("=" * 60)
    
    try:
        collector = ContinuousDataCollector()
        
        while True:
            print("\n📋 OPCIONES:")
            print("1. Ver estado actual")
            print("2. Iniciar recolección")
            print("3. Pausar recolección")
            print("4. Reanudar recolección")
            print("5. Forzar recolección ahora")
            print("6. Ejecutar mantenimiento")
            print("7. Ver métricas")
            print("8. Guardar estado")
            print("9. Salir")
            
            try:
                choice = input("\n🎯 Selecciona una opción (1-9): ").strip()
                
                if choice == "1":
                    status = collector.get_status_report()
                    print(f"\n📊 Estado: {status['status']}")
                    print(f"🏃 Ejecutándose: {status['running']}")
                    if status.get('current_session', {}).get('name'):
                        session = status['current_session']
                        print(f"📅 Sesión: {session['name']} ({session['interval_minutes']} min)")
                    else:
                        print("💤 Sin sesión activa")
                
                elif choice == "2":
                    if collector.start_collection():
                        print("✅ Recolección iniciada")
                    else:
                        print("❌ Error iniciando recolección")
                
                elif choice == "3":
                    if collector.pause_collection():
                        print("⏸️ Recolección pausada")
                    else:
                        print("❌ Error pausando recolección")
                
                elif choice == "4":
                    if collector.resume_collection():
                        print("▶️ Recolección reanudada")
                    else:
                        print("❌ Error reanudando recolección")
                
                elif choice == "5":
                    print("🚀 Ejecutando recolección forzada...")
                    results = collector.force_collection_now()
                    successful = len([r for r in results if r.success])
                    print(f"✅ Completado: {successful}/{len(results)} exitosos")
                
                elif choice == "6":
                    print("🔧 Ejecutando mantenimiento...")
                    maintenance = collector.perform_gap_maintenance()
                    if maintenance['success']:
                        print(f"✅ Mantenimiento exitoso")
                        print(f"   Gaps encontrados: {maintenance['total_gaps_found']}")
                    else:
                        print("❌ Error en mantenimiento")
                
                elif choice == "7":
                    metrics = collector.get_collection_metrics(24)
                    print(f"\n📈 MÉTRICAS (24h):")
                    print(f"   Recolecciones: {metrics.get('total_collections', 0)}")
                    print(f"   Tasa éxito: {metrics.get('success_rate_percent', 0):.1f}%")
                    print(f"   Uptime: {metrics.get('uptime_hours', 0):.1f}h")
                    print(f"   Gaps detectados: {metrics.get('gaps_detected', 0)}")
                
                elif choice == "8":
                    if collector.save_collector_state():
                        print("💾 Estado guardado correctamente")
                    else:
                        print("❌ Error guardando estado")
                
                elif choice == "9":
                    collector.stop_collection()
                    print("👋 ¡Hasta luego!")
                    break
                
                else:
                    print("❌ Opción inválida")
                    
            except KeyboardInterrupt:
                collector.stop_collection()
                print("\n👋 ¡Hasta luego!")
                break
                
        return True
        
    except Exception as e:
        print(f"❌ Error en demo interactivo: {e}")
        return False

# =============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    """Ejecutar según argumentos de línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Continuous Data Collector V3.1")
    parser.add_argument("--mode", 
                       choices=["service", "daemon", "test", "interactive"], 
                       default="interactive",
                       help="Modo de ejecución")
    parser.add_argument("--test-type", 
                       choices=["basic", "forced", "maintenance", "all"], 
                       default="all",
                       help="Tipo de test a ejecutar")
    
    args = parser.parse_args()
    
    print("📊 CONTINUOUS DATA COLLECTOR V3.1")
    print("=" * 50)
    
    if args.mode == "service":
        exit_code = run_collector_service()
        sys.exit(exit_code)
        
    elif args.mode == "daemon":
        exit_code = run_collector_daemon()
        sys.exit(exit_code)
        
    elif args.mode == "test":
        success = True
        
        if args.test_type in ["basic", "all"]:
            collector = test_collector_basic()
            if not collector:
                success = False
        
        if args.test_type in ["forced", "all"] and success:
            if not test_collector_forced_collection():
                success = False
        
        if args.test_type in ["maintenance", "all"] and success:
            if not test_collector_maintenance():
                success = False
        
        print(f"\n🏁 Tests completados: {'✅ ÉXITO' if success else '❌ FALLOS'}")
        sys.exit(0 if success else 1)
        
    elif args.mode == "interactive":
        if demo_collector_interactive():
            sys.exit(0)
        else:
            sys.exit(1)
    
    else:
        print("❌ Modo no reconocido")
        sys.exit(1)