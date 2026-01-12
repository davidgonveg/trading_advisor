
import yfinance as yf
import pandas as pd

def check():
    symbol = "SPY"
    print(f"Fetching {symbol} from yfinance...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="1h")
    
    print("Columns:", df.columns)
    print("Head:\n", df.head())
    
    if 'Volume' in df.columns:
        print("Volume Stats:")
        print(df['Volume'].describe())
    else:
        print("Volume column NOT FOUND")

if __name__ == "__main__":
    check()
