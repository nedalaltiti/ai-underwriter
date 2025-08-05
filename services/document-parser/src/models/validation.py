# services/document-parser/src/models/validation.py
"""Models for document validation."""

from typing import Optional

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Model for validation results."""
    field: str
    passed: bool
    reason: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    severity: str = Field(default="medium")  # low, medium, high, critical
    category: str = Field(default="general")  # general, financial, legal, compliance
    
    @property
    def is_critical(self) -> bool:
        """Check if this is a critical validation failure."""
        return self.severity == "critical" and not self.passed
    
    @property
    def is_blocking(self) -> bool:
        """Check if this validation failure should block processing."""
        return self.severity in ["high", "critical"] and not self.passed