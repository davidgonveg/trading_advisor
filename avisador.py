import time
import logging
import requests
import datetime
import pytz
import pandas as pd
import numpy as np
import threading
import codecs
import re

import sqlite3
from sqlite3 import Error

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Finnhub API configuration
FINNHUB_API_KEY = "YOUR_FINNHUB_API_KEY"  # Replace with your actual Finnhub API key


def get_last_data_from_db(connection, symbol, limit=200):
    """
    Gets the latest historical data for a symbol from the database.
    
    Args:
        connection: Database connection
        symbol: Stock symbol
        limit: Maximum number of records to retrieve
        
    Returns:
        DataFrame with historical data or None
    """
    try:
        if not connection:
            return None
            
        cursor = connection.cursor()
        
        # Get data ordered by date in descending order
        cursor.execute(f'''
        SELECT fecha_hora, precio_open, precio_high, precio_low, precio_close, 
               volumen, bb_inferior, bb_media, bb_superior, macd, macd_signal, rsi, rsi_k
        FROM datos_historicos 
        WHERE simbolo = ?
        ORDER BY fecha_hora DESC
        LIMIT {limit}
        ''', (symbol,))
        
        records = cursor.fetchall()
        
        if not records:
            logger.info(f"No historical data for {symbol} in the database")
            return None
            
        # Create DataFrame with the data
        columns = ['fecha_hora', 'Open', 'High', 'Low', 'Close', 'Volume', 
                  'BB_INFERIOR', 'BB_MEDIA', 'BB_SUPERIOR', 'MACD', 'MACD_SIGNAL', 'RSI', 'RSI_K']
        
        df = pd.DataFrame(records, columns=columns)
        
        # Convert fecha_hora column to datetime index
        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        df.set_index('fecha_hora', inplace=True)
        
        # Sort by index in ascending order (oldest first)
        df = df.sort_index()
        
        return df
        
    except Error as e:
        logger.error(f"Error retrieving historical data from DB: {e}")
        return None


# Functions to handle SQLite database
def create_connection(db_path="stock_alerts.db"):
    """
    Creates a connection to the SQLite database.
    
    Args:
        db_path: Path to the database file
        
    Returns:
        Connection to the database or None
    """
    connection = None
    try:
        connection = sqlite3.connect(db_path)
        return connection
    except Error as e:
        logger.error(f"Error connecting to the database: {e}")
        return None

def create_tables(connection):
    """
    Creates necessary tables in the database.
    
    Args:
        connection: Database connection
    """
    try:
        cursor = connection.cursor()
        
        # Table for storing alerts
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simbolo TEXT NOT NULL,
            precio REAL NOT NULL,
            fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tipo_alerta TEXT,
            mensaje TEXT,
            bb_inferior REAL,
            bb_media REAL,
            macd REAL,
            macd_signal REAL,
            rsi_k REAL
        )
        ''')
        
        # Table for storing historical data
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS datos_historicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simbolo TEXT NOT NULL,
            fecha_hora TIMESTAMP,
            precio_open REAL,
            precio_high REAL,
            precio_low REAL,
            precio_close REAL,
            volumen INTEGER,
            bb_inferior REAL,
            bb_media REAL,
            bb_superior REAL,
            macd REAL,
            macd_signal REAL,
            rsi REAL,
            rsi_k REAL
        )
        ''')
        
        connection.commit()
        logger.info("Tables created successfully")
    except Error as e:
        logger.error(f"Error creating tables: {e}")

def save_alert_to_db(connection, symbol, data, index, message, alert_type="sequence"):
    """
    Saves an alert to the database.
    
    Args:
        connection: Database connection
        symbol: Stock symbol
        data: DataFrame with the data
        index: Alert index in the DataFrame
        message: Alert message
        alert_type: Type of alert generated
    """
    try:
        cursor = connection.cursor()
        
        row = data.iloc[index]
        
        # Prepare data for insertion
        alert_data = (
            symbol,
            float(row['Close']),
            str(data.index[index]),
            alert_type,
            message,
            float(row['BB_INFERIOR']) if 'BB_INFERIOR' in row else None,
            float(row['BB_MEDIA']) if 'BB_MEDIA' in row else None,
            float(row['MACD']) if 'MACD' in row else None,
            float(row['MACD_SIGNAL']) if 'MACD_SIGNAL' in row else None,
            float(row['RSI_K']) if 'RSI_K' in row else None
        )
        
        cursor.execute('''
        INSERT INTO alertas 
        (simbolo, precio, fecha_hora, tipo_alerta, mensaje, bb_inferior, bb_media, macd, macd_signal, rsi_k)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', alert_data)
        
        connection.commit()
        logger.info(f"Alert for {symbol} saved to database")
        return True
    except Error as e:
        logger.error(f"Error saving alert to database: {e}")
        return False

def save_historical_data(connection, symbol, data):
    """
    Saves historical data to the database.
    Only saves the last row to avoid overloading the DB.
    
    Args:
        connection: Database connection
        symbol: Stock symbol
        data: DataFrame with the data
    """
    try:
        if data.empty:
            return False
            
        cursor = connection.cursor()
        
        # Only save the last row of data
        last_row = data.iloc[-1]
        
        # Check if a record already exists for this symbol and date
        cursor.execute('''
        SELECT id FROM datos_historicos 
        WHERE simbolo = ? AND fecha_hora = ?
        ''', (symbol, str(data.index[-1])))
        
        exists = cursor.fetchone()
        
        if exists:
            logger.info(f"Data for {symbol} at {data.index[-1]} already exists in DB. Skipping.")
            return False
        
        # Prepare data for insertion
        hist_data = (
            symbol,
            str(data.index[-1]),
            float(last_row['Open']),
            float(last_row['High']),
            float(last_row['Low']),
            float(last_row['Close']),
            int(last_row['Volume']) if 'Volume' in last_row else 0,
            float(last_row['BB_INFERIOR']) if 'BB_INFERIOR' in last_row else None,
            float(last_row['BB_MEDIA']) if 'BB_MEDIA' in last_row else None,
            float(last_row['BB_SUPERIOR']) if 'BB_SUPERIOR' in last_row else None,
            float(last_row['MACD']) if 'MACD' in last_row else None,
            float(last_row['MACD_SIGNAL']) if 'MACD_SIGNAL' in last_row else None,
            float(last_row['RSI']) if 'RSI' in last_row else None,
            float(last_row['RSI_K']) if 'RSI_K' in last_row else None
        )
        
        cursor.execute('''
        INSERT INTO datos_historicos 
        (simbolo, fecha_hora, precio_open, precio_high, precio_low, precio_close, 
         volumen, bb_inferior, bb_media, bb_superior, macd, macd_signal, rsi, rsi_k)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', hist_data)
        
        connection.commit()
        logger.info(f"Historical data for {symbol} saved to database")
        return True
    except Error as e:
        logger.error(f"Error saving historical data to database: {e}")
        return False


# Function to send message via Telegram
def send_telegram_alert(message, bot_token, chat_id):
    """
    Sends an alert message via Telegram with improved error handling.
    
    Args:
        message: Message content
        bot_token: Telegram bot token
        chat_id: Chat ID where to send the message
        
    Returns:
        bool: True if sending was successful, False otherwise
    """
    try:
        # Validate token format (basic format)
        if not bot_token or not bot_token.count(':') == 1:
            print(f"❌ Error: Bot token seems to have an incorrect format: {bot_token}")
            return False
            
        # Validate chat_id (should be a number)
        try:
            # Try to convert to int for validation (but continue using the original)
            int(chat_id)
        except ValueError:
            print(f"❌ Error: Chat ID doesn't seem to be a valid number: {chat_id}")
            return False
        
        # IMPORTANT: Sanitize message to avoid HTML issues
        safe_message = sanitize_html_message(message)
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": safe_message,
            "parse_mode": "HTML"  # Allows basic HTML formatting
        }
        
        print(f"Sending message to Telegram...")
        response = requests.post(url, data=payload, timeout=10)
        response_json = response.json()
        
        if response.status_code == 200 and response_json.get('ok'):
            logger.info(f"Alert sent to Telegram chat {chat_id}")
            return True
        else:
            print(f"❌ Error sending message to Telegram: {response_json}")
            logger.error(f"Error sending message to Telegram: {response_json}")
            
            # If it fails with HTML, try without HTML formatting
            if 'can\'t parse entities' in str(response_json):
                print("Trying to send message without HTML formatting...")
                # Remove all HTML tags
                plain_message = re.sub(r'<[^>]*>', '', message)
                # Replace HTML entities
                plain_message = plain_message.replace('&lt;', '<').replace('&gt;', '>')
                
                payload = {
                    "chat_id": chat_id,
                    "text": plain_message
                }
                
                print("Sending plain text message...")
                response = requests.post(url, data=payload, timeout=10)
                response_json = response.json()
                
                if response.status_code == 200 and response_json.get('ok'):
                    logger.info(f"Alert sent to Telegram in plain text")
                    return True
                else:
                    print(f"❌ Error sending plain text message: {response_json}")
            
            # Show help information based on the error code
            if response.status_code == 404:
                print("→ Error 404: Bot not found. Verify that the token is correct.")
            elif response.status_code == 401:
                print("→ Error 401: Unauthorized. The bot token is invalid.")
            elif response.status_code == 400:
                if 'chat not found' in str(response_json):
                    print("→ Error: Chat not found. Make sure the bot and user have exchanged at least one message.")
                elif 'chat_id is empty' in str(response_json):
                    print("→ Error: chat_id is empty or invalid.")
            
            return False
    except Exception as e:
        print(f"❌ Error sending alert via Telegram: {e}")
        logger.error(f"Error sending alert via Telegram: {e}")
        return False

