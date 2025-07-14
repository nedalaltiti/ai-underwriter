# shared/forth_shared/utils/logging.py
import sys
import json
from typing import Any, Dict
from loguru import logger
from pythonjsonlogger import jsonlogger


class CorrelationIdFilter:
    """Add correlation ID to log records."""
    
    def __init__(self, correlation_id_getter):
        self.correlation_id_getter = correlation_id_getter
    
    def __call__(self, record):
        record["extra"]["correlation_id"] = self.correlation_id_getter()
        return True


def setup_logging(
    service_name: str,
    log_level: str = "INFO",
    log_format: str = "json"
):
    """Setup structured logging with loguru."""
    # Remove default logger
    logger.remove()
    
    # Configure format
    if log_format == "json":
        # JSON format for production with ISO timestamps
        logger.add(
            sys.stdout,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {message}",
            serialize=True,
            enqueue=True,
            backtrace=True,
            diagnose=False
        )
    else:
        # Human-readable format for development
        def custom_format(record):
            """Custom formatter for development logging."""
            try:
                time_str = record["time"].strftime("%b%d %H:%M:%S")  # Jul12 00:34:18
                level = record["level"].name
                service = record.get("extra", {}).get("service", "")
                message = record["message"]
                
                # Add structured data if available
                extra_data = []
                extra = record.get("extra", {})
                for key in ["contact_id", "doc_id", "doc_type", "correlation_id", "processing_time_ms"]:
                    if key in extra:
                        value = extra[key]
                        # Skip template values and empty values
                        if value and value != "-" and not str(value).startswith("{"):
                            extra_data.append(f"{key}={value}")
                
                extra_str = f" [{', '.join(extra_data)}]" if extra_data else ""
                
                # Color coding
                if level == "INFO":
                    level_color = "\033[36m"  # Cyan
                elif level == "WARNING":
                    level_color = "\033[33m"  # Yellow
                elif level == "ERROR":
                    level_color = "\033[31m"  # Red
                else:
                    level_color = "\033[37m"  # White
                
                reset = "\033[0m"
                green = "\033[32m"
                cyan = "\033[36m"
                
                return f"{green}{time_str}{reset} | {level_color}{level:<5}{reset} | {cyan}{service}{reset} | {message}{extra_str}\n"
            except Exception as e:
                # Fallback to simple format if custom formatting fails
                return f"{record['time'].strftime('%b%d %H:%M:%S')} | {record['level'].name} | {record['message']}\n"
        
        logger.add(
            sys.stdout,
            level=log_level,
            format=custom_format,
            colorize=False,  # We handle colors manually
            enqueue=True,
            backtrace=True,
            diagnose=True
        )
    
    # Add service name to all logs
    logger.configure(extra={"service": service_name, "correlation_id": "-"})
    
    # Log startup
    logger.info(
        f"Logging initialized | format={log_format} | level={log_level}",
        service=service_name,
        level=log_level,
        format=log_format
    )
