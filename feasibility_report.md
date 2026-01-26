# Análisis de Viabilidad: Implementación de Estrategias Day Trading

## 1. VWAP Bounce

### 1.1 Compatibilidad con Código Existente
**✅ Reutilizable (0% modificación):**
- `data_loader.py` (usando `DataManager`): Descarga y gestión de OHLCV 1H.
- `risk_manager.py`: Gestión de tamaño de posición y riesgo.
- `backtester.py`: Motor de simulación soporta la clase base `Strategy`.

**⚠️ Adaptación menor (<10% modificación):**
- `analysis/indicators.py`: El cálculo de VWAP ya existe (`session vwap`), pero se debe verificar que se resetee correctamente cada día en el backtest continuo.
- `strategy/base.py`: Nueva clase `VWAPBounceStrategy` heredando de `Strategy`.

**🆕 Nuevo desde cero:**
- `pattern_detector.py`: Lógica para calcular `body`, `upper_wick`, `lower_wick` y detectar el patrón de rechazo (mecha > 2x cuerpo). (~50 líneas).

### 1.2 Datos Necesarios vs Disponibles
**Datos disponibles:**
- SPY, QQQ, IWM: Datos 1H disponibles vía yfinance (sin límite práctico para backtest de varios años).
- Indicadores: VWAP calculable "on-the-fly" con los datos OHLCV.

**Datos requeridos no disponibles:**
- Ninguno. La estrategia es completamente viable con los datos actuales.

### 1.3 Complejidad de Implementación
**Puntuación: 4/10 (Moderada)**
1.  **Cálculo VWAP**: 1/10 (Ya implementado).
2.  **Detección de mechas**: 3/10 (Matemática simple sobre OHLC).
3.  **Lógica de entrada**: 4/10 (Sincronizar cruce de precio y cierre de vela).
4.  **Gestión TP/SL**: 5/10 (Requiere lógica de partial take profit, que puede necesitar soporte en el `Broker` si no existe).

### 1.4 Estimación de Tiempo de Desarrollo
- **Implementación base**: 4 horas.
- **Testing y Debugging**: 3 horas.
- **Backtesting y Validación**: 2 horas.
- **Total: ~9-10 horas.**

### 1.5 Cambios Arquitectónicos
- **Estructura de Clases**: Nueva clase `VWAPBounceStrategy`.
- **Riesgo**: Sin cambios.

### 1.6 Dependencias
- Ninguna adicional.

### 1.7 Riesgos y Bloqueadores
- **Riesgo Bajo**: Validación correcta del reset diario del VWAP en datos continuos sin pre-procesamiento por sesiones explícitas.

---

## 2. EMA Trend Following

### 2.1 Compatibilidad con Código Existente
**✅ Reutilizable:**
- `DataManager`: Ya tiene métodos para descargar datos diarios (`get_latest_daily_data`).
- `BarData`: La estructura de datos del backtest (`schema.py`) ya incluye campos para `daily_bars` y `daily_indicators`.

**⚠️ Adaptación menor:**
- `backtesting/engine.py`: Asegurar que el motor alimente correctamente `daily_indicators` en cada paso del backtest 1H (evitar lookahead bias).

**🆕 Nuevo desde cero:**
- Clase `EMATrendStrategy`.

### 2.2 Datos Necesarios vs Disponibles
**Datos disponibles:**
- 1D y 1H para SPY, QQQ, IWM accesibles vía yfinance.

**Datos requeridos:**
- EMA(100) en D1 (calculable).
- EMA(20) en H1 (calculable).

### 2.3 Complejidad de Implementación
**Puntuación: 5/10 (Moderada)**
1.  **Sincronización Multi-Timeframe**: 6/10 (El mayor desafío es asegurar que la EMA diaria usada en la vela de las 10:00 AM sea la calculada al cierre de ayer, no la de hoy).
2.  **Lógica de entrada/salida**: 4/10 (Pullbacks y cruces de medias son estándar).

### 2.4 Estimación de Tiempo de Desarrollo
- **Implementación base**: 5 horas.
- **Validación Multi-TF**: 3 horas.
- **Backtesting**: 2 horas.
- **Total: ~10 horas.**

### 2.5 Cambios Arquitectónicos
- **Data Pipeline**: Activar descarga sistemática de datos 1D en paralelo a 1H.

### 2.6 Dependencias
- Ninguna adicional.

### 2.7 Riesgos y Bloqueadores
- **Riesgo Medio**: Lookahead bias accidental al mezclar datos diarios y horarios. Se debe usar estrictamente `shift(1)` en datos diarios.

---

## 3. First Hour Trend Lock

### 3.1 Compatibilidad con Código Existente
**❌ Bloqueadores:** 
- `yfinance` solo provee 60 días de historial para datos de 5 minutos. Esto hace imposible un backtest de 2-4 años.

