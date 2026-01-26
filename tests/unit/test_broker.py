import unittest
import sys
import os

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from datetime import datetime
from backtesting.simulation.broker import Broker
from backtesting.simulation.broker_schema import Order, OrderSide, OrderType, OrderStatus, Position
from backtesting.data.schema import BarData, Candle

class TestBrokerShortSelling(unittest.TestCase):
    
    def setUp(self):
        self.broker = Broker(initial_cash=10000.0)
        self.symbol = "AAPL"
        
    def create_candle(self, price, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        return Candle(
            timestamp=timestamp,
            symbol=self.symbol,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000
        )
        
    def create_bar_data(self, candle):
        return BarData(
            timestamp=candle.timestamp,
            bars={self.symbol: candle},
            daily_bars={},
            daily_indicators={}
        )

    def test_open_short_position(self):
        """Test opening a short position from zero."""
        # Sell 10 @ 100
        order = Order(
            id="1",
            symbol=self.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=10
        )
        
        self.broker.submit_order(order)
        
        # Process Bar to fill
        candle = self.create_candle(100.0)
        self.broker.process_bar(self.create_bar_data(candle))
        
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(len(self.broker.positions), 1)
        
        pos = self.broker.positions[self.symbol]
        self.assertEqual(pos.quantity, -10)
        self.assertEqual(pos.average_price, 100.0)
        
        # Check Cash/Equity
        # Cash should increase by proceeds (1000) minus comm
        # Comm = max(1.0, 10 * 0.005 = 0.05) -> 1.0
        expected_cash = 10000.0 + 1000.0 - 1.0 # 10999.0
        self.assertAlmostEqual(self.broker.cash, expected_cash)
        
        # Equity = Cash + PosValue (-1000) = 10999 - 1000 = 9999
        self.assertAlmostEqual(self.broker.equity, 9999.0)

    def test_close_short_position_profit(self):
        """Test closing a short position for profit."""
        # 1. Open Short 10 @ 100
        self.test_open_short_position() 
        
        # 2. Buy 10 @ 90
        order = Order(
            id="2",
            symbol=self.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10
        )
        self.broker.submit_order(order)
        
        candle = self.create_candle(90.0)
        self.broker.process_bar(self.create_bar_data(candle))
        
        # Position should be closed (deleted)
        self.assertNotIn(self.symbol, self.broker.positions)
        
        # PnL Check
        # Short @ 100, Cover @ 90. Profit = 10 * 10 = 100.
        # Comm on entry: 1.0. Comm on exit: 1.0.
        # Total Realized PnL = 100 - 2.0 = 98.0
        # Wait, Realized Pnl in Broker object is not tracked globally, but on Position object.
        # But Position object is deleted. Broker just has 'trades'.
        # We can check Equity.
        # Start 10000. Profit 100. Comm 2. Final Equity 10098.
        self.assertAlmostEqual(self.broker.equity, 10098.0)
        self.assertAlmostEqual(self.broker.cash, 10098.0) # Cash and Equity align when flat

    def test_flip_long_to_short(self):
        """Test flipping from Long to Short."""
        # 1. Buy 10 @ 100
        order1 = Order(id="1", symbol=self.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
        self.broker.submit_order(order1)
        self.broker.process_bar(self.create_bar_data(self.create_candle(100.0)))
        
        # Verify Long
        self.assertEqual(self.broker.positions[self.symbol].quantity, 10)
        
        # 2. Sell 20 @ 110
        order2 = Order(id="2", symbol=self.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=20)
        self.broker.submit_order(order2)
        self.broker.process_bar(self.create_bar_data(self.create_candle(110.0)))
        
        # Expect Short 10 @ 110 (Remainder)
        pos = self.broker.positions[self.symbol]
        self.assertEqual(pos.quantity, -10)
        self.assertEqual(pos.average_price, 110.0) # Reset to new entry price
        
        # Realized PnL from the closed long portion (10 shares)
        # Buy @ 100, Sell @ 110 -> Profit $100.
        self.assertEqual(pos.realized_pnl, 100.0) 

    def test_flip_short_to_long(self):
        """Test flipping from Short to Long."""
        # 1. Sell 10 @ 100
        order1 = Order(id="1", symbol=self.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10)
        self.broker.submit_order(order1)
        self.broker.process_bar(self.create_bar_data(self.create_candle(100.0)))
        
        # Verify Short
        self.assertEqual(self.broker.positions[self.symbol].quantity, -10)
        
        # 2. Buy 20 @ 90
        order2 = Order(id="2", symbol=self.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=20)
        self.broker.submit_order(order2)
        self.broker.process_bar(self.create_bar_data(self.create_candle(90.0)))
        
        # Expect Long 10 @ 90
        pos = self.broker.positions[self.symbol]
        self.assertEqual(pos.quantity, 10)
        self.assertEqual(pos.average_price, 90.0)
        
        # Realized PnL from Short portion (10 shares)
        # Sell @ 100, Buy @ 90 -> Profit $100.
        self.assertEqual(pos.realized_pnl, 100.0)

if __name__ == '__main__':
    unittest.main()
