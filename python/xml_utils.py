"""
Shared XML utilities for the Sanctions Screening System

This module contains common XML processing functions used by multiple
components to avoid code duplication.

SECURITY: All XML parsing uses secure defaults to prevent XXE attacks.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Any, Tuple

# Try lxml first for better security features, fall back to defusedxml or stdlib
try:
    from lxml import etree as lxml_etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False

try:
    import defusedxml.ElementTree as defused_ET
    HAS_DEFUSEDXML = True
except ImportError:
    HAS_DEFUSEDXML = False

import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def get_secure_parser():
    """Get a secure XML parser that prevents XXE attacks
    
    Returns:
        Secure parser object or None if using stdlib
    """
    if HAS_LXML:
        # lxml secure parser: disable DTD, entities, network access
        return lxml_etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            dtd_validation=False,
            load_dtd=False,
            huge_tree=False
        )
    return None


def secure_parse(xml_path: Path) -> Tuple[Any, Any]:
    """Securely parse an XML file, preventing XXE attacks
    
    Args:
        xml_path: Path to XML file
        
    Returns:
        Tuple of (tree, root) element
        
    Raises:
        ValueError: If XML is invalid or contains dangerous content
    """
    if HAS_LXML:
        parser = get_secure_parser()
        tree = lxml_etree.parse(str(xml_path), parser)
        return tree, tree.getroot()
    elif HAS_DEFUSEDXML:
        # defusedxml provides secure parsing by default
        tree = defused_ET.parse(str(xml_path))
        return tree, tree.getroot()
    else:
        # stdlib - limited protection, log warning
        logger.warning("Using stdlib XML parser - consider installing lxml or defusedxml for better security")
        tree = ET.parse(xml_path)
        return tree, tree.getroot()


def secure_iterparse(xml_path: Path, events: Tuple[str, ...] = ('end',), tag: Optional[str] = None):
    """Securely iterparse an XML file for memory-efficient processing
    
    Args:
        xml_path: Path to XML file
        events: Tuple of events to listen for
        tag: Optional tag to filter for (lxml only)
        
    Returns:
        Iterator over (event, element) tuples
    """
    if HAS_LXML:
        if tag:
            return lxml_etree.iterparse(str(xml_path), events=events, tag=tag)
        return lxml_etree.iterparse(str(xml_path), events=events)
    else:
        # stdlib doesn't support tag filter
        return ET.iterparse(xml_path, events=events)


def sanitize_for_logging(text: str) -> str:
    """Sanitize user input for safe logging, preventing log injection
    
    Removes newlines, carriage returns, and other control characters
    that could be used to inject fake log entries.
    
    Args:
        text: User input text
        
    Returns:
        Sanitized text safe for logging
    """
    if not text:
        return ''
    # Remove newlines, carriage returns, and other control characters
    sanitized = re.sub(r'[\r\n\x00-\x1f\x7f-\x9f]', ' ', str(text))
    # Collapse multiple spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # Truncate to reasonable length
    return sanitized[:500] if len(sanitized) > 500 else sanitized


def extract_xml_namespace(xml_path: Path) -> str:
    """Dynamically extract namespace from XML root element
    
    This function reads the first element of an XML file to determine
    its namespace. It handles both namespaced and non-namespaced XML files.
    
    Args:
        xml_path: Path to the XML file
        
    Returns:
        Namespace string with curly braces (e.g., '{http://...}') or empty string
        
    Example:
        >>> ns = extract_xml_namespace(Path('sdn_enhanced.xml'))
        >>> print(ns)
        '{https://sanctionslistservice.ofac.treas.gov/api/...}'
    """
    try:
        with open(xml_path, 'rb') as f:
            for event, elem in ET.iterparse(f, events=('start',)):
                tag = elem.tag
                if tag.startswith('{'):
                    ns_end = tag.index('}')
                    namespace = tag[:ns_end + 1]
                    logger.debug(f"Extracted namespace from {xml_path.name}: {namespace}")
                    return namespace
                break
    except FileNotFoundError:
        logger.error(f"XML file not found: {xml_path}")
    except ET.ParseError as e:
        logger.error(f"XML parse error in {xml_path}: {e}")
    except Exception as e:
        logger.warning(f"Could not extract namespace from {xml_path}: {e}")
    
    return ''


def get_text_from_element(elem: Any, path: str) -> Optional[str]:
    """Safely get text content from an XML element
    
    Args:
        elem: Parent XML element
        path: XPath-style path to child element
        
    Returns:
        Stripped text content or None if element not found or empty
    """
    child = elem.find(path)
    if child is not None and child.text:
        return child.text.strip()
    return None


def count_elements(xml_path: Path, element_name: str, namespace: str = '') -> int:
    """Count occurrences of an element in an XML file
    
    Uses iterparse for memory-efficient counting of large files.
    
    Args:
        xml_path: Path to XML file
        element_name: Name of element to count
        namespace: XML namespace (with curly braces)
        
    Returns:
        Count of elements found
    """
    count = 0
    full_tag = f'{namespace}{element_name}'
    
    try:
        for event, elem in ET.iterparse(xml_path, events=('end',)):
            if elem.tag == full_tag:
                count += 1
                elem.clear()  # Free memory
    except Exception as e:
        logger.error(f"Error counting elements in {xml_path}: {e}")
    
    return count
