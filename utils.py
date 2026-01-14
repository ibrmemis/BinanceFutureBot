import sys
import logging
import os

# Force stdout to be line-buffered if possible
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
from pathlib import Path

class FlushStreamHandler(logging.StreamHandler):
    """
    StreamHandler that flushes the stream after every log record.
    This ensures logs appear immediately in the console/terminal.
    """
    def emit(self, record):
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logger(name: str = "trading_bot", log_level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return a logger instance.
    """
    logger = logging.getLogger(name)
    
    # If logger already has handlers, assume it's configured
    if logger.handlers:
        return logger
        
    logger.setLevel(log_level)
    
    # Create console handler with flushing
    console_handler = FlushStreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    return logger

def get_project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.absolute()