# Function to sanitize HTML messages
def sanitize_html_message(message):
    # This function ensures that all HTML tags are balanced
    # (each <b> has its corresponding </b>, etc.)
    # And that < and > symbols that are not part of HTML tags are escaped
    
    # List of HTML tags allowed by Telegram
    allowed_tags = ['b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del', 'a', 'code', 'pre']
    
    # Replace < with &lt; when not followed by a valid tag
    message = re.sub(r'<(?!(\/?' + r'|\/?'.join(allowed_tags) + r')[>\s])', '&lt;', message)
    
    # Check balance of HTML tags
    for tag in allowed_tags:
        # Count opening and closing tags
        opened = len(re.findall(fr'<{tag}[>\s]', message))
        closed = len(re.findall(f'</{tag}>', message))
        
        # If there are more open tags than closed, add missing closures
        if opened > closed:
            message += f'</{tag}>' * (opened - closed)
        
        # If there are more closed tags than open, remove the excess
        elif closed > opened:
            excess = closed - opened
            for _ in range(excess):
                pos = message.rfind(f'</{tag}>')
                if pos >= 0:
                    message = message[:pos] + message[pos + len(f'</{tag}>'):]
    
    return message

# Function to save alert to file (as backup)
def save_alert_to_file(message, filename="stock_alerts.log"):
    try:
        # Use codecs to open the file with UTF-8 encoding
        with codecs.open(filename, "a", "utf-8") as file:
            file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        return True
    except Exception as e:
        logger.error(f"Error saving alert to file: {e}")
        
        # If it fails, try to save a simplified version without emojis or HTML
        try:
            simple_message = re.sub(r'<[^>]*>', '', message)  # Remove HTML
            simple_message = re.sub(r'[^\x00-\x7F]+', '', simple_message)  # Remove non-ASCII
            
            with open(filename, "a") as file:
                file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - [SIMPLIFIED] {simple_message}\n")
            return True
        except Exception as e2:
            logger.error(f"Also failed to save simplified version: {e2}")
            return False

# Function to check if the market is open
def is_market_open():
    """
    Checks if the US market is currently open or within 45 minutes before opening.
    
    Returns:
        bool: True if the market is open or about to open, False otherwise
    """
    # New York time zone (US market)
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    
    # Check if it's a weekend (0 is Monday, 6 is Sunday)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Regular market hours (9:30 AM - 4:00 PM ET)
    opening_time = datetime.time(9, 30)
    closing_time = datetime.time(16, 0)
    
    # Time to start monitoring (45 minutes before opening)
    pre_market_time = datetime.time(8, 45)  # 9:30 - 0:45 = 8:45 AM
    
    current_time = now.time()
    
    # Check if we're in market hours or in the 45 minutes before
    return pre_market_time <= current_time <= closing_time


def detect_market_type(df):
    """
    Detects the current market type (sideways, bullish, bearish, high/low volatility).
    
    Args:
        df: DataFrame with data and indicators
        
    Returns:
        dict: Dictionary with market type and its characteristics
    """
    if len(df) < 50:  # We need enough data to analyze
        return {"tipo": "undetermined", "descripcion": "Insufficient data"}
    
    # Calculate EMA50 slope (if it already exists in the DataFrame)
    if 'EMA50' not in df.columns:
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # Get data from the last 50 candles
    last_candles = df.iloc[-50:]
    
    # EMA50 slope (trend)
    first_value = last_candles['EMA50'].iloc[0]
    last_value = last_candles['EMA50'].iloc[-1]
    percent_change = ((last_value / first_value) - 1) * 100
    
    # Volatility (Bollinger Bands width)
    bands_width = (last_candles['BB_SUPERIOR'] - last_candles['BB_INFERIOR']) / last_candles['Close'] * 100
    avg_volatility = bands_width.mean()
    
    # Analyze market type
    market_type = {}
    
    # Trend analysis
    if percent_change > 2:
        market_type["tendencia"] = "bullish"
    elif percent_change < -2:
        market_type["tendencia"] = "bearish"
    else:
        market_type["tendencia"] = "sideways"
    
    # Volatility analysis
    if avg_volatility > 5:  # Threshold for high volatility (adjust according to your assets)
        market_type["volatilidad"] = "high"
    elif avg_volatility < 2:  # Threshold for low volatility
        market_type["volatilidad"] = "low"
    else:
        market_type["volatilidad"] = "moderate"
    
    # Combined description
    market_type["descripcion"] = f"{market_type['tendencia']} market with {market_type['volatilidad']} volatility"
    
    return market_type


