# services/document-parser/src/utils/logging.py
"""Backward compatibility bridge for logging - use forth_shared logging."""

# Import from shared logging utilities
from libs.forth_shared.utils.logging import setup_logging
from loguru import logger

def get_logger(name: str = None):
    """Get logger instance for backward compatibility."""
    return logger

# Re-export for backward compatibility
__all__ = ['setup_logging', 'get_logger', 'logger']