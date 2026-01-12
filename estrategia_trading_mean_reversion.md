# Estrategia de Trading: Mean Reversion Selectiva

## Resumen Ejecutivo

Estrategia de swing trading basada en reversión a la media para operaciones de 4-48 horas. Diseñada para generar 10-20 señales mensuales de alta probabilidad, operando ETFs de alta liquidez en mercado estadounidense.

| Métrica Objetivo | Valor |
|------------------|-------|
| Win Rate esperado | 65-75% |
| Profit Factor | 1.6-2.2 |
| R:R medio | 1:2.5 |
| Trades/mes | 10-20 |
| Drawdown máximo | 12-18% |
| Tiempo en trade | 4-48 horas |

---

## 1. Universo de Productos

### Tier 1: Núcleo (Monitorear Siempre)

| Ticker | Producto | Descripción | Características |
|--------|----------|-------------|-----------------|
| SPY | SPDR S&P 500 | ETF del S&P 500 | Máxima liquidez, spread mínimo, ideal para la estrategia |
| QQQ | Invesco Nasdaq 100 | ETF del Nasdaq 100 | Más volátil que SPY, tech-heavy |
| IWM | iShares Russell 2000 | ETF de small caps | Descorrelacionado, buenos swings |

### Tier 2: Sectoriales (Añadir Variedad)

| Ticker | Producto | Sector | Características |
|--------|----------|--------|-----------------|
| XLF | Financial Select SPDR | Financiero | Sensible a tipos de interés |
| XLE | Energy Select SPDR | Energía | Muy volátil, correlacionado con petróleo |
| XLK | Technology Select SPDR | Tecnología | Similar a QQQ, más diversificado |
| SMH | VanEck Semiconductor | Semiconductores | El más volátil, requiere sizing conservador |

### Tier 3: Opcionales (Diversificación)

| Ticker | Producto | Tipo | Características |
|--------|----------|------|-----------------|
| GLD | SPDR Gold Shares | Oro | Refugio, descorrelacionado de equity |
| TLT | iShares 20+ Year Treasury | Bonos | Inverso a tipos de interés |
| EEM | iShares Emerging Markets | Emergentes | Mayor riesgo/reward |

### Productos Excluidos

- **Acciones individuales**: Riesgo de earnings, noticias, gaps
- **Criptomonedas**: Spreads altos, manipulación, 24/7
- **Forex**: Requiere conocimiento macro específico

---

## 2. Configuración Técnica

### Timeframe

**Velas de 1 hora (1H)** para señales de entrada y gestión.

**Gráfico diario (1D)** para filtro de tendencia macro (SMA 50).

### Indicadores

| Indicador | Configuración | Propósito |
|-----------|---------------|-----------|
| RSI | Periodo 7 | Detectar sobreventa/sobrecompra con reactividad |
| Bollinger Bands | Periodo 20, Desviación 2 | Identificar extremos de precio |
| ADX | Periodo 14 | Filtrar mercados tendenciales |
| VWAP | Estándar diario | Nivel institucional de referencia |
| ATR | Periodo 14 | Calcular stops, entries y targets |
| SMA | Periodo 50 (en diario) | Filtro de tendencia macro |
| Volumen | SMA 20 periodos | Confirmar interés institucional |

---

## 3. Reglas de Entrada

### 3.1 Entrada LONG (Compra)

**TODAS las condiciones deben cumplirse simultáneamente:**

| # | Condición | Explicación |
|---|-----------|-------------|
| 1 | RSI(7) < 35 | Activo sobrevendido |
| 2 | RSI(7) actual > RSI(7) vela anterior | Momentum girando al alza |
| 3 | Precio ≤ Banda inferior Bollinger(20,2) | Precio en extremo inferior |
| 4 | Precio < VWAP diario | Por debajo del precio "justo" institucional |
| 5 | ADX(14) < 22 | Mercado en rango, no tendencial |
| 6 | Precio > SMA(50) en gráfico DIARIO | Tendencia macro alcista o neutral |
| 7 | Vela de reversión alcista presente | Martillo, envolvente alcista, doji en soporte |
| 8 | Volumen > SMA(20) del volumen | Confirmación de interés real |

### 3.2 Entrada SHORT (Venta)