# Function to get stock data with 5-minute interval using Finnhub
def get_stock_data(symbol, period='1d', interval='5m', db_connection=None, only_new=False):
    """
    Gets recent data for a stock with the specified interval using Finnhub.
    If there is a database connection, tries to get only new data.
    Handles cases of gaps in the data.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        period: Data period ('1d', '5d', etc.)
        interval: Time interval between data points ('5m', '1h', etc.)
        db_connection: Optional database connection
        only_new: If True, tries to get only new data
        
    Returns:
        DataFrame with stock data
    """
    try:
        # If we don't want to use historical data or there's no DB connection
        if not db_connection or not only_new:
            logger.info(f"Getting all data for {symbol} from Finnhub API")
            return get_finnhub_candles(symbol, period, interval)
            
        # Try to get historical data from the DB
        historical_data = get_last_data_from_db(db_connection, symbol)
        
        if historical_data is None or historical_data.empty:
            logger.info(f"No historical data for {symbol}. Getting all from Finnhub API")
            return get_finnhub_candles(symbol, period, interval)
            
        # Get the last recorded date
        last_date = historical_data.index[-1]
        
        # Calculate from when we need new data
        import datetime
        import pytz
        
        # Make sure the date is in UTC time zone
        if last_date.tzinfo is None:
            last_date = pytz.UTC.localize(last_date)
            
        # Calculate the necessary period
        now = datetime.datetime.now(pytz.UTC)
        difference = now - last_date
        
        # If the difference is very small, we don't need new data
        if difference.total_seconds() < 300:  # less than 5 minutes
            logger.info(f"Data already updated for {symbol}. Using only historical data")
            return historical_data
            
        # Check if there's a large gap in data (more than 1 day)
        large_gap = difference.total_seconds() > 86400  # more than 24 hours
        
        # Adjust the period according to the difference
        days_difference = max(1, difference.days + 1)  # Minimum 1 day
        
        # If there's a large gap or we're in a new day, request complete data
        if large_gap or last_date.date() < now.date():
            logger.info(f"Possible gap in data for {symbol}. Getting complete period")
            # Get a longer period to cover the gap
            request_period = period if large_gap else f"{days_difference}d"
            new_data = get_finnhub_candles(symbol, request_period, interval)
            
            # Check for gaps in the obtained data
            if len(new_data) > 0:
                expected_interval = 5  # minutes for '5m' interval
                internal_gaps = False
                
                # Convert to DataFrame if it's not already
                import pandas as pd
                if not isinstance(new_data, pd.DataFrame):
                    new_data = pd.DataFrame(new_data)
                
                # Check for internal gaps only during market hours
                if len(new_data) > 1:
                    indices = new_data.index
                    for i in range(1, len(indices)):
                        # Only check during market hours (ignore overnight closure)
                        prev_hour = indices[i-1].hour
                        curr_hour = indices[i].hour
                        if 9 <= prev_hour <= 16 and 9 <= curr_hour <= 16:
                            minute_difference = (indices[i] - indices[i-1]).total_seconds() / 60
                            if minute_difference > expected_interval * 1.5:  # 50% margin
                                internal_gaps = True
                                logger.warning(f"Internal gap detected in {symbol} data: {indices[i-1]} -> {indices[i]}")
                
                if internal_gaps and large_gap:
                    # Try with an even longer period
                    logger.info(f"Internal gaps detected. Trying with longer period for {symbol}")
                    extended_period = '5d' if period == '1d' else '10d'
                    new_data = get_finnhub_candles(symbol, extended_period, interval)
        else:
            # Get only the new data since the last date
            logger.info(f"Getting new data for {symbol} since {last_date}")
            new_data = get_finnhub_candles(symbol, f"{days_difference}d", interval, from_time=last_date)
        
        # Filter only data after the last date
        if not new_data.empty:
            # Add a small margin to avoid exact duplicates (5 seconds)
            margin = datetime.timedelta(seconds=5)
            new_data = new_data[new_data.index > (last_date - margin)]
        
        if new_data.empty:
            logger.info(f"No new data for {symbol}")
            return historical_data
            
        # Combine historical data with new data
        import pandas as pd
        combined_data = pd.concat([historical_data, new_data])
        
        # Remove possible duplicates
        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
        
        # Sort by date (important for technical analysis)
        combined_data = combined_data.sort_index()
        
        logger.info(f"Combined data for {symbol}: {len(historical_data)} historical + {len(new_data)} new")
        
        # Check data continuity
        if len(combined_data) > 1:
            # Only for same-day data during market hours
            prev_date = None
            gaps_found = 0
            for date in combined_data.index:
                if prev_date is not None:
                    # Only check during market hours (9:30 AM - 4:00 PM ET)
                    hour = date.hour + date.minute/60
                    prev_hour = prev_date.hour + prev_date.minute/60
                    
                    if date.date() == prev_date.date() and 9.5 <= prev_hour <= 16 and 9.5 <= hour <= 16:
                        minute_difference = (date - prev_date).total_seconds() / 60
                        # For 5-minute interval, we expect ~5 minutes between records
                        if minute_difference > 7:  # Allow a 2-minute margin
                            gaps_found += 1
                            if gaps_found <= 3:  # Limit the number of log messages
                                logger.warning(f"Possible gap in {symbol} data: {prev_date} -> {date} ({minute_difference:.1f} min)")
                
                prev_date = date
            
            if gaps_found > 0:
                logger.warning(f"Total of {gaps_found} potential gaps in {symbol} data")
        
        return combined_data
        
    except Exception as e:
        logger.error(f"Error getting data for {symbol}: {e}")
        # If there's an error, try to return only the historical data if it exists
        if db_connection and only_new:
            historical_data = get_last_data_from_db(db_connection, symbol)
            if historical_data is not None and not historical_data.empty:
                logger.info(f"Using only historical data for {symbol} due to error")
                return historical_data
        return None


def get_finnhub_candles(symbol, period='1d', interval='5m', from_time=None):
    """
    Gets candle data from Finnhub API.
    
    Args:
        symbol: Stock symbol
        period: Time period ('1d', '5d', etc.)
        interval: Time interval between candles ('5m', '1h', etc.)
        from_time: Optional start time (datetime object)
        
    Returns:
        DataFrame with OHLCV data
    """
    try:
        # Convert period to seconds
        if period.endswith('d'):
            days = int(period[:-1])
            period_seconds = days * 86400
        elif period.endswith('h'):
            hours = int(period[:-1])
            period_seconds = hours * 3600
        else:
            # Default to 1 day if format is unknown
            period_seconds = 86400
        
        # Convert interval to seconds
        if interval.endswith('m'):
            interval_seconds = int(interval[:-1]) * 60
        elif interval.endswith('h'):
            interval_seconds = int(interval[:-1]) * 3600
        else:
            # Default to 5 minutes if format is unknown
            interval_seconds = 300
        
        # Calculate start and end times
        end_time = int(time.time())
        if from_time:
            # Convert from_time to UNIX timestamp
            start_time = int(from_time.timestamp())
        else:
            start_time = end_time - period_seconds
        
        # Create the Finnhub API URL
        url = "https://finnhub.io/api/v1/stock/candle"
        
        # Map intervals to Finnhub resolution format
        resolution_map = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '1d': 'D',
            '1w': 'W'
        }
        
        resolution = resolution_map.get(interval, '5')  # Default to 5m if not found
        
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'from': start_time,
            'to': end_time,
            'token': FINNHUB_API_KEY
        }
        
        logger.info(f"Requesting data from Finnhub for {symbol} with resolution {resolution}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Error from Finnhub API: {response.status_code} - {response.text}")
            return pd.DataFrame()
        
        data = response.json()
        
        # Check if data is valid
        if data.get('s') == 'no_data' or 'c' not in data:
            logger.warning(f"No data returned from Finnhub for {symbol}")
            return pd.DataFrame()
        
        # Create DataFrame from Finnhub data
        df = pd.DataFrame({
            'Open': data['o'],
            'High': data['h'],
            'Low': data['l'],
            'Close': data['c'],
            'Volume': data['v']
        }, index=pd.to_datetime(data['t'], unit='s'))
        
        # Convert index to datetime and sort
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        return df
        
    except Exception as e:
        logger.error(f"Error in Finnhub candle data request for {symbol}: {e}")
        return pd.DataFrame()


