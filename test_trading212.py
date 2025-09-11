#!/usr/bin/env python3
"""
Script simple para probar compra y venta de acciones en Trading212.
Realiza una compra de 10 euros en un instrumento y luego lo vende.
"""
import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
logger = setup_logger()

# Tiempo de espera entre operaciones para respetar límites de tasa
WAIT_TIME_SECONDS = 10

def wait_for_api(message="Esperando antes de la siguiente operación..."):
    """Espera un tiempo fijo entre llamadas a la API para respetar límites de tasa."""
    print(f"{message} ({WAIT_TIME_SECONDS} segundos)")
    time.sleep(WAIT_TIME_SECONDS)

def test_buy_and_sell(ticker, amount=10, quantity=0.1, wait_before_sell=60, simulation=True):
    """
    Realiza una prueba simple de compra y venta de un instrumento.
    
    Args:
        ticker: Ticker del instrumento en formato Trading212 (ej: AAPL_US_EQ)
        amount: Cantidad en euros a invertir (default: 10)
        quantity: Cantidad de acciones a comprar como alternativa (default: 0.1)
        wait_before_sell: Segundos a esperar entre compra y venta (default: 60)
        simulation: Si es True, opera en modo simulación (default: True)
    
    Returns:
        bool: True si la prueba fue exitosa
    """
    from trading212.api import Trading212API
    from trading212 import initialize
    
    print("\n" + "=" * 60)
    print(f"PRUEBA DE COMPRA Y VENTA EN {'SIMULACIÓN' if simulation else 'REAL'}")
    print("=" * 60)
    
    # Inicializar Trading212
    print("\nInicializando Trading212...")
    result = initialize(simulation_mode=simulation)
    
    if not result:
        print("❌ Error al inicializar Trading212")
        return False
    
    print("✅ Trading212 inicializado correctamente")
    
    # Obtener instancias necesarias
    import trading212
    api_client = trading212._api_client
    order_manager = trading212._order_manager
    
    # 1. Verificar efectivo disponible
    wait_for_api("Verificando efectivo disponible")
    try:
        cash_info = api_client.get_account_cash()
        if not cash_info:
            print("❌ No se pudo obtener información de efectivo")
            return False
        
        free_cash = cash_info.get('free', 0)
        print(f"✅ Efectivo disponible: {free_cash}")
        
        if free_cash < amount:
            print(f"❌ No hay suficiente efectivo para comprar {amount} euros")
            return False
    except Exception as e:
        print(f"❌ Error al verificar efectivo: {e}")
        return False
    
    # 2. Verificar si el instrumento existe
    wait_for_api("Verificando instrumento")
    try:
        instruments = api_client.get_instruments()
        instrument_found = False
        
        for instrument in instruments:
            if instrument.get('ticker') == ticker:
                instrument_found = True
                print(f"✅ Instrumento encontrado: {instrument.get('name')} ({ticker})")
                break
        
        if not instrument_found:
            print(f"❌ No se encontró el instrumento {ticker}")
            return False
    except Exception as e:
        print(f"❌ Error al verificar instrumento: {e}")
        return False
    
    # 3. Extraer el símbolo base del ticker para usarlo después
    symbol_base = ticker.split('_')[0] if '_' in ticker else ticker
    
    # 4. Ejecutar compra
    wait_for_api("Preparando operación de compra")
    print(f"\n--- EJECUTANDO COMPRA DE {ticker} POR {quantity} unidades ---")
    
    # Probar distintas estrategias de compra
    buy_success = False
    
    # Estrategia 1: place_market_order con cantidad
    try:
        print("Intentando compra con place_market_order y cantidad...")
        result = api_client.place_market_order(ticker=ticker, quantity=quantity)
        order_result = self.api.place_market_order(ticker=trading212_ticker, quantity=quantity)
        
        if result:
            print(f"✅ Orden de compra ejecutada: {result}")
            buy_success = True
        else:
            print("⚠️ No se recibió confirmación de la orden")
    except Exception as e:
        print(f"⚠️ Error en estrategia 1: {e}")
    
    # Si la estrategia 1 falló, intentar con el OrderManager
    if not buy_success:
        try:
            print("\nObteniendo datos de precio actuales...")
            # Importar yfinance para obtener datos reales
            import yfinance as yf
            
            # Usar el símbolo base para yfinance
            ticker_data = yf.Ticker(symbol_base)
            current_data = ticker_data.history(period="1d", interval="1m")
            
            if not current_data.empty:
                print(f"✅ Datos obtenidos para {symbol_base}")
                
                # Intentar colocar una orden directamente usando el OrderManager
                print("\nIntentando compra con OrderManager...")
                success = order_manager.execute_entry(symbol_base, current_data)
                
                if success:
                    print(f"✅ Orden colocada usando OrderManager")
                    buy_success = True
                else:
                    print(f"⚠️ OrderManager no pudo ejecutar la orden")
            else:
                print(f"⚠️ No se pudieron obtener datos para {symbol_base}")
        except Exception as e:
            print(f"⚠️ Error en estrategia 2: {e}")
            import traceback
            traceback.print_exc()
    
    # Si ninguna estrategia funcionó, salir
    if not buy_success:
        print("❌ Todas las estrategias de compra fallaron")
        return False
    
    # 5. Esperar a que se confirme la compra
    wait_for_api("Esperando confirmación de la compra")
    
    try:
        portfolio = api_client.get_portfolio()
        position_found = False
        position_ticker = None
        
        # Buscar tanto por ticker completo como por símbolo base
        potential_tickers = [ticker, symbol_base]
        
        for position in portfolio:
            pos_ticker = position.get('ticker')
            if pos_ticker in potential_tickers or ticker in pos_ticker:
                position_found = True
                position_ticker = pos_ticker
                position_quantity = position.get('quantity', 0)
                avg_price = position.get('averagePrice', 0)
                print(f"✅ Posición confirmada: {position_quantity} unidades de {position_ticker} a {avg_price} por unidad")
                break
        
        if not position_found:
            print("⚠️ No se encontró la posición en el portafolio. Puede estar pendiente.")
            print("Portafolio actual:")
            for pos in portfolio:
                print(f"  - {pos.get('ticker')}: {pos.get('quantity')} unidades")
    except Exception as e:
        print(f"⚠️ Error al verificar portafolio: {e}")
    
    # 6. Esperar antes de vender
    print(f"\nEsperando {wait_before_sell} segundos antes de vender...")
    time.sleep(wait_before_sell)
    
    # 7. Ejecutar venta
    wait_for_api("Preparando operación de venta")
    
    # Si no encontramos la posición antes, intentar de nuevo
    if not position_found:
        try:
            portfolio = api_client.get_portfolio()
            for position in portfolio:
                pos_ticker = position.get('ticker')
                if pos_ticker in potential_tickers or ticker in pos_ticker:
                    position_found = True
                    position_ticker = pos_ticker
                    position_quantity = position.get('quantity', 0)
                    print(f"✅ Posición encontrada ahora: {position_quantity} unidades de {position_ticker}")
                    break
        except Exception as e:
            print(f"⚠️ Error al verificar portafolio nuevamente: {e}")
    
    # Si encontramos una posición, venderla
    sell_success = False
    
    if position_found and position_ticker:
        print(f"\n--- EJECUTANDO VENTA DE {position_ticker} ---")
        
        # Estrategia 1: Venta directa con place_market_order
        try:
            print("Intentando venta con place_market_order...")
            # Obtener la cantidad que podemos vender
            portfolio = api_client.get_portfolio()
            for position in portfolio:
                if position.get('ticker') == position_ticker:
                    sell_quantity = position.get('quantity', 0)
                    
                    if sell_quantity > 0:
                        print(f"Vendiendo {sell_quantity} unidades de {position_ticker}")
                        result = api_client.place_market_order(ticker=position_ticker, quantity=sell_quantity)
                        
                        if result:
                            print(f"✅ Orden de venta ejecutada: {result}")
                            sell_success = True
                        else:
                            print("⚠️ No se recibió confirmación de la venta")
                    else:
                        print(f"⚠️ Cantidad a vender es 0 o negativa: {sell_quantity}")
                    break
        except Exception as e:
            print(f"⚠️ Error en venta directa: {e}")
        
        # Si la estrategia 1 falló, intentar con el OrderManager
        if not sell_success:
            try:
                print("\nObteniendo datos de precio actuales para venta...")
                # Importar yfinance para obtener datos reales
                import yfinance as yf
                
                # Determinar el símbolo a usar con yfinance
                from trading212.config import REVERSE_TICKER_MAPPING
                sell_symbol = REVERSE_TICKER_MAPPING.get(position_ticker, symbol_base)
                
                # Obtener datos actuales
                ticker_data = yf.Ticker(sell_symbol)
                current_data = ticker_data.history(period="1d", interval="1m")
                
                if not current_data.empty:
                    print(f"✅ Datos obtenidos para {sell_symbol}")
                    
                    # Intentar vender usando el OrderManager
                    print("\nIntentando venta con OrderManager...")
                    success = order_manager.execute_exit(sell_symbol, current_data, reason="TEST")
                    
                    if success:
                        print(f"✅ Venta ejecutada con OrderManager")
                        sell_success = True
                    else:
                        print(f"⚠️ OrderManager no pudo ejecutar la venta")
                else:
                    print(f"⚠️ No se pudieron obtener datos para {sell_symbol}")
            except Exception as e:
                print(f"⚠️ Error en venta con OrderManager: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("❌ No se pudo encontrar una posición para vender")
    
    # 8. Verificar que la posición se cerró
    wait_for_api("Verificando cierre de posición")
    
    try:
        portfolio = api_client.get_portfolio()
        position_closed = True
        
        for position in portfolio:
            pos_ticker = position.get('ticker')
            if pos_ticker == position_ticker:
                position_closed = False
                break
        
        if position_closed:
            print("✅ Posición cerrada correctamente")
        else:
            print("⚠️ La posición aún aparece en el portafolio. Puede estar en proceso de cierre.")
    except Exception as e:
        print(f"⚠️ Error al verificar cierre: {e}")
    
    # 9. Mostrar resumen
    wait_for_api("Consultando resumen de operaciones")
    
    try:
        # Mostrar resumen del order_manager si tiene una función para ello
        if hasattr(order_manager, 'get_order_history_summary'):
            summary = order_manager.get_order_history_summary()
            print("\n----- RESUMEN DE OPERACIONES -----")
            print(summary)
        else:
            print("\n----- RESUMEN DE OPERACIONES -----")
            print("No se pudo obtener un resumen detallado")
    except Exception as e:
        print(f"⚠️ Error al obtener resumen: {e}")
    
    print("\n" + "=" * 60)
    print("PRUEBA COMPLETADA")
    print("=" * 60)
    return True

def main():
    parser = argparse.ArgumentParser(description='Prueba simple de compra y venta en Trading212')
    
    parser.add_argument('--ticker', type=str, default='AAPL_US_EQ', help='Ticker a usar (formato Trading212)')
    parser.add_argument('--amount', type=float, default=10, help='Cantidad en euros a invertir (default: 10)')
    parser.add_argument('--quantity', type=float, default=0.1, help='Cantidad de acciones a comprar (default: 0.1)')
    parser.add_argument('--wait', type=int, default=60, help='Tiempo en segundos entre compra y venta (default: 60)')
    parser.add_argument('--real', action='store_true', help='Usar modo real, no simulación')
    parser.add_argument('--rate-limit', type=int, default=10, help='Tiempo mínimo entre operaciones (default: 10 segundos)')
    
    args = parser.parse_args()
    
    # Actualizar tiempo de espera global
    global WAIT_TIME_SECONDS
    WAIT_TIME_SECONDS = args.rate_limit
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Ejecutar prueba
    test_buy_and_sell(
        ticker=args.ticker,
        amount=args.amount,
        quantity=args.quantity,
        wait_before_sell=args.wait,
        simulation=not args.real
    )

if __name__ == "__main__":
    main()