**TODAS las condiciones deben cumplirse simultáneamente:**

| # | Condición | Explicación |
|---|-----------|-------------|
| 1 | RSI(7) > 65 | Activo sobrecomprado |
| 2 | RSI(7) actual < RSI(7) vela anterior | Momentum girando a la baja |
| 3 | Precio ≥ Banda superior Bollinger(20,2) | Precio en extremo superior |
| 4 | Precio > VWAP diario | Por encima del precio "justo" institucional |
| 5 | ADX(14) < 22 | Mercado en rango, no tendencial |
| 6 | Precio < SMA(50) en gráfico DIARIO | Tendencia macro bajista o neutral |
| 7 | Vela de reversión bajista presente | Estrella fugaz, envolvente bajista |
| 8 | Volumen > SMA(20) del volumen | Confirmación de interés real |

### 3.3 Patrones de Velas Válidos

**Para LONG (alcistas):**
- Martillo (hammer)
- Envolvente alcista (bullish engulfing)
- Doji en soporte
- Pinza de fondo (tweezer bottom)

**Para SHORT (bajistas):**
- Estrella fugaz (shooting star)
- Envolvente bajista (bearish engulfing)
- Doji en resistencia
- Pinza de techo (tweezer top)

---

## 4. Entrada Escalonada

### 4.1 Estructura de Entrada LONG

| Nivel | % Posición | Precio | Condición |
|-------|------------|--------|-----------|
| E1 | 50% | Cierre de vela de señal | Inmediata al mercado |
| E2 | 30% | E1 - 0.5 × ATR(14) | Orden limitada |
| E3 | 20% | E1 - 1.0 × ATR(14) | Solo si ADX no ha subido >3 puntos desde señal |

### 4.2 Estructura de Entrada SHORT

| Nivel | % Posición | Precio | Condición |
|-------|------------|--------|-----------|
| E1 | 50% | Cierre de vela de señal | Inmediata al mercado |
| E2 | 30% | E1 + 0.5 × ATR(14) | Orden limitada |
| E3 | 20% | E1 + 1.0 × ATR(14) | Solo si ADX no ha subido >3 puntos desde señal |

### 4.3 Regla de Cancelación de E3

**Cancelar E3 si:**
- ADX sube más de 3 puntos desde el momento de E1
- Han pasado más de 12 horas sin ejecutarse E2
- El precio ha alcanzado TP1 antes de ejecutar E2/E3

**Razón:** Si ADX sube, está naciendo una tendencia (probablemente en tu contra). No promediar contra tendencia naciente.

---

## 5. Stop Loss

### 5.1 Cálculo del Stop Loss

| Dirección | Fórmula | Ejemplo (ATR=$5, Entrada=$100) |
|-----------|---------|-------------------------------|
| LONG | Precio entrada promedio - 2 × ATR(14) | $100 - $10 = $90 |
| SHORT | Precio entrada promedio + 2 × ATR(14) | $100 + $10 = $110 |

### 5.2 Características del Stop

- **Tipo:** Fijo (no trailing inicialmente)
- **Ubicación:** Por debajo/encima del soporte/resistencia más cercano
- **Múltiplo ATR:** 2x para dar espacio al ruido normal
- **Ajuste post-TP1:** Mover a breakeven después de alcanzar TP1

### 5.3 Stop Loss para Entradas Escalonadas

El stop se calcula sobre el **precio promedio ponderado** de las entradas ejecutadas:

```
Precio Promedio = (E1 × 0.50 + E2 × 0.30 + E3 × 0.20) / (suma de % ejecutados)
```

Si solo se ejecutan E1 y E2:
```
Precio Promedio = (E1 × 0.50 + E2 × 0.30) / 0.80
```

---

## 6. Take Profit

### 6.1 Estructura de Salida LONG

| Nivel | % Posición | Precio | Acción Adicional |
|-------|------------|--------|------------------|
| TP1 | 50% | Entrada promedio + 1.5 × ATR | Mover SL a breakeven |
| TP2 | 30% | Entrada promedio + 2.5 × ATR | Activar trailing stop de 1 × ATR |
| TP3 | 20% | Entrada promedio + 4.0 × ATR | O cerrar por trailing stop |

### 6.2 Estructura de Salida SHORT

