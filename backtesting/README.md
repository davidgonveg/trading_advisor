# 📊 Professional Backtesting System

Este es un motor de backtesting profesional diseñado desde cero para ser robusto, modular y libre de sesgos (look-ahead bias). El sistema permite comparar múltiples estrategias de trading bajo condiciones de mercado realistas.

---

## 🏗️ Arquitectura del Sistema

La carpeta `backtesting/` está organizada de forma modular siguiendo principios de ingeniería de software:

- **`core/`**: El motor principal del sistema.
  - `backtester.py`: Motor de eventos que procesa datos barra por barra.
  - `order_executor.py`: Simulador de órdenes (Market, Limit, Stop) con **slippage** y **comisiones**.
  - `portfolio.py`: Gestión de capital, posiciones y seguimiento de P&L realizado (FIFO).
  - `data_loader.py`: Carga y validación técnica de datos OHLCV desde la base de datos.
  - `strategy_interface.py`: Clase abstracta que define el contrato que deben seguir todas las estrategias.
  - `validator.py`: Tests de integridad del motor (conservación de capital, determinismo, anti-look-ahead).
  - `schema.py`: Definiciones de datos (Order, Trade, Position).

- **`strategies/`**: Repositorio de estrategias intercambiables.
  - `vwap_bounce.py`: Estrategia premium con reset diario, patrones de rechazo y gestión de TP/SL dinámico.
  - `sma_crossover.py`: Template de cruce de medias.
  - `rsi_strategy.py`: Template de reversión a la media.

- **`analytics/`**: Módulos de reporting.
  - `metrics.py`: Cálculo de Sharpe Ratio, Drawdown, Profit Factor y Win Rate basado en P&L realizado.

---

## 🚀 Cómo Empezar

### 1. Configuración
Toda la configuración del sistema reside en [config.json](backtesting/config.json). Puedes ajustar:
- Capital inicial.
- Comisiones y slippage.
- Período de tiempo y activos (Símbolos).
- Parámetros específicos de cada estrategia.

### 2. Ejecutar un Backtest
Simplemente ejecuta el script principal desde la raíz del proyecto:
```bash
python backtesting/main.py
```
Esto realizará las siguientes acciones:
1. Ejecuta los **Engine Validation Tests** para asegurar que el motor es fiable.
2. Carga los datos históricos validados.
3. Ejecuta todas las estrategias configuradas de forma secuencial.
4. Genera una **Tabla Comparativa** de resultados en la consola.

---

## 🛠️ Cómo Crear una Nueva Estrategia

El sistema es altamente intercambiable. Para añadir una estrategia:

1. Crea un archivo en `backtesting/strategies/mi_estrategia.py`.
2. Implementa la clase heredando de `StrategyInterface`:
```python
from backtesting.core.strategy_interface import StrategyInterface, Signal, SignalSide

class MiEstrategia(StrategyInterface):
    def setup(self, params):
        self.periodo = params.get('periodo', 14)

    def on_bar(self, history, portfolio_context):
        # history: DataFrame con datos hasta el momento actual
        # portfolio_context: Diccionario con cash, posiciones y trades abiertos
        if condicion_compra:
            return Signal(SignalSide.BUY, quantity_pct=1.0, stop_loss=95.0, tag="ENTRADA")
        return Signal(SignalSide.HOLD)
```
3. Añade la estrategia y sus parámetros a `config.json` y regístrala en `main.py`.

---

## ✅ Garantías de Fiabilidad

- **Zero Look-ahead Bias**: La estrategia nunca recibe datos del futuro. Las órdenes enviadas al cierre de la barra T se ejecutan siempre con la acción de precio de la barra T+1.
- **Validación Atómica**: El motor se auto-valida antes de correr cualquier estrategia real para garantizar que los cálculos son matemáticamente consistentes.
- **Gestión de Costes**: Cada operación deduce comisiones y aplica penalización por slippage, evitando resultados "demasiado buenos para ser ciertos".
