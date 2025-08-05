# services/document-parser/src/utils/json_parser.py
"""JSON parsing utilities for document processing."""

import json
import re
from typing import Any, Dict

from .logging import get_logger

logger = get_logger(__name__)


def extract_json_from_response(response_text: str) -> Dict[str, Any]:
    """
    Extract and parse JSON from text response.
    
    Args:
        response_text: Raw text response potentially containing JSON
        
    Returns:
        Parsed JSON data
    """
    # Try direct parsing first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # Extract first balanced JSON object
    json_obj = _extract_first_json_object(response_text)
    if json_obj:
        try:
            return json.loads(json_obj)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extracted JSON: {e}")
    
    raise ValueError("No valid JSON found in response")


def _extract_first_json_object(text: str) -> str | None:
    """
    Extract the first balanced JSON object from text.
    
    Args:
        text: Text potentially containing JSON
        
    Returns:
        First balanced JSON object or None
    """
    openings = [i for i, c in enumerate(text) if c == "{"]
    
    for start in openings:
        depth = 0
        for end, c in enumerate(text[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:end + 1]
                    # Validate it looks like a JSON object
                    if re.match(r"^\s*\{.*\}\s*$", candidate, re.S):
                        return candidate
                    break
    return None