| Nivel | % Posición | Precio | Acción Adicional |
|-------|------------|--------|------------------|
| TP1 | 50% | Entrada promedio - 1.5 × ATR | Mover SL a breakeven |
| TP2 | 30% | Entrada promedio - 2.5 × ATR | Activar trailing stop de 1 × ATR |
| TP3 | 20% | Entrada promedio - 4.0 × ATR | O cerrar por trailing stop |

### 6.3 Trailing Stop (después de TP2)

- **Activación:** Después de alcanzar TP2
- **Distancia:** 1 × ATR(14) del precio máximo/mínimo alcanzado
- **Actualización:** Cada cierre de vela 1H

### 6.4 Salida Anticipada por Señal Técnica

Cerrar posición completa si:
- **LONG:** RSI(7) > 75 (sobrecompra extrema)
- **SHORT:** RSI(7) < 25 (sobreventa extrema)
- Aparece patrón de vela de reversión contra la posición

---

## 7. Time Stop

### 7.1 Regla Principal

**Si después de 48 horas no se ha alcanzado TP1 ni SL → Cerrar posición al mercado.**

### 7.2 Razón

La reversión a la media funciona rápido (12-36 horas típicamente) o no funciona. Un trade que lleva 48 horas sin moverse indica que la tesis está rota.

### 7.3 Excepciones

No aplicar time stop si:
- El trade está en profit (aunque no haya tocado TP1)
- Faltan menos de 2 horas para cierre de mercado un viernes (esperar al lunes)

---

## 8. Gestión de Riesgo

### 8.1 Sizing por Trade

| Parámetro | Valor |
|-----------|-------|
| Riesgo máximo por trade | 1.5% del capital |
| Máximo trades simultáneos | 4 |
| Riesgo total máximo | 6% del capital |

### 8.2 Fórmula de Position Sizing

```
Tamaño Posición = (Capital × 0.015) / (2 × ATR × Precio)
```

**Ejemplo:**
- Capital: €10,000
- ATR de SPY: $5
- Precio SPY: $580

```
Tamaño = (10,000 × 0.015) / (2 × 5) = 150 / 10 = 15 participaciones
```

### 8.3 Ajuste por Volatilidad

| Condición | Ajuste de Sizing |
|-----------|------------------|
| ATR actual < ATR promedio 20 días | Sizing normal (100%) |
| ATR actual > 1.5 × ATR promedio | Reducir sizing al 75% |
| ATR actual > 2 × ATR promedio | Reducir sizing al 50% |

### 8.4 Correlación Entre Trades

Evitar tener simultáneamente:
- Más de 2 trades en ETFs del mismo sector
- LONG en SPY y LONG en QQQ (alta correlación)
- Más de 3 trades en la misma dirección (todos LONG o todos SHORT)

---

## 9. Horarios de Operación

### 9.1 Horarios Óptimos (Hora España/CET)

| Ventana | Horario | Calidad | Razón |
|---------|---------|---------|-------|
| Apertura US | 15:30 - 17:30 | ⭐⭐⭐ Óptima | Mayor volumen y volatilidad |
| Mediodía US | 17:30 - 20:00 | ⚠️ Evitar | Bajo volumen, movimientos erráticos |
| Cierre US | 20:00 - 22:00 | ⭐⭐⭐ Óptima | Institucionales ajustan posiciones |

### 9.2 Reglas de Horario

- **Solo tomar señales** durante ventanas óptimas (15:30-17:30 y 20:00-22:00)
- **Ignorar señales** que aparezcan entre 17:30-20:00
- **No abrir trades** en los últimos 30 minutos del viernes
- **Revisar posiciones** antes de apertura del lunes para gaps de fin de semana

### 9.3 Días a Evitar

- Días de FOMC (anuncios de la Fed)
- Días de NFP (Non-Farm Payrolls, primer viernes del mes)
- Vísperas de festivos US (volumen reducido)

---

## 10. Formato de Alertas Telegram

### 10.1 Alerta de Entrada LONG

