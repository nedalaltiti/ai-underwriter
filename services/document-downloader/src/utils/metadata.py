# services/document-downloader/src/utils/metadata.py
"""Utilities for handling S3 metadata and non-ASCII characters."""

import base64
from loguru import logger


def sanitize_metadata_value(value: str) -> str:
    """
    Sanitize metadata value to contain only ASCII characters.
    
    AWS S3 metadata can only contain ASCII characters. This function
    replaces non-ASCII characters with safe placeholders.
    
    Args:
        value: Original metadata value
        
    Returns:
        ASCII-only version of the value
    """
    if not value:
        return ""
    
    try:
        # Try to encode as ASCII - if it works, return as-is
        value.encode('ascii')
        return value
    except UnicodeEncodeError:
        # Contains non-ASCII characters, create a safe version
        # Replace non-ASCII characters with safe placeholders
        ascii_chars = []
        for char in value:
            try:
                char.encode('ascii')
                ascii_chars.append(char)
            except UnicodeEncodeError:
                # Replace with a safe placeholder
                ascii_chars.append('?')
        
        sanitized = ''.join(ascii_chars)
        logger.debug(f"Sanitized metadata: '{value}' -> '{sanitized}'")
        return sanitized


def encode_non_ascii_metadata(value: str) -> str:
    """
    Encode non-ASCII metadata value as base64 for preservation.
    
    This allows storing the original non-ASCII value in a way that's
    compatible with S3 metadata restrictions, while preserving the
    ability to reconstruct the original value.
    
    Args:
        value: Original metadata value
        
    Returns:
        Base64 encoded value if contains non-ASCII, otherwise original value
    """
    if not value:
        return ""
    
    try:
        # Try to encode as ASCII - if it works, return as-is
        value.encode('ascii')
        return value
    except UnicodeEncodeError:
        # Contains non-ASCII characters, encode as base64
        encoded_bytes = value.encode('utf-8')
        base64_value = base64.b64encode(encoded_bytes).decode('ascii')
        logger.debug(f"Base64 encoded metadata: '{value}' -> '{base64_value}'")
        return base64_value


def decode_base64_metadata(encoded_value: str) -> str:
    """
    Decode base64-encoded metadata value back to original.
    
    Args:
        encoded_value: Base64 encoded metadata value
        
    Returns:
        Original decoded value, or encoded_value if not base64
    """
    if not encoded_value:
        return ""
    
    try:
        # Try to decode as base64
        decoded_bytes = base64.b64decode(encoded_value)
        decoded_value = decoded_bytes.decode('utf-8')
        return decoded_value
    except Exception:
        # Not base64 encoded, return as-is
        return encoded_value


def prepare_s3_metadata(metadata: dict) -> dict:
    """
    Prepare metadata dictionary for S3 upload by sanitizing all values.
    
    Args:
        metadata: Dictionary of metadata key-value pairs
        
    Returns:
        Dictionary with ASCII-safe metadata values
    """
    sanitized_metadata = {}
    
    for key, value in metadata.items():
        if isinstance(value, str):
            # For string values, sanitize and preserve original if needed
            sanitized_value = sanitize_metadata_value(value)
            sanitized_metadata[key] = sanitized_value
            
            # If the value was changed, also store the original encoded version
            if sanitized_value != value:
                original_key = f"{key}_original"
                sanitized_metadata[original_key] = encode_non_ascii_metadata(value)
        else:
            # For non-string values, convert to string and sanitize
            str_value = str(value)
            sanitized_metadata[key] = sanitize_metadata_value(str_value)
    
    return sanitized_metadata 