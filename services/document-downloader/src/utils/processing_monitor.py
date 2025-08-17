# services/document-downloader/src/utils/processing_monitor.py
from typing import Dict, Set, List, Optional
from collections import defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class DocumentProcessingStats:
    """Statistics for document processing."""
    doc_id: str
    contact_id: str
    first_seen: datetime
    last_seen: datetime
    attempt_count: int = 0
    status: str = "processing"
    error_message: Optional[str] = None
    correlation_ids: Set[str] = field(default_factory=set)
    
    def add_attempt(self, correlation_id: Optional[str] = None):
        """Record a processing attempt."""
        self.attempt_count += 1
        self.last_seen = datetime.utcnow()
        if correlation_id:
            self.correlation_ids.add(correlation_id)


class ProcessingMonitor:
    """Monitor document processing to provide clearer insights."""
    
    def __init__(self):
        self._documents: Dict[str, DocumentProcessingStats] = {}
        self._last_summary = datetime.utcnow()
        
    def _get_doc_key(self, contact_id: str, doc_id: str) -> str:
        """Generate unique key for document."""
        return f"{contact_id}:{doc_id}"
    
    def record_processing_start(self, contact_id: str, doc_id: str, correlation_id: Optional[str] = None):
        """Record that document processing has started."""
        doc_key = self._get_doc_key(contact_id, doc_id)
        
        if doc_key not in self._documents:
            self._documents[doc_key] = DocumentProcessingStats(
                doc_id=doc_id,
                contact_id=contact_id,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
        
        self._documents[doc_key].add_attempt(correlation_id)
        
        # Log if this is a repeated attempt
        stats = self._documents[doc_key]
        if stats.attempt_count > 1:
            logger.bind(
                contact_id=contact_id,
                doc_id=doc_id,
                attempt_count=stats.attempt_count,
                correlation_id=correlation_id,
                unique_correlations=len(stats.correlation_ids)
            ).warning(f"attempt.reprocess contact={contact_id} doc={doc_id} count={stats.attempt_count}")
    
    def record_processing_result(self, contact_id: str, doc_id: str, success: bool, error_message: Optional[str] = None):
        """Record the result of document processing."""
        doc_key = self._get_doc_key(contact_id, doc_id)
        
        if doc_key not in self._documents:
            # This shouldn't happen, but handle gracefully
            self._documents[doc_key] = DocumentProcessingStats(
                doc_id=doc_id,
                contact_id=contact_id,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
        
        stats = self._documents[doc_key]
        stats.status = "completed" if success else "failed"
        stats.error_message = error_message
        stats.last_seen = datetime.utcnow()
        
        # Log result with context
        if success:
            logger.bind(
                contact_id=contact_id,
                doc_id=doc_id,
                total_attempts=stats.attempt_count,
                processing_duration_seconds=(stats.last_seen - stats.first_seen).total_seconds()
            ).info(f"process.completed contact={contact_id} doc={doc_id}")
        else:
            logger.bind(
                contact_id=contact_id,
                doc_id=doc_id,
                total_attempts=stats.attempt_count,
                error_message=error_message,
                processing_duration_seconds=(stats.last_seen - stats.first_seen).total_seconds(),
                unique_correlations=len(stats.correlation_ids)
            ).warning(f"process.failed contact={contact_id} doc={doc_id}")
    
    def record_permanent_failure(self, contact_id: str, doc_id: str, error_message: str, sent_to_dlq: bool = True):
        """Record that a document has been permanently failed."""
        self.record_processing_result(contact_id, doc_id, False, error_message)
        
        doc_key = self._get_doc_key(contact_id, doc_id)
        if doc_key in self._documents:
            stats = self._documents[doc_key]
            stats.status = "permanent_failure"
            
            if sent_to_dlq:
                log_message = f"process.permanent_failure contact={contact_id} doc={doc_id} dlq=true"
                log_level = "error"
            else:
                log_message = f"process.not_found_deleted contact={contact_id} doc={doc_id} dlq=false"
                log_level = "info"
                
            bound_logger = logger.bind(
                contact_id=contact_id,
                doc_id=doc_id,
                total_attempts=stats.attempt_count,
                error_message=error_message,
                unique_correlations=len(stats.correlation_ids),
                first_seen=stats.first_seen.isoformat(),
                duration_minutes=(stats.last_seen - stats.first_seen).total_seconds() / 60
            )
            
            if log_level == "error":
                bound_logger.error(log_message)
            else:
                bound_logger.info(log_message)
    
    def get_processing_summary(self) -> Dict[str, any]:
        """Get a summary of current processing status."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        
        # Filter to recent documents
        recent_docs = {
            key: stats for key, stats in self._documents.items()
            if stats.last_seen > cutoff
        }
        
        # Calculate statistics
        total_documents = len(recent_docs)
        completed = sum(1 for stats in recent_docs.values() if stats.status == "completed")
        failed = sum(1 for stats in recent_docs.values() if stats.status == "failed")
        permanent_failures = sum(1 for stats in recent_docs.values() if stats.status == "permanent_failure")
        processing = sum(1 for stats in recent_docs.values() if stats.status == "processing")
        
        # Find documents with multiple attempts
        repeated_attempts = {
            key: stats for key, stats in recent_docs.items()
            if stats.attempt_count > 1
        }
        
        # Most common errors
        error_counts: Dict[str, int] = {}
        for stats in recent_docs.values():
            if stats.error_message:
                error_counts[stats.error_message] = error_counts.get(stats.error_message, 0) + 1
        
        return {
            "summary": {
                "total_documents_1h": total_documents,
                "completed": completed,
                "failed": failed,
                "permanent_failures": permanent_failures,
                "still_processing": processing,
                "documents_with_retries": len(repeated_attempts)
            },
            "repeated_attempts": {
                key: {
                    "attempts": stats.attempt_count,
                    "unique_correlations": len(stats.correlation_ids),
                    "status": stats.status,
                    "duration_minutes": (stats.last_seen - stats.first_seen).total_seconds() / 60
                }
                for key, stats in repeated_attempts.items()
            },
            "common_errors": dict(sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
            "timestamp": now.isoformat()
        }
    
    def log_periodic_summary(self, force: bool = False):
        """Log a periodic summary of processing status."""
        now = datetime.utcnow()
        
        # Log summary every 5 minutes or if forced
        if not force and (now - self._last_summary).total_seconds() < 300:
            return
            
        summary = self.get_processing_summary()
        self._last_summary = now
        
        s = summary["summary"]
        logger.info(
            f"summary.1h total={s['total_documents_1h']} ok={s['completed']} dlq={s['permanent_failures']} retries={s['documents_with_retries']} processing={s['still_processing']}"
        )
        
        # Log details about repeated attempts
        if summary["repeated_attempts"]:
            for doc_key, details in list(summary["repeated_attempts"].items())[:5]:  # Top 5
                contact_id, doc_id = doc_key.split(":", 1)
                logger.bind(
                    contact_id=contact_id,
                    doc_id=doc_id,
                    **details
                ).warning(f"attempt.multi contact={contact_id} doc={doc_id} attempts={details['attempts']}")
    
    def cleanup_old_entries(self):
        """Clean up old document entries to prevent memory leaks."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        old_keys = [
            key for key, stats in self._documents.items()
            if stats.last_seen < cutoff
        ]
        
        for key in old_keys:
            del self._documents[key]
        
        if old_keys:
            logger.debug(f"🧹 Cleaned up {len(old_keys)} old document entries")


# Global monitor instance
processing_monitor = ProcessingMonitor()