```
🟢 LONG - [TICKER] (1H)

📊 SETUP: Mean Reversion Alcista
━━━━━━━━━━━━━━━━━━━━━
- RSI(7): [valor] < 35 ✓
- RSI girando: [actual] > [anterior] ✓
- Precio $[precio] ≤ BB inferior ✓
- Precio < VWAP ($[vwap]) ✓
- ADX: [valor] < 22 ✓
- SMA(50)D: $[sma] (precio encima) ✓
- Vela: [tipo de vela] ✓
- Volumen: [ratio]x promedio ✓

📥 ENTRADA ESCALONADA:
━━━━━━━━━━━━━━━━━━━━━
• 50% ([X] uds) a $[E1] [MERCADO]
• 30% ([X] uds) a $[E2] [LIMITADA]
• 20% ([X] uds) a $[E3] [LIMITADA*]
  *Cancelar si ADX sube >3 pts

🛑 STOP LOSS: $[SL] (todos)

✅ TAKE PROFIT:
━━━━━━━━━━━━━━━━━━━━━
• TP1: 50% a $[TP1] → SL a breakeven
• TP2: 30% a $[TP2] → trailing 1×ATR
• TP3: 20% a $[TP3] o trailing

⏱️ Time stop: 48 horas
⏰ Señal válida: [hora inicio] - [hora fin] CET

💰 Riesgo: €[X] (1.5%)
📊 R:R esperado: 1:2.5
📈 Trades abiertos: [X]/4
⚠️ Riesgo total actual: [X]%
```

### 10.2 Alerta de Entrada SHORT

```
🔴 SHORT - [TICKER] (1H)

📊 SETUP: Mean Reversion Bajista
━━━━━━━━━━━━━━━━━━━━━
- RSI(7): [valor] > 65 ✓
- RSI girando: [actual] < [anterior] ✓
- Precio $[precio] ≥ BB superior ✓
- Precio > VWAP ($[vwap]) ✓
- ADX: [valor] < 22 ✓
- SMA(50)D: $[sma] (precio debajo) ✓
- Vela: [tipo de vela] ✓
- Volumen: [ratio]x promedio ✓

📥 ENTRADA ESCALONADA:
━━━━━━━━━━━━━━━━━━━━━
• 50% ([X] uds) a $[E1] [MERCADO]
• 30% ([X] uds) a $[E2] [LIMITADA]
• 20% ([X] uds) a $[E3] [LIMITADA*]
  *Cancelar si ADX sube >3 pts

🛑 STOP LOSS: $[SL] (todos)

✅ TAKE PROFIT:
━━━━━━━━━━━━━━━━━━━━━
• TP1: 50% a $[TP1] → SL a breakeven
• TP2: 30% a $[TP2] → trailing 1×ATR
• TP3: 20% a $[TP3] o trailing

⏱️ Time stop: 48 horas
⏰ Señal válida: [hora inicio] - [hora fin] CET

💰 Riesgo: €[X] (1.5%)
📊 R:R esperado: 1:2.5
📈 Trades abiertos: [X]/4
⚠️ Riesgo total actual: [X]%
```

### 10.3 Alerta de Gestión

```
⚡ ACTUALIZACIÓN - [TICKER]

[Tipo de actualización]:
• TP1 alcanzado → SL movido a breakeven
• E2 ejecutada → Nuevo precio promedio: $[X]
• E3 cancelada → ADX subió a [X]
• Time stop → Cerrar posición
• Trailing activado → Nuevo SL: $[X]

📊 Estado actual:
• P&L actual: [+/-]$[X] ([%])
• Posición restante: [X]%
• Nuevo SL: $[X]
```

### 10.4 Alerta de Cierre

```
✅ TRADE CERRADO - [TICKER]

📊 Resumen:
━━━━━━━━━━━━━━━━━━━━━
• Dirección: [LONG/SHORT]
• Entrada promedio: $[X]
• Salida promedio: $[X]
• Duración: [X] horas

💰 Resultado:
• P&L: [+/-]$[X]
• Retorno: [+/-][X]%
• R múltiple: [X]R

📈 Estadísticas actualizadas:
• Win rate mes: [X]%
• Profit factor mes: [X]
• Trades este mes: [X]
```

---

## 11. Checklist Pre-Trade

Antes de ejecutar cualquier señal, verificar:

### 11.1 Condiciones de Mercado

