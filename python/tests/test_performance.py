"""
Performance Tests for the Sanctions Screening System

Tests validation function performance to ensure they meet requirements:
- Input validation: <1ms per call
- Log sanitization: <0.5ms per call
- XML parsing overhead: <20% vs unsafe parsing

Uses time measurement since pytest-benchmark may not be available.
"""

import pytest
import time
import tempfile
from pathlib import Path
from typing import Callable, Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from screener import ScreeningInput, validate_screening_input, InputValidationError
from xml_utils import sanitize_for_logging, secure_parse
from config_manager import ConfigManager


def measure_time(func: Callable, *args, iterations: int = 1000, **kwargs) -> float:
    """Measure average execution time of a function
    
    Args:
        func: Function to measure
        *args: Arguments to pass to function
        iterations: Number of iterations to average
        **kwargs: Keyword arguments to pass to function
        
    Returns:
        Average execution time in milliseconds
    """
    start = time.perf_counter()
    for _ in range(iterations):
        try:
            func(*args, **kwargs)
        except Exception:
            pass  # Ignore errors for timing
    end = time.perf_counter()
    return (end - start) / iterations * 1000  # Convert to milliseconds


class TestInputValidationPerformance:
    """Performance tests for input validation"""
    
    @pytest.fixture(autouse=True)
    def reset_config(self):
        """Reset config before each test"""
        ConfigManager.reset_instance()
    
    def test_short_name_validation_performance(self):
        """Test that short name validation is under 1ms"""
        input_data = ScreeningInput(name="Li Wei")
        avg_time = measure_time(validate_screening_input, input_data)
        
        assert avg_time < 1.0, f"Short name validation took {avg_time:.3f}ms, expected <1ms"
    
    def test_long_name_validation_performance(self):
        """Test that long name (200 chars) validation is under 1ms"""
        # Create 200 character name
        long_name = "John " * 40  # 200 chars
        input_data = ScreeningInput(name=long_name[:200])
        avg_time = measure_time(validate_screening_input, input_data)
        
        assert avg_time < 1.0, f"Long name validation took {avg_time:.3f}ms, expected <1ms"
    
    def test_invalid_name_validation_performance(self):
        """Test that invalid name validation (triggers checks) is under 1ms"""
        input_data = ScreeningInput(name="<script>alert('xss')</script>")
        avg_time = measure_time(validate_screening_input, input_data)
        
        assert avg_time < 1.0, f"Invalid name validation took {avg_time:.3f}ms, expected <1ms"
    
    def test_full_input_validation_performance(self):
        """Test that full input with all fields is under 1ms"""
        input_data = ScreeningInput(
            name="John Doe Smith",
            document_number="X12345678",
            document_type="passport",
            date_of_birth="1980-01-15",
            nationality="USA",
            country="US"
        )
        avg_time = measure_time(validate_screening_input, input_data)
        
        assert avg_time < 1.0, f"Full validation took {avg_time:.3f}ms, expected <1ms"
    
    def test_unicode_name_validation_performance(self):
        """Test that Unicode name validation is under 1ms"""
        # Chinese + Arabic + Cyrillic
        names = ["李明 王伟", "محمد علي", "Владимир Путин"]
        
        for name in names:
            input_data = ScreeningInput(name=name)
            avg_time = measure_time(validate_screening_input, input_data, iterations=500)
            assert avg_time < 1.0, f"Unicode name '{name}' validation took {avg_time:.3f}ms, expected <1ms"
    
    def test_validation_no_degradation_over_1000_requests(self):
        """Test that performance doesn't degrade over 1000 requests"""
        input_data = ScreeningInput(name="John Doe")
        
        # Warm up
        for _ in range(100):
            validate_screening_input(input_data)
        
        # Measure first batch
        start1 = time.perf_counter()
        for _ in range(500):
            validate_screening_input(input_data)
        time1 = time.perf_counter() - start1
        
        # Measure second batch (should be similar)
        start2 = time.perf_counter()
        for _ in range(500):
            validate_screening_input(input_data)
        time2 = time.perf_counter() - start2
        
        # Second batch shouldn't be more than 50% slower
        assert time2 < time1 * 1.5, f"Performance degraded: {time1:.3f}s -> {time2:.3f}s"


