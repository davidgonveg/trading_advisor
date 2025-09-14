# 📥 SISTEMA DE DATOS HISTÓRICOS V3.0

Sistema completo de descarga, procesamiento y gestión de datos históricos para el trading bot.

## 🚀 INICIO RÁPIDO

### 1. Setup Automático
```bash
cd historical_data/
python start_system.py --auto
```

### 2. Modo Interactivo
```bash
python start_system.py --interactive
```

### 3. Solo Testing
```bash
python start_system.py --test-quick
```

## 📁 ESTRUCTURA DEL SISTEMA

```
historical_data/
├── config.py              # Configuración centralizada
├── api_manager.py         # Gestor de APIs con rotación
├── data_downloader.py     # Descargador masivo paralelo
├── test_historical_system.py  # Suite de testing completa
├── start_system.py        # Inicializador principal
├── README.md             # Esta documentación
│
├── raw_data/             # Datos descargados (CSV)
├── processed_data/       # Datos procesados
├── logs/                 # Logs y reportes
└── temp_data/           # Archivos temporales
```

## 🔑 CONFIGURACIÓN DE APIs

### 1. Variables de Entorno (.env en directorio padre)
```bash
# Alpha Vantage (500 requests/día gratuito)
ALPHA_VANTAGE_API_KEY=tu_api_key_aqui

# Twelve Data (800 requests/día gratuito)  
TWELVE_DATA_API_KEY=tu_api_key_aqui

# Polygon.io (100 requests/día gratuito)
POLYGON_API_KEY=tu_api_key_aqui

# Yahoo Finance no requiere API key (opción principal)
```

### 2. Prioridad de APIs (configurable)
1. **Yahoo Finance** - Sin límites, primera opción
2. **Twelve Data** - 800 requests/día, buena calidad
3. **Alpha Vantage** - 500 requests/día, confiable  
4. **Polygon.io** - 100 requests/día, backup

### 3. Rate Limits Inteligentes
- **Yahoo**: 1 seg entre requests (conservador)
- **Alpha Vantage**: 13 seg (respeta límite oficial)
- **Twelve Data**: 2 seg (muy conservador)
- **Polygon**: 15 seg (ultra conservador)

## 🎯 FUNCIONALIDADES PRINCIPALES

### API Manager
- ✅ Rotación automática entre APIs si una falla
- ✅ Rate limiting inteligente por API
- ✅ Tracking de uso diario con persistencia
- ✅ Retry automático con exponential backoff
- ✅ Monitoreo de performance en tiempo real

### Data Downloader  
- ✅ Descarga masiva multi-símbolo y multi-timeframe
- ✅ Procesamiento paralelo (workers configurables)
- ✅ Progress tracking con tiempo estimado
- ✅ Resume capability (continúa donde se quedó)
- ✅ Validación automática de calidad de datos
- ✅ Integración con indicadores técnicos del sistema principal

### Testing Suite
- ✅ Tests de conectividad de APIs
- ✅ Validación de calidad de datos OHLCV
- ✅ Tests de performance y memory usage
- ✅ Tests de integración end-to-end
- ✅ Reportes detallados en JSON

## 📊 DATOS SOPORTADOS

### Símbolos
- Configurables en `config.py`
- Default: Top stocks del S&P 500
- Extensible a crypto, forex, etc.

### Timeframes
- **15m** - Datos intraday de 15 minutos
- **1h** - Datos horarios  
- **1d** - Datos diarios
- Extensible a otros intervals

### Datos por Punto
- **OHLCV básico**: Open, High, Low, Close, Volume
- **Indicadores técnicos** (si está disponible):
  - RSI, MACD, Bollinger Bands
  - Moving Averages (SMA, EMA)
  - Stochastic, ATR, etc.

### Período Histórico
- **Default**: 3-12 meses atrás
- **Configurable**: Hasta 5 años según API
- **Incremental**: Solo descarga datos nuevos

## 🚦 MODOS DE EJECUCIÓN

### 1. Modo Automático (Recomendado)
```bash
python start_system.py --auto
```
- Setup completo del sistema
- Tests de validación
- Descarga inicial de datos
- Todo en un comando