# Function to calculate Bollinger Bands
def calculate_bollinger(df, window=18, deviations=2.25):
    """
    Calculates Bollinger Bands for a DataFrame.
    
    Args:
        df: DataFrame with price data
        window: Period for the moving average
        deviations: Number of standard deviations
        
    Returns:
        DataFrame with columns 'BB_MEDIA', 'BB_SUPERIOR', 'BB_INFERIOR'
    """
    if len(df) < window:
        logger.warning(f"Insufficient data to calculate Bollinger (at least {window} periods needed)")
        return df
    
    # Calculate the moving average
    df['BB_MEDIA'] = df['Close'].rolling(window=window).mean()
    
    # Calculate the standard deviation
    rolling_std = df['Close'].rolling(window=window).std()
    
    # Calculate upper and lower bands
    df['BB_SUPERIOR'] = df['BB_MEDIA'] + (rolling_std * deviations)
    df['BB_INFERIOR'] = df['BB_MEDIA'] - (rolling_std * deviations)
    
    return df

# Function to calculate MACD (manual implementation)
def calculate_macd(df, fast=8, slow=21, signal=9, column='Close'):
    """
    Calculates MACD for a DataFrame.
    
    Args:
        df: DataFrame with price data
        fast: Period for the fast moving average
        slow: Period for the slow moving average
        signal: Period for the signal line
        column: Price column to use
        
    Returns:
        DataFrame with columns 'MACD', 'MACD_SIGNAL' and 'MACD_HIST'
    """
    if len(df) < max(fast, slow, signal):
        logger.warning(f"Insufficient data to calculate MACD")
        return df
    
    # Calculate EMAs (Exponential Moving Averages)
    df['EMA_RAPIDA'] = df[column].ewm(span=fast, adjust=False).mean()
    df['EMA_LENTA'] = df[column].ewm(span=slow, adjust=False).mean()
    
    # Calculate MACD line
    df['MACD'] = df['EMA_RAPIDA'] - df['EMA_LENTA']
    
    # Calculate signal line (EMA of MACD)
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    
    # Calculate histogram
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']
    
    return df

# Function to calculate RSI
def calculate_rsi(df, period=14, column='Close'):
    """
    Calculates the RSI (Relative Strength Index) for a DataFrame.
    
    Args:
        df: DataFrame with price data
        period: Period for RSI calculation
        column: Price column to use
        
    Returns:
        Series with RSI values
    """
    delta = df[column].diff()
    
    # Separate gains (up) and losses (down)
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    down = down.abs()
    
    # Calculate the exponential moving average of ups and downs
    avg_up = up.ewm(com=period-1, adjust=False).mean()
    avg_down = down.ewm(com=period-1, adjust=False).mean()
    
    # Calculate RS and RSI
    rs = avg_up / avg_down
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

# Function to calculate Stochastic RSI
def calculate_stochastic_rsi(df, rsi_period=14, k_period=14, d_period=3, smooth=3, column='Close'):
    """
    Calculates the Stochastic RSI for a DataFrame.
    
    Args:
        df: DataFrame with price data
        rsi_period: Period for RSI
        k_period: Period for %K
        d_period: Period for %D
        smooth: Smoothing for %K
        column: Price column to use
        
    Returns:
        DataFrame with columns 'RSI', 'RSI_K' and 'RSI_D'
    """
    if len(df) < max(rsi_period, k_period, d_period, smooth):
        logger.warning(f"Insufficient data to calculate Stochastic RSI")
        return df
    
    # Calculate RSI
    df['RSI'] = calculate_rsi(df, period=rsi_period, column=column)
    
    # Calculate Stochastic RSI
    # Use RSI min and max instead of prices
    df['RSI_MIN'] = df['RSI'].rolling(window=k_period).min()
    df['RSI_MAX'] = df['RSI'].rolling(window=k_period).max()
    
    # Calculate %K (equivalent to stochastic but applied to RSI)
    # Avoid division by zero
    denominator = df['RSI_MAX'] - df['RSI_MIN']
    denominator = denominator.replace(0, np.nan)  # Replace zeros with NaN
    
    df['RSI_K_RAW'] = 100 * ((df['RSI'] - df['RSI_MIN']) / denominator)
    df['RSI_K_RAW'] = df['RSI_K_RAW'].fillna(0)  # Replace NaN with 0
    
    # Apply smoothing to %K
    df['RSI_K'] = df['RSI_K_RAW'].rolling(window=smooth).mean()
    
    # Calculate %D (moving average of %K)
    df['RSI_D'] = df['RSI_K'].rolling(window=d_period).mean()
    
    return df

# Function to detect Bollinger Band breakout
def detect_bollinger_breakout(df):
    """
    Detects when the lower Bollinger Band is broken in the last 15 minutes (3 periods of 5 min).
    
    Args:
        df: DataFrame with calculated indicators
        
    Returns:
        (bool, int): Tuple with (breakout_detected, breakout_index)
    """
    if df.empty or len(df) < 5:  # We need at least some periods
        return False, None
    
    # Check the last 3 periods (15 minutes in 5 min intervals)
    periods_to_check = min(3, len(df) - 1)
    
    for i in range(1, periods_to_check + 1):
        index = -i  # Starting from the last and going backwards
        
        # Check if price is below the lower band
        if not pd.isna(df['Close'].iloc[index]) and not pd.isna(df['BB_INFERIOR'].iloc[index]):
            if df['Close'].iloc[index] < df['BB_INFERIOR'].iloc[index]:
                # If in the previous period it wasn't broken, then it's a new breakout
                if index > -len(df) and df['Close'].iloc[index-1] >= df['BB_INFERIOR'].iloc[index-1]:
                    return True, index
    
    return False, None

