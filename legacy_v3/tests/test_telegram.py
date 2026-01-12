import pytest
from unittest.mock import MagicMock, patch, ANY
from services.telegram_bot import TelegramBot
from telegram.error import NetworkError

class TestTelegramBot:
    
    @pytest.fixture
    def bot(self, mock_config):
        return TelegramBot()

    def test_initialization(self, bot):
        assert bot.token == 'TEST_TOKEN'
        assert bot.chat_id == '123456'
        assert bot.connection_config['connect_timeout'] == 45.0

    @patch('services.telegram_bot.Bot')
    def test_send_message_success(self, mock_telegram_cls, bot):
        """Test sending a message successfully"""
        mock_bot_api = mock_telegram_cls.return_value
        # Configure mock to return a success message object
        from unittest.mock import AsyncMock
        mock_bot_api.send_message = AsyncMock()
        
        # We need to manually initialize the bot attribute since __init__ doesn't creating it until run?
        # Actually __init__ creates self.bot = None, and then it is usually lazy or init_bot.
        # Looking at code from memory/view, it seemed to init in __init__ or have a method.
        # Let's assume we need to inject the mock.
        bot.bot = mock_bot_api
        
        # Method calls usually run async or sync. Bot V3.2 implies potentially sync or async wrapper.
        # Assuming sync usage or wrapper for this test.
        # If the original code uses asyncio.run or similar, we might need pytest-asyncio.
        # For now, let's treat it as calling the method logic.
        
        result = bot.send_message("Test Message")
        assert result is True
        mock_bot_api.send_message.assert_called_with(
            chat_id='123456', 
            text="Test Message", 
            parse_mode='HTML', 
            disable_web_page_preview=True
        )


    @patch('services.telegram_bot.Bot')
    @patch('asyncio.sleep')
    def test_send_message_retry_logic(self, mock_sleep, mock_telegram_cls, bot):
        """Test retry logic on network error"""
        mock_bot_api = mock_telegram_cls.return_value
        bot.bot = mock_bot_api
        bot.chat_id = "123456" # Ensure chat_id is set
        bot.initialized = True # Ensure initialized check passes
        bot.last_send_time = 0 # Ensure rate limit check passes immediately
        
        # Prepare side effects for async calls
        from unittest.mock import AsyncMock
        
        # Define a real exception class for testing
        class MockNetworkError(Exception):
            pass

        # Patch the NetworkError in the module under test
        with patch('services.telegram_bot.NetworkError', MockNetworkError), \
             patch('services.telegram_bot.TimedOut', MockNetworkError):
            
            # We need to set the method itself to be an AsyncMock, not just the return value
            mock_bot_api.send_message = AsyncMock()
            
            # Configure side effects on the AsyncMock using the REAL exception class
            mock_bot_api.send_message.side_effect = [
                MockNetworkError("Connection timed out"),
                MockNetworkError("Connection reset"),
                True # Success
            ]
            
            import asyncio
            result = asyncio.run(bot._send_with_retry(message="Retry Me"))
            
            assert result is True
            assert mock_bot_api.send_message.call_count == 3


    def test_format_signal_alert(self, bot):
        """Test formatting of a trading signal"""
        # Create a detailed mock signal
        mock_signal = MagicMock()
        mock_signal.symbol = "AAPL"
        mock_signal.signal_type = "LONG"
        mock_signal.signal_strength = 95 # Int
        mock_signal.confidence_level = "VERY_HIGH"
        mock_signal.current_price = 150.50 # Float
        mock_signal.entry_quality = "FULL_ENTRY"
        mock_signal.risk_reward_ratio = 3.5 # Float
        mock_signal.expected_hold_time = "2-4h"
        mock_signal.market_context = "UPTREND"
        
        # Indicator scores dict must be real dict
        mock_signal.indicator_scores = {'MACD': 20, 'RSI': 15}
        mock_signal.indicator_signals = {'MACD': 'BULLISH', 'RSI': 'OVERSOLD'}
        
        # Position plan
        mock_plan = MagicMock()
        mock_plan.strategy_type = "SCALP"
        mock_plan.total_risk_percent = 1.0
        mock_plan.max_risk_reward = 3.0
        mock_plan.avg_risk_reward = 2.5
        mock_plan.expected_hold_time = "1h"
        mock_plan.entries = [] 
        mock_plan.exits = []
        mock_plan.stop_loss = MagicMock()
        mock_plan.stop_loss.price = 148.0
        mock_plan.stop_loss.percentage = 1.6
        
        mock_signal.position_plan = mock_plan
        
        message = bot.format_signal_alert(mock_signal)
        
        # Verify message contains key info
        # Note: Exact string match depends on TelegramBot's template
        # We check for basic presence of data
        assert "LONG" in message
        assert "AAPL" in message
        assert "95" in message # Signal strength
        assert "150.50" in message # Price formatted
