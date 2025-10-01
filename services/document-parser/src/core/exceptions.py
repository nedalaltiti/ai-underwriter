# services/document-parser/src/core/exceptions.py
"""Custom exceptions for document-parser service."""


class DocumentParserError(Exception):
    """Base exception for document-parser service."""
    pass


class ConfigurationError(DocumentParserError):
    """Configuration-related errors."""
    pass


class DocumentProcessingError(DocumentParserError):
    """Document processing errors."""
    pass


class ExtractionError(DocumentProcessingError):
    """Document extraction errors."""
    pass


class ValidationError(DocumentProcessingError):
    """Document validation errors."""
    pass


class GeminiAPIError(DocumentParserError):
    """Gemini API related errors."""
    pass


class GeminiTimeoutError(GeminiAPIError):
    """Gemini API timeout errors."""
    pass


class GeminiRateLimitError(GeminiAPIError):
    """Gemini API rate limit errors."""
    pass


class GeminiMaxTokensError(GeminiAPIError):
    """Gemini API max tokens exceeded error."""
    pass


class DocumentDownloadError(DocumentProcessingError):
    """Document download errors."""
    pass


class DatabaseError(DocumentParserError):
    """Database operation errors."""
    pass


class QueueError(DocumentParserError):
    """Message queue errors."""
    pass


class UnderwritingValidationError(ValidationError):
    """Underwriting validation errors."""
    pass


class RetryableError(DocumentParserError):
    """Base class for retryable errors."""
    pass


class NonRetryableError(DocumentParserError):
    """Base class for non-retryable errors."""
    pass