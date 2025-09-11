# 🐳 DOCKERFILE PARA SISTEMA DE TRADING AUTOMATIZADO V2.0
# =======================================================

# Usar Python 3.11 slim como base (más ligero)
FROM python:3.11-slim

# Información del mantenedor
LABEL maintainer="Trading System v2.0"
LABEL description="Sistema automatizado de trading con alertas por Telegram"

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=America/New_York

# Crear usuario no-root para seguridad
RUN groupadd -r trader && useradd -r -g trader trader

# Instalar dependencias del sistema necesarias para TA-Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Instalar TA-Lib desde source (necesario para indicadores técnicos)
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements primero (para aprovechar cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Cambiar propietario de archivos al usuario trader
RUN chown -R trader:trader /app

# Cambiar a usuario no-root
USER trader

# Crear directorio para logs
RUN mkdir -p /app/logs

# Comando por defecto
CMD ["python", "main.py"]

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1