### 2. Modo Interactivo
```bash
python start_system.py --interactive
```
- Menú paso a paso
- Control total sobre cada operación
- Ideal para primera configuración

### 3. Comandos Específicos
```bash
# Solo configurar
python start_system.py --setup

# Solo tests
python start_system.py --test

# Solo descarga
python start_system.py --download

# Ver estado
python start_system.py --status
```

### 4. Descarga Personalizada
```bash
# Script directo
python data_downloader.py --symbols AAPL GOOGL MSFT \
                         --timeframes 1d 1h \
                         --start-date 2023-01-01 \
                         --workers 4

# O desde start_system.py interactivo opción 6
```

## 🧪 TESTING Y VALIDACIÓN

### Suite Completa de Tests
```bash
python test_historical_system.py
```

### Tests por Categoría
```bash
# Solo API Manager
python test_historical_system.py --category api

# Solo Data Downloader  
python test_historical_system.py --category downloader

# Solo calidad de datos
python test_historical_system.py --category quality
```

### Quick Test
```bash
python test_historical_system.py --quick
```

### Validaciones Incluidas
- ✅ Conectividad de APIs
- ✅ Rate limiting funcionando
- ✅ Calidad OHLCV (High >= Low, etc.)
- ✅ Continuidad de fechas
- ✅ Precios razonables (no extremos)
- ✅ Performance y memory usage
- ✅ Integración end-to-end

## 📈 CONFIGURACIÓN AVANZADA

### Parallel Processing
```python
# En config.py
PARALLEL_CONFIG = {
    'max_workers': 4,           # Máximo workers paralelos
    'batch_size': 100,          # Tareas por batch
    'timeout_per_request': 30   # Timeout por request
}
```

### Rate Limiting Personalizado
```python
# En config.py  
RATE_LIMITS = {
    'YAHOO': 0.5,           # 0.5 seg entre requests
    'ALPHA_VANTAGE': 12.5,  # 12.5 seg entre requests
    'TWELVE_DATA': 1.0,     # 1 seg entre requests
    'POLYGON': 10.0         # 10 seg entre requests
}
```

### Timeframes Personalizados
```python
# En config.py
TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d', '1w']
```

## 🗄️ INTEGRACIÓN CON SISTEMA PRINCIPAL

### Base de Datos
- Los datos descargados se pueden integrar con `database/`
- Formato compatible con `indicators_data` table
- Histórico de señales recreable con parámetros actuales

### Indicadores Técnicos
- Auto-detección del módulo `indicators.py`
- Cálculo automático durante descarga
- Compatibilidad total con sistema de trading

### Backtesting Preparation
- Datos listos para motor de backtesting
- Formato estándar OHLCV + indicadores
- Metadata de calidad incluida

## 🛠️ TROUBLESHOOTING

### Problema: No hay APIs disponibles
**Solución:**
1. Verificar archivo `.env` en directorio padre
2. Al menos configurar una API key
3. Yahoo Finance funciona sin API key

### Problema: Rate limits excedidos
**Solución:**
1. El sistema maneja automáticamente
2. Ajustar `RATE_LIMITS` en config.py si es necesario
3. Usar múltiples APIs para mayor throughput

### Problema: Descarga incompleta
**Solución:**
1. Ejecutar nuevamente - sistema resume automáticamente
2. Verificar conectividad de red
3. Revisar logs en `logs/` para detalles

### Problema: Calidad de datos mala
**Solución:**
1. Ejecutar `python test_historical_system.py --category quality`
2. Revisar fuente de datos en uso
3. Probar con diferentes API como fuente

### Problema: Performance lenta
**Solución:**
1. Reducir `max_workers` en configuración
2. Aumentar `RATE_LIMITS` si APIs lo permiten
3. Descargar menos símbolos/timeframes simultáneamente

## 📊 MONITOREO Y LOGS

### Ubicación de Logs
```
logs/
├── api_usage.json          # Stats de uso de APIs
├── download_progress.json  # Progreso de descarga
└── test_report_*.json     # Reportes de testing
```

### Monitoreo en Tiempo Real
```bash
# Ver progreso de descarga
tail -f logs/download_progress.json

# Ver uso de APIs
python -c "from api_manager import APIManager; print(APIManager().get_daily_summary())"
```

