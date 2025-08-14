# services/document-downloader/src/utils/file_operations.py
"""Utilities for file operations and S3 key generation."""

from pathlib import Path
from datetime import datetime, UTC
from typing import Optional
from models.download import DownloadTask


def generate_s3_key(task: DownloadTask, s3_prefix: str = "") -> str:
    """
    Generate S3 key for document storage.
    
    Uses date partitioning for better organization and performance.
    Format: {year}/{month}/{day}/{contact_id}/{doc_id}/{filename}
    
    Args:
        task: Download task containing document information
        s3_prefix: S3 key prefix (default: "" - no prefix)
        
    Returns:
        Generated S3 key for the document
    """
    # Use date partitioning for better organization (date first)
    date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
    
    # Clean filename - ensure it's safe for S3
    filename = task.doc_name or f"{task.doc_id}.pdf"
    safe_filename = Path(filename).name
    
    # Generate key with hierarchical structure: date/contact_id/doc_id/filename
    if s3_prefix:
        return f"{s3_prefix}/{date_prefix}/{task.contact_id}/{task.doc_id}/{safe_filename}"
    else:
        return f"{date_prefix}/{task.contact_id}/{task.doc_id}/{safe_filename}"


def get_file_extension_from_filename(filename: str) -> str:
    """
    Extract file extension from filename.
    
    Args:
        filename: The filename to extract extension from
        
    Returns:
        File extension including the dot (e.g., ".pdf"), or ".pdf" as default
    """
    if not filename:
        return ".pdf"
    
    return Path(filename).suffix or ".pdf"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage.
    
    Removes or replaces characters that might cause issues in file systems
    or S3 storage while preserving the original name as much as possible.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for storage
    """
    if not filename:
        return "document.pdf"
    
    # Get the Path object for easier manipulation
    path = Path(filename)
    name = path.stem
    extension = path.suffix or ".pdf"
    
    # Replace problematic characters but preserve Unicode characters
    # Only replace characters that are problematic for file systems
    problematic_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
    
    for char in problematic_chars:
        name = name.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    name = name.strip(' .')
    
    # Ensure name is not empty
    if not name:
        name = "document"
    
    return f"{name}{extension}"



def get_content_type_from_extension(extension: str) -> str:
    """
    Get MIME content type from file extension.
    
    Args:
        extension: File extension (with or without dot)
        
    Returns:
        MIME content type string
    """
    # Normalize extension
    ext = extension.lower().lstrip('.')
    
    content_types = {
        'pdf': 'application/pdf',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain',
        'rtf': 'application/rtf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'tiff': 'image/tiff',
        'tif': 'image/tiff',
    }
    
    return content_types.get(ext, 'application/octet-stream') 