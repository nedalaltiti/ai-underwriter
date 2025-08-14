# services/document-downloader/src/utils/error_classification.py
from typing import Set
from models.download import DownloadResult, DownloadStatus


def is_permanent_failure(result: DownloadResult) -> bool:
    """
    Determine if a download failure is permanent and should not be retried.
    
    Args:
        result: The download result to classify
        
    Returns:
        True if the failure is permanent, False if it's retryable
    """
    permanent_error_codes: Set[str] = {
        "DOCUMENT_NOT_FOUND",
        "DOCUMENT_EXCLUDED",
        "FORTH_API_UNAUTHORIZED",  # 401 errors are permanent
        "FORTH_API_FORBIDDEN",     # 403 errors are permanent
    }
    
    permanent_statuses: Set[DownloadStatus] = {
        DownloadStatus.NOT_FOUND,
        DownloadStatus.SKIPPED,
    }
    
    return (
        result.error_code in permanent_error_codes or
        result.status in permanent_statuses
    )


def is_successful_completion(result: DownloadResult) -> bool:
    """
    Determine if a result represents a successful completion (including skipped documents).
    
    Args:
        result: The download result to check
        
    Returns:
        True if the operation was successful or the document was appropriately skipped
    """
    return (
        result.success or 
        result.status == DownloadStatus.SKIPPED
    )


def get_failure_category(result: DownloadResult) -> str:
    """
    Categorize the type of failure for logging and metrics purposes.
    
    Args:
        result: The download result to categorize
        
    Returns:
        A string category for the failure type
    """
    if result.success:
        return "success"
    
    if result.status == DownloadStatus.SKIPPED:
        return "skipped"
    
    if result.status == DownloadStatus.NOT_FOUND:
        return "not_found"
    
    if result.error_code:
        if "API" in result.error_code:
            return "api_error"
        elif "NETWORK" in result.error_code:
            return "network_error"
        elif "FILE_SIZE" in result.error_code:
            return "file_size_error"
        elif "TIMEOUT" in result.error_code:
            return "timeout_error"
    
    return "unknown_error"