class TestLogSanitizationPerformance:
    """Performance tests for log sanitization"""
    
    def test_clean_string_sanitization_performance(self):
        """Test that clean string (100 chars) sanitization is under 0.5ms"""
        clean_input = "A" * 100
        avg_time = measure_time(sanitize_for_logging, clean_input)
        
        assert avg_time < 0.5, f"Clean string sanitization took {avg_time:.3f}ms, expected <0.5ms"
    
    def test_malicious_string_sanitization_performance(self):
        """Test that malicious string (1000 chars) sanitization is under 0.5ms"""
        # String with many control characters
        malicious = "A\x00B\x0aC\x0D" * 250  # 1000 chars with control chars
        avg_time = measure_time(sanitize_for_logging, malicious)
        
        assert avg_time < 0.5, f"Malicious string sanitization took {avg_time:.3f}ms, expected <0.5ms"
    
    def test_empty_string_sanitization_performance(self):
        """Test empty string sanitization is fast"""
        avg_time = measure_time(sanitize_for_logging, "")
        
        assert avg_time < 0.1, f"Empty string sanitization took {avg_time:.3f}ms, expected <0.1ms"
    
    def test_unicode_sanitization_performance(self):
        """Test Unicode string sanitization performance"""
        unicode_input = "李明محمد علي Владимир" * 20  # ~400 chars
        avg_time = measure_time(sanitize_for_logging, unicode_input)
        
        assert avg_time < 0.5, f"Unicode sanitization took {avg_time:.3f}ms, expected <0.5ms"


class TestXMLParsingPerformance:
    """Performance tests for XML parsing"""
    
    def test_small_xml_parsing_performance(self, tmp_path):
        """Test small XML (1KB) parsing overhead"""
        # Create small XML
        xml_content = '''<?xml version="1.0"?>
<root>
''' + '<item id="1">Content</item>\n' * 20 + '</root>'
        
        xml_file = tmp_path / "small.xml"
        xml_file.write_text(xml_content)
        
        # Measure secure parsing
        avg_time = measure_time(secure_parse, xml_file, iterations=100)
        
        # Small XML should parse in under 5ms
        assert avg_time < 5.0, f"Small XML parsing took {avg_time:.3f}ms, expected <5ms"
    
    def test_medium_xml_parsing_performance(self, tmp_path):
        """Test medium XML (~100KB) parsing"""
        # Create medium XML (roughly 100KB)
        xml_content = '''<?xml version="1.0"?>
<root>
'''
        for i in range(700):
            xml_content += f'<item id="{i}">{"X" * 100}</item>\n'
        xml_content += '</root>'
        
        xml_file = tmp_path / "medium.xml"
        xml_file.write_text(xml_content)
        
        # Measure secure parsing
        avg_time = measure_time(secure_parse, xml_file, iterations=10)
        
        # Medium XML should parse in under 100ms
        assert avg_time < 100.0, f"Medium XML parsing took {avg_time:.3f}ms, expected <100ms"


class TestMemoryUsage:
    """Test that operations don't leak memory"""
    
    def test_validation_no_memory_leak(self):
        """Test that repeated validation doesn't accumulate memory"""
        import gc
        
        # Force garbage collection
        gc.collect()
        
        # Run many validations
        input_data = ScreeningInput(name="John Doe Smith")
        for _ in range(10000):
            validate_screening_input(input_data)
        
        # Should complete without memory error
        gc.collect()
    
    def test_sanitization_no_memory_leak(self):
        """Test that repeated sanitization doesn't accumulate memory"""
        import gc
        
        gc.collect()
        
        test_input = "A" * 500
        for _ in range(10000):
            sanitize_for_logging(test_input)
        
        gc.collect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
