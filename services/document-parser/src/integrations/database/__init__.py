# services/document-parser/src/integrations/database/__init__.py
"""Database integration package for document-parser."""

from .adapter import UnderwritingDatabaseAdapter

__all__ = ['UnderwritingDatabaseAdapter']
