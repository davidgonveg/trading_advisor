#!/usr/bin/env python3
"""
⚡ QUICK TEST - VALIDACIÓN DE CONECTIVIDAD V4.0
=============================================

Test simple y efectivo para validar que todas las APIs funcionan correctamente.
Sin complejidad innecesaria - directo al grano.
"""

import os
import sys
import time
import requests
import json
from datetime import datetime, timedelta

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import config
try:
    import config
    print("✅ Config cargado correctamente")
except ImportError as e:
    print(f"❌ Error cargando config: {e}")
    sys.exit(1)

class QuickAPITester:
    """Tester simple de conectividad de APIs"""
    
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
    
    def test_yahoo_finance(self):
        """Test Yahoo Finance usando yfinance library (como en sistema principal)"""
        print("🟡 Testing Yahoo Finance...")
        
        try:
            # Usar yfinance library como en indicators.py
            import yfinance as yf
            from datetime import datetime, timedelta
            
            # Mismo approach que indicators.py
            ticker = yf.Ticker("AAPL")
            data = ticker.history(
                period="5d",
                interval="1d",
                auto_adjust=True,
                prepost=True
            )
            
            if not data.empty:
                # Validar que tenemos datos
                points = len(data)
                print(f"   ✅ Yahoo: {points} puntos de datos obtenidos")
                
                # Validar columnas OHLCV
                required_fields = ['Open', 'High', 'Low', 'Close', 'Volume']
                available_fields = [field for field in required_fields if field in data.columns]
                
                if len(available_fields) == len(required_fields):
                    print(f"   ✅ Yahoo: Estructura OHLCV completa")
                    
                    # Test adicional: verificar que los datos son razonables
                    latest = data.iloc[-1]
                    if latest['High'] >= latest['Low'] and latest['Close'] > 0:
                        print(f"   ✅ Yahoo: Datos válidos (último close: ${latest['Close']:.2f})")
                        return True, f"OK - {points} puntos"
                    else:
                        print(f"   ⚠️ Yahoo: Datos inconsistentes")
                        return True, f"PARCIAL - {points} puntos"
                else:
                    missing = [f for f in required_fields if f not in data.columns]
                    print(f"   ⚠️ Yahoo: Faltan campos: {missing}")
                    return True, f"PARCIAL - {points} puntos, faltan {len(missing)} campos"
            else:
                print(f"   ❌ Yahoo: DataFrame vacío")
                return False, "Sin datos"
                
        except ImportError:
            print(f"   ❌ Yahoo: yfinance no instalado")
            return False, "yfinance no disponible"
        except Exception as e:
            error_msg = str(e)
            
            # Manejar errores comunes de yfinance
            if "429" in error_msg or "Too Many Requests" in error_msg:
                print(f"   ⏰ Yahoo: Rate limited, esperando...")
                time.sleep(2)  # Esperar y reintentar una vez
                try:
                    ticker = yf.Ticker("AAPL")
                    data = ticker.history(period="2d", interval="1d")
                    if not data.empty:
                        points = len(data)
                        print(f"   ✅ Yahoo: Retry exitoso - {points} puntos")
                        return True, f"OK después de retry - {points} puntos"
                except:
                    pass
                print(f"   ❌ Yahoo: Rate limit persistente")
                return False, "Rate limited"
            elif "No data found" in error_msg:
                print(f"   ❌ Yahoo: No hay datos para símbolo")
                return False, "No data found"
            else:
                print(f"   ❌ Yahoo: {error_msg[:60]}")
                return False, error_msg[:60]
    
    def test_alpha_vantage(self):
        """Test Alpha Vantage API"""
        print("🔵 Testing Alpha Vantage...")
        
        if not config.is_api_available('ALPHA_VANTAGE'):
            print("   ⏭️ Alpha Vantage: Sin API key")
            return None, "Sin API key"
        
        try:
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': 'AAPL',
                'apikey': config.API_KEYS['ALPHA_VANTAGE'],
                'outputsize': 'compact'
            }
            
            response = requests.get(config.API_ENDPOINTS['ALPHA_VANTAGE'], 
                                  params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'Error Message' in data:
                    print(f"   ❌ Alpha Vantage: {data['Error Message']}")
                    return False, data['Error Message']
                elif 'Note' in data:
                    print(f"   ⚠️ Alpha Vantage: Rate limit - {data['Note']}")
                    return False, "Rate limited"
                elif 'Time Series (Daily)' in data:
                    time_series = data['Time Series (Daily)']
                    points = len(time_series)
                    print(f"   ✅ Alpha Vantage: {points} puntos de datos")
                    return True, f"OK - {points} puntos"
                else:
                    print(f"   ❌ Alpha Vantage: Respuesta inesperada")
                    return False, "Respuesta inesperada"
            else:
                print(f"   ❌ Alpha Vantage: HTTP {response.status_code}")
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ Alpha Vantage: Timeout")
            return False, "Timeout"
        except Exception as e:
            print(f"   ❌ Alpha Vantage: {str(e)[:50]}")
            return False, str(e)[:50]
    
    def test_twelve_data(self):
        """Test Twelve Data API"""
        print("🟢 Testing Twelve Data...")
        
        if not config.is_api_available('TWELVE_DATA'):
            print("   ⏭️ Twelve Data: Sin API key")
            return None, "Sin API key"
        
        try:
            params = {
                'symbol': 'AAPL',
                'interval': '1day',
                'apikey': config.API_KEYS['TWELVE_DATA'],
                'outputsize': 30
            }
            
            response = requests.get(config.API_ENDPOINTS['TWELVE_DATA'], 
                                  params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'status' in data and data['status'] == 'error':
                    print(f"   ❌ Twelve Data: {data.get('message', 'Error desconocido')}")
                    return False, data.get('message', 'Error')
                elif 'values' in data and len(data['values']) > 0:
                    points = len(data['values'])
                    print(f"   ✅ Twelve Data: {points} puntos de datos")
                    
                    # Validar estructura
                    sample = data['values'][0]
                    required_fields = ['open', 'high', 'low', 'close', 'volume']
                    has_all_fields = all(field in sample for field in required_fields)
                    
                    if has_all_fields:
                        print(f"   ✅ Twelve Data: Estructura OHLCV completa")
                        return True, f"OK - {points} puntos"
                    else:
                        print(f"   ⚠️ Twelve Data: Estructura OHLCV parcial")
                        return True, f"PARCIAL - {points} puntos"
                else:
                    print(f"   ❌ Twelve Data: Sin datos en respuesta")
                    return False, "Sin datos"
            else:
                print(f"   ❌ Twelve Data: HTTP {response.status_code}")
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ Twelve Data: Timeout")
            return False, "Timeout"
        except Exception as e:
            print(f"   ❌ Twelve Data: {str(e)[:50]}")
            return False, str(e)[:50]
    
    def test_polygon(self):
        """Test Polygon.io API"""
        print("🟣 Testing Polygon...")
        
        if not config.is_api_available('POLYGON'):
            print("   ⏭️ Polygon: Sin API key")
            return None, "Sin API key"
        
        try:
            # Usar fechas de días de semana (evitar fines de semana)
            from datetime import datetime, timedelta
            
            # Buscar último viernes si es fin de semana
            end_date = datetime.now()
            while end_date.weekday() >= 5:  # Sábado (5) o Domingo (6)
                end_date -= timedelta(days=1)
            
            start_date = end_date - timedelta(days=7)
            
            # Formato correcto para Polygon API
            url = f"{config.API_ENDPOINTS['POLYGON']}AAPL/range/1/day/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            params = {
                'apikey': config.API_KEYS['POLYGON'],
                'adjusted': 'true',
                'sort': 'asc'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'OK':
                    results = data.get('results', [])
                    points = len(results)
                    
                    if points > 0:
                        print(f"   ✅ Polygon: {points} puntos de datos")
                        
                        # Validar estructura (Polygon usa nombres cortos)
                        sample = results[0]
                        required_fields = ['o', 'h', 'l', 'c', 'v', 't']  # open, high, low, close, volume, timestamp
                        has_all_fields = all(field in sample for field in required_fields)
                        
                        if has_all_fields:
                            print(f"   ✅ Polygon: Estructura OHLCV completa")
                            
                            # Validar que los datos son razonables
                            if sample['h'] >= sample['l'] and sample['c'] > 0:
                                close_price = sample['c']
                                print(f"   ✅ Polygon: Datos válidos (último close: ${close_price:.2f})")
                                return True, f"OK - {points} puntos"
                            else:
                                print(f"   ⚠️ Polygon: Datos inconsistentes")
                                return True, f"PARCIAL - {points} puntos"
                        else:
                            missing = [f for f in required_fields if f not in sample]
                            print(f"   ⚠️ Polygon: Faltan campos: {missing}")
                            return True, f"PARCIAL - {points} puntos, faltan campos"
                    else:
                        print(f"   ⚠️ Polygon: Sin datos (posible fin de semana/feriado)")
                        return True, "Sin datos (mercado cerrado?)"
                elif data.get('status') == 'ERROR':
                    error_msg = data.get('error', 'Error desconocido')
                    print(f"   ❌ Polygon: {error_msg}")
                    return False, error_msg
                else:
                    status = data.get('status', 'UNKNOWN')
                    print(f"   ❌ Polygon: Status inesperado: {status}")
                    return False, f"Status: {status}"
            elif response.status_code == 401:
                print(f"   ❌ Polygon: API key inválida")
                return False, "API key inválida"
            elif response.status_code == 429:
                print(f"   ⏰ Polygon: Rate limited")
                return False, "Rate limited"
            else:
                print(f"   ❌ Polygon: HTTP {response.status_code}")
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ Polygon: Timeout")
            return False, "Timeout"
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Polygon: {error_msg[:60]}")
            return False, error_msg[:60]
    
    def test_environment(self):
        """Test del entorno y directorios"""
        print("🔧 Testing entorno...")
        
        try:
            # Verificar/crear directorios
            for path_name, path_value in config.PATHS.items():
                if path_name.endswith('_file'):
                    # Es un archivo, verificar directorio padre
                    dir_path = os.path.dirname(path_value)
                else:
                    # Es un directorio
                    dir_path = path_value
                
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    print(f"   📁 Creado: {dir_path}")
                
            print(f"   ✅ Entorno: Directorios preparados")
            return True, "OK"
            
        except Exception as e:
            print(f"   ❌ Entorno: {str(e)}")
            return False, str(e)
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("⚡ QUICK TEST - SISTEMA HISTÓRICO V4.0")
        print("=" * 50)
        
        # Lista de tests
        tests = [
            ("🔧 Entorno", self.test_environment),
            ("🟡 Yahoo Finance", self.test_yahoo_finance),
            ("🔵 Alpha Vantage", self.test_alpha_vantage),
            ("🟢 Twelve Data", self.test_twelve_data),
            ("🟣 Polygon", self.test_polygon)
        ]
        
        # Ejecutar tests
        results = {}
        for test_name, test_func in tests:
            print(f"\n{test_name}")
            print("-" * 30)
            
            try:
                success, message = test_func()
                results[test_name] = (success, message)
            except Exception as e:
                results[test_name] = (False, f"Exception: {str(e)}")
                print(f"   💥 Error inesperado: {e}")
        
        # Resumen final
        self.print_summary(results)
        return results
    
    def print_summary(self, results):
        """Imprimir resumen de resultados"""
        elapsed = time.time() - self.start_time
        
        print(f"\n" + "=" * 50)
        print(f"📋 RESUMEN DE CONECTIVIDAD")
        print(f"=" * 50)
        
        working_apis = []
        failed_apis = []
        skipped_apis = []
        
        for test_name, (success, message) in results.items():
            if test_name == "🔧 Entorno":
                status = "✅ OK" if success else "❌ ERROR"
                print(f"   {status} {test_name}: {message}")
            else:
                if success is None:
                    status = "⏭️ SKIP"
                    skipped_apis.append(test_name)
                elif success:
                    status = "✅ OK  "
                    working_apis.append(test_name)
                else:
                    status = "❌ FAIL"
                    failed_apis.append(test_name)
                
                print(f"   {status} {test_name}: {message}")
        
        # Estadísticas
        total_apis = len(working_apis) + len(failed_apis)
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"   APIs funcionando: {len(working_apis)}")
        print(f"   APIs con problemas: {len(failed_apis)}")
        print(f"   APIs sin configurar: {len(skipped_apis)}")
        print(f"   Tiempo total: {elapsed:.1f}s")
        
        # Evaluación final
        if len(working_apis) >= 2:
            print(f"\n🎉 SISTEMA LISTO PARA DESCARGA!")
            print(f"💡 Tienes {len(working_apis)} APIs funcionando - perfecto para rate limits")
            print(f"💡 Siguiente paso: python downloader.py --test")
        elif len(working_apis) >= 1:
            print(f"\n⚠️ SISTEMA PARCIALMENTE LISTO")
            print(f"💡 Solo {len(working_apis)} API funcionando - considera configurar más")
        else:
            print(f"\n❌ SISTEMA NECESITA CONFIGURACIÓN")
            print(f"💡 Ninguna API funcionando - revisa las claves en .env")

def main():
    """Función principal"""
    tester = QuickAPITester()
    results = tester.run_all_tests()
    
    # Exit code basado en resultados
    working_count = sum(1 for success, _ in results.values() if success is True)
    sys.exit(0 if working_count > 0 else 1)

if __name__ == "__main__":
    main()