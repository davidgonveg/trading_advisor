
import unittest
from datetime import datetime, timezone
from analysis.signal import Signal, SignalType
from trading.manager import TradeManager

class TestTradeManager(unittest.TestCase):
    def setUp(self):
        self.manager = TradeManager()
        
    def test_create_plan_long(self):
        sig = Signal(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            type=SignalType.LONG,
            price=100.0,
            atr_value=1.0,
            metadata={}
        )
        
        # Capital 10,000. Risk 1.5% = 150.
        # Stop Distance = 2 * ATR = 2.
        # Size = 150 / 2 = 75 units.
        
        plan = self.manager.create_trade_plan(sig, capital=10000.0)
        
        self.assertIsNotNone(plan)
        self.assertEqual(plan.total_size, 75)
        
        # Check E1 (50% = 37)
        e1 = next(o for o in plan.entry_orders if o.tag == "E1")
        self.assertEqual(e1.quantity, 37)
        
        # Check SL (Entry - 2*ATR = 100 - 2 = 98)
        self.assertEqual(plan.stop_loss_price, 98.0)

if __name__ == "__main__":
    unittest.main()
