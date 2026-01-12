# 📈 Sistema de Trading Automatizado v2.0

## 🎯 Descripción del Proyecto

Sistema automatizado en Python que detecta señales de trading de alta calidad basadas en múltiples indicadores técnicos y envía alertas inteligentes por Telegram para operaciones de daytrading/scalping en acciones.

## 🔧 Características Principales

### 📊 Indicadores Técnicos Implementados
- **MACD (12,26,9)** - Detección de cambios de tendencia
- **RSI (14)** - Zonas de sobreventa/sobrecompra  
- **VWAP** - Referencia de valor institucional
- **ROC/Momentum (10)** - Confirmación de fuerza direccional
- **Bollinger Bands (20,2)** - Zonas de valor extremo
- **Oscilador de Volumen (5,20)** - Confirmación institucional
- **ATR (14)** - Cálculo de stops dinámicos

### 🎯 Sistema de Señales
- **Timeframe**: 15 minutos
- **Puntuación dinámica**: 0-100 puntos por señal
- **Filtros de calidad**: Múltiples confirmaciones requeridas
- **Gestión de riesgo**: Entradas y salidas escalonadas

### 📱 Alertas Inteligentes
- **Notificaciones por Telegram** con niveles de entrada y salida
- **Cálculo automático** de posiciones escalonadas
- **Información completa**: Precios, stops, take profits y tamaños

## 🏗️ Estructura del Proyecto

```
trading_system/
│
├── main.py                  # 🚀 Archivo principal - Coordinador del sistema
├── config.py               # ⚙️ Configuración - Parámetros y ajustes
├── indicators.py           # 📊 Indicadores - Cálculo de señales técnicas
├── scanner.py              # 🔍 Scanner - Evaluación y puntuación de señales
├── telegram_bot.py         # 📱 Telegram - Envío de alertas formateadas
├── position_calculator.py  # 💰 Posiciones - Cálculo de niveles y tamaños
├── requirements.txt        # 📦 Dependencias del proyecto
├── .env                    # 🔐 Variables de entorno (tokens, IDs)
├── .gitignore             # 🚫 Archivos a ignorar en git
└── README.md              # 📋 Documentación del proyecto
```

## 🎲 Estrategia de Trading

### 📈 Condiciones para Señal LARGO
1. **MACD**: Cruce hacia arriba (histogram > 0)
2. **RSI**: < 40 (zona de sobreventa)
3. **Precio vs VWAP**: Cerca del VWAP (±0.5%)
4. **ROC**: > +1.5% (momentum alcista)
5. **Bollinger Bands**: Precio en zona inferior
6. **Volumen**: Oscilador > +50% (preferible)

### 📉 Condiciones para Señal CORTO
1. **MACD**: Cruce hacia abajo (histogram < 0)
2. **RSI**: > 60 (zona de sobrecompra)
3. **Precio vs VWAP**: Alejado del VWAP (>+1.0%)
4. **ROC**: < -1.5% (momentum bajista)
5. **Bollinger Bands**: Precio en zona superior
6. **Volumen**: Oscilador > +50% (preferible)

### 🎯 Sistema de Puntuación
- **🟢 Entrada Completa (≥100 pts)**: 5/5 señales + volumen fuerte
- **🟡 Entrada Parcial (70-99 pts)**: 4/5 señales + momentum building
- **🔴 No Operar (<70 pts)**: Insuficientes confirmaciones

## 💰 Gestión de Posiciones

### 📊 Entradas Escalonadas
- **Entrada 1 (40%)**: Señal completa confirmada
- **Entrada 2 (30%)**: Precio -0.5 ATR (largos) / +0.5 ATR (cortos)
- **Entrada 3 (30%)**: Precio -1.0 ATR (largos) / +1.0 ATR (cortos)

### 🎯 Salidas Escalonadas
- **TP1 (25%)**: 1.5R - Asegurar ganancia inicial
- **TP2 (25%)**: 2.5R - Capitalizar momentum
- **TP3 (25%)**: 4.0R - Aprovechar movimientos extendidos
- **TP4 (25%)**: Trailing stop desde 4R