### 3.2 Datos Necesarios vs Disponibles
**Datos faltantes críticos:**
- Histórico 5min > 60 días para SPY, QQQ, IWM.

**Alternativas:**
- **Alpaca API**: Plan gratuito ofrece datos, pero requiere integración nueva.
- **Compra de datos**: Costoso.

### 3.3 Complejidad de Implementación
**Puntuación: 8/10 (Alta - debido a infraestructura)**
1.  **Integración Nueva API**: 7/10 (Autenticación, rate limits, normalización de datos).
2.  **Lógica de Rangos Horarios**: 5/10 (Definir High/Low de 9:30-10:30 requiere manejo preciso de Timezones).

### 3.4 Estimación de Tiempo de Desarrollo
- **Integración Alpaca/Nueva Fuente**: 6-8 horas.
- **Lógica Estrategia**: 6 horas.
- **Validación Datos**: 3 horas.
- **Total: ~15-18 horas.**

### 3.5 Cambios Arquitectónicos
- **Data Manager**: Refactorización mayor para soportar múltiples `Providers` (actualmente muy acoplado a yfinance).

### 3.6 Dependencias
- `alpaca-trade-api` (si se elige esta ruta).

### 3.7 Riesgos y Bloqueadores
- **CRÍTICO**: Falta de datos históricos 5min.
- **Recomendación**: **Posponer** hasta tener infraestructura de datos robusta.

---

## 4. Comparativa de Esfuerzo

| Estrategia | Complejidad | Tiempo Dev | Nuevos Datos | Nuevas Deps | Bloqueadores | Prioridad |
|------------|-------------|------------|--------------|-------------|--------------|-----------|
| **VWAP Bounce** | 4/10 | ~9h | No | No | Ninguno | 🥇 Alta |
| **EMA Trend** | 5/10 | ~10h | Sí (1D) | No | Riesgo Bias | 🥈 Media |
| **First Hour** | 8/10 | ~17h | Sí (5min API) | Sí | ❌ Datos | 🥉 Baja |

---

## 5. Recomendación Estratégica

**🥇 PRIMERA PRIORIDAD: VWAP BOUNCE**
- **Razón**: Es el "Quick Win". Aprovecha al 100% la infraestructura actual (1H data, yfinance). La lógica es intradiaria pura y encaja perfecto con el motor de backtest actual.
- **Timeline**: 1 Semana (a tiempo parcial).

**🥈 SEGUNDA PRIORIDAD: EMA TREND FOLLOWING**
- **Razón**: Introduce la capacidad multi-timeframe (Diario + Horario) que es valiosa para futuras estrategias. Requiere cuidado con la sincronización de datos pero es técnicamente viable hoy.
- **Timeline**: 2 Semanas.

**🥉 TERCERA PRIORIDAD: FIRST HOUR TREND LOCK**
- **Razón**: **NO IMPLEMENTAR AHORA**. El requerimiento de datos de 5 minutos históricos rompe el modelo actual de "datos gratis y sencillos con yfinance". Requiere integrar un nuevo proveedor de datos (Alpaca), lo cual es un proyecto de infraestructura en sí mismo.
- **Timeline**: Postergado (Backlog).

---

## 6. Plan de Implementación Detallado (VWAP Bounce)

**Semana 1: Desarrollo y Validación**

**Día 1: Core Logic**
- [ ] Crear `analysis/pattern_detector.py` para lógica de mechas y velas.
- [ ] Unit tests para detección de rechazos.
- [ ] Verificar cálculo de VWAP en `indicators.py` (reset diario).

**Día 2: Estrategia y Señales**
- [ ] Implementar `strategies/vwap_bounce.py` heredando de `BaseStrategy`.
- [ ] Implementar reglas de entrada (VWAP cross + rejection).
- [ ] Configurar gestión de salida (TP parcial si el motor lo soporta, o simplificado a TP único inicialmente).

**Día 3: Integración y Backtest**
- [ ] Ejecutar backtest en SPY (2020-2024, 1H).
- [ ] Analizar visualmente en gráficos si las entradas coinciden con los toques al VWAP.
- [ ] Ajustar umbrales (tamaño de mecha, filtros).

**Día 4-5: Refinamiento y Reporte**
- [ ] Optimizar parámetros básicos.
- [ ] Documentar resultados (Win Rate, Profit Factor).
- [ ] Commit y Merge.

### 6.1 Snippets Clave

**Detección de Mecha (Conceptual):**
```python
def is_bullish_rejection(open, high, low, close, vwap):
    body = abs(close - open)
    lower_wick = min(open, close) - low
    
    # Regla 1: Toque de VWAP
    if not (low <= vwap and close > vwap):
        return False
        
    # Regla 2: Mecha larga
    if lower_wick < (2 * body):
        return False
        
    return True
```