# Function to verify MACD and RSI conditions
def verify_additional_conditions(df, index):
    """
    Verifies if MACD and Stochastic RSI conditions are met.
    Optimized to alert BEFORE MACD crosses upward.
    
    Args:
        df: DataFrame with calculated indicators
        index: Index to verify (-1 for the last row)
        
    Returns:
        (bool, str): Tuple with (conditions_met, detail_message)
    """
    if df.empty or abs(index) > len(df):
        return False, "Insufficient data to analyze"
    
    # Get the data row at the specified index
    row = df.iloc[index]
    previous_row = df.iloc[index-1] if abs(index) < len(df) else None
    
    # Check if there are NaN values in the indicators we need
    required_indicators = ['MACD', 'MACD_SIGNAL', 'RSI_K', 'MACD_HIST']
    if any(pd.isna(row[ind]) for ind in required_indicators):
        return False, "Incomplete data for analysis"
    
    # =========== OPTIMIZED CONDITIONS ===========
    
    # Condition 1: Stochastic RSI below 20
    rsi_condition = row['RSI_K'] < 20
    
    # Condition 2: MACD below Signal but closing the distance
    # Check if MACD is approaching the signal line
    if previous_row is not None and not pd.isna(previous_row['MACD']) and not pd.isna(previous_row['MACD_SIGNAL']):
        # Calculate current and previous distance between MACD and Signal
        current_distance = row['MACD_SIGNAL'] - row['MACD']
        previous_distance = previous_row['MACD_SIGNAL'] - previous_row['MACD']
        
        # MACD is below signal but approaching (distance is decreasing)
        macd_approaching_condition = (row['MACD'] < row['MACD_SIGNAL'] and 
                                     current_distance < previous_distance and
                                     current_distance > 0)
        
        # Additionally, verify positive MACD slope
        macd_slope_condition = row['MACD'] > previous_row['MACD']
        
        # Histogram must be increasing (becoming less negative)
        histogram_condition = row['MACD_HIST'] > previous_row['MACD_HIST']
        
        # Combine MACD conditions
        macd_condition = macd_approaching_condition and macd_slope_condition and histogram_condition
    else:
        macd_condition = False
    
    # Condition 3: Calculate distance to crossing (prediction)
    prediction_message = ""
    if macd_condition:
        # Estimate how many candles are left until crossing based on current speed
        if current_distance > 0 and previous_distance > current_distance and previous_distance != current_distance:
            closing_speed = previous_distance - current_distance
            estimated_candles_to_cross = current_distance / closing_speed if closing_speed > 0 else float('inf')
            
            if estimated_candles_to_cross < 5:  # If we estimate less than 5 candles to crossing
                prediction_message = f"⚠️ IMMINENT CROSSING - Approx. {estimated_candles_to_cross:.1f} candles until MACD cross"
    
    # Message with details
    detail_messages = []
    detail_messages.append(f"Price ({row['Close']:.2f}) below lower Bollinger Band ({row['BB_INFERIOR']:.2f})")
    
    if rsi_condition:
        detail_messages.append(f"Stochastic RSI ({row['RSI_K']:.2f}) below 20")
    
    if macd_condition:
        detail_messages.append(f"MACD ({row['MACD']:.4f}) approaching Signal ({row['MACD_SIGNAL']:.4f})")
        if prediction_message:
            detail_messages.append(prediction_message)
    
    # Check if all necessary conditions are met
    conditions_met = rsi_condition and macd_condition
    
    return conditions_met, ", ".join(detail_messages)

# Function to analyze a stock
def analyze_stock(symbol):
    """
    Analyzes a stock to verify if it meets the optimized technical conditions.
    
    Args:
        symbol: Stock symbol to analyze
        
    Returns:
        (bool, str): Tuple with (alert_generated, alert_message)
    """
    try:
        # Get data with 5-minute interval for the last day
        data = get_stock_data(symbol, period='1d', interval='5m')
        
        if data is None or data.empty or len(data) < 30:
            logger.warning(f"Insufficient data to analyze {symbol}")
            return False, f"Insufficient data for {symbol}"
        
        # Calculate indicators
        data = calculate_bollinger(data, window=18, deviations=2.25)
        data = calculate_macd(data, fast=8, slow=21, signal=9)
        data = calculate_stochastic_rsi(data, rsi_period=14, k_period=14, d_period=3, smooth=3)
        
        # Step 1: Detect Bollinger Band breakout in the last 15 minutes
        breakout_detected, breakout_index = detect_bollinger_breakout(data)
        
        if breakout_detected:
            logger.info(f"Bollinger breakout detected for {symbol} in period {breakout_index}")
            
            # Step 2: Verify MACD and RSI in the same period as the breakout
            additional_conditions, _ = verify_additional_conditions(data, breakout_index)
            
            if additional_conditions:
                # If all conditions are met, generate alert with improved message
                message = generate_alert_message(symbol, data, breakout_index)
                return True, message
            else:
                logger.info(f"Bollinger breakout detected for {symbol}, but other conditions are not met")
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return False, f"Error analyzing {symbol}: {str(e)}"

# Record of sent alerts (to avoid duplicates)
sent_alerts = {}

def update_stock_list():
    """
    Returns the updated list of stocks to monitor.
    """
    return [
        # Original tech stocks
        'NVDA',  # NVIDIA
        'TSLA',  # Tesla
        'META',  # Meta (Facebook)
        'AAPL',  # Apple
        'MSFT',  # Microsoft
        'GOOGL', # Google
        'AMZN',  # Amazon
        'ASTS',  # AST SpaceMobile
        'PLTR',  # Palantir
        'AMD',   # AMD
        'SMCI',  # Super Micro Computer
        
        # Financial (new)
        'JPM',   # JPMorgan Chase
        'GS',    # Goldman Sachs
        'V',     # Visa
        
        # Consumer (new)
        'WMT',   # Walmart
        'NKE',   # Nike
        'SBUX',  # Starbucks
        
        # Health (new)
        'PFE',   # Pfizer
        'UNH',   # UnitedHealth
        'LLY',   # Eli Lilly
        
        # Energy (new)
        'CVX',   # Chevron
        'ENPH',  # Enphase Energy
        'XOM',   # Exxon Mobil
        
        # Industrial (new)
        'CAT',   # Caterpillar
        'DE',    # Deere & Company
        'LMT',   # Lockheed Martin
    ]

# Function to check all stocks and send alerts
def check_stocks(bot_token, chat_id, db_connection=None):
    """
    Checks all stocks in the updated list and sends alerts if conditions are met.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        db_connection: Database connection (optional)
    """
    # Check if the market is open
    if not is_market_open():
        logger.info("Market closed. No checks will be performed.")
        return
    
    logger.info("Checking stocks...")
    
    # Get updated list of stocks
    stocks = update_stock_list()
    
    for symbol in stocks:
        try:
            logger.info(f"Analyzing {symbol}...")
            meets_conditions, message = analyze_stock_flexible(symbol, db_connection)
            
            if meets_conditions:
                # Check if we already sent an alert for this symbol in the last hour
                current_time = time.time()
                if symbol in sent_alerts:
                    last_alert = sent_alerts[symbol]
                    # Avoid sending more than one alert for the same symbol in 60 minutes
                    if current_time - last_alert < 3600:
                        logger.info(f"Alert for {symbol} already sent in the last hour. Skipping.")
                        continue
                
                # Send alert via Telegram
                logger.info(f"Conditions met for {symbol}, sending alert")
                send_telegram_alert(message, bot_token, chat_id)
                
                # Record the sending time of this alert
                sent_alerts[symbol] = current_time
                
                # As backup, save to file
                save_alert_to_file(message)
                
                # Wait 2 seconds between each send to avoid overloading the Telegram API
                time.sleep(2)
            else:
                logger.info(f"Conditions not met for {symbol}")
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")