- [ ] No hay evento FOMC/NFP hoy o mañana
- [ ] VIX no está en extremos (>30 o <12)
- [ ] No es víspera de festivo US
- [ ] Estamos en horario óptimo

### 11.2 Condiciones de la Señal

- [ ] Todas las condiciones técnicas se cumplen
- [ ] La vela de señal está cerrada (no entrar en vela abierta)
- [ ] El volumen confirma la señal
- [ ] No hay earnings del ETF o sus principales componentes

### 11.3 Gestión de Riesgo

- [ ] No excedo 4 trades simultáneos
- [ ] Riesgo total no excede 6%
- [ ] No tengo correlación excesiva con trades abiertos
- [ ] El sizing está ajustado por volatilidad si corresponde

---

## 12. Diario de Trading

### 12.1 Campos a Registrar por Trade

| Campo | Descripción |
|-------|-------------|
| Fecha/hora entrada | Timestamp de E1 |
| Ticker | Símbolo del ETF |
| Dirección | LONG o SHORT |
| Setup | Condiciones que se cumplieron |
| Entradas ejecutadas | E1, E2, E3 con precios y cantidades |
| Precio promedio | Calculado ponderado |
| Stop loss | Precio inicial |
| TPs alcanzados | Cuáles y a qué precio |
| Fecha/hora salida | Timestamp de cierre |
| Motivo salida | TP, SL, Time stop, Señal técnica |
| P&L | En $ y % |
| R múltiple | Ganancia/pérdida en unidades de riesgo |
| Notas | Observaciones, errores, mejoras |

### 12.2 Métricas Semanales a Revisar

- Win rate
- Profit factor
- Promedio de R ganador vs R perdedor
- Tiempo promedio en trade ganador vs perdedor
- Drawdown máximo de la semana
- Trades cancelados por E3/ADX

---

## 13. Parámetros para Backtesting

### 13.1 Datos Necesarios

| Dato | Fuente | Periodo |
|------|--------|---------|
| OHLCV 1H | yfinance | Últimos 730 días |
| OHLCV 1D | yfinance | Últimos 5 años |

### 13.2 Costes a Incluir

| Concepto | Valor Estimado |
|----------|----------------|
| Comisión por trade | $1 fijo o 0.1% |
| Spread | 0.02% para ETFs líquidos |
| Slippage | 0.03% |

### 13.3 Métricas a Calcular

- Win Rate
- Profit Factor
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Calmar Ratio
- Promedio de trades por mes
- Distribución de R múltiples

### 13.4 Validación

- Walk-forward analysis con ventanas de 6 meses
- Out-of-sample testing con 30% de datos
- Monte Carlo simulation para distribución de resultados

---

## 14. Limitaciones Conocidas

### 14.1 Limitaciones de los Datos

- yfinance: Máximo ~730 días de datos intradía
- Gaps de fin de semana no modelados
- Datos de volumen pueden ser inexactos en tiempo real

### 14.2 Limitaciones de la Estrategia

- No funciona bien en mercados fuertemente tendenciales
- Requiere disciplina estricta en horarios
- Los shorts pueden tener costes adicionales de préstamo
- Gaps pueden saltar el stop loss

### 14.3 Riesgos No Cubiertos

- Flash crashes
- Halts de trading
- Eventos de cisne negro
- Cambios regulatorios

---

## 15. Historial de Versiones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | [Fecha] | Versión inicial |

---

## Anexo A: Tickers para yfinance

```python
TICKERS = {
    'tier1': ['SPY', 'QQQ', 'IWM'],
    'tier2': ['XLF', 'XLE', 'XLK', 'SMH'],
    'tier3': ['GLD', 'TLT', 'EEM']
}
```

## Anexo B: Fórmulas Rápidas

```
# Stop Loss
SL_LONG = Entrada_Promedio - (2 * ATR)
SL_SHORT = Entrada_Promedio + (2 * ATR)

# Take Profits
TP1 = Entrada ± (1.5 * ATR)
TP2 = Entrada ± (2.5 * ATR)
TP3 = Entrada ± (4.0 * ATR)

# Position Sizing
Tamaño = (Capital * 0.015) / (2 * ATR)

# Precio Promedio Ponderado
Promedio = (E1*0.50 + E2*0.30 + E3*0.20) / %_ejecutado
```
