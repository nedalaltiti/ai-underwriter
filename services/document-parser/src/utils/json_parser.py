# services/document-parser/src/utils/json_parser.py
"""JSON parsing utilities for extracting structured data from Gemini responses."""

import json
import re
from typing import Any, Dict, Optional
from utils.logging import get_logger

logger = get_logger(__name__)


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from text response that may contain markdown formatting or other text.
    
    Args:
        text: Text response that may contain JSON
        
    Returns:
        Parsed JSON dictionary or None if no valid JSON found
    """
    if not text:
        return None
    
    # Strategy 1: Try to parse the entire text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Look for JSON between ```json and ``` markers
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, text, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Strategy 3: Look for JSON between ``` markers (without json keyword)
    code_pattern = r'```\s*(.*?)\s*```'
    matches = re.findall(code_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Strategy 4: Look for JSON starting with { and ending with } (improved)
    # This pattern handles nested braces better
    def find_json_blocks(text):
        """Find potential JSON blocks by balancing braces."""
        blocks = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                start = i
                brace_count = 1
                i += 1
                while i < len(text) and brace_count > 0:
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                    i += 1
                if brace_count == 0:
                    blocks.append(text[start:i])
            else:
                i += 1
        return blocks
    
    json_blocks = find_json_blocks(text)
    # Sort by length (largest first)
    json_blocks.sort(key=len, reverse=True)
    
    for block in json_blocks:
        try:
            result = json.loads(block)
            # Validate it's a dictionary and has some content
            if isinstance(result, dict) and len(result) > 0:
                return result
        except json.JSONDecodeError:
            continue
    
    # Strategy 5: Try to extract JSON array
    array_pattern = r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]'
    matches = re.findall(array_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            result = json.loads(match)
            # If it's an array, wrap it in a standard structure
            if isinstance(result, list):
                return {"data": result}
        except json.JSONDecodeError:
            continue
    
    # Strategy 6: Handle truncated JSON by attempting repair
    try:
        # Look for incomplete JSON that might be repairable
        if '{' in text and text.count('{') > text.count('}'):
            # Find the main JSON block
            start_idx = text.find('{')
            if start_idx >= 0:
                json_part = text[start_idx:]
                # Add missing closing braces
                missing_braces = json_part.count('{') - json_part.count('}')
                if missing_braces > 0 and missing_braces <= 5:  # Reasonable limit
                    repaired = json_part + '}' * missing_braces
                    try:
                        result = json.loads(repaired)
                        logger.warning(f"Repaired truncated JSON by adding {missing_braces} closing braces")
                        return result
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass

    # Strategy 7: Clean common issues and retry
    cleaned_text = clean_json_text(text)
    if cleaned_text != text:
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
    
    # Strategy 8: Look for JSON after common prefixes
    prefixes = [
        "Here is the JSON:",
        "Here's the JSON:",
        "JSON:",
        "Result:",
        "Output:",
        "Response:",
        "Data:",
        "The extracted data is:",
        "The result is:"
    ]
    
    for prefix in prefixes:
        if prefix in text:
            # Find text after the prefix
            after_prefix = text.split(prefix, 1)[1].strip()
            try:
                return json.loads(after_prefix)
            except json.JSONDecodeError:
                # Try to find JSON in the text after prefix using brace matching
                def find_json_in_text(text):
                    blocks = []
                    i = 0
                    while i < len(text):
                        if text[i] == '{':
                            start = i
                            brace_count = 1
                            i += 1
                            while i < len(text) and brace_count > 0:
                                if text[i] == '{':
                                    brace_count += 1
                                elif text[i] == '}':
                                    brace_count -= 1
                                i += 1
                            if brace_count == 0:
                                blocks.append(text[start:i])
                        else:
                            i += 1
                    return blocks
                
                json_blocks = find_json_in_text(after_prefix)
                for block in json_blocks:
                    try:
                        result = json.loads(block)
                        if isinstance(result, dict) and len(result) > 0:
                            return result
                    except json.JSONDecodeError:
                        continue
    
    logger.debug(f"Could not extract JSON from text: {text[:200]}...")
    return None


def clean_json_text(text: str) -> str:
    """
    Clean common issues in JSON text.
    
    Args:
        text: Text that might contain malformed JSON
        
    Returns:
        Cleaned text
    """
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Remove BOM if present
    if text.startswith('\ufeff'):
        text = text[1:]
    
    # Remove trailing commas before closing braces/bracket
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Handle multiple trailing commas or commas with newlines
    text = re.sub(r',\s*,\s*([}\]])', r'\1', text)  # Remove double commas
    text = re.sub(r',\s*\n\s*([}\]])', r'\n\1', text)  # Remove comma before newline and closing brace
    
    # Replace single quotes with double quotes (careful with apostrophes)
    # Only replace single quotes that are likely JSON string delimiters
    text = re.sub(r"(?<=[{\[,:])\s*'", '"', text)
    text = re.sub(r"'\s*(?=[}\],:])", '"', text)
    
    # Fix unquoted keys (simple cases)
    text = re.sub(r'([{\[,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', text)
    
    # Remove comments (both // and /* */ style)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    
    # Handle None/null confusion
    text = text.replace('None', 'null')
    text = text.replace('True', 'true')
    text = text.replace('False', 'false')
    
    return text


def validate_extracted_data(data: Dict[str, Any]) -> bool:
    """
    Validate that extracted data contains meaningful information.
    
    Args:
        data: Extracted data dictionary
        
    Returns:
        True if data appears valid
    """
    if not data or not isinstance(data, dict):
        return False
    
    # Check if dictionary has content
    if len(data) == 0:
        return False
    
    # Check if at least some values are non-null
    non_null_values = sum(1 for v in data.values() if v is not None and v != "")
    
    # Require at least 20% of fields to have values
    if non_null_values / len(data) < 0.2:
        logger.warning(f"Extracted data has too many null values: {non_null_values}/{len(data)}")
        return False
    
    return True


def merge_json_objects(obj1: Dict[str, Any], obj2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two JSON objects, preferring non-null values from obj2.
    
    Args:
        obj1: First object (base)
        obj2: Second object (updates)
        
    Returns:
        Merged object
    """
    result = obj1.copy()
    
    for key, value in obj2.items():
        if value is not None and value != "":
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = merge_json_objects(result[key], value)
            else:
                result[key] = value
    
    return result