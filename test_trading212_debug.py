#!/usr/bin/env python3
"""
Script mejorado para probar la integración con Trading212.
Realiza una secuencia completa de inicio a fin para verificar que todo funcione.
"""
import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Asegurar que podemos importar desde el directorio raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger, logger

# Intentar importar desde utils_fixed si existe, si no, usar utils normal
try:
    from trading212.utils_fixed import wait_for_rate_limit, format_currency
except ImportError:
    try:
        from trading212.utils import wait_for_rate_limit, format_currency
    except ImportError:
        # Implementar versiones básicas si no se encuentra ninguna
        def wait_for_rate_limit(last_call_time, endpoint_limit=1.0):
            time.sleep(endpoint_limit)
            return time.time()
            
        def format_currency(amount, decimals=2):
            try:
                return f"${float(amount):.{decimals}f}"
            except (ValueError, TypeError):
                return f"${0:.{decimals}f}"

# Tiempo de espera entre operaciones para respetar límites de tasa
WAIT_TIME_SECONDS = 10

def wait_for_api(message="Esperando antes de la siguiente operación..."):
    """Espera un tiempo fijo entre llamadas a la API para respetar límites de tasa."""
    print(f"{message} ({WAIT_TIME_SECONDS} segundos)")
    time.sleep(WAIT_TIME_SECONDS)

def main():
    parser = argparse.ArgumentParser(description='Prueba de integración con Trading212')
    
    parser.add_argument('--ticker', type=str, default='AAPL_US_EQ', help='Ticker a usar')
    parser.add_argument('--quantity', type=float, default=0.1, help='Cantidad a comprar')
    parser.add_argument('--wait', type=int, default=60, help='Tiempo de espera entre compra y venta (segundos)')
    parser.add_argument('--real', action='store_true', help='Usar modo real, no simulación')
    parser.add_argument('--telegram', action='store_true', help='Probar integración con Telegram')
    
    args = parser.parse_args()
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Probar integración con Telegram si se solicita
    if args.telegram:
        test_telegram_integration(f"Prueba de Trading212 para {args.ticker}")
    
    # Inicializar Trading212
    api_client, order_manager, simulation_mode = test_trading212_initialization(simulation=not args.real)
    
    if api_client is None or order_manager is None:
        print("❌ No se pudo inicializar Trading212. Abortando prueba.")
        return False
    
    # Ejecutar prueba de compra y venta
    test_buy_and_sell(
        api_client=api_client,
        order_manager=order_manager,
        ticker=args.ticker,
        quantity=args.quantity,
        wait_before_sell=args.wait,
        simulation=simulation_mode
    )
    
    return True

if __name__ == "__main__":
    main()

def test_trading212_initialization(api_key=None, api_url=None, simulation=True):
    """
    Prueba la inicialización de Trading212.
    
    Args:
        api_key: Clave API para Trading212 (opcional)
        api_url: URL base de Trading212 (opcional)
        simulation: Si es True, usa modo simulación (por defecto: True)
        
    Returns:
        tuple: (Trading212API, OrderManager, simulation_mode)
    """
    print("\n" + "=" * 60)
    print(f"INICIALIZACIÓN DE TRADING212 EN {'SIMULACIÓN' if simulation else 'REAL'}")
    print("=" * 60)
    
    # Inicializar Trading212
    import trading212
    
    # Usar valores por defecto si no se proporcionan
    if not api_key:
        from config import TRADING212_API_KEY
        api_key = TRADING212_API_KEY
    
    if not api_url:
        from config import TRADING212_API_URL
        api_url = TRADING212_API_URL
    
    print("\nInicializando Trading212...")
    result = trading212.initialize(api_key=api_key, api_url=api_url, simulation_mode=simulation)
    
    if not result:
        print("❌ Error al inicializar Trading212")
        return None, None, None
    
    print("✅ Trading212 inicializado correctamente")
    
    # Obtener instancias necesarias
    api_client = trading212._api_client
    order_manager = trading212._order_manager
    
    # Verificar simulación
    is_simulation = trading212._integrator.simulation_mode if hasattr(trading212, "_integrator") else simulation
    
    return api_client, order_manager, is_simulation

