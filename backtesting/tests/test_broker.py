import unittest
from datetime import datetime
from backtesting.simulation.broker import Broker, Order, OrderType, OrderSide, OrderStatus
from backtesting.data.schema import BarData, Candle

class TestBroker(unittest.TestCase):
    def setUp(self):
        self.broker = Broker(initial_cash=10000.0)
        self.symbol = "TEST"
        self.timestamp = datetime(2023, 1, 1, 10, 0)

    def create_candle(self, open=100, high=105, low=95, close=100):
        return Candle(self.timestamp, self.symbol, open, high, low, close, 1000)

    def test_submit_order_insufficient_funds(self):
        # Try to buy 1000 shares at $100 = $100k (Have $10k)
        # Broker V1 checks funds at FILL time, not submission time (pending Limit orders don't block cash yet).
        # Let's test MARKET order fill.
        
        order = Order("1", self.symbol, OrderSide.BUY, OrderType.MARKET, 1000)
        self.broker.submit_order(order)
        
        # Process Bar
        bar = BarData(self.timestamp, {self.symbol: self.create_candle(100, 100, 100, 100)}, {})
        self.broker.process_bar(bar)
        
        self.assertEqual(order.status, OrderStatus.REJECTED)
        self.assertEqual(len(self.broker.trades), 0)
        self.assertEqual(self.broker.cash, 10000.0)

    def test_limit_buy_execution(self):
        # Place Limit Buy at 98
        order = Order("2", self.symbol, OrderSide.BUY, OrderType.LIMIT, 10, price=98)
        self.broker.submit_order(order)
        
        # 1. Candle Low 99 (No Fill)
        bar1 = BarData(self.timestamp, {self.symbol: self.create_candle(100, 102, 99, 101)}, {})
        self.broker.process_bar(bar1)
        self.assertEqual(order.status, OrderStatus.ACCEPTED)
        
        # 2. Candle Low 97 (Fill!)
        bar2 = BarData(self.timestamp, {self.symbol: self.create_candle(99, 100, 97, 98)}, {})
        self.broker.process_bar(bar2)
        
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.filled_price, 98.0) # Or better?
        self.assertEqual(len(self.broker.trades), 1)
        
        # Check Cash Deduction (10 * 98 = 980 + Comm)
        expected_cost = 980 + (max(1.0, 10 * 0.005))
        self.assertAlmostEqual(self.broker.cash, 10000.0 - expected_cost)

if __name__ == '__main__':
    unittest.main()