## 🚀 ROADMAP FUTURO

### Próximas Funcionalidades
- [ ] **Motor de Backtesting**: Engine completo de simulación
- [ ] **ML Integration**: Features para modelos predictivos
- [ ] **Multi-Asset Support**: Crypto, Forex, Commodities
- [ ] **Real-time Streaming**: Datos en vivo complementarios
- [ ] **Cloud Deployment**: Escalabilidad en la nube
- [ ] **Advanced Analytics**: Dashboard web interactivo

### Optimizaciones Planeadas  
- [ ] **Database Integration**: Population automática de SQLite
- [ ] **Compression**: Auto-compresión de datos antiguos
- [ ] **Incremental Updates**: Solo nuevos datos diariamente
- [ ] **Quality Scoring**: Scoring automático de calidad
- [ ] **A/B Testing**: Framework para estrategias

## 🤝 CONTRIBUCIÓN

### Para contribuir:
1. Fork el repositorio
2. Crear branch para feature: `git checkout -b feature/nueva-funcionalidad`
3. Commit cambios: `git commit -am 'Add nueva funcionalidad'`
4. Push al branch: `git push origin feature/nueva-funcionalidad`
5. Crear Pull Request

### Áreas de Contribución
- 🔧 **APIs nuevas**: Integración de más fuentes de datos
- 📊 **Indicadores**: Nuevos indicadores técnicos
- 🧪 **Testing**: Más casos de prueba y validaciones
- 📈 **Performance**: Optimizaciones de velocidad/memoria
- 📚 **Documentación**: Mejoras en docs y ejemplos

## 📞 SOPORTE

### Logs de Debug
```bash
# Activar logging detallado
export LOGGING_LEVEL=DEBUG
python start_system.py --test
```

### Contacto
- 📧 Issues: GitHub Issues del repositorio
- 📖 Docs: README y docstrings en código
- 🧪 Testing: Suite completa incluida

## 📝 CHANGELOG

### V3.0 (Actual)
- ✅ Sistema completo de APIs con rotación inteligente
- ✅ Descargador masivo con procesamiento paralelo
- ✅ Suite completa de testing y validación
- ✅ Progress tracking y resume capability
- ✅ Integración con sistema principal de trading
- ✅ Documentación completa y scripts de inicio

### V2.0 (Anterior)
- ✅ API Manager básico
- ✅ Descarga simple de datos
- ✅ Configuración inicial

### V1.0 (Inicial)
- ✅ Proof of concept
- ✅ Descarga manual básica

---

## 🎯 EJEMPLO DE USO COMPLETO

### Primer Setup (Nuevo Usuario)
```bash
# 1. Configurar API keys en .env (directorio padre)
echo "ALPHA_VANTAGE_API_KEY=tu_key_aqui" >> ../.env

# 2. Setup automático completo
cd historical_data/
python start_system.py --auto

# 3. Verificar que todo funciona
python start_system.py --status
```

### Uso Diario (Usuario Existente)
```bash
# Descarga incremental de nuevos datos
python data_downloader.py --symbols AAPL GOOGL --timeframes 1d 1h

# O usar el sistema interactivo
python start_system.py --interactive
# Seleccionar opción 6: Descarga personalizada
```

### Testing Periódico
```bash
# Test rápido semanal
python start_system.py --test-quick

# Test completo mensual
python test_historical_system.py
```

### Integración con Trading Bot
```python
# Desde el sistema principal
from historical_data.data_downloader import DataDownloader
from historical_data.api_manager import APIManager

# Inicializar
api_manager = APIManager()
downloader = DataDownloader(api_manager)

# Descargar datos específicos
success, df, error = downloader.download_single_symbol(
    DownloadTask(
        symbol='AAPL',
        timeframe='15m', 
        start_date='2024-01-01',
        end_date='2024-12-31'
    )
)

if success:
    # Datos listos para backtesting o análisis
    print(f"Descargados {len(df)} puntos de AAPL")
    print(f"Columnas disponibles: {list(df.columns)}")
```

---

**🚀 ¡Sistema listo para usar! Ejecuta `python start_system.py --auto` para comenzar.**