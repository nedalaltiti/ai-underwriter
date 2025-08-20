# services/document-parser/src/utils/logging.py
"""Professional logging utilities for document-parser service."""

import sys
from typing import Optional
from loguru import logger
from config import config


def setup_logging() -> None:
    """Setup professional JSON logging configuration."""
    # Remove default loguru handler
    logger.remove()
    
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name} | {message}",
        level=config.log_level,
        serialize=True,  
        enqueue=True,    # Thread-safe
        catch=True       # Catch exceptions
    )
    
    # Configure external library logging levels
    import logging
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    
    # Service startup log
    logger.bind(service=config.service_name, version=config.service_version).info(
        f"service.start name={config.service_name} version={config.service_version} env={config.environment}"
    )


def get_logger(name: Optional[str] = None):
    """
    Get a loguru logger instance with service context.
    
    Args:
        name: Logger name (defaults to service name)
        
    Returns:
        Loguru logger instance
    """
    if name is None:
        name = config.service_name
    
    return logger.bind(service=config.service_name, module=name)