import unittest
from analysis.risk import RiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.risk = RiskManager(capital=10000.0)

    def test_calculate_size_example(self):
        """test doc example: Cap=10k, ATR=5, Price=580 -> Size=15"""
        # Formula: Size = (Capital * 0.015) / (2 * ATR)
        # 10000 * 0.015 = 150
        # 2 * 5 = 10
        # 150 / 10 = 15
        size = self.risk.calculate_size(price=580, atr=5.0)
        self.assertEqual(size, 15)

    def test_calculate_size_zero_atr(self):
        size = self.risk.calculate_size(price=100, atr=0)
        self.assertEqual(size, 0)
    
    def test_calculate_size_small_capital(self):
        # Cap 1000. Risk 15. ATR=5 (Stop 10). Size = 1.5 -> 1.
        rm = RiskManager(capital=1000.0)
        size = rm.calculate_size(price=100, atr=5.0)
        self.assertEqual(size, 1)

    def test_volatility_adjustment(self):
        # Ratio < 1.5 -> 1.0
        self.assertEqual(self.risk.check_volatility_adjustment(1.0, 1.0), 1.0)
        # Ratio > 1.5 -> 0.75
        self.assertEqual(self.risk.check_volatility_adjustment(1.6, 1.0), 0.75)
        # Ratio > 2.0 -> 0.5
        self.assertEqual(self.risk.check_volatility_adjustment(2.1, 1.0), 0.5)

if __name__ == '__main__':
    unittest.main()
