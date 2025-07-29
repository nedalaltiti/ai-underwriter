# services/document-downloader/src/core/exceptions.py
"""Custom exceptions for document downloader service."""


class DocumentDownloadError(Exception):
    """Base exception for document download errors."""
    pass


class FileSizeExceededError(DocumentDownloadError):
    """Raised when file size exceeds the configured limit."""
    
    def __init__(self, actual_size: int, max_size: int):
        self.actual_size = actual_size
        self.max_size = max_size
        super().__init__(
            f"File size {actual_size} bytes exceeds maximum allowed size {max_size} bytes"
        )


class DownloadTimeoutError(DocumentDownloadError):
    """Raised when download operation times out."""
    pass


class ForthAPIError(DocumentDownloadError):
    """Raised when Forth API returns an error."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Forth API error {status_code}: {message}")


class S3UploadError(DocumentDownloadError):
    """Raised when S3 upload fails."""
    pass


class TempFileError(DocumentDownloadError):
    """Raised when temporary file operations fail."""
    pass 