# Sistema de Alertas Técnicas para Acciones

Este proyecto es un sistema automatizado para el análisis técnico de acciones que detecta patrones específicos y envía alertas vía Telegram cuando se identifican oportunidades de trading.

## Características

- Monitoreo automático de múltiples acciones
- Análisis técnico usando múltiples indicadores:
  - Bandas de Bollinger
  - MACD (Moving Average Convergence Divergence)
  - RSI (Relative Strength Index) y RSI Estocástico
- Detección de patrones de trading específicos
- Alertas en tiempo real vía Telegram
- Almacenamiento de datos históricos en base de datos SQLite
- Adaptación a diferentes tipos de mercado (alcista, bajista, alta/baja volatilidad)

## Requisitos

- Python 3.8+
- API key de Finnhub (datos del mercado)
- Bot de Telegram (para enviar alertas)

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
- Editar `config.py` con tus claves API de Finnhub y Telegram

## Uso

Para iniciar el sistema de monitoreo:

```bash
python main.py
```

Para enviar un mensaje de prueba a Telegram:

```bash
python -c "from notifications.telegram import send_telegram_test; send_telegram_test('Mensaje de prueba', 'TU_TOKEN_BOT', 'TU_CHAT_ID')"
```

## Estructura del Proyecto

- `config.py`: Configuración global y parámetros
- `database/`: Módulo para manejo de base de datos
- `indicators/`: Cálculo de indicadores técnicos
- `market/`: Interacción con API de mercado
- `analysis/`: Detección de patrones y análisis
- `notifications/`: Sistema de envío de alertas
- `utils/`: Utilidades generales
- `data/`: Almacenamiento de datos y bases de datos
- `logs/`: Archivos de registro

## Personalización

Puedes personalizar:

- La lista de acciones a monitorear en `config.py`
- Los parámetros de los indicadores técnicos
- El formato de los mensajes de alerta
- Los criterios de detección de patrones

## Contribuir

Las contribuciones son bienvenidas. Por favor, sigue estos pasos:

1. Haz un fork del proyecto
2. Crea una rama para tu función (`git checkout -b feature/nueva-funcion`)
3. Haz commit de tus cambios (`git commit -am 'Añade nueva función'`)
4. Haz push a la rama (`git push origin feature/nueva-funcion`)
5. Abre un Pull Request

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo LICENSE para más detalles.