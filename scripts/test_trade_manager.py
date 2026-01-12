
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from analysis.signal import Signal, SignalType
from trading.manager import TradeManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_manager():
    print("\n💼 TESTING TRADE MANAGER")
    print("=" * 60)
    
    manager = TradeManager()
    
    # 1. Mock Signal (SPY Long)
    # Price: 580, ATR: 5 (from Doc Example)
    # Expected Size: 15 shares
    
    sig = Signal(
        symbol="SPY",
        timestamp=datetime.utcnow(),
        type=SignalType.LONG,
        timeframe="1h",
        price=580.0,
        atr_value=5.0,
        metadata={"rsi": 30}
    )
    
    print(f"Signal: {sig}")
    
    # 2. Create Plan
    plan = manager.create_trade_plan(sig, capital=10000.0)
    
    if plan:
        print("\n✅ Plan Created Successfully!")
        print(f"Total Size: {plan.total_size} (Expected: 15)")
        print(f"Risk Amount: ${plan.risk_amount:.2f} (Expected: ~$150)")
        print(f"Stop Loss: ${plan.stop_loss_price:.2f}")
        
        print("\n📋 Orders:")
        for o in plan.entry_orders:
            print(f"  [{o.tag}] {o.side} {o.quantity} @ {o.price if o.price else 'MARKET'} ({o.type})")
            
        print("\n🎯 Take Profits:")
        for o in plan.take_profits:
            print(f"  [{o.tag}] {o.side} @ {o.price} ({o.type})")
            
        # Verify specific values against strategy
        # E1: 580 (50% = 7)
        # E2: 580 - 0.5*5 = 577.5 (30% = 4)
        # E3: 580 - 1.0*5 = 575.0 (20% = 4)
        # SL: 580 - 2.0*5 = 570.0
        
        # Check E2 Price
        e2 = next(o for o in plan.entry_orders if o.tag == "E2")
        assert e2.price == 577.5, f"E2 Price wrong: {e2.price}"
        
        print("\nUnit Test Passed Logic Checks.")
    else:
        print("❌ Failed to create plan.")

if __name__ == "__main__":
    test_manager()
