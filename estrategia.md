# VWAP Bounce Strategy (v1.0)
**Versión:** 1.0 (Base)
**Tipo:** Day Trading / Swing Intradiario
**Horizonte:** 2-8 horas (mismo día)
**Última revisión:** Enero 2026

## 📊 Resumen Ejecutivo
Estrategia de mean reversion basada en rebotes del precio sobre VWAP (Volume Weighted Average Price), diseñada para ser ejecutada de forma manual y mecánica en timeframe de 1 hora.
La estrategia explota el comportamiento institucional de respetar VWAP como nivel de referencia para ejecución de órdenes. Cuando el precio se aleja de VWAP y muestra rechazo con volumen, existe alta probabilidad de reversión hacia la media.

**Filosofía central:**
*   VWAP actúa como "imán" intradiario
*   Toques con rechazo (mechas largas) son señales de agotamiento
*   Volumen confirma la intención institucional
*   Gestión de salidas manual escalonada (broker no soporta TPs dinámicos)

## 🎯 Métricas Objetivo
| Métrica | Objetivo |
| :--- | :--- |
| **Win Rate esperado** | 58-62% |
| **R:R medio** | 1:1.8 – 1:2.0 |
| **Profit Factor** | 1.4-1.6 |
| **Trades/mes (1 activo)** | 15-20 |
| **Trades/mes (3 activos)** | 45-60 |
| **Drawdown máximo** | 12-15% |
| **Sharpe Ratio** | 1.2-1.5 |
| **Tiempo medio en trade** | 2-6 horas |

## 1️⃣ Universo de Productos
**ETFs permitidos:**
*   **Core (siempre activos):** SPY, QQQ, IWM
*   **Sectoriales (expansión):** XLF, XLE, XLK, SMH
*   **Diversificación (expansión):** GLD, TLT, EEM

**Excluidos:** Acciones individuales, Criptomonedas, ETFs baja liquidez, Apalancados.

## 2️⃣ Timeframes
*   **1H:** Análisis, entradas, gestión y salidas (único timeframe necesario).
*   **1D (opcional):** Contexto de tendencia.

## 3️⃣ Indicadores Utilizados
| Indicador | Configuración | Uso |
| :--- | :--- | :--- |
| **VWAP** | Reset diario | Nivel de referencia |
| **Volumen SMA** | SMA(20) | Confirmación |
| **Patrón de vela** | Body/Wicks | Detección rechazo |
| **EMA Tendencia** | EMA(200) | Filtro de Tendencia (Nuevo) |
| **ATR** | Periodo 14 | Gestión de Riesgo |

## 4️⃣ Reglas de Indicadores

### 4.1 VWAP
Typical Price (TP) = (High + Low + Close) / 3
VWAP = Σ(TP × Volume) / Σ(Volume) (Reset diario a las 9:30 EST)

### 4.2 Patrón de Vela (Rechazo)
*   `Body = |Close - Open|`
*   `Lower_Wick = min(Open, Close) - Low`
*   `Upper_Wick = High - max(Open, Close)`

### 4.3 Filtro de Tendencia (Smart Hunter)
*   **Alcista:** Close > EMA(200)
*   **Bajista:** Close < EMA(200)

## 5️⃣ Reglas de Entrada

### 5.1 Entrada LONG
1.  **Filtro Tendencia:** `Close > EMA(200)`
2.  **Toque de VWAP desde arriba:** `Low <= VWAP` y `Close > VWAP`
3.  **Patrón de rechazo alcista:** `Lower_Wick > 2 × Body`
4.  **Confirmación de volumen:** `Volume > SMA(20)`
5.  **Vela 1H cerrada.**

### 5.2 Entrada SHORT
1.  **Filtro Tendencia:** `Close < EMA(200)`
2.  **Toque de VWAP desde abajo:** `High >= VWAP` y `Close < VWAP`
3.  **Patrón de rechazo bajista:** `Upper_Wick > 2 × Body`
4.  **Confirmación de volumen:** `Volume > SMA(20)`
5.  **Vela 1H cerrada.**

## 6️⃣ Gestión de Riesgo y Salida (Smart Hunter)

*   **Riesgo por trade:** 2.0% del capital.
*   **Stop Loss (SL):** 2.0 × ATR(14) desde entrada.
*   **Take Profit (TP):** 4.0 × ATR(14) desde entrada (Salida Total).
*   **Time Stop:** 8 horas (Cierre forzado si no toca SL/TP).

## 7️⃣ Implementación Simplificada
*   Se utiliza un modelo de **Entrada Única / Salida Única**.
*   No hay escalado de posiciones ni cierres parciales.
*   El objetivo es capturar el movimiento de reversión completo o salir por stop.

---

# Plan de Implementación (Backtesting)

Este plan se centra en habilitar el backtesting de la estrategia en la rama `feature/strategies-implementation`.

## Fase 1: Infraestructura y Core
- [ ] **Habilitar Short Selling en Broker**: Modificar `backtesting/simulation/broker.py` para permitir órdenes de venta que resulten en posiciones negativas.
- [ ] **Validar Cálculo VWAP**: Crear test unitario (`tests/unit/test_vwap.py`) para asegurar que el VWAP se resetea correctamente cada día en el flujo de datos continuo.
- [ ] **Implementar Detector de Patrones**: Crear `analysis/patterns.py` con la función `detect_rejection(candle, vwap)` que retorne si es rechazo alcista o bajista según las reglas de mechas.

## Fase 2: Estrategia y Lógica
- [ ] **Crear Estrategia VWAP Bounce**: Implementar `backtesting/strategy/vwap_bounce.py` heredando de `Strategy`.
    - [ ] Implementar `on_bar` para calcular indicadores on-the-fly.
    - [ ] Implementar gestión de estado simple (Entry -> Wait for SL/TP).
    - [ ] Integrar señales de entrada.
- [ ] **Actualizar Configuración**: Crear archivo de configuración o parámetros por defecto.

## Fase 3: Validación y Backtest
- [ ] **Unit Tests**:
    - [ ] Test de lógica de entradas (mocks de velas).
    - [ ] Test de gestión de salidas parciales en el broker simulado.
- [ ] **Ejecución de Backtest**:
    - [ ] Correr simulación sobre SPY (2022-2024).
    - [ ] Generar logs detallados de operaciones.
- [ ] **Análisis de Resultados**:
    - [ ] Verificar Win Rate y Profit Factor contra objetivos.
    - [ ] Validar visualmente 5-10 trades aleatorios.
