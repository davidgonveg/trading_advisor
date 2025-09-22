#!/usr/bin/env python3
"""
📱 SISTEMA DE ALERTAS POR TELEGRAM - TRADING AUTOMATIZADO V2.0 + V3.0 FIX
=======================================================================

Este módulo maneja todas las comunicaciones por Telegram:
- Envío de alertas de señales formateadas
- Notificaciones de sistema (inicio, errores)
- Mensajes de test y confirmación
- Manejo de errores de conectividad

🔧 FIXED V3.0: Mejorada detección de targets adaptativos

Formatos de Mensajes:
- 🟢 Señales LONG con emojis y formato HTML
- 🔴 Señales SHORT con información completa
- ⚠️ Alertas de sistema y errores
- 📊 Resúmenes y estadísticas
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
import pytz
from telegram import Bot
from telegram.error import TelegramError, NetworkError, TimedOut
import html

# Importar configuración y módulos del sistema
import config
# 🆕 V3.0: Import targets adaptativos
try:
    import config
    if getattr(config, 'USE_ADAPTIVE_TARGETS', False):
        from position_calculator import PositionPlan as PositionPlanV3
        V3_AVAILABLE = True
    else:
        V3_AVAILABLE = False
except ImportError:
    V3_AVAILABLE = False
    
from scanner import TradingSignal
from position_calculator import PositionPlan

# Configurar logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, 'INFO'))
logger = logging.getLogger(__name__)

class TelegramBot:
    """
    Bot de Telegram para enviar alertas de trading de alta calidad
    """
    
    def __init__(self):
        """Inicializar el bot de Telegram con configuración"""
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.CHAT_ID
        self.bot = None
        self.initialized = False
        
        # Zona horaria para timestamps
        self.timezone = pytz.timezone(config.MARKET_TIMEZONE)
        self.spain_tz = pytz.timezone('Europe/Madrid')
        
        # Configuración de mensajes
        self.parse_mode = config.TELEGRAM_CONFIG.get('PARSE_MODE', 'HTML')
        self.timeout = config.TELEGRAM_CONFIG.get('TIMEOUT', 30)
        
        # Contadores y estadísticas
        self.messages_sent = 0
        self.errors_count = 0
        self.last_message_time = None
        
        self._initialize_bot()
    
    def _initialize_bot(self) -> bool:
        """
        Inicializar la conexión con Telegram
        
        Returns:
            True si se inicializa correctamente, False si hay error
        """
        try:
            if not self.token or not self.chat_id:
                raise ValueError("TELEGRAM_TOKEN o CHAT_ID no configurados en .env")
            
            self.bot = Bot(token=self.token)
            self.initialized = True
            
            logger.info("📱 Bot de Telegram inicializado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando bot de Telegram: {e}")
            self.initialized = False
            return False
    
    def format_signal_alert(self, signal: TradingSignal) -> str:
        """
        🔧 FIXED V3.0: Formatear señal de trading como mensaje HTML para Telegram
        Ahora detecta correctamente los targets adaptativos V3.0
        
        Args:
            signal: TradingSignal con toda la información
            
        Returns:
            Mensaje formateado en HTML
        """
        try:
            # Emojis según tipo de señal
            direction_emoji = "🟢" if signal.signal_type == "LONG" else "🔴"
            direction_name = "COMPRA" if signal.signal_type == "LONG" else "VENTA"
            
            # Emoji de confianza
            confidence_emoji = {
                "VERY_HIGH": "🔥",
                "HIGH": "💪", 
                "MEDIUM": "⚡",
                "LOW": "⚠️"
            }.get(signal.confidence_level, "📊")
            
            # Hora actual en España
            spain_time = signal.timestamp.astimezone(self.spain_tz)
            time_str = spain_time.strftime("%H:%M")
            
            # Determinar sesión
            hour = spain_time.hour
            if 15 <= hour < 18:
                session = "Mañana"
            elif 19 <= hour < 22:
                session = "Tarde"
            else:
                session = "Fuera de horario"
            
            # Construir mensaje principal
            message_lines = []
            
            # === CABECERA ===
            message_lines.append(f"{direction_emoji} <b>SEÑAL {direction_name} - {signal.symbol}</b>")
            message_lines.append(f"📊 <b>Fuerza:</b> {signal.signal_strength}/100 | <b>Confianza:</b> {signal.confidence_level}")
            message_lines.append(f"💰 <b>Precio:</b> ${signal.current_price:.2f}")
            message_lines.append(f"⏰ <b>Hora:</b> {time_str} España ({session})")
            message_lines.append("")
            
            # 🔧 FIX V3.0: VERIFICACIÓN MEJORADA PARA TARGETS ADAPTATIVOS
            has_position_plan = hasattr(signal, 'position_plan') and signal.position_plan is not None
            
            if has_position_plan:
                plan = signal.position_plan
                
                # 🔧 FIX: Verificación mejorada para targets adaptativos
                has_adaptive_targets = (
                    hasattr(plan, 'exits') and 
                    len(plan.exits) > 0 and 
                    any(
                        hasattr(exit_level, 'risk_reward') or 
                        hasattr(exit_level, 'technical_basis') or
                        hasattr(exit_level, 'confidence')
                        for exit_level in plan.exits
                    )
                )
                
                logger.info(f"🔍 DEBUG: {signal.symbol} - Plan exists: {has_position_plan}, Adaptive: {has_adaptive_targets}")
                
                if has_adaptive_targets:
                    # === MOSTRAR TARGETS ADAPTATIVOS V3.0 ===
                    message_lines.append("🎯 <b>TARGETS ADAPTATIVOS V3.0:</b>")
                    
                    # Mostrar entradas optimizadas
                    if hasattr(plan, 'entries') and plan.entries:
                        message_lines.append("💰 <b>ENTRADAS OPTIMIZADAS:</b>")
                        for i, entry in enumerate(plan.entries, 1):
                            message_lines.append(f"• <b>E{i}</b> ({entry.percentage}%): ${entry.price:.2f}")
                        message_lines.append("")
                    
                    # Mostrar targets adaptativos
                    message_lines.append("🎯 <b>SALIDAS ADAPTATIVAS:</b>")
                    for i, exit_level in enumerate(plan.exits, 1):
                        # R:R del target
                        rr_text = f" - {exit_level.risk_reward:.1f}R" if hasattr(exit_level, 'risk_reward') and exit_level.risk_reward else ""
                        message_lines.append(f"• <b>TP{i}</b> ({exit_level.percentage}%): ${exit_level.price:.2f}{rr_text}")
                        
                        # Mostrar confianza si está disponible
                        if hasattr(exit_level, 'confidence') and exit_level.confidence:
                            message_lines.append(f"  📊 Confianza: {exit_level.confidence:.0f}%")
                        
                        # Mostrar base técnica (máximo 1 línea)
                        if hasattr(exit_level, 'technical_basis') and exit_level.technical_basis:
                            if isinstance(exit_level.technical_basis, list) and exit_level.technical_basis:
                                basis = exit_level.technical_basis[0]
                            else:
                                basis = str(exit_level.technical_basis)
                            message_lines.append(f"  🔍 Base: {basis}")
                    
                    message_lines.append("")
                    
                    # Stop loss adaptativo
                    if hasattr(plan, 'stop_loss') and plan.stop_loss:
                        stop = plan.stop_loss
                        message_lines.append("🛡️ <b>STOP LOSS ADAPTATIVO:</b>")
                        message_lines.append(f"• <b>Stop:</b> ${stop.price:.2f} ({stop.description})")
                        message_lines.append("")
                    
                    # Métricas V3.0
                    message_lines.append("📈 <b>MÉTRICAS ADAPTATIVAS:</b>")
                    if hasattr(plan, 'max_risk_reward'):
                        message_lines.append(f"• <b>R:R Máximo:</b> 1:{plan.max_risk_reward:.1f}")
                    if hasattr(plan, 'avg_risk_reward'):
                        message_lines.append(f"• <b>R:R Promedio:</b> 1:{plan.avg_risk_reward:.1f}")
                    if hasattr(plan, 'strategy_type'):
                        message_lines.append(f"• <b>Estrategia:</b> {plan.strategy_type}")
                    if hasattr(plan, 'total_risk_percent'):
                        message_lines.append(f"• <b>Riesgo Total:</b> {plan.total_risk_percent:.1f}%")
                    message_lines.append("")
                    
                    # Análisis técnico V3.0
                    if hasattr(plan, 'technical_summary') and plan.technical_summary:
                        message_lines.append("🔍 <b>ANÁLISIS TÉCNICO V3.0:</b>")
                        message_lines.append(f"• {plan.technical_summary}")
                        if hasattr(plan, 'market_context'):
                            message_lines.append(f"• {plan.market_context}")
                        message_lines.append("")
                
                else:
                    # === FALLBACK: PLAN CLÁSICO V2.0 (si no hay targets adaptativos) ===
                    logger.warning(f"⚠️ {signal.symbol}: No se detectaron targets adaptativos, usando plan clásico")
                    
                    # Mostrar entradas básicas
                    if hasattr(plan, 'entries') and plan.entries:
                        message_lines.append("💰 <b>ENTRADAS CLÁSICAS:</b>")
                        for i, entry in enumerate(plan.entries, 1):
                            message_lines.append(f"• <b>Entrada {i}</b> ({entry.percentage}%): ${entry.price:.2f}")
                        message_lines.append("")
                    
                    # Mostrar salidas básicas
                    if hasattr(plan, 'exits') and plan.exits:
                        message_lines.append("🎯 <b>TARGETS CLÁSICOS:</b>")
                        for i, exit_level in enumerate(plan.exits, 1):
                            message_lines.append(f"• <b>TP{i}</b> ({exit_level.percentage}%): ${exit_level.price:.2f}")
                        message_lines.append("")
                    
                    # Stop loss básico
                    if hasattr(plan, 'stop_loss') and plan.stop_loss:
                        message_lines.append(f"🛡️ <b>Stop Loss:</b> ${plan.stop_loss.price:.2f}")
                        message_lines.append("")
            
            else:
                # === SIN PLAN DE POSICIÓN ===
                logger.warning(f"⚠️ {signal.symbol}: No hay plan de posición disponible")
                message_lines.append("⚠️ <b>Plan de posición no disponible</b>")
                message_lines.append("💡 Revisar configuración de targets adaptativos")
                message_lines.append("")
            
            # === ANÁLISIS TÉCNICO ===
            message_lines.append("🔍 <b>ANÁLISIS TÉCNICO:</b>")
            
            # Formatear indicadores técnicos
            indicators_status = []
            for indicator, signal_value in signal.indicator_signals.items():
                emoji = self._get_indicator_emoji(signal_value)
                
                if indicator == "MACD":
                    indicators_status.append(f"MACD: {emoji}")
                elif indicator == "RSI":
                    rsi_value = self._extract_rsi_value(signal_value)
                    indicators_status.append(f"RSI: {rsi_value} {emoji}")
                elif indicator == "VWAP":
                    indicators_status.append(f"VWAP: {emoji}")
                elif indicator == "ROC":
                    roc_text = self._extract_roc_text(signal_value)
                    indicators_status.append(f"ROC: {roc_text} {emoji}")
                elif indicator == "BOLLINGER":
                    indicators_status.append(f"BB: {emoji}")
                elif indicator == "VOLUME":
                    indicators_status.append(f"VOL: {emoji}")
            
            # Dividir indicadores en líneas
            message_lines.append(" | ".join(indicators_status[:3]))
            if len(indicators_status) > 3:
                message_lines.append(" | ".join(indicators_status[3:]))
            message_lines.append("")
            
            # === CONTEXTO DE MERCADO ===
            if signal.market_context:
                message_lines.append(f"🌐 <b>Contexto:</b> {signal.market_context}")
                message_lines.append("")
            
            # === FOOTER ===
            version_info = "V3.0 Targets Adaptativos" if has_position_plan and has_adaptive_targets else "V2.0 Clásico"
            message_lines.append(f"{confidence_emoji} <i>Trading automatizado {version_info} - Señal #{signal.signal_strength}</i>")
            
            return "\n".join(message_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formateando mensaje de señal: {e}")
            return f"❌ Error formateando señal para {signal.symbol}: {str(e)}"
    
    def _get_indicator_emoji(self, signal_value: str) -> str:
        """Obtener emoji para valor de indicador"""
        positive_signals = [
            'BULLISH_CROSS', 'OVERSOLD', 'NEAR_VWAP', 'STRONG_BULLISH', 
            'MODERATE_BULLISH', 'LOWER_BAND', 'HIGH', 'ABOVE_UPPER',
            'BELOW_LOWER', 'BEARISH_CROSS', 'OVERBOUGHT', 'AWAY_VWAP',
            'STRONG_BEARISH', 'MODERATE_BEARISH', 'UPPER_BAND'
        ]
        
        return "✅" if signal_value in positive_signals else "⚡"
    
    def _extract_rsi_value(self, rsi_signal: str) -> str:
        """Extraer valor numérico del RSI para mostrar"""
        rsi_map = {
            "OVERSOLD_EXTREME": "< 30",
            "OVERSOLD": "< 40", 
            "WEAK": "40-50",
            "NEUTRAL": "50-60",
            "OVERBOUGHT": "> 60",
            "OVERBOUGHT_EXTREME": "> 70"
        }
        return rsi_map.get(rsi_signal, "50")
    
    def _extract_roc_text(self, roc_signal: str) -> str:
        """Extraer texto del ROC para mostrar"""
        roc_map = {
            "VERY_STRONG_BULLISH": "+3%+",
            "STRONG_BULLISH": "+2%",
            "MODERATE_BULLISH": "+1%",
            "NEUTRAL": "0%",
            "MODERATE_BEARISH": "-1%",
            "STRONG_BEARISH": "-2%",
            "VERY_STRONG_BEARISH": "-3%-"
        }
        return roc_map.get(roc_signal, "0%")
    
    def send_message(self, message: str, disable_preview: bool = True) -> bool:
        """
        Enviar mensaje por Telegram de forma síncrona
        
        Args:
            message: Mensaje a enviar
            disable_preview: Desactivar preview de links
            
        Returns:
            True si se envía correctamente, False si hay error
        """
        try:
            if not self.initialized:
                logger.error("❌ Bot no inicializado")
                return False
            
            # Ejecutar envío asíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    self.send_message_async(message, disable_preview)
                )
                return result
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje: {e}")
            self.errors_count += 1
            return False
    
    def send_signal_alert(self, signal: TradingSignal) -> bool:
        """
        Enviar alerta de señal formateada
        
        Args:
            signal: TradingSignal para formatear y enviar
            
        Returns:
            True si se envía correctamente
        """
        try:
            # Verificar si las alertas de señales están habilitadas
            if not config.ALERT_TYPES.get('SIGNAL_ALERTS', True):
                return True
            
            # Formatear mensaje y enviar
            message = self.format_signal_alert(signal)
            success = self.send_message(message)
            
            if success:
                logger.info(f"📱 Alerta de señal enviada: {signal.symbol} - {signal.signal_type}")
            else:
                logger.error(f"❌ Error enviando alerta: {signal.symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error en send_signal_alert: {e}")
            return False
    
    def format_system_message(self, message_type: str, content: str) -> str:
        """
        Formatear mensajes del sistema
        
        Args:
            message_type: Tipo de mensaje (START, ERROR, INFO)
            content: Contenido del mensaje
            
        Returns:
            Mensaje formateado
        """
        try:
            spain_time = datetime.now(self.spain_tz)
            time_str = spain_time.strftime("%H:%M:%S")
            
            emoji_map = {
                "START": "🚀",
                "ERROR": "❌", 
                "WARNING": "⚠️",
                "INFO": "ℹ️",
                "SUCCESS": "✅"
            }
            
            emoji = emoji_map.get(message_type.upper(), "📢")
            
            message_lines = [
                f"{emoji} <b>SISTEMA DE TRADING</b>",
                f"⏰ <b>Hora:</b> {time_str} España",
                "",
                content
            ]
            
            return "\n".join(message_lines)
            
        except Exception as e:
            logger.error(f"Error formateando mensaje del sistema: {e}")
            return f"{content}"
    
    def send_system_alert(self, message_type: str, content: str) -> bool:
        """
        Enviar alerta del sistema
        
        Args:
            message_type: Tipo de mensaje (START, ERROR, INFO)
            content: Contenido del mensaje
            
        Returns:
            True si se envía correctamente
        """
        try:
            # Verificar si este tipo de alerta está habilitado
            alert_key = f"SYSTEM_{message_type.upper()}"
            if not config.ALERT_TYPES.get(alert_key, True):
                return True
            
            # Formatear y enviar
            message = self.format_system_message(message_type, content)
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"❌ Error enviando alerta del sistema: {e}")
            return False
    
    def send_startup_message(self) -> bool:
        """Enviar mensaje de inicio del sistema"""
        try:
            content = (
                f"🔍 <b>Sistema iniciado correctamente</b>\n"
                f"📊 Símbolos monitoreados: {len(config.SYMBOLS)}\n"
                f"⏰ Intervalo de escaneo: {config.SCAN_INTERVAL} min\n"
                f"🎯 Modo: {'Desarrollo' if config.DEVELOPMENT_MODE else 'Producción'}\n"
                f"💰 Riesgo por operación: {config.RISK_PER_TRADE}%"
            )
            
            return self.send_system_alert("START", content)
            
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de inicio: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """Enviar mensaje de test para verificar conectividad"""
        try:
            content = (
                f"🧪 <b>Test de conectividad</b>\n"
                f"✅ Bot configurado correctamente\n"
                f"📱 Chat ID: {self.chat_id}\n"
                f"⏰ Sistema funcionando"
            )
            
            return self.send_system_alert("INFO", content)
            
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de test: {e}")
            return False
    
    async def send_message_async(self, message: str, disable_preview: bool = True) -> bool:
        """
        Enviar mensaje de forma asíncrona
        
        Args:
            message: Mensaje a enviar
            disable_preview: Desactivar preview de links
            
        Returns:
            True si se envía correctamente, False si hay error
        """
        try:
            if not self.initialized:
                logger.error("❌ Bot no inicializado")
                return False
            
            # Escapar caracteres HTML problemáticos
            safe_message = html.escape(message, quote=False)
            # Restaurar tags HTML válidos
            safe_message = safe_message.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
            safe_message = safe_message.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=safe_message,
                parse_mode=self.parse_mode,
                disable_web_page_preview=disable_preview
                # Nota: timeout removido para compatibilidad
            )
            
            self.messages_sent += 1
            self.last_message_time = datetime.now()
            
            logger.info(f"📱 Mensaje enviado correctamente a Telegram")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ Error de Telegram: {e}")
            self.errors_count += 1
            return False
        except Exception as e:
            logger.error(f"❌ Error general enviando mensaje: {e}")
            self.errors_count += 1
            return False
    
    def get_bot_stats(self) -> Dict:
        """Obtener estadísticas del bot"""
        return {
            'initialized': self.initialized,
            'messages_sent': self.messages_sent,
            'errors_count': self.errors_count,
            'last_message': self.last_message_time.isoformat() if self.last_message_time else None,
            'success_rate': f"{((self.messages_sent / max(self.messages_sent + self.errors_count, 1)) * 100):.1f}%"
        }
    
    def debug_position_plan(self, signal: TradingSignal) -> str:
        """🔧 DEBUG: Función adicional para verificar el estado del position_plan"""
        debug_info = []
        
        debug_info.append(f"=== DEBUG POSITION PLAN - {signal.symbol} ===")
        
        if hasattr(signal, 'position_plan'):
            plan = signal.position_plan
            debug_info.append(f"✅ position_plan exists: {plan is not None}")
            
            if plan:
                debug_info.append(f"📊 Strategy: {getattr(plan, 'strategy_type', 'N/A')}")
                debug_info.append(f"💰 Entries: {len(getattr(plan, 'entries', []))}")
                debug_info.append(f"🎯 Exits: {len(getattr(plan, 'exits', []))}")
                
                # Verificar exits detalladamente
                if hasattr(plan, 'exits'):
                    for i, exit_level in enumerate(plan.exits):
                        debug_info.append(f"  Exit {i+1}:")
                        debug_info.append(f"    Price: {getattr(exit_level, 'price', 'N/A')}")
                        debug_info.append(f"    Has risk_reward: {hasattr(exit_level, 'risk_reward')}")
                        debug_info.append(f"    Has technical_basis: {hasattr(exit_level, 'technical_basis')}")
                        debug_info.append(f"    Has confidence: {hasattr(exit_level, 'confidence')}")
            else:
                debug_info.append("❌ position_plan is None")
        else:
            debug_info.append("❌ No position_plan attribute")
        
        debug_info.append("=" * 40)
        
        return "\n".join(debug_info)


# =============================================================================
# 🧪 FUNCIONES DE TESTING Y DEMO
# =============================================================================

def test_telegram_connection():
    """Test básico de conexión con Telegram"""
    print("🧪 TESTING CONEXIÓN TELEGRAM")
    print("=" * 50)
    
    try:
        bot = TelegramBot()
        
        if not bot.initialized:
            print("❌ Bot no se pudo inicializar")
            print("💡 Verifica TELEGRAM_TOKEN y CHAT_ID en .env")
            return False
        
        print("✅ Bot inicializado correctamente")
        print(f"📱 Chat ID: {bot.chat_id}")
        
        # Enviar mensaje de test
        print("\n📤 Enviando mensaje de test...")
        success = bot.send_test_message()
        
        if success:
            print("✅ Mensaje de test enviado correctamente")
            print("📱 Verifica tu Telegram para confirmar recepción")
        else:
            print("❌ Error enviando mensaje de test")
        
        return success
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

def test_signal_formatting():
    """Test del formato de mensajes de señales"""
    print("🧪 TESTING FORMATO DE SEÑALES")
    print("=" * 50)
    
    try:
        # Crear señal de ejemplo
        from scanner import TradingSignal
        from position_calculator import PositionCalculator, PositionPlan
        
        # Mock signal data
        mock_signal = TradingSignal(
            symbol="AAPL",
            timestamp=datetime.now(pytz.timezone('US/Eastern')),
            signal_type="LONG",
            signal_strength=85,
            confidence_level="HIGH",
            current_price=230.50,
            entry_quality="FULL_ENTRY",
            indicator_scores={
                'MACD': 20,
                'RSI': 18,
                'VWAP': 15,
                'ROC': 18,
                'BOLLINGER': 15,
                'VOLUME': 8
            },
            indicator_signals={
                'MACD': 'BULLISH_CROSS',
                'RSI': 'OVERSOLD',
                'VWAP': 'NEAR_VWAP',
                'ROC': 'STRONG_BULLISH',
                'BOLLINGER': 'LOWER_BAND',
                'VOLUME': 'HIGH'
            },
            market_context="UPTREND | HIGH_VOLUME"
        )
        
        # Crear bot y formatear mensaje
        bot = TelegramBot()
        formatted_message = bot.format_signal_alert(mock_signal)
        
        print("📝 MENSAJE FORMATEADO:")
        print("-" * 50)
        print(formatted_message)
        print("-" * 50)
        
        print("✅ Formato generado correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en test de formato: {e}")
        return False

def demo_telegram_bot():
    """Demostración completa del bot de Telegram"""
    print("🚀 DEMOSTRACIÓN COMPLETA BOT TELEGRAM")
    print("=" * 60)
    
    try:
        # 1. Inicializar bot
        print("1️⃣ Inicializando bot...")
        bot = TelegramBot()
        
        if not bot.initialized:
            print("❌ No se pudo inicializar el bot")
            print("💡 Configura TELEGRAM_TOKEN y CHAT_ID en .env")
            return False
        
        print("✅ Bot inicializado")
        
        # 2. Test de conectividad
        print("\n2️⃣ Enviando test de conectividad...")
        if bot.send_test_message():
            print("✅ Test enviado correctamente")
        else:
            print("❌ Error en test")
            return False
        
        # 3. Test de formato de señales
        print("\n3️⃣ Test de formato de señales...")
        if test_signal_formatting():
            print("✅ Formato de señales OK")
        else:
            print("❌ Error en formato")
        
        # 4. Estadísticas del bot
        print("\n4️⃣ Estadísticas del bot:")
        stats = bot.get_bot_stats()
        for key, value in stats.items():
            print(f"  📊 {key}: {value}")
        
        print("\n🎉 Demostración completada exitosamente!")
        print("📱 Verifica tu Telegram para ver los mensajes enviados")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en demostración: {e}")
        return False


# =============================================================================
# 🧪 MAIN - TESTING DIRECTO DEL MÓDULO
# =============================================================================

if __name__ == "__main__":
    print("📱 TELEGRAM BOT - SISTEMA DE TRADING V2.0 + V3.0 FIX")
    print("=" * 60)
    print()
    print("Opciones de testing:")
    print("1. Test básico de conexión")
    print("2. Test de formato de señales")
    print("3. Demostración completa")
    print("4. Enviar mensaje personalizado")
    print("5. Estadísticas del bot")
    print()
    
    try:
        choice = input("Selecciona una opción (1-5): ").strip()
        
        if choice == '1':
            print("\n" + "="*50)
            test_telegram_connection()
            
        elif choice == '2':
            print("\n" + "="*50)
            test_signal_formatting()
            
        elif choice == '3':
            print("\n" + "="*50)
            demo_telegram_bot()
            
        elif choice == '4':
            print("\n" + "="*50)
            print("📝 ENVÍO DE MENSAJE PERSONALIZADO")
            
            bot = TelegramBot()
            if bot.initialized:
                message = input("Escribe tu mensaje: ")
                if bot.send_message(message):
                    print("✅ Mensaje enviado correctamente")
                else:
                    print("❌ Error enviando mensaje")
            else:
                print("❌ Bot no inicializado")
                
        elif choice == '5':
            print("\n" + "="*50)
            print("📊 ESTADÍSTICAS DEL BOT")
            
            bot = TelegramBot()
            if bot.initialized:
                stats = bot.get_bot_stats()
                for key, value in stats.items():
                    print(f"  📊 {key}: {value}")
            else:
                print("❌ Bot no inicializado")
                
        else:
            print("❌ Opción no válida")
            
    except KeyboardInterrupt:
        print("\n\n👋 Test cancelado por el usuario")
    except Exception as e:
        print(f"\n❌ Error durante el test: {e}")
    
    print("\n🔚 Test finalizado")