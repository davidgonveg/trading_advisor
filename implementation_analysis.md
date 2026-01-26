# Análisis de Implementación: Estrategia VWAP Bounce (v1.0)

Este documento detalla el plan técnico para implementar la estrategia **VWAP Bounce** en la rama `feature/strategies-implementation`.

## 1. Modificaciones de Infraestructura (Core)

Para soportar la estrategia completa (Long y Short), es necesario habilitar la venta en corto en el motor de simulación, que actualmente está bloqueada.

### `backtesting/simulation/broker.py`
*   **Habilitar Short Selling**: Eliminar restricción en `submit_order` que impide vender si `quantity > current_position`.
    *   *Ubicación*: Líneas ~163-168.
    *   *Verificación*: Asegurar que `Position` maneja cantidades negativas (ya validado en `broker_schema.py`).
    *   *Cambio*: Permitir que `self.cash` aumente al vender en corto (ya soportado en línea 178) y que `self.positions` acepte valores negativos.

## 2. Nuevos Componentes

### `analysis/patterns.py` (Nuevo)
Implementación de la lógica de detección de patrones de velas.
*   **Función `detect_rejection_candle(open, high, low, close, vwap)`**:
    *   Calcula `body`, `lower_wick`, `upper_wick`.
    *   **Long Rejection**: `Low <= VWAP` AND `Close > VWAP` AND `lower_wick > 2 * body`.
    *   **Short Rejection**: `High >= VWAP` AND `Close < VWAP` AND `upper_wick > 2 * body`.
    *   Retorna enum o flag: `None`, `BULLISH_REJECTION`, `BEARISH_REJECTION`.

## 3. Implementación de Estrategia

### `backtesting/strategy/vwap_bounce.py` (Nuevo)
Esta clase heredará de `Strategy` y contendrá toda la lógica de ejecución manual simulada.

**Estructura de clase:**
```python
class VWAPBounceStrategy(Strategy):
    def __init__(self, symbols):
        super().__init__(symbols)
        # Estado para "Manual Management"
        # Map symbol -> { 'entry_price': float, 'tp1_hit': bool, 'tp2_hit': bool, 'sl_price': float }
        self.trade_state = {} 

    def on_bar(self, ctx):
        # 1. Calcular Datos (VWAP, Candles)
        # 2. Gestionar Posiciones Abiertas (Simulación Alertas)
        # 3. Buscar Nuevas Entradas
```

**Lógica de Gestión ("Workflow Manual"):**
Dado que el broker no soporta OCO compleja ni TPs dinámicos nativos, simularemos el comportamiento del trader manual en `on_bar`:

1.  **Monitoreo TP1 (+0.8%)**:
    *   Si `High >= Entry * 1.008` (Long) y no `tp1_hit`:
        *   Cerrar 60% de la posición (Market Order).
        *   Actualizar SL interno a Break Even (`Entry`).
        *   Marcar `tp1_hit = True`.

2.  **Monitoreo TP2 (+1.2%)**:
    *   Si `High >= Entry * 1.012` (Long):
        *   Cerrar resto de posición (Market Order).
        *   Limpiar estado.

3.  **Stop Loss Dinámico**:
    *   Si `Low <= SL` (Long):
        *   Cerrar posición completa.

**Lógica de Entrada:**
1.  Verificar condiciones (VWAP Touch, Patrón, Volumen > SMA20).
2.  Si Setup Válido:
    *   Calcular Size (Riesgo 1.5%).
    *   Enviar `Limit Order` al precio de cierre.
    *   Inicializar `trade_state` para este símbolo.

## 4. Validación de Datos (Pre-requisito)

*   **VWAP Reset**: Verificar en `analysis/indicators.py` que el cálculo de Session VWAP hace reset correcto diariamente cuando se le pasa un DataFrame continuo de múltiples días.
    *   *Acción*: Crear test unitario `tests/unit/test_vwap_reset.py`.

## 5. Plan de Pruebas

### Unit Tests
*   `test_pattern_detector.py`: Probar velas sintéticas para asegurar detección precisa de `wick > 2 * body`.
*   `test_broker_short.py`: Verificar que se puede entrar y salir de posiciones cortas y que el PnL se calcula bien (Vender alto, comprar bajo = Ganancia).

### Backtest de Validación
*   Ejecutar estrategia sobre SPY (2023-2024).
*   Verificar logs trade a trade:
    *   Entrada en cruce VWAP.
    *   Salida parcial ("Partial Fill" o dos ventas separadas).
    *   Stop Loss movido a BE (verificar que no hay pérdidas > 0 tras tocar TP1).

## 6. Siguientes Pasos (Roadmap Inmediato)

1.  **Refactor Broker**: Habilitar Shorts.
2.  **Core Logic**: Crear `pattern_detector.py`.
3.  **Strategy**: Codificar `VWAPBounceStrategy`.
4.  **Dry Run**: Ejecutar backtest corto.
