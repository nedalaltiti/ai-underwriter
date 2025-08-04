# services/document-parser/src/utils/logging.py
"""Logging utilities for document-parser service."""

import logging
import sys
from typing import Optional

from config import config


def setup_logging() -> None:
    """Setup logging configuration for the service."""
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-5s | %(name)s | %(message)s',
        datefmt='%b%d %H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.INFO)
    
    # Service-specific logger
    service_logger = logging.getLogger(config.service_name)
    service_logger.info(f"🚀 Starting {config.service_name} v{config.service_version}")
    service_logger.info(f"Environment: {config.environment}")
    service_logger.info(f"Log level: {config.log_level}")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (defaults to service name)
        
    Returns:
        Logger instance
    """
    if name is None:
        name = config.service_name
    return logging.getLogger(name)