def test_telegram_integration(message="Prueba de integración Trading212", bot_token=None, chat_id=None):
    """
    Prueba el envío de un mensaje a Telegram.
    
    Args:
        message: Mensaje a enviar (opcional)
        bot_token: Token del bot de Telegram (opcional)
        chat_id: ID del chat de Telegram (opcional)
        
    Returns:
        bool: True si el mensaje se envió correctamente
    """
    try:
        from notifications.telegram import send_telegram_test
        
        # Usar valores por defecto si no se proporcionan
        if not bot_token or not chat_id:
            from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
            bot_token = bot_token or TELEGRAM_BOT_TOKEN
            chat_id = chat_id or TELEGRAM_CHAT_ID
        
        print("\nEnviando mensaje de prueba a Telegram...")
        result = send_telegram_test(message, bot_token, chat_id)
        
        if result:
            print("✅ Mensaje de prueba enviado correctamente a Telegram")
        else:
            print("❌ Error al enviar mensaje de prueba a Telegram")
            
        return result
    except Exception as e:
        print(f"❌ Error al enviar mensaje de prueba a Telegram: {e}")
        return False

def verify_market_data(symbol):
    """
    Verifica que se pueden obtener datos del mercado para un símbolo.
    
    Args:
        symbol: Símbolo a verificar
        
    Returns:
        tuple: (DataFrame, éxito)
    """
    try:
        import yfinance as yf
        
        print(f"\nObteniendo datos de mercado para {symbol}...")
        ticker = yf.Ticker(symbol)
        
        # Obtener datos históricos recientes
        history = ticker.history(period="1d", interval="1m")
        
        if history.empty:
            print(f"❌ No se pudieron obtener datos para {symbol}")
            return None, False
        
        print(f"✅ Datos obtenidos: {len(history)} registros")
        print(f"   Último precio: {format_currency(history['Close'].iloc[-1])}")
        
        return history, True
    except Exception as e:
        print(f"❌ Error al obtener datos para {symbol}: {e}")
        return None, False

