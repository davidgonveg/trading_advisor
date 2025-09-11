#!/usr/bin/env python3
"""
🧪 TEST DE CONFIGURACIÓN DEL SISTEMA DE TRADING V2.0
===================================================

Script para probar que la configuración es correcta antes de ejecutar el sistema completo.
"""

import sys
import os
from datetime import datetime
import yfinance as yf

def test_environment():
    """Probar variables de entorno"""
    print("🔐 Probando variables de entorno...")
    
    # Probar carga de .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Archivo .env cargado correctamente")
    except Exception as e:
        print(f"❌ Error cargando .env: {e}")
        return False
    
    # Verificar variables críticas
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    
    if not telegram_token:
        print("❌ TELEGRAM_TOKEN no encontrado en .env")
        return False
    else:
        print(f"✅ TELEGRAM_TOKEN configurado (longitud: {len(telegram_token)})")
    
    if not chat_id:
        print("❌ CHAT_ID no encontrado en .env")
        return False
    else:
        print(f"✅ CHAT_ID configurado: {chat_id}")
    
    return True

def test_dependencies():
    """Probar que todas las dependencias están instaladas"""
    print("\n📦 Probando dependencias...")
    
    dependencies = [
        ('pandas', 'pandas'),      # Corregido: era 'pd'
        ('numpy', 'numpy'),        # Corregido: era 'np' 
        ('yfinance', 'yfinance'),  # Corregido: era 'yf'
        ('schedule', 'schedule'),
        ('telegram', 'telegram'),
        ('dotenv', 'dotenv'),
    ]
    
    failed = []
    
    for dep_name, import_name in dependencies:
        try:
            __import__(import_name)
            print(f"✅ {dep_name}")
        except ImportError as e:
            print(f"❌ {dep_name}: {e}")
            failed.append(dep_name)
    
    # Probar TA-Lib por separado (más complejo)
    try:
        import talib
        print("✅ TA-Lib")
    except ImportError as e:
        print(f"❌ TA-Lib: {e}")
        print("   💡 TA-Lib requiere instalación especial. Ver README.md")
        failed.append('TA-Lib')
    
    return len(failed) == 0

def test_config_loading():
    """Probar carga de configuración"""
    print("\n⚙️ Probando configuración...")
    
    try:
        from config import (
            SYMBOLS, SCAN_INTERVAL, TELEGRAM_TOKEN, CHAT_ID,
            validate_config, print_config_summary
        )
        print("✅ Archivo config.py importado correctamente")
        
        # Ejecutar validación
        errors = validate_config()
        if errors:
            print("❌ Errores de validación:")
            for error in errors:
                print(f"   {error}")
            return False
        else:
            print("✅ Configuración válida")
            print_config_summary()
            return True
            
    except Exception as e:
        print(f"❌ Error importando configuración: {e}")
        return False

def test_market_data():
    """Probar descarga de datos de mercado"""
    print("\n📊 Probando conexión con datos de mercado...")
    
    try:
        # Probar descarga de datos simple
        ticker = yf.Ticker("AAPL")
        data = ticker.history(period="1d", interval="15m")
        
        if data.empty:
            print("❌ No se pudieron descargar datos de AAPL")
            return False
        else:
            print(f"✅ Datos descargados correctamente")
            print(f"   📈 Último precio AAPL: ${data['Close'].iloc[-1]:.2f}")
            print(f"   📅 Última actualización: {data.index[-1]}")
            return True
            
    except Exception as e:
        print(f"❌ Error descargando datos: {e}")
        return False

def test_telegram_connection():
    """Probar conexión con Telegram (sin enviar mensaje)"""
    print("\n📱 Probando configuración de Telegram...")
    
    try:
        from telegram import Bot
        from config import TELEGRAM_TOKEN, CHAT_ID
        
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print("❌ Token o Chat ID no configurados")
            return False
        
        # Solo verificar que el bot se puede inicializar
        bot = Bot(token=TELEGRAM_TOKEN)
        print("✅ Bot de Telegram inicializado correctamente")
        print("   💡 Para probar envío real, usar: python -c \"from telegram_bot import send_test_message; send_test_message()\"")
        return True
        
    except Exception as e:
        print(f"❌ Error configurando Telegram: {e}")
        return False

def main():
    """Ejecutar todos los tests"""
    print("🧪 INICIANDO TESTS DE CONFIGURACIÓN")
    print("=" * 50)
    
    tests = [
        ("Variables de Entorno", test_environment),
        ("Dependencias", test_dependencies),
        ("Configuración", test_config_loading),
        ("Datos de Mercado", test_market_data),
        ("Telegram", test_telegram_connection),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"💥 Error ejecutando test {test_name}: {e}")
            results.append((test_name, False))
    
    # Resumen final
    print("\n" + "=" * 50)
    print("📋 RESUMEN DE TESTS")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n📊 Resultado: {passed}/{len(tests)} tests pasaron")
    
    if passed == len(tests):
        print("🎉 ¡Todos los tests pasaron! El sistema está listo.")
        return True
    else:
        print("⚠️  Algunos tests fallaron. Revisa la configuración antes de continuar.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)