### 🛡️ Gestión de Riesgo
- **Riesgo máximo**: 1.5% del capital por operación
- **Stop loss**: 1 ATR desde precio de entrada
- **R:R objetivo**: Mínimo 1:4, promedio 1:5+

## ⏰ Filtros Temporales

### ✅ Sesiones de Alta Probabilidad
- **Mañana**: 09:45 - 11:30 AM
- **Tarde**: 14:00 - 15:30 PM

### ❌ Horarios a Evitar
- **Apertura volátil**: 09:30 - 09:45 AM
- **Almuerzo**: 11:30 - 14:00 PM
- **Cierre**: 15:30 - 16:00 PM

## 🚀 Instalación y Configuración

### 1. Clonar el Repositorio
```bash
git clone [URL_DEL_REPOSITORIO]
cd trading_system
```

### 2. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno
Crear archivo `.env` con:
```env
TELEGRAM_TOKEN=tu_token_de_telegram
CHAT_ID=tu_chat_id
```

### 4. Configurar Parámetros
Editar `config.py` con tus preferencias:
- Símbolos a escanear
- Parámetros de indicadores
- Configuración de riesgo

### 5. Ejecutar el Sistema
```bash
python main.py
```

## 📱 Configuración de Telegram

### Crear Bot de Telegram
1. Hablar con [@BotFather](https://t.me/BotFather)
2. Usar comando `/newbot`
3. Seguir instrucciones y copiar el token
4. Obtener tu Chat ID hablando con [@userinfobot](https://t.me/userinfobot)

### Formato de Alertas
```
🟢 SEÑAL DETECTADA - AAPL
📊 Tipo: LONG | Confianza: 85/100

💰 ENTRADAS ESCALONADAS:
• Entrada 1 (40%): $150.25
• Entrada 2 (30%): $149.75  
• Entrada 3 (30%): $149.25

🎯 SALIDAS ESCALONADAS:
• TP1 (25%): $152.50
• TP2 (25%): $154.00
• TP3 (25%): $156.75
• TP4 (25%): Trailing desde $158.25

🛡️ Stop Loss: $148.75

📊 INDICADORES:
MACD: ✅ | RSI: 35 ✅ | VWAP: ✅ | ROC: +2.1% ✅ | BB: ✅ | VOL: +65% ✅
```

## 🔧 Tecnologías Utilizadas

- **Python 3.10+**
- **yfinance** - Datos de mercado en tiempo real
- **pandas & numpy** - Procesamiento de datos
- **ta-lib** - Indicadores técnicos
- **python-telegram-bot** - Alertas por Telegram
- **schedule** - Programación de tareas

## 📊 Símbolos Monitoreados

Por defecto, el sistema monitorea:
- **SPY** - S&P 500 ETF
- **QQQ** - Nasdaq 100 ETF
- **AAPL** - Apple Inc.
- **NVDA** - NVIDIA Corporation
- **AMD** - Advanced Micro Devices
- **TSLA** - Tesla Inc.

## 🎯 Objetivos de Performance

- **Señales por día**: 3-5 de alta calidad
- **Tasa de éxito objetivo**: 65-75%
- **R:R promedio**: 1:4.5
- **Drawdown máximo**: 8-12%
- **ROI anual objetivo**: 25-35%

## 📝 Logs y Monitoreo

El sistema genera logs detallados en:
- **Consola**: Output en tiempo real
- **Archivo**: `trading_system.log`
- **Telegram**: Alertas de señales detectadas

## ⚠️ Disclaimer

Este sistema es solo para fines educativos e informativos. No constituye asesoramiento financiero. Operar en los mercados financieros conlleva riesgo de pérdida. Siempre realiza tu propia investigación y considera consultar con un asesor financiero antes de tomar decisiones de inversión.

## 📞 Soporte

Para reportar problemas o sugerir mejoras, crear un issue en el repositorio o contactar al desarrollador.

---

**🚀 ¡Listo para automatizar tu trading!** 

*Sistema desarrollado para traders que buscan señales de alta calidad con gestión de riesgo profesional.*