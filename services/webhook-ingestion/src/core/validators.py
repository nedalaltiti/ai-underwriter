# services/webhook-ingestion/src/core/validators.py
import re
from typing import Dict, Any, Optional
from datetime import datetime, UTC
from loguru import logger

from models.requests import WebhookPayload, WebhookSource
from core.exceptions import ValidationError


class WebhookValidator:
    """Validates incoming webhook data."""
    
    def __init__(self) -> None:
        # Patterns for validation
        self.contact_id_pattern = re.compile(r'^\d+$')
        self.doc_id_pattern = re.compile(r'^\d+$')
        
        # Known document types
        self.valid_doc_types = {
            "agreement", "contract", "hardship", "bank_statement",
            "paystub", "tax_return", "identification", "other"
        }
    
    def validate_webhook(self, data: Dict[str, Any]) -> WebhookPayload:
        """
        Validate webhook data and return structured payload.
        
        Args:
            data: Raw webhook data
            
        Returns:
            Validated WebhookPayload
            
        Raises:
            ValidationError: If validation fails
        """
        try:
            # Extract required fields
            contact_id = self._validate_contact_id(data)
            doc_id = self._validate_doc_id(data)
            doc_type = self._validate_doc_type(data)
            
            # Extract optional fields
            doc_name = self._extract_doc_name(data)
            correlation_id = data.get("correlation_id") or self._generate_correlation_id()
            source = self._determine_source(data)
            
            # Extract additional fields
            doc_url = data.get("doc_url")
            hardship_description = data.get("hardship_description")
            
            # Create validated payload
            payload = WebhookPayload(
                contact_id=contact_id,
                doc_id=doc_id,
                doc_type=doc_type,
                doc_name=doc_name,
                correlation_id=correlation_id,
                source=source,
                raw_data=data,
                doc_url=doc_url,
                hardship_description=hardship_description
            )
            
            logger.debug(f"Webhook validated: {payload.contact_id}/{payload.doc_id}")
            return payload
            
        except KeyError as e:
            raise ValidationError(f"Missing required field: {e}")
        except ValueError as e:
            raise ValidationError(f"Invalid field value: {e}")
        except Exception as e:
            logger.error(f"Unexpected validation error: {e}")
            raise ValidationError(f"Validation failed: {str(e)}")
    
    def _validate_contact_id(self, data: Dict[str, Any]) -> str:
        """Validate contact ID."""
        contact_id = data.get("contact_id", "").strip()
        
        if not contact_id:
            raise ValidationError("contact_id is required")
        
        if not self.contact_id_pattern.match(contact_id):
            raise ValidationError(f"Invalid contact_id format: {contact_id}")
        
        return contact_id
    
    def _validate_doc_id(self, data: Dict[str, Any]) -> str:
        """Validate document ID."""
        # Try multiple possible field names
        doc_id = (
            data.get("doc_id") or 
            data.get("document_id") or 
            data.get("id", "")
        ).strip()
        
        if not doc_id:
            raise ValidationError("doc_id is required")
        
        # Handle comma-separated IDs (Forth CRM sometimes sends multiple)
        if "," in doc_id:
            doc_ids = [id.strip() for id in doc_id.split(",") if id.strip()]
            # Take the last valid numeric ID
            for id in reversed(doc_ids):
                if self.doc_id_pattern.match(id):
                    logger.bind(
                        selected_doc_id=id,
                        all_doc_ids=doc_id
                    ).info(
                        f"📄 Multiple doc_ids received, using: {id}"
                    )
                    return id
            raise ValidationError(f"No valid doc_id found in: {doc_id}")
        
        if not self.doc_id_pattern.match(doc_id):
            raise ValidationError(f"Invalid doc_id format: {doc_id}")
        
        return doc_id
    
    def _validate_doc_type(self, data: Dict[str, Any]) -> str:
        """Validate document type."""
        doc_type = data.get("doc_type", "agreement").strip().lower()
        
        # Handle complex doc types like "contract / agreement"
        if "/" in doc_type:
            # Take the first valid part
            parts = [part.strip() for part in doc_type.split("/")]
            for part in parts:
                if part in ["contract", "agreement"]:
                    doc_type = "agreement"
                    break
                elif part in self.valid_doc_types:
                    doc_type = part
                    break
            else:
                doc_type = parts[0]  # Fallback to first part
        
        # Map common variations
        type_mapping = {
            "contract": "agreement",
            "agreement": "agreement", 
            "hardship": "hardship",
            "bank": "bank_statement",
            "bank_statement": "bank_statement",
            "paystub": "paystub",
            "pay_stub": "paystub",
            "tax": "tax_return",
            "tax_return": "tax_return",
            "id": "identification",
            "identification": "identification"
        }
        
        normalized_type = type_mapping.get(doc_type, doc_type)
        
        if normalized_type not in self.valid_doc_types:
            logger.bind(
                original_type=data.get("doc_type", ""),
                normalized_type="other"
            ).warning(
                f"⚠️  Unknown document type '{data.get('doc_type', '')}', using 'other'"
            )
            normalized_type = "other"
        
        return normalized_type
    
    def _extract_doc_name(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract document name from various fields."""
        doc_name = (
            data.get("doc_name") or
            data.get("document_name") or
            data.get("filename") or
            data.get("file_name")
        )
        
        if doc_name:
            # Clean filename
            doc_name = str(doc_name).strip()
            # Remove any path components
            doc_name = doc_name.split("/")[-1].split("\\")[-1]
            
        return doc_name
    
    def _determine_source(self, data: Dict[str, Any]) -> WebhookSource:
        """Determine webhook source."""
        source = data.get("source", "").lower()
        
        if source == "manual":
            return WebhookSource.MANUAL
        elif source == "test":
            return WebhookSource.TEST
        else:
            # Default to Forth CRM
            return WebhookSource.FORTH_CRM
    
    def _generate_correlation_id(self) -> str:
        """Generate correlation ID if not provided."""
        from uuid import uuid4
        now = datetime.now(UTC)
        return f"webhook-{uuid4().hex[:8]}-{int(now.timestamp())}"
