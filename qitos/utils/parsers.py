"""
LLM Output Parsing Utilities

Standard library for parsing and processing LLM output.
Provides robust parsing functions for common formats.
"""

import re
import json
from typing import Any, Dict, List, Optional, Union


def parse_bullet_points(text: str) -> List[str]:
    """
    Parse bullet points from text.
    
    Handles various bullet formats:
    - Numbered lists: "1. Item", "2) Item"
    - Dashes: "- Item", "− Item" (en dash)
    - Asterisks: "* Item"
    
    Args:
        text: Input text containing bullet points
        
    Returns:
        List of cleaned bullet point strings
        
    Example:
        >>> text = "1. First item\\n2. Second item\\n- Third item"
        >>> parse_bullet_points(text)
        ['First item', 'Second item', 'Third item']
    """
    if not text or not text.strip():
        return []
    
    lines = text.split('\n')
    result = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            continue
        
        patterns = [
            r'^\d+\.\s+(.+)$',
            r'^\d+\)\s+(.+)$',
            r'^-\s+(.+)$',
            r'^−\s+(.+)$',
            r'^\*\s+(.+)$',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, stripped)
            if match:
                result.append(match.group(1).strip())
                break
    
    return result


def parse_json_block(text: str) -> Optional[Union[dict, list]]:
    """
    Extract and parse JSON from triple backtick code blocks.
    
    Finds the first JSON object/array inside:
    ```json
    {...}
    ```
    
    Args:
        text: Input text that may contain JSON code blocks
        
    Returns:
        Parsed JSON object/list, or None if parsing fails
        
    Example:
        >>> text = "Here is the JSON:\\n```json\\n{\\"key\\": \\"value\\"}\\n```"
        >>> parse_json_block(text)
        {'key': 'value'}
    """
    if not text:
        return None
    
    patterns = [
        r'```json\s*\n(.+?)\n\s*```',
        r'```\s*\n(.+?)\n\s*```',
        r'\{\s*"[^"]+"\s*:',
        r'\[\s*\{',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1) if match.lastindex else match.group(0)
            
            json_str = json_str.strip()
            
            if json_str.startswith('{') or json_str.startswith('['):
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
    
    return None


def parse_kv_pairs(text: str) -> Dict[str, str]:
    """
    Parse key-value pairs from text.
    
    Handles formats like:
    - "Key: Value"
    - "Key = Value"
    - "Key - Value"
    
    Args:
        text: Input text containing key-value pairs
        
    Returns:
        Dictionary of parsed key-value pairs
        
    Example:
        >>> text = "name: John\\nage: 30\\ncity: New York"
        >>> parse_kv_pairs(text)
        {'name': 'John', 'age': '30', 'city': 'New York'}
    """
    result = {}
    
    if not text:
        return result
    
    lines = text.split('\n')
    
    separators = [':', '=', '-']
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            continue
        
        for sep in separators:
            if sep in stripped:
                parts = stripped.split(sep, 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    
                    if key and value:
                        result[key] = value
                    break
    
    return result


def extract_thought(text: str) -> Optional[str]:
    """
    Extract thought/reasoning content from LLM output.
    
    Looks for:
    - "Thought: ..." sections
    - "Reasoning: ..." sections
    
    Args:
        text: LLM output text
        
    Returns:
        Extracted thought content, or None if not found
    """
    if not text:
        return None
    
    patterns = [
        r'(?:Thought|Reasoning)[:：]\s*(.+?)(?=\n(?:Action|Final Answer)|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            thought = match.group(1).strip()
            if thought:
                return thought
    
    return None


def extract_final_answer(text: str) -> Optional[str]:
    """
    Extract final answer from LLM output.
    
    Looks for "Final Answer:" or "Answer:" markers.
    
    Args:
        text: LLM output text
        
    Returns:
        Extracted final answer, or None if not found
    """
    if not text:
        return None
    
    patterns = [
        r'(?:Final Answer|Answer|Final)[:：]\s*(.+?)(?=$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            answer = match.group(1).strip()
            if answer:
                return answer
    
    return None


def clean_action_text(text: str) -> str:
    """
    Clean and normalize action text.
    
    Removes extra whitespace and normalizes newlines.
    
    Args:
        text: Raw action text
        
    Returns:
        Cleaned action text
    """
    if not text:
        return ""
    
    lines = text.split('\n')
    cleaned = [line.strip() for line in lines if line.strip()]
    
    return '\n'.join(cleaned)


def parse_action_blocks(text: str) -> List[str]:
    """
    Parse multiple action blocks from text.
    
    Extracts content between "Action:" markers.
    
    Args:
        text: Input text containing actions
        
    Returns:
        List of action strings
    """
    if not text:
        return []
    
    pattern = r'(?:Action|Action \d+)[:：]\s*(.+?)(?=(?:Action|Action \d+)|$)'
    
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    
    return [match.strip() for match in matches if match.strip()]


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in text.
    
    Collapses multiple spaces and newlines.
    
    Args:
        text: Input text
        
    Returns:
        Text with normalized whitespace
    """
    if not text:
        return ""
    
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()
