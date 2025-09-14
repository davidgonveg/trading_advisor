#!/usr/bin/env python3
"""
⚡ QUICK TEST SIMPLE - PRUEBA BÁSICA SIN DEPENDENCIAS V3.0
========================================================

Version simplificada del quick test que funciona sin dependencias complejas.
Usa solo las funciones básicas para verificar conectividad.
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta

# Setup básico de paths
def setup_paths():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

setup_paths()

# Importar config básico
try:
    import config as config
    print("✅ Usando configuración mínima")
except ImportError:
    print("❌ No se pudo cargar configuración")
    sys.exit(1)

class SimpleAPITester:
    """Tester simple de APIs sin dependencias complejas"""
    
    def __init__(self):
        self.results = {}
    
    def test_yahoo_api(self):
        """Test directo de Yahoo Finance"""
        print("🔍 Testing Yahoo Finance...")
        
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
            params = {
                'interval': '1d',
                'period': '5d'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'chart' in data and data['chart']['result']:
                    result = data['chart']['result'][0]
                    if 'timestamp' in result:
                        points = len(result['timestamp'])
                        print(f"   ✅ Yahoo: {points} puntos de datos")
                        return True
                    
            print(f"   ❌ Yahoo: Error en formato de datos")
            return False
            
        except Exception as e:
            print(f"   ❌ Yahoo: {str(e)[:50]}")
            return False
    
    def test_alpha_vantage_api(self):
        """Test directo de Alpha Vantage"""
        print("🔍 Testing Alpha Vantage...")
        
        try:
            api_keys = getattr(config, 'API_KEYS', {})
            api_key = api_keys.get('ALPHA_VANTAGE')
            
            if not api_key:
                print("   ⏭️ Alpha Vantage: No API key configurada")
                return None
            
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': 'AAPL',
                'apikey': api_key,
                'outputsize': 'compact'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verificar si hay error o rate limit
                if 'Error Message' in data:
                    print(f"   ❌ Alpha Vantage: {data['Error Message']}")
                    return False
                elif 'Note' in data:
                    print(f"   ⚠️ Alpha Vantage: Rate limited")
                    return False
                elif 'Time Series (Daily)' in data:
                    points = len(data['Time Series (Daily)'])
                    print(f"   ✅ Alpha Vantage: {points} puntos de datos")
                    return True
                else:
                    print(f"   ❌ Alpha Vantage: Formato de respuesta inesperado")
                    return False
            else:
                print(f"   ❌ Alpha Vantage: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ Alpha Vantage: {str(e)}")
            return False
    
    def test_twelve_data_api(self):
        """Test directo de Twelve Data"""
        print("🔍 Testing Twelve Data...")
        
        try:
            api_keys = getattr(config, 'API_KEYS', {})
            api_key = api_keys.get('TWELVE_DATA')
            
            if not api_key:
                print("   ⏭️ Twelve Data: No API key configurada")
                return None
            
            url = "https://api.twelvedata.com/time_series"
            params = {
                'symbol': 'AAPL',
                'interval': '1day',
                'apikey': api_key,
                'outputsize': 5
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'status' in data and data['status'] == 'error':
                    print(f"   ❌ Twelve Data: {data.get('message', 'Error desconocido')}")
                    return False
                elif 'values' in data and len(data['values']) > 0:
                    points = len(data['values'])
                    print(f"   ✅ Twelve Data: {points} puntos de datos")
                    return True
                else:
                    print(f"   ❌ Twelve Data: No hay datos en respuesta")
                    return False
            else:
                print(f"   ❌ Twelve Data: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ Twelve Data: {str(e)}")
            return False
    
    def test_environment(self):
        """Test del entorno básico"""
        print("🔍 Testing entorno...")
        
        # Verificar directorios
        dirs_to_check = ['logs', 'raw_data', 'processed_data', 'temp_data']
        missing_dirs = []
        
        for directory in dirs_to_check:
            full_path = os.path.join('historical_data', directory)
            if not os.path.exists(full_path):
                try:
                    os.makedirs(full_path, exist_ok=True)
                    print(f"   📁 Creado: {directory}")
                except:
                    missing_dirs.append(directory)
        
        if missing_dirs:
            print(f"   ❌ No se pudieron crear: {missing_dirs}")
            return False
        else:
            print(f"   ✅ Estructura de directorios OK")
            return True
    
    def test_config(self):
        """Test de configuración"""
        print("🔍 Testing configuración...")
        
        # Verificar APIs disponibles
        available_apis = []
        for api in config.API_PRIORITY:
            if config.is_api_available(api):
                available_apis.append(api)
        
        if available_apis:
            print(f"   ✅ APIs configuradas: {', '.join(available_apis)}")
        else:
            print(f"   ❌ No hay APIs configuradas")
            return False
        
        # Verificar símbolos
        if config.SYMBOLS and len(config.SYMBOLS) > 0:
            print(f"   ✅ Símbolos: {len(config.SYMBOLS)} configurados")
        else:
            print(f"   ❌ No hay símbolos configurados")
            return False
        
        return True
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("⚡ QUICK TEST SIMPLE - DATOS HISTÓRICOS V3.0")
        print("=" * 60)
        
        tests = [
            ("🔧 Entorno", self.test_environment),
            ("⚙️ Configuración", self.test_config),
            ("🟡 Yahoo Finance", self.test_yahoo_api),
            ("🔵 Alpha Vantage", self.test_alpha_vantage_api),
            ("🟢 Twelve Data", self.test_twelve_data_api)
        ]
        
        results = []
        start_time = time.time()
        
        for test_name, test_func in tests:
            print(f"\n{test_name}")
            print("-" * 40)
            
            try:
                result = test_func()
                if result is True:
                    results.append((test_name, "✅ PASS"))
                elif result is False:
                    results.append((test_name, "❌ FAIL"))
                else:
                    results.append((test_name, "⏭️ SKIP"))
                    
            except Exception as e:
                results.append((test_name, f"💥 ERROR: {str(e)[:30]}"))
        
        # Resumen final
        elapsed = time.time() - start_time
        
        print(f"\n" + "=" * 60)
        print(f"📋 RESUMEN DEL TEST")
        print(f"=" * 60)
        
        for test_name, result in results:
            print(f"   {result} {test_name}")
        
        # Contar resultados
        passed = sum(1 for _, result in results if "✅" in result)
        failed = sum(1 for _, result in results if "❌" in result)
        total = len([r for _, r in results if "⏭️" not in r])
        
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"   Total: {total} tests")
        print(f"   Pasados: {passed}")
        print(f"   Fallidos: {failed}")
        print(f"   Tiempo: {elapsed:.1f}s")
        
        # Evaluación general
        if failed == 0 and passed >= 3:
            print(f"\n🎉 SISTEMA LISTO PARA USAR!")
            print(f"💡 Siguiente: python data_downloader.py --test")
        elif passed >= 2:
            print(f"\n⚠️ SISTEMA PARCIALMENTE FUNCIONAL")
            print(f"💡 Al menos tienes conectividad básica")
        else:
            print(f"\n❌ SISTEMA NECESITA CONFIGURACIÓN")
            print(f"💡 Revisa las API keys en el archivo .env")

def main():
    """Función principal"""
    tester = SimpleAPITester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()