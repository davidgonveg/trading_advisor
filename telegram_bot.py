#!/usr/bin/env python3
"""
📱 SISTEMA DE ALERTAS POR TELEGRAM - TRADING AUTOMATIZADO V2.0
============================================================

Este módulo maneja todas las comunicaciones por Telegram:
- Envío de alertas de señales formateadas
- Notificaciones de sistema (inicio, errores)
- Mensajes de test y confirmación
- Manejo de errores de conectividad

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
        Formatear señal de trading como mensaje HTML para Telegram
        
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
            
            # === PLAN DE POSICIÓN ===
            if signal.position_plan:
                plan = signal.position_plan
                
                # Entradas escalonadas
                message_lines.append("💰 <b>ENTRADAS ESCALONADAS:</b>")
                for i, entry in enumerate(plan.entries, 1):
                    message_lines.append(f"• <b>Entrada {i}</b> ({entry.percentage}%): ${entry.price:.2f}")
                message_lines.append("")
                
                # Take Profits
                message_lines.append("🎯 <b>TAKE PROFITS:</b>")
                for i, exit_level in enumerate(plan.exits, 1):
                    # Calcular R:R para cada TP
                    entry_price = plan.entries[0].price
                    stop_price = plan.stop_loss.price
                    risk = abs(entry_price - stop_price)
                    reward = abs(exit_level.price - entry_price)
                    rr_ratio = reward / risk if risk > 0 else 0
                    
                    message_lines.append(f"• <b>TP{i}</b> ({exit_level.percentage}%): ${exit_level.price:.2f} - {rr_ratio:.1f}R")
                message_lines.append("")
                
                # Stop Loss
                message_lines.append(f"🛡️ <b>Stop Loss:</b> ${plan.stop_loss.price:.2f}")
                message_lines.append("")
                
                # Métricas de la operación
                message_lines.append("📈 <b>MÉTRICAS:</b>")
                message_lines.append(f"• <b>R:R Máximo:</b> 1:{plan.max_risk_reward:.1f}")
                message_lines.append(f"• <b>Estrategia:</b> {plan.strategy_type}")
                message_lines.append(f"• <b>Tiempo estimado:</b> {plan.expected_hold_time}")
                message_lines.append(f"• <b>Riesgo:</b> {plan.total_risk_percent:.1f}% del capital")
                message_lines.append("")
            
            # === ANÁLISIS TÉCNICO ===
            message_lines.append("📊 <b>ANÁLISIS TÉCNICO:</b>")
            
            # Crear línea compacta con indicadores
            indicators_status = []
            for indicator, score in signal.indicator_scores.items():
                indicator_signal = signal.indicator_signals.get(indicator, "")
                
                # Emoji según puntuación
                if score >= 15:
                    emoji = "✅"
                elif score >= 10:
                    emoji = "🟡" 
                elif score > 0:
                    emoji = "🔶"
                else:
                    emoji = "❌"
                
                # Formato compacto
                if indicator == "MACD":
                    indicators_status.append(f"MACD: {emoji}")
                elif indicator == "RSI":
                    # Obtener valor RSI real si está disponible
                    rsi_value = self._extract_rsi_value(indicator_signal)
                    indicators_status.append(f"RSI: {rsi_value} {emoji}")
                elif indicator == "VWAP":
                    indicators_status.append(f"VWAP: {emoji}")
                elif indicator == "ROC":
                    # Obtener valor ROC si está disponible  
                    roc_text = self._extract_roc_text(indicator_signal)
                    indicators_status.append(f"ROC: {roc_text} {emoji}")
                elif indicator == "BOLLINGER":
                    indicators_status.append(f"BB: {emoji}")
                elif indicator == "VOLUME":
                    indicators_status.append(f"VOL: {emoji}")
            
            # Dividir en líneas para mejor legibilidad
            message_lines.append(" | ".join(indicators_status[:3]))
            if len(indicators_status) > 3:
                message_lines.append(" | ".join(indicators_status[3:]))
            message_lines.append("")
            
            # === CONTEXTO DE MERCADO ===
            if signal.market_context:
                message_lines.append(f"🌐 <b>Contexto:</b> {signal.market_context}")
                message_lines.append("")
            
            # === FOOTER ===
            message_lines.append(f"{confidence_emoji} <i>Trading automatizado - Señal #{signal.signal_strength}</i>")
            
            return "\n".join(message_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formateando mensaje de señal: {e}")
            return f"❌ Error formateando señal para {signal.symbol}"
    
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
            self.errors_count += 1
            logger.error(f"❌ Error de Telegram: {e}")
            return False
        except Exception as e:
            self.errors_count += 1
            logger.error(f"❌ Error enviando mensaje: {e}")
            return False
    
    def send_message(self, message: str, disable_preview: bool = True) -> bool:
        """
        Enviar mensaje de forma síncrona (wrapper para async)
        
        Args:
            message: Mensaje a enviar
            disable_preview: Desactivar preview de links
            
        Returns:
            True si se envía correctamente, False si hay error
        """
        try:
            # Crear nuevo loop si no existe
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Ejecutar envío asíncrono
            return loop.run_until_complete(
                self.send_message_async(message, disable_preview)
            )
            
        except Exception as e:
            logger.error(f"❌ Error en envío síncrono: {e}")
            return False
    
    def send_signal_alert(self, signal: TradingSignal) -> bool:
        """
        Enviar alerta de señal de trading
        
        Args:
            signal: TradingSignal a enviar
            
        Returns:
            True si se envía correctamente
        """
        try:
            # Verificar si las alertas de señales están habilitadas
            if not config.ALERT_TYPES.get('SIGNAL_DETECTED', True):
                logger.info(f"📵 Alertas de señales deshabilitadas - No enviando {signal.symbol}")
                return True
            
            # Formatear mensaje
            message = self.format_signal_alert(signal)
            
            # Enviar mensaje
            success = self.send_message(message)
            
            if success:
                logger.info(f"✅ Alerta de señal enviada: {signal.symbol} {signal.signal_type}")
            else:
                logger.error(f"❌ Error enviando alerta: {signal.symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error en send_signal_alert: {e}")
            return False
    
    def send_system_alert(self, message_type: str, content: str) -> bool:
        """
        Enviar alerta del sistema
        
        Args:
            message_type: Tipo de mensaje (START, ERROR, WARNING, INFO)
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
    
    def get_bot_stats(self) -> Dict:
        """Obtener estadísticas del bot"""
        return {
            'initialized': self.initialized,
            'messages_sent': self.messages_sent,
            'errors_count': self.errors_count,
            'last_message': self.last_message_time.isoformat() if self.last_message_time else None,
            'success_rate': f"{((self.messages_sent / max(self.messages_sent + self.errors_count, 1)) * 100):.1f}%"
        }


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
        
        # 2. Test de formato
        print("\n2️⃣ Testeando formato de mensajes...")
        format_success = test_signal_formatting()
        
        # 3. Decidir si enviar mensaje real
        print(f"\n3️⃣ ¿Enviar mensaje de test a Telegram? (y/n): ", end="")
        response = input().strip().lower()
        
        if response == 'y':
            print("📤 Enviando mensaje de test...")
            send_success = bot.send_test_message()
            
            if send_success:
                print("✅ Mensaje enviado - verifica tu Telegram")
            else:
                print("❌ Error enviando mensaje")
        else:
            print("⏭️ Test de envío omitido")
            send_success = True
        
        # 4. Estadísticas
        print("\n4️⃣ Estadísticas del bot:")
        stats = bot.get_bot_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print("\n🎯 DEMOSTRACIÓN COMPLETADA")
        return format_success and send_success
        
    except Exception as e:
        print(f"❌ Error en demostración: {e}")
        return False

