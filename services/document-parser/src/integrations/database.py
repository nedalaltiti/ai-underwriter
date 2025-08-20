# services/document-parser/src/integrations/database.py
"""Database integration - backward compatibility bridge."""

# Import from new modular structure
try:
    from .database.adapter import UnderwritingDatabaseAdapter
except ImportError:
    # Fallback for container environment
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), 'database'))
    from adapter import UnderwritingDatabaseAdapter

# Backward compatibility
__all__ = ['UnderwritingDatabaseAdapter']