# Function to run checks continuously
def run_continuous_checks(bot_token, chat_id, interval_minutes=20, db_path="stock_alerts.db"):
    """
    Runs checks continuously in a separate thread.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        interval_minutes: Interval between checks in minutes
        db_path: Path to the database file
    """
    # Create database connection
    connection = create_connection(db_path)
    if connection:
        # Create tables if they don't exist
        create_tables(connection)
        logger.info(f"Database initialized: {db_path}")
    else:
        logger.warning("Could not create database connection. Continuing without DB.")
    
    # Integrity check control (once a day)
    last_integrity_check = 0
    integrity_check_interval = 86400  # 24 hours in seconds
    
    while True:
        try:
            start_time = time.time()
            
            # Renew DB connection if necessary
            if connection:
                try:
                    # Test if the connection is still active
                    connection.execute("SELECT 1")
                except:
                    logger.warning("DB connection lost. Reconnecting...")
                    connection = create_connection(db_path)
                    if connection:
                        logger.info("DB reconnection successful")
            
            # Get list of stocks
            stocks = update_stock_list()
            
            # Check data integrity (once a day)
            if start_time - last_integrity_check > integrity_check_interval:
                logger.info("Running periodic data integrity check")
                check_data_integrity(connection, stocks)
                last_integrity_check = start_time
            
            # Normal stock check
            check_stocks(bot_token, chat_id, connection)
            
            # Calculate how long to wait until the next check
            elapsed_time = time.time() - start_time
            wait_time = max(0, interval_minutes * 60 - elapsed_time)
            
            if wait_time > 0:
                logger.info(f"Waiting {wait_time:.1f} seconds until next check")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Error in the check loop: {e}")
            # Wait one minute before retrying in case of error
            time.sleep(60)


def check_data_integrity(db_connection, symbols):
    """
    Checks the integrity of historical data to detect and correct gaps.
    
    Args:
        db_connection: Database connection
        symbols: List of symbols to check
    """
    if not db_connection:
        logger.warning("No database connection to check integrity")
        return
        
    logger.info("Starting data integrity check...")
    
    for symbol in symbols:
        try:
            logger.info(f"Checking data integrity for {symbol}")
            
            # Get historical data
            data = get_last_data_from_db(db_connection, symbol, limit=1000)
            
            if data is None or data.empty:
                logger.info(f"No historical data for {symbol}")
                continue
                
            # Check for gaps during market hours
            import pandas as pd
            dates = data.index
            
            # Create an ideal time series with 5-minute interval during market hours
            import datetime
            import pytz
            
            # Determine the date range to check (last month)
            start_date = dates.min()
            end_date = dates.max()
            
            # Limit to 30 days to avoid overload
            if (end_date - start_date).days > 30:
                start_date = end_date - datetime.timedelta(days=30)
            
            # Create a range of ideal dates during market hours
            ideal_dates = []
            current_date = start_date
            
            while current_date <= end_date:
                # Only business days (0=Monday, 4=Friday)
                if current_date.weekday() < 5:
                    # Market hours (9:30 AM - 4:00 PM ET)
                    start_hour = datetime.time(9, 30)
                    end_hour = datetime.time(16, 0)
                    
                    # Generate 5-minute intervals
                    current_hour = datetime.datetime.combine(current_date.date(), start_hour)
                    current_hour = pytz.timezone('America/New_York').localize(current_hour)
                    
                    while current_hour.time() <= end_hour:
                        ideal_dates.append(current_hour)
                        current_hour += datetime.timedelta(minutes=5)
                
                current_date += datetime.timedelta(days=1)
            
            # Convert to DataFrame for comparison
            ideal_df = pd.DataFrame(index=ideal_dates)
            
            # Identify missing dates (gaps)
            missing_dates = ideal_df.index.difference(dates)
            
            if len(missing_dates) > 0:
                # Group missing dates by day for the report
                days_with_gaps = set([date.date() for date in missing_dates])
                
                logger.warning(f"Detected {len(missing_dates)} potential gaps for {symbol} on {len(days_with_gaps)} different days")
                
                # If there are many gaps, we could schedule a complete data reload
                if len(missing_dates) > 20:
                    logger.info(f"Scheduling complete data reload for {symbol}")
                    # Here we could mark the symbol for full reload
                    # or implement the reload directly
                
            else:
                logger.info(f"No significant gaps detected for {symbol}")
                
        except Exception as e:
            logger.error(f"Error checking data integrity for {symbol}: {e}")


# Function to send a test message via Telegram
def send_telegram_test(test_message="Stock Alerts System Test", bot_token=None, chat_id=None):
    """
    Sends a test message via Telegram to verify the configuration.
    
    Args:
        test_message: Message to send
        bot_token: Telegram bot token
        chat_id: Chat ID where to send the message
        
    Returns:
        bool: True if sending was successful, False otherwise
    """
    if not bot_token or not chat_id:
        print("❌ Error: You must provide bot_token and chat_id")
        return False
    
    complete_message = f"""
🔔 <b>{test_message}</b>

If you're seeing this message, your Telegram configuration is working correctly.
<i>Sent from your Stock Technical Alerts System</i>
"""
    
    result = send_telegram_alert(complete_message, bot_token, chat_id)
    
    if result:
        print(f"✅ Test message sent successfully to Telegram")
    else:
        print(f"❌ Error sending test message to Telegram")
    
    return result

def generate_alert_message(symbol, data, breakout_index):
    """
    Generates a more informative alert message with recommended price levels
    and adaptations based on market type.
    
    Args:
        symbol: Stock symbol
        data: DataFrame with data and indicators
        breakout_index: Index where the breakout was detected
        
    Returns:
        str: Formatted message for the alert
    """
    row = data.iloc[breakout_index]
    current_price = data['Close'].iloc[-1]
    date_time = data.index[breakout_index]
    
    # Detect market type
    market_type = detect_market_type(data)
    
    # Adapt parameters based on market type
    if market_type["tendencia"] == "bearish":
        # In a bearish market, tighter stop loss and more conservative take profit
        pct_stop_loss = 0.4  # 0.4% instead of 0.5%
        pct_take_profit1 = 0.4  # 0.4% instead of 0.5%
        pct_take_profit2 = 0.8  # 0.8% instead of 1.0%
    elif market_type["volatilidad"] == "high":
        # In a volatile market, wider stop loss and more ambitious take profit
        pct_stop_loss = 0.7  # 0.7% instead of 0.5%
        pct_take_profit1 = 0.7  # 0.7% instead of 0.5%
        pct_take_profit2 = 1.4  # 1.4% instead of 1.0%
    else:
        # Normal values
        pct_stop_loss = 0.5
        pct_take_profit1 = 0.5
        pct_take_profit2 = 1.0
    
    # Calculate recommended price levels
    entry_price = current_price
    stop_loss = round(entry_price * (1 - pct_stop_loss/100), 2)
    take_profit_1 = round(entry_price * (1 + pct_take_profit1/100), 2)
    take_profit_2 = round(entry_price * (1 + pct_take_profit2/100), 2)
    
    # Distance to middle band (potential target)
    middle_band_distance = ((row['BB_MEDIA'] / current_price) - 1) * 100
    
    message = f"🔔 <b>TECHNICAL ALERT: {symbol}</b>\n\n"
    
    # Add market type
    message += f"<b>Market:</b> {market_type['descripcion']}\n\n"
    
    # Add technical conditions that are met
    _, detail = verify_additional_conditions(data, breakout_index)
    message += detail
    
    # Add trading recommendations
    message += f"\n\n<b>Trading Data:</b>"
    message += f"\nCurrent price: ${current_price:.2f}"
    message += f"\nSuggested stop loss: ${stop_loss} (-{pct_stop_loss}%)"
    message += f"\nTake profit 1: ${take_profit_1} (+{pct_take_profit1}%)"
    message += f"\nTake profit 2: ${take_profit_2} (+{pct_take_profit2}%)"
    message += f"\nMiddle band: ${row['BB_MEDIA']:.2f} ({middle_band_distance:.1f}% from current price)"
    
    # Add momentum and signal strength
    rsi_strength = "STRONG" if row['RSI_K'] < 10 else "MODERATE"
    message += f"\n\n<b>Signal strength:</b> {rsi_strength}"
    
    # Add specific recommendation based on market
    if market_type["tendencia"] == "bearish":
        message += f"\n\n⚠️ <b>Caution:</b> Bearish market - Consider reducing position size and taking profits quickly."
    elif market_type["volatilidad"] == "high":
        message += f"\n\n⚠️ <b>Caution:</b> High volatility - Wider stop loss and watch for quick reversal."
    
    # Add timestamps
    message += f"\n\nSignal date and time: {date_time}"
    message += f"\nCurrent date and time: {data.index[-1]}"
    
    return message



