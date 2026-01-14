import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Iterator

from backtesting.data.schema import DataFeed, BarData, Candle
from backtesting.simulation.engine import BacktestEngine
from backtesting.strategy.mean_reversion import MeanReversionStrategy

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')

class SyntheticFeed(DataFeed):
    """Generates a perfect sine wave to trigger RSI signals."""
    def __init__(self, symbol="TEST", length=300):
        self.symbol = symbol
        self.length = length
        
    @property
    def symbols(self):
        return [self.symbol]
        
    def __iter__(self) -> Iterator[BarData]:
        # Generate Sine Wave
        for i in range(self.length):
            t = datetime(2024, 1, 1) + timedelta(hours=i)
            
            # Sine wave: overlaps between 90 and 110. 
            # Period = 24h
            val = 100 + 10 * np.sin(i / 5.0) 
            
            # Make it "trending" slightly or mean reverting
            # RSI needs volatility.
            
            candle = Candle(
                timestamp=t,
                symbol=self.symbol,
                open=val - 1,
                high=val + 2,
                low=val - 2,
                close=val,
                volume=1000
            ) 
            
            # Daily bar (fake)
            daily = {
                self.symbol: Candle(
                    timestamp=t.replace(hour=0, minute=0),
                    symbol=self.symbol,
                    open=100, high=120, low=80, close=100, volume=50000
                )
            }
            
            yield BarData(timestamp=t, bars={self.symbol: candle}, daily_bars=daily)

def run_test():
    print(">>> RUNNING SYNTHETIC TEST <<<")
    feed = SyntheticFeed()
    engine = BacktestEngine(feed, initial_capital=10000.0)
    strategy = MeanReversionStrategy(symbols=["TEST"])
    
    engine.set_strategy(strategy)
    engine.run()
    
    print("\n>>> RESULTS <<<")
    print(f"Equity: {engine.broker.equity}")
    print(f"Trades: {len(engine.broker.trades)}")
    for t in engine.broker.trades:
        print(f"  {t.timestamp} {t.side.value} {t.quantity} @ {t.price:.2f} (Comm: {t.commission:.2f})")

if __name__ == "__main__":
    run_test()
