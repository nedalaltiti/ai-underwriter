# shared/forth_shared/models/base.py
from datetime import datetime, UTC
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from uuid import uuid4


class BaseTimestampModel(BaseModel):
    """Base model with timestamp fields."""
    
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: Optional[datetime] = None


class BaseIdentifiableModel(BaseTimestampModel):
    """Base model with ID and timestamps."""
    
    id: str = Field(default_factory=lambda: str(uuid4()))