# Improved function to detect signal sequence in flexible time windows
def detect_signal_sequence(df, max_window=5):
    """
    Detects the appropriate sequence of technical signals in a flexible time window.
    First looks for Bollinger breakout and low RSI (in any order but close together),
    and then MACD approaching its signal line.
    
    Args:
        df: DataFrame with calculated indicators
        max_window: Maximum number of candles to consider for the complete sequence
        
    Returns:
        (bool, dict): Tuple with (sequence_detected, detailed_information)
    """
    if df.empty or len(df) < 10:  # We need enough data to analyze sequences
        return False, {"mensaje": "Insufficient data to analyze sequence"}
    
    # We'll analyze the last 'max_window + 3' candles to have margin
    # (+3 because we may need to verify conditions that depend on previous candles)
    periods_to_check = min(max_window + 3, len(df) - 2)
    last_candles = df.iloc[-periods_to_check:]
    
    # Variables to detect events
    bollinger_event = None  # Index where Bollinger breaks
    low_rsi_event = None   # Index where RSI is below 20
    macd_event = None       # Index where MACD starts approaching
    
    # 1. Detect Bollinger breakout (the most recent)
    for i in range(1, periods_to_check):
        index = -i
        
        # Check for lower Bollinger Band breakout
        if (not pd.isna(df['Close'].iloc[index]) and 
            not pd.isna(df['BB_INFERIOR'].iloc[index]) and
            df['Close'].iloc[index] < df['BB_INFERIOR'].iloc[index]):
            
            # Confirm it's a new breakout
            if index > -len(df) and df['Close'].iloc[index-1] >= df['BB_INFERIOR'].iloc[index-1]:
                bollinger_event = index
                break
    
    # 2. Detect Stochastic RSI below 20 (the most recent)
    for i in range(1, periods_to_check):
        index = -i
        
        if not pd.isna(df['RSI_K'].iloc[index]) and df['RSI_K'].iloc[index] < 20:
            low_rsi_event = index
            break
    
    # If we don't have either of the first two events, there's no sequence
    if bollinger_event is None or low_rsi_event is None:
        return False, {"mensaje": "No Bollinger breakout or low RSI detected"}
    
    # 3. Check that both events (Bollinger and RSI) occur close in time
    # Calculate the distance in candles between the two events
    events_distance = abs(abs(bollinger_event) - abs(low_rsi_event))
    if events_distance > 3:  # Maximum 3 candles (15 minutes) difference
        return False, {"mensaje": "Bollinger breakout and low RSI too distant"}
    
    # 4. Look for MACD signal after Bollinger/RSI events
    # Determine which of the two events occurred most recently
    last_event_index = min(abs(bollinger_event), abs(low_rsi_event))
    
    # Look for MACD approaching signal after the last event
    for i in range(last_event_index, periods_to_check):
        index = -i
        previous_index = index - 1
        
        if (previous_index < -len(df) or 
            pd.isna(df['MACD'].iloc[index]) or 
            pd.isna(df['MACD_SIGNAL'].iloc[index]) or
            pd.isna(df['MACD'].iloc[previous_index]) or
            pd.isna(df['MACD_SIGNAL'].iloc[previous_index])):
            continue
        
        # Calculate distances and trends in MACD
        current_distance = df['MACD_SIGNAL'].iloc[index] - df['MACD'].iloc[index]
        previous_distance = df['MACD_SIGNAL'].iloc[previous_index] - df['MACD'].iloc[previous_index]
        
        # Conditions for MACD approaching
        macd_approaching_condition = (df['MACD'].iloc[index] < df['MACD_SIGNAL'].iloc[index] and 
                                      current_distance < previous_distance and
                                      current_distance > 0)
        
        # Positive slope
        macd_slope_condition = df['MACD'].iloc[index] > df['MACD'].iloc[previous_index]
        
        # Histogram improving
        histogram_condition = df['MACD_HIST'].iloc[index] > df['MACD_HIST'].iloc[previous_index]
        
        if macd_approaching_condition and macd_slope_condition and histogram_condition:
            macd_event = index
            break
    
    # If there's no MACD event or it's too far away, there's no complete sequence
    if macd_event is None:
        return False, {"mensaje": "No favorable MACD detected after the breakout"}
    
    # Check that the complete sequence occurs within the maximum window
    total_window = abs(macd_event) - min(abs(bollinger_event), abs(low_rsi_event))
    if total_window > max_window:
        return False, {"mensaje": f"Sequence exceeds maximum window of {max_window} candles"}
    
    # Calculate distance to crossing
    if current_distance > 0 and previous_distance > current_distance:
        closing_speed = previous_distance - current_distance
        estimated_candles_to_cross = current_distance / closing_speed if closing_speed > 0 else float('inf')
    else:
        estimated_candles_to_cross = float('inf')
    
    # Prepare detailed information about the sequence
    details = {
        "secuencia_ok": True,
        "indice_bollinger": bollinger_event,
        "indice_rsi": low_rsi_event,
        "indice_macd": macd_event,
        "distancia_bollinger_rsi": events_distance,
        "ventana_total": total_window,
        "velas_para_cruce": estimated_candles_to_cross
    }
    
    return True, details


