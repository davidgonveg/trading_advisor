# Estrategia de Trading: Mean Reversion Selectiva v3.1

**Versión:** 3.1 (Simplificación operativa)
**Tipo:** Swing Trading con Mean Reversion
**Horizonte:** 1–5 días
**Última revisión:** Enero 2026

---

## 📊 Resumen Ejecutivo

Estrategia de swing trading basada en **reversión a la media selectiva**, diseñada para ser ejecutada de forma **manual, clara y sin ambigüedad**, con 10–20 operaciones mensuales en ETFs altamente líquidos del mercado estadounidense.

La versión **v3.1** mantiene intacta la lógica central de la v3.0, pero introduce mejoras clave orientadas a:

* Reducir complejidad operativa
* Eliminar decisiones discrecionales
* Mejorar consistencia y reproducibilidad

Cambios principales:

* Reducción de salidas a **dos Take Profits fijos** (sin trailing)
* **Filtro de volumen dinámico** según régimen de mercado
* **Cancelación inteligente** de entradas escalonadas E2 y E3

---

## 🎯 Métricas Objetivo

| Métrica               | Objetivo      |
| --------------------- | ------------- |
| Win Rate esperado     | 52–60%        |
| R:R medio             | 1:1.6 – 1:2.0 |
| Profit Factor         | 1.3–1.6       |
| Trades/mes            | 10–20         |
| Drawdown máximo       | 15–20%        |
| Tiempo medio en trade | 1–4 días      |

---

## 1️⃣ Universo de Productos

### ETFs permitidos

**Core (siempre activos):**

* SPY, QQQ, IWM

**Sectoriales:**

* XLF, XLE, XLK, SMH

**Diversificación:**

* GLD, TLT, EEM

### Productos excluidos

* Acciones individuales
* Criptomonedas
* Forex

Motivo: riesgo de gaps, spreads elevados o dependencia macro específica.

---

## 2️⃣ Timeframes

* **1H:** entradas, gestión y salidas
* **1D:** filtros estructurales (tendencia y régimen)

---

## 3️⃣ Indicadores Utilizados

| Indicador       | Configuración | Uso                 |
| --------------- | ------------- | ------------------- |
| Connors RSI     | (3,2,100)     | Gatillo principal   |
| Bollinger Bands | (20,2)        | Extremos y TP       |
| SMA 200         | Diario        | Filtro de tendencia |
| ADX +DI/-DI     | Diario (14)   | Régimen             |
| ATR             | (14)          | SL y sizing         |
| Volumen         | SMA 20        | Confirmación        |
| VWAP            | Diario        | Opcional            |

---

## 4️⃣ Filtros de Mercado

### 4.1 Filtro de Tendencia (obligatorio)

* **LONG:** Precio > SMA 200 diario
* **SHORT:** Precio < SMA 200 diario

---

### 4.2 Filtro de Régimen (ADX)

| Condición                      | Acción                                       |
| ------------------------------ | -------------------------------------------- |
| ADX < 20                       | Mercado lateral → mean reversion óptimo      |
| ADX 20–30                      | Régimen neutral → operar con reglas estándar |
| ADX ≥ 30 + dirección favorable | Pullbacks permitidos                         |
| ADX ≥ 30 + dirección contraria | NO operar                                    |

---

## 5️⃣ Filtro de Volumen Dinámico

El requisito de volumen se adapta al régimen:

| Régimen    | Condición ADX | Volumen mínimo |
| ---------- | ------------- | -------------- |
| Lateral    | ADX < 20      | ≥ 1.0 × SMA20  |
| Neutral    | ADX 20–30     | ≥ 1.2 × SMA20  |
| Tendencial | ADX ≥ 30      | ≥ 1.5 × SMA20  |

Si el volumen no cumple → **no se toma la entrada**, aunque el resto del setup sea perfecto.

---

## 6️⃣ Reglas de Entrada

### 6.1 Entrada LONG

Todas deben cumplirse:

1. Connors RSI < 10
2. Precio ≤ banda inferior Bollinger
3. Precio > SMA 200 diario
4. Régimen permitido según ADX
5. Volumen válido según régimen
6. Vela 1H cerrada

### 6.2 Entrada SHORT

Simétrico:

1. Connors RSI > 90
2. Precio ≥ banda superior Bollinger
3. Precio < SMA 200 diario
4. Régimen permitido
5. Volumen válido
6. Vela 1H cerrada

---

## 7️⃣ Entrada Escalonada

### Distribución

| Nivel | % Posición | Precio            |
| ----- | ---------- | ----------------- |
| E1    | 50%        | Cierre vela señal |
| E2    | 30%        | ± 0.5 × ATR       |
| E3    | 20%        | ± 1.0 × ATR       |

---

### Cancelación Inteligente de E2 y E3

Cancelar **inmediatamente** E2 y E3 si ocurre cualquiera:

1. **Alivio estadístico:**

   * LONG: CRSI > 25
   * SHORT: CRSI < 75

2. **Reversión inicial:**

   * LONG: cierre 1H sobre BB media
   * SHORT: cierre 1H bajo BB media

3. **Expansión de régimen:**

   * ADX diario +3 puntos desde E1

4. **Timeout:**

   * 4 horas desde E1

---

## 8️⃣ Stop Loss

* SL inicial = Precio promedio ± 2 × ATR
* SL recalculado solo si entra E2/E3
* Nunca se mueve contra la posición

---

## 9️⃣ Take Profit (Simplificado)

### Estructura Única

| TP  | %   | Nivel                  | Acción                   |
| --- | --- | ---------------------- | ------------------------ |
| TP1 | 60% | Banda media BB (SMA20) | SL restante → Break Even |
| TP2 | 40% | Banda opuesta BB       | Cerrar trade             |

### Reglas clave

* Una vez alcanzado TP1, el trade **no puede acabar en pérdida**
* No hay trailing stop
* No hay TP discrecional

Si TP1 y TP2 se alcanzan en la misma vela → ejecutar ambos y cerrar.

---

## 🔁 Invalidez Temprana del Trade

Antes de TP1, cerrar trade completo si:

* CRSI cruza extremo opuesto
* Y el precio no ha alcanzado BB media

Evita trades zombis.

---

## ⏱️ Time Stop

* Cerrar trade si tras 5 días:

  * No se alcanzó TP1
  * Y el precio no supera ±0.5×ATR

**No aplicar time stop** si:

* TP1 ya ejecutado
* SL está en BE

---

## 💰 Gestión de Riesgo

* Riesgo por trade: 1.5%
* Máx trades simultáneos: 4
* Riesgo total máximo: 6%
* Ajuste por volatilidad ATR
* Reglas estrictas de correlación

---

## 🕒 Horarios

* Operar solo:

  * 15:30–17:30 CET
  * 20:00–22:00 CET

Evitar:

* Viernes última media hora
* FOMC, NFP, CPI según calendario

---

## ✅ Checklist Final

* Tendencia válida
* Régimen válido
* Volumen correcto
* CRSI extremo
* Precio en banda BB
* Riesgo y correlación OK

---

## 🧠 Conclusión

La versión **v3.1** es una evolución natural hacia una estrategia:

* Más limpia
* Más ejecutable
* Menos ambigua
* Igual de robusta

**Menos decisiones → mejor trading.**
