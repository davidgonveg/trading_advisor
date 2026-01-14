import unittest
from unittest.mock import MagicMock
import pandas as pd
from datetime import datetime

from backtesting.strategy.mean_reversion import MeanReversionStrategy
from backtesting.simulation.context import TradingContext
from backtesting.simulation.broker import OrderSide, OrderType

class TestStrategyLogic(unittest.TestCase):
    def setUp(self):
        self.strategy = MeanReversionStrategy(["TEST"])
        self.ctx = MagicMock(spec=TradingContext)
        self.ctx.positions = {}
        self.ctx.active_orders = {}
        self.ctx.capital = 10000.0
        self.ctx.timestamp = datetime(2023, 1, 1)
        # Mock Data Object on Context
        self.ctx.data = MagicMock()
        # Mock DataFeed Daily
        self.ctx.data.daily_bars = {}

    def test_long_entry_trigger(self):
        # 1. Populate History with 50 bars
        # Last bar needs: RSI < 35, RSI > Prev, Price <= BB Low, ADX < 22
        
        # Construct DF manually to control indicators result? 
        # Easier: Mock `get_history_df` and `IndicatorCalculator`.
        # But we want to test "Atomic Logic".
        
        # Mock DF with 50+ rows to pass 'len(df) < 50' check
        dates = pd.date_range(start='2023-01-01', periods=52, freq='h')
        df = pd.DataFrame(index=dates)
        
        # Default values (No signal)
        df['Close'] = [100.0] * 52
        df['RSI'] = [50.0] * 52
        df['BB_lower'] = [90.0] * 52
        df['ADX'] = [15.0] * 52
        df['ATR'] = [2.0] * 52
        df['High'] = [101.0] * 52 
        df['Low'] = [99.0] * 52
        
        # --- Set Trigger Conditions on Last 2 Rows ---
        # Index -2 (Previous)
        # RSI must be < 35
        df.iloc[-2, df.columns.get_loc('RSI')] = 30.0 
        
        # Index -1 (Current)
        # RSI must be < 35 AND > Prev(30) (Turning Up)
        df.iloc[-1, df.columns.get_loc('RSI')] = 32.0 
        
        # Price <= BB Lower (95 <= 96)
        df.iloc[-1, df.columns.get_loc('Close')] = 95.0
        df.iloc[-1, df.columns.get_loc('BB_lower')] = 96.0
        
        # ADX < 22 (20 is fine)
        df.iloc[-1, df.columns.get_loc('ADX')] = 20.0
        
        # ATR for Sizing
        df.iloc[-1, df.columns.get_loc('ATR')] = 2.0
        
        # Mock Strategy methods
        self.strategy.get_history_df = MagicMock(return_value=df)
        
        # Mock IndicatorCalculator to return the DF as is (already calculated)
        from backtesting.strategy.mean_reversion import IndicatorCalculator
        original_calc = IndicatorCalculator.calculate
        IndicatorCalculator.calculate = lambda x: x # Identity
        
        try:
            # Run Logic
            self.strategy.check_entry(self.ctx, "TEST")
            
            # Assertions
            # Should subscribe 3 Buy Orders + 1 Stop Order
            self.assertEqual(self.ctx.submit_order.call_count, 4)
            
            # Check E1 (Market)
            # args[0] is the Order object
            orders = [call.args[0] for call in self.ctx.submit_order.call_args_list]
            
            e1 = next(o for o in orders if o.tag == "E1")
            self.assertEqual(e1.order_type, OrderType.MARKET)
            self.assertEqual(e1.side, OrderSide.BUY)
            
            e2 = next(o for o in orders if o.tag == "E2")
            self.assertEqual(e2.order_type, OrderType.LIMIT)
            self.assertEqual(e2.price, 95 - (0.5 * 2)) # 94.0
            
            sl = next(o for o in orders if o.tag == "SL")
            self.assertEqual(sl.stop_price, 95 - (2.0 * 2)) # 91.0
            
        finally:
            # Restore
            IndicatorCalculator.calculate = original_calc

if __name__ == '__main__':
    unittest.main()