# Updated function to analyze stock using the flexible sequence
def analyze_stock_flexible(symbol, db_connection=None):
    """
    Analyzes a stock using the flexible sequence detection.
    
    Args:
        symbol: Stock symbol to analyze
        db_connection: Database connection (optional)
        
    Returns:
        (bool, str): Tuple with (alert_generated, alert_message)
    """
    try:
        # Get data combining historical and new if possible
        data = get_stock_data(symbol, period='1d', interval='5m', 
                             db_connection=db_connection, 
                             only_new=(db_connection is not None))
        
        if data is None or data.empty or len(data) < 30:
            logger.warning(f"Insufficient data to analyze {symbol}")
            return False, f"Insufficient data for {symbol}"
        
        # Check if we already have all calculated indicators
        complete_indicators = all(col in data.columns for col in 
                                 ['BB_INFERIOR', 'BB_MEDIA', 'BB_SUPERIOR', 
                                  'MACD', 'MACD_SIGNAL', 'MACD_HIST', 
                                  'RSI', 'RSI_K', 'RSI_D'])
        
        # If indicators are missing, calculate all
        if not complete_indicators:
            data = calculate_bollinger(data, window=18, deviations=2.25)
            data = calculate_macd(data, fast=8, slow=21, signal=9)
            data = calculate_stochastic_rsi(data, rsi_period=14, k_period=14, d_period=3, smooth=3)
        
        # Save historical data if there's a DB connection
        if db_connection:
            save_historical_data(db_connection, symbol, data)
        
        # Detect flexible sequence of signals (maximum 5 candles or 25 minutes between first and last)
        sequence_detected, details = detect_signal_sequence(data, max_window=5)
        
        if sequence_detected:
            logger.info(f"Signal sequence detected for {symbol}: {details}")
            
            # Use the MACD index (the last signal) to generate the alert
            message = generate_flexible_alert_message(symbol, data, details)
            
            # Save alert to the database if there's a connection
            if db_connection:
                macd_index = details.get("indice_macd", -1)
                save_alert_to_db(db_connection, symbol, data, macd_index, message, "sequence")
            
            return True, message
        else:
            logger.info(f"Complete sequence not detected for {symbol}: {details.get('mensaje', '')}")
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return False, f"Error analyzing {symbol}: {str(e)}"


# Function to generate alert message with the flexible sequence
def generate_flexible_alert_message(symbol, data, sequence_details):
    """
    Generates an alert message adapted to the flexible sequence.
    
    Args:
        symbol: Stock symbol
        data: DataFrame with data and indicators
        sequence_details: Dictionary with details of the detected sequence
        
    Returns:
        str: Formatted message for the alert
    """
    # Extract sequence indices
    bollinger_index = sequence_details["indice_bollinger"]
    rsi_index = sequence_details["indice_rsi"]
    macd_index = sequence_details["indice_macd"]
    
    # Use the latest event for current price information
    current_price = data['Close'].iloc[-1]
    
    # Data for each event
    bollinger_data = data.iloc[bollinger_index]
    rsi_data = data.iloc[rsi_index]
    macd_data = data.iloc[macd_index]
    
    # Candles to crossing - Explicitly convert to float if it's numpy.float64
    candles_to_cross = float(sequence_details.get("velas_para_cruce", float('inf')))
    imminent_cross = candles_to_cross < 5
    
    # Detect market type
    market_type = detect_market_type(data)
    
    # Adapt parameters based on market type
    if market_type["tendencia"] == "bearish":
        pct_stop_loss = 0.4
        pct_take_profit1 = 0.4
        pct_take_profit2 = 0.8
    elif market_type["volatilidad"] == "high":
        pct_stop_loss = 0.7
        pct_take_profit1 = 0.7
        pct_take_profit2 = 1.4
    else:
        pct_stop_loss = 0.5
        pct_take_profit1 = 0.5
        pct_take_profit2 = 1.0
    
    # Calculate price levels
    stop_loss = round(current_price * (1 - pct_stop_loss/100), 2)
    take_profit_1 = round(current_price * (1 + pct_take_profit1/100), 2)
    take_profit_2 = round(current_price * (1 + pct_take_profit2/100), 2)
    
    # Distance to middle band (potential target)
    middle_band_distance = ((bollinger_data['BB_MEDIA'] / current_price) - 1) * 100
    
    # Build message with < and > symbols properly escaped
    message = f"🔔 <b>TECHNICAL ALERT: {symbol}</b>\n\n"
    message += f"<b>Market:</b> {market_type['descripcion']}\n\n"
    message += f"<b>Signal Sequence Detected:</b>\n"
    
    # 1. Bollinger breakout - IMPORTANT: Manually escape < symbol
    bollinger_time = data.index[bollinger_index]
    message += f"• Bollinger Breakout: {bollinger_time.strftime('%H:%M')} - Price ({bollinger_data['Close']:.2f}) &lt; Lower BB ({bollinger_data['BB_INFERIOR']:.2f})\n"
    
    # 2. Low Stochastic RSI
    rsi_time = data.index[rsi_index]
    message += f"• Stochastic RSI: {rsi_time.strftime('%H:%M')} - RSI-K ({rsi_data['RSI_K']:.2f}) below 20\n"
    
    # 3. MACD approaching
    macd_time = data.index[macd_index]
    message += f"• MACD: {macd_time.strftime('%H:%M')} - MACD ({macd_data['MACD']:.4f}) approaching Signal ({macd_data['MACD_SIGNAL']:.4f})\n"
    
    # Rest of the message...
    if imminent_cross:
        message += f"\n⚠️ <b>IMMINENT CROSSING</b> - Approx. {candles_to_cross:.1f} candles until MACD cross\n"
    
    message += f"\n<b>Trading Data:</b>"
    message += f"\nCurrent price: ${current_price:.2f}"
    message += f"\nSuggested stop loss: ${stop_loss} (-{pct_stop_loss}%)"
    message += f"\nTake profit 1: ${take_profit_1} (+{pct_take_profit1}%)"
    message += f"\nTake profit 2: ${take_profit_2} (+{pct_take_profit2}%)"
    message += f"\nMiddle band: ${bollinger_data['BB_MEDIA']:.2f} ({middle_band_distance:.1f}% from current price)"
    
    rsi_strength = "STRONG" if rsi_data['RSI_K'] < 10 else "MODERATE"
    message += f"\n\n<b>Signal strength:</b> {rsi_strength}"
    
    if market_type["tendencia"] == "bearish":
        message += f"\n\n⚠️ <b>Caution:</b> Bearish market - Consider reducing position size and taking profits quickly."
    elif market_type["volatilidad"] == "high":
        message += f"\n\n⚠️ <b>Caution:</b> High volatility - Wider stop loss and watch for quick reversal."
    
    message += f"\n\nCurrent date and time: {data.index[-1]}"
    
    return message

if __name__ == "__main__":
    # Configuration
    TOKEN_BOT = "7869353980:AAGGPrOKCTD4afFc8k3PifPOzLLE6KY3E2E"  # Entre comillas y sin coma
    CHAT_ID = "477718262"  # Entre comillas
    FINNHUB_API_KEY = "cveivgpr01ql1jnbobc0cveivgpr01ql1jnbobcg"  # Replace with your actual Finnhub API key
    
    # Start with a test message
    print("Sending test message to verify configuration...")
    send_telegram_test("TECHNICAL ALERTS SYSTEM ACTIVATED", TOKEN_BOT, CHAT_ID)
    
    logger.info("Starting technical alerts system with sequential detection...")
    logger.info("Monitoring stocks with 5-minute interval")
    
    # Start continuous checks in an independent thread
    check_thread = threading.Thread(
        target=run_continuous_checks,
        args=(TOKEN_BOT, CHAT_ID, 20, "stock_alerts.db"),  # Check every 20 minutes
        daemon=True
    )
    
    check_thread.start()
    
    # Keep the program running
    try:
        print("\nSystem is running. Press Ctrl+C to stop.")
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("System stopped by user")