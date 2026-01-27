import logging
import os
import json
from datetime import datetime
from typing import Dict, Any

class CustomFormatter(logging.Formatter):
    """Custom formatter with colors for console."""
    
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    green = "\x1b[32;20m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def setup_logging(config: Dict[str, Any]):
    """
    Sets up logging based on the provided configuration.
    """
    log_config = config.get("logging", {})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Root logger setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Catch everything, handlers will filter
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler
    console_cfg = log_config.get("console", {})
    if console_cfg.get("enabled", True):
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, console_cfg.get("level", "INFO")))
        ch.setFormatter(CustomFormatter())
        root_logger.addHandler(ch)

    # File Handler
    file_cfg = log_config.get("file", {})
    if file_cfg.get("enabled", False):
        log_path = file_cfg.get("path", "backtest.log").replace("{timestamp}", ts)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        fh = logging.FileHandler(log_path)
        fh.setLevel(getattr(logging, file_cfg.get("level", "DEBUG")))
        fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root_logger.addHandler(fh)

    logger = logging.getLogger("backtesting.logger")
    logger.info("Logging initialized.")
    return ts

class AuditTrail:
    """Helper to collect and save full execution audit."""
    def __init__(self, config: Dict[str, Any], timestamp: str, symbol: str = "asset", strategy: str = "strat"):
        self.config = config
        self.timestamp = timestamp
        self.symbol = symbol
        self.strategy = strategy
        self.data = {
            "metadata": {},
            "bars": [],
            "trades": [],
            "final_metrics": {}
        }
        self.enabled = config.get("logging", {}).get("audit_log", {}).get("enabled", False)
        
        # Build path with symbol and strategy to avoid overwrites
        base_path = config.get("logging", {}).get("audit_log", {}).get("path", "audit.json")
        ext = os.path.splitext(base_path)[1]
        folder = os.path.dirname(base_path)
        filename = f"audit_{symbol}_{strategy}_{timestamp}{ext}"
        self.path = os.path.join(folder, filename)

    def set_metadata(self, metadata: Dict[str, Any]):
        self.data["metadata"] = metadata

    def log_bar(self, bar_info: Dict[str, Any]):
        if self.enabled:
            self.data["bars"].append(bar_info)

    def log_trade(self, trade_info: Dict[str, Any]):
        if self.enabled:
            self.data["trades"].append(trade_info)

    def save(self, metrics: Dict[str, Any]):
        if not self.enabled:
            return
        self.data["final_metrics"] = metrics
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)
        logging.getLogger("backtesting.audit").info(f"Audit trail saved to {self.path}")
