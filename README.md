# Sistema de Alertas Técnicas para Acciones

Este proyecto es un sistema automatizado para el análisis técnico de acciones que detecta patrones específicos y envía alertas vía Telegram cuando se identifican oportunidades de trading.

## Características

- Monitoreo automático de múltiples acciones configurables
- Análisis técnico basado en múltiples indicadores:
  - Bandas de Bollinger (con parámetros optimizados)
  - MACD (Moving Average Convergence Divergence)
  - RSI (Relative Strength Index) y RSI Estocástico
- Detección inteligente de secuencias de señales con ventana flexible
- Adaptación automática a diferentes tipos de mercado (alcista, bajista, alta/baja volatilidad)
- Alertas en tiempo real vía Telegram con información detallada
- Almacenamiento de datos históricos en base de datos SQLite
- Resúmenes diarios y semanales de trading
- Sistema de backup automático de la base de datos
- Verificación espaciada de acciones para optimizar llamadas a la API
- Sistema de logs con rotación automática

## Requisitos

- Python 3.8+
- Biblioteca yfinance (datos del mercado)
- Bot de Telegram (para enviar alertas)
- Dependencias listadas en `requirements.txt`

## Instalación

1. Clonar el repositorio:
```bash
git clone https://github.com/tu-usuario/stock-alerts.git
cd stock-alerts
```

2. Crear y activar un entorno virtual:
```bash
# En Linux/Mac
python3 -m venv venv
source venv/bin/activate

# En Windows
python -m venv venv
venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar credenciales:
- Copiar `config_example.py` a `config.py`
- Editar `config.py` con tu token de bot de Telegram y chat ID

## Uso

Para iniciar el sistema de monitoreo:

```bash
python main.py
```

Opciones adicionales:

```bash
# Enviar un mensaje de prueba a Telegram para verificar configuración
python main.py --test

# Crear manualmente un backup de la base de datos
python main.py --backup

# Analizar un símbolo específico para comprobar si genera señal
python main.py --symbol AAPL

# Cambiar el intervalo de verificación (en minutos)
python main.py --interval 10
```

## Estrategia de Detección de Señales

El sistema implementa una detección de secuencias de señales flexible:

1. Busca una ruptura de la Banda de Bollinger inferior (precio por debajo de la banda)
2. Detecta RSI Estocástico en zona de sobreventa (por debajo de 20)
3. Identifica señales de MACD favorables (MACD acercándose a su línea de señal)

La ventaja del enfoque de secuencia flexible es que detecta estas condiciones en cualquier orden siempre que ocurran dentro de una ventana de tiempo configurable (por defecto 5 velas de 5 minutos).

## Estructura del Proyecto

- `main.py`: Punto de entrada principal
- `config.py`: Configuración global del sistema
- `database/`: Módulo para manejo de base de datos
  - `connection.py`: Funciones para crear conexiones
  - `operations.py`: Operaciones CRUD en la base de datos
- `indicators/`: Cálculo de indicadores técnicos
  - `bollinger.py`: Bandas de Bollinger
  - `macd.py`: Moving Average Convergence Divergence
  - `rsi.py`: Relative Strength Index y RSI Estocástico
- `market/`: Interacción con API de mercado
  - `data.py`: Obtención de datos mediante yfinance
  - `utils.py`: Utilidades relacionadas con el mercado
- `analysis/`: Detección de patrones y análisis
  - `detector.py`: Detección de secuencias de señales
  - `market_type.py`: Detección del tipo de mercado
- `notifications/`: Sistema de envío de alertas
  - `telegram.py`: Envío de mensajes vía Telegram
  - `formatter.py`: Formateo de mensajes de alerta
- `utils/`: Utilidades generales
  - `logger.py`: Sistema de logging con rotación
- `data/`: Almacenamiento de datos y bases de datos
- `logs/`: Archivos de registro

## Personalización

En el archivo `config.py` puedes personalizar:

- La lista de acciones a monitorear
- Los parámetros de los indicadores técnicos
- Intervalos de verificación
- Configuración de notificaciones
- Opciones de rendimiento del sistema

## Scripts de Prueba

El proyecto incluye varios scripts para probar componentes específicos:

- `test_database.py`: Prueba el almacenamiento en base de datos
- `test_signal_detection.py`: Prueba la detección de señales
- `test_yfinance.py`: Verifica la integración con yfinance

## Ejecución en Segundo Plano

Para ejecutar el sistema en segundo plano en servidores Linux:

```bash
nohup python main.py > output.log 2>&1 &
```

## Contribuir

Las contribuciones son bienvenidas. Por favor, sigue estos pasos:

1. Haz un fork del proyecto
2. Crea una rama para tu función (`git checkout -b feature/nueva-funcion`)
3. Haz commit de tus cambios (`git commit -am 'Añade nueva función'`)
4. Haz push a la rama (`git push origin feature/nueva-funcion`)
5. Abre un Pull Request

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo LICENSE para más detalles.
