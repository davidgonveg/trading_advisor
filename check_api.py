import time
import requests
import json
import sqlite3
from datetime import datetime

# Tu API key de Finnhub
FINNHUB_API_KEY = "cveivgpr01ql1jnbobc0cveivgpr01ql1jnbobcg"

def create_stock_table(symbol):
    """Crea una tabla individual para un símbolo de stock específico."""
    conn = sqlite3.connect('stock_quotes_individual.db')
    cursor = conn.cursor()
    
    # Crear tabla para el símbolo específico si no existe
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {symbol}_quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        current_price REAL,
        change REAL,
        change_percent REAL,
        low_price REAL,
        high_price REAL,
        timestamp DATETIME
    )
    ''')
    
    conn.commit()
    conn.close()

def insert_quote_to_db(symbol, data):
    """Inserta los datos de cotización en la tabla específica del stock."""
    try:
        conn = sqlite3.connect('stock_quotes_individual.db')
        cursor = conn.cursor()
        
        # Insertar datos de cotización en la tabla específica del stock
        cursor.execute(f'''
        INSERT INTO {symbol}_quotes 
        (current_price, change, change_percent, low_price, high_price, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['c'],  # current price
            data['d'],  # change
            data['dp'],  # change percent
            data['l'],  # low price
            data['h'],  # high price
            datetime.now()  # timestamp
        ))
        
        conn.commit()
        print(f"✅ Datos de {symbol} guardados en la base de datos")
        
    except sqlite3.Error as e:
        print(f"❌ Error al guardar en la base de datos: {e}")
    
    finally:
        conn.close()

def get_current_quote(symbol):
    """Obtiene datos de cotización en tiempo real para un símbolo."""
    try:
        url = f"https://finnhub.io/api/v1/quote"
        params = {
            'symbol': symbol,
            'token': FINNHUB_API_KEY
        }
        
        print(f"Solicitando cotización actual para {symbol}...")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Verificar que los datos no estén vacíos
            if 'c' in data and data['c'] > 0:
                print(f"✅ Cotización obtenida para {symbol}")
                print(f"   Precio actual: ${data['c']}")
                print(f"   Cambio: ${data['d']} ({data['dp']}%)")
                print(f"   Rango del día: ${data['l']} - ${data['h']}")
                
                # Crear tabla para el símbolo y guardar en base de datos
                create_stock_table(symbol)
                insert_quote_to_db(symbol, data)
                
                return data
            else:
                print(f"⚠️ Datos incompletos para {symbol}: {data}")
                return None
        else:
            print(f"❌ Error al obtener cotización: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error al conectar con Finnhub: {e}")
        return None

def test_quotes():
    """Prueba la obtención de cotizaciones para varios símbolos."""
    print("\n" + "="*50)
    print("PRUEBA DE COTIZACIONES EN TIEMPO REAL")
    print("="*50)
    
    symbols = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN', 'META']
    results = {}
    
    for symbol in symbols:
        print("\n" + "-"*50)
        data = get_current_quote(symbol)
        if data:
            results[symbol] = data
        time.sleep(1)  # Pequeña pausa para no sobrecargar la API
    
    # Guardar resultados en un archivo JSON para referencia
    with open("quotes_results.json", "w") as f:
        json.dump(results, f, indent=4)
    
    print("\n" + "="*50)
    print(f"Cotizaciones obtenidas: {len(results)}/{len(symbols)}")
    print("="*50)

def view_stock_database_contents(symbol=None):
    """Muestra el contenido de la base de datos para un stock específico o todos."""
    try:
        conn = sqlite3.connect('stock_quotes_individual.db')
        cursor = conn.cursor()
        
        # Obtener lista de tablas en la base de datos (excluyendo tablas de sistema)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_quotes';")
        tables = cursor.fetchall()
        
        print("\n" + "="*50)
        print("CONTENIDO DE TODAS LAS TABLAS DE STOCKS")
        print("="*50)
        
        for table in tables:
            table_name = table[0]
            print(f"\nTabla: {table_name}")
            cursor.execute(f'SELECT * FROM {table_name}')
            records = cursor.fetchall()
            
            for record in records:
                print(f"ID: {record[0]}")
                print(f"Precio Actual: ${record[1]}")
                print(f"Cambio: ${record[2]} ({record[3]}%)")
                print(f"Rango: ${record[4]} - ${record[5]}")
                print(f"Timestamp: {record[6]}")
                print("-"*50)
        
    except sqlite3.Error as e:
        print(f"❌ Error al leer la base de datos: {e}")
    
    finally:
        conn.close()

def view_specific_stock_contents(symbol):
    """Muestra el contenido de la base de datos para un stock específico."""
    try:
        conn = sqlite3.connect('stock_quotes_individual.db')
        cursor = conn.cursor()
        
        cursor.execute(f'SELECT * FROM {symbol}_quotes')
        records = cursor.fetchall()
        
        print(f"\n" + "="*50)
        print(f"CONTENIDO DE LA BASE DE DATOS PARA {symbol}")
        print("="*50)
        
        for record in records:
            print(f"ID: {record[0]}")
            print(f"Precio Actual: ${record[1]}")
            print(f"Cambio: ${record[2]} ({record[3]}%)")
            print(f"Rango: ${record[4]} - ${record[5]}")
            print(f"Timestamp: {record[6]}")
            print("-"*50)
        
    except sqlite3.Error as e:
        print(f"❌ Error al leer la base de datos: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    test_quotes()
    
    # Mostrar todos los stocks
    view_stock_database_contents()
    
    # O mostrar un stock específico (descomenta la línea siguiente y cambia el símbolo si lo deseas)
    # view_specific_stock_contents('AAPL')