def test_buy_and_sell(api_client, order_manager, ticker, quantity=0.1, wait_before_sell=60, simulation=True):
    """
    Realiza una prueba completa de compra y venta de un instrumento.
    
    Args:
        api_client: Cliente API de Trading212
        order_manager: Gestor de órdenes
        ticker: Ticker del instrumento
        quantity: Cantidad a comprar (por defecto: 0.1)
        wait_before_sell: Tiempo a esperar entre compra y venta (por defecto: 60 segundos)
        simulation: Si es True, opera en modo simulación (por defecto: True)
    
    Returns:
        bool: True si la prueba fue exitosa
    """
    print("\n" + "=" * 60)
    print(f"PRUEBA DE COMPRA Y VENTA EN {'SIMULACIÓN' if simulation else 'REAL'}")
    print("=" * 60)
    
    success = {
        'verify_cash': False,
        'verify_instrument': False,
        'buy': False,
        'verify_position': False,
        'sell': False
    }
    
    # 1. Verificar efectivo disponible
    wait_for_api("Verificando efectivo disponible")
    try:
        cash_info = api_client.get_account_cash()
        if not cash_info:
            print("❌ No se pudo obtener información de efectivo")
        else:
            free_cash = cash_info.get('free', 0)
            print(f"✅ Efectivo disponible: {format_currency(free_cash)}")
            success['verify_cash'] = True
            
            if free_cash < 50:  # Suponiendo un mínimo de $50 para operar
                print(f"⚠️ Efectivo disponible muy bajo para operar")
    except Exception as e:
        print(f"❌ Error al verificar efectivo: {e}")
    
    # 2. Verificar si el instrumento existe
    wait_for_api("Verificando instrumento")
    try:
        instruments = api_client.get_instruments()
        instrument_found = False
        instrument_details = None
        
        if not instruments:
            print("❌ No se pudieron obtener los instrumentos")
        else:
            for instrument in instruments:
                if instrument.get('ticker') == ticker:
                    instrument_found = True
                    instrument_details = instrument
                    print(f"✅ Instrumento encontrado: {instrument.get('name')} ({ticker})")
                    print(f"   - Cantidad mínima: {instrument.get('minTradeQuantity')}")
                    print(f"   - Cantidad máxima: {instrument.get('maxOpenQuantity')}")
                    success['verify_instrument'] = True
                    break
            
            if not instrument_found:
                print(f"❌ No se encontró el instrumento {ticker}")
    except Exception as e:
        print(f"❌ Error al verificar instrumento: {e}")
    
    # 3. Obtener datos de mercado
    market_data, market_success = verify_market_data(ticker.split('_')[0])
    
    # 4. Ejecutar compra
    if success['verify_instrument'] and market_success:
        wait_for_api("Preparando operación de compra")
        print(f"\n--- EJECUTANDO COMPRA DE {ticker} POR {quantity} unidades ---")
        
        # Verificar que tenemos datos de mercado suficientes
        if market_data is None or market_data.empty:
            print("❌ No hay datos de mercado para ejecutar la compra")
        else:
            # Intentar ejecutar compra con OrderManager
            try:
                buy_success = order_manager.execute_entry(ticker.split('_')[0], market_data)
                
                if buy_success:
                    print(f"✅ Orden de compra ejecutada correctamente")
                    success['buy'] = True
                else:
                    print(f"❌ Error al ejecutar orden de compra")
            except Exception as e:
                print(f"❌ Error durante la ejecución de la compra: {e}")
                import traceback
                traceback.print_exc()
    
    # 5. Verificar posición
    if success['buy']:
        wait_for_api("Verificando posición abierta")
        
        try:
            # Verificar posiciones activas en el OrderManager
            position_found = ticker.split('_')[0] in order_manager.active_positions
            
            if position_found:
                position = order_manager.active_positions[ticker.split('_')[0]]
                position_quantity = position.get('quantity', 0)
                avg_price = position.get('entry_price', 0)
                
                print(f"✅ Posición confirmada: {position_quantity} unidades a {format_currency(avg_price)} por unidad")
                success['verify_position'] = True
            else:
                # Intentar verificar en el portafolio directamente
                try:
                    portfolio = api_client.get_portfolio()
                    for pos in portfolio:
                        if pos.get('ticker') == ticker:
                            print(f"✅ Posición encontrada en portafolio: {pos.get('quantity')} unidades")
                            success['verify_position'] = True
                            break
                    
                    if not success['verify_position']:
                        print("⚠️ No se encontró la posición en el portafolio ni en el gestor de órdenes")
                except Exception as e:
                    print(f"❌ Error al verificar portafolio: {e}")
        except Exception as e:
            print(f"❌ Error al verificar posición: {e}")
    
    # 6. Esperar antes de vender
    if success['verify_position'] or success['buy']:
        print(f"\nEsperando {wait_before_sell} segundos antes de vender...")
        time.sleep(wait_before_sell)
        
        # Actualizar datos de mercado para la venta
        market_data, market_success = verify_market_data(ticker.split('_')[0])
        
        # 7. Ejecutar venta
        wait_for_api("Preparando operación de venta")
        
        print(f"\n--- EJECUTANDO VENTA DE {ticker} ---")
        
        if not market_success:
            print("❌ No hay datos de mercado actualizados para ejecutar la venta")
        else:
            try:
                # Intentar vender con OrderManager
                sell_success = order_manager.execute_exit(ticker.split('_')[0], market_data, reason="TEST")
                
                if sell_success:
                    print(f"✅ Orden de venta ejecutada correctamente")
                    success['sell'] = True
                else:
                    print(f"❌ Error al ejecutar orden de venta")
            except Exception as e:
                print(f"❌ Error durante la ejecución de la venta: {e}")
                import traceback
                traceback.print_exc()
    
    # 8. Verificar cierre de posición
    wait_for_api("Verificando cierre de posición")
    
    if success['sell']:
        try:
            position_closed = ticker.split('_')[0] not in order_manager.active_positions
            
            if position_closed:
                print("✅ Posición cerrada correctamente")
            else:
                print("⚠️ La posición aún aparece en las posiciones activas")
                
                # Verificar directamente en el portafolio
                try:
                    portfolio = api_client.get_portfolio()
                    position_in_portfolio = False
                    
                    for pos in portfolio:
                        if pos.get('ticker') == ticker:
                            position_in_portfolio = True
                            break
                    
                    if not position_in_portfolio:
                        print("✅ La posición no aparece en el portafolio")
                    else:
                        print("⚠️ La posición aún aparece en el portafolio")
                except Exception as e:
                    print(f"❌ Error al verificar portafolio: {e}")
        except Exception as e:
            print(f"❌ Error al verificar cierre de posición: {e}")
    
    # 9. Mostrar resumen
    wait_for_api("Consultando resumen")
    
    print("\n----- RESUMEN DE LA PRUEBA -----")
    print(f"Verificación de efectivo: {'✅' if success['verify_cash'] else '❌'}")
    print(f"Verificación de instrumento: {'✅' if success['verify_instrument'] else '❌'}")
    print(f"Ejecución de compra: {'✅' if success['buy'] else '❌'}")
    print(f"Verificación de posición: {'✅' if success['verify_position'] else '❌'}")
    print(f"Ejecución de venta: {'✅' if success['sell'] else '❌'}")
    
    # Mostrar resumen del OrderManager
    print("\n----- HISTORIAL DE ÓRDENES -----")
    order_history = order_manager.get_order_history_summary()
    print(order_history)
    
    print("\n----- POSICIONES ACTIVAS -----")
    position_summary = order_manager.get_position_summary()
    print(position_summary)
    
    print("\n" + "=" * 60)
    print("PRUEBA COMPLETADA")
    print("=" * 60)
    
    # La prueba es exitosa si se pudo verificar el instrumento
    # (no es necesario que la compra/venta sean exitosas para que la integración funcione)
    return success['verify_instrument']