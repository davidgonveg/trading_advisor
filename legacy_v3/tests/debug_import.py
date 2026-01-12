import sys
import os
from unittest.mock import MagicMock

# Add root
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root)

print(f"Root: {root}")
print(f"Sys Path: {sys.path}")

try:
    import config
    print("✅ Config imported")
except Exception as e:
    print(f"❌ Config import failed: {e}")

try:
    import indicators
    print("✅ Indicators imported")
except Exception as e:
    print(f"❌ Indicators import failed: {e}")
    import traceback
    traceback.print_exc()

# 💉 Mock telegram
if 'telegram' not in sys.modules:
    sys.modules['telegram'] = MagicMock()
if 'telegram.ext' not in sys.modules:
    sys.modules['telegram.ext'] = MagicMock()
if 'telegram.error' not in sys.modules:
    sys.modules['telegram.error'] = MagicMock()

try:
    import telegram_bot
    print("✅ TelegramBot imported")
except Exception as e:
    print(f"❌ TelegramBot import failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from continuous_collector import ContinuousDataCollector
    print("✅ Collector imported")
except Exception as e:
    print(f"❌ Collector import failed: {e}")
    import traceback
    traceback.print_exc()
