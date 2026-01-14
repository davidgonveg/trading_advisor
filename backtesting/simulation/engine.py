import logging
import time
from typing import Optional, Callable
from datetime import datetime

from backtesting.data.schema import DataFeed
from backtesting.simulation.broker import Broker
from backtesting.simulation.context import TradingContext

logger = logging.getLogger("backtesting.engine")

class BacktestEngine:
    def __init__(self, data_feed: DataFeed, initial_capital: float = 10000.0):
        self.feed = data_feed
        self.broker = Broker(initial_capital)
        self.strategy = None # Set later
        
    def set_strategy(self, strategy_instance):
        self.strategy = strategy_instance
        
    def run(self):
        """
        The Main Event Loop.
        """
        if not self.strategy:
            raise ValueError("No strategy set!")
            
        logger.info("Starting Event-Driven Backtest...")
        start_time = time.time()
        
        step_count = 0
        
        for bar_data in self.feed:
            step_count += 1
            current_time = bar_data.timestamp
            
            # 1. Update Broker (Check Fills against NEW Bar)
            #    Crucially: Limit orders submitted yesterday are checked against Today's Low/High.
            self.broker.process_bar(bar_data)
            
            # 2. create Context
            ctx = TradingContext(self.broker, current_time, bar_data)
            
            # 3. Invoke Strategy (Generate Signals / Adjust Orders)
            #    Strategy sees 'Close' of current bar (e.g. 10:00). 
            #    Decisions made now will execute at 11:00 Open (Market) or Intraday 10:00-11:00 (Limit).
            #    Wait. If we are processing bar 10:00-11:00.
            #    Signal is generated at 11:00 (Close).
            #    Market order fills at 12:00 Open.
            
            try:
                self.strategy.on_bar(ctx)
            except Exception as e:
                logger.error(f"Strategy Error at {current_time}: {e}")
                # Don't crash full backtest?
                raise e 
                
        duration = time.time() - start_time
        logger.info(f"Backtest Completed. Processed {step_count} steps in {duration:.2f}s")
        logger.info(f"Final Equity: {self.broker.equity:.2f}")