if __name__ == "__main__":
    # Menú interactivo para testing
    print("📱 SISTEMA TELEGRAM BOT V2.0 - MODO TESTING")
    print("=" * 60)
    print("Selecciona un test:")
    print("1. Test de conexión básica")
    print("2. Test de formato de señales")
    print("3. Demostración completa")
    print("4. Ejecutar todos los tests")
    print("")
    
    try:
        choice = input("Elige una opción (1-4): ").strip()
        print("")
        
        if choice == "1":
            test_telegram_connection()
        elif choice == "2":
            test_signal_formatting()
        elif choice == "3":
            demo_telegram_bot()
        elif choice == "4":
            # Ejecutar todos los tests
            print("🧪 EJECUTANDO TODOS LOS TESTS")
            print("=" * 60)
            
            tests = [
                ("Formato de señales", test_signal_formatting),
                ("Conexión Telegram", test_telegram_connection),
                ("Demostración completa", demo_telegram_bot)
            ]
            
            results = []
            for test_name, test_func in tests:
                print(f"\n🔬 {test_name}...")
                try:
                    result = test_func()
                    results.append((test_name, "✅" if result else "❌"))
                    print(f"Resultado: {'✅ PASÓ' if result else '❌ FALLÓ'}")
                except Exception as e:
                    results.append((test_name, "❌"))
                    print(f"Error: {e}")
                
                print("-" * 40)
            
            print("\n📊 RESUMEN DE TESTS:")
            for test_name, status in results:
                print(f"{status} {test_name}")
        
        else:
            print("❌ Opción no válida")
            
    except KeyboardInterrupt:
        print("\n👋 Tests interrumpidos por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando tests: {e}")
    
    print("\n🏁 Tests completados!")
    print("El módulo telegram_bot.py está listo para integración con main.py")