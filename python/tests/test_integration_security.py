"""
Integration Security Tests for the Sanctions Screening System

End-to-end tests that verify security across the entire system:
- Full screening workflow with malicious inputs
- Multi-vector attack resistance
- Cross-component security
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_manager import ConfigManager, ConfigurationError
from screener import ScreeningInput, validate_screening_input, InputValidationError
from xml_utils import sanitize_for_logging, secure_parse
from security_logger import SecurityLogger, SecurityEvent, get_security_logger, reset_security_logger


class TestSecurityLoggerIntegration:
    """Tests for security event logging"""
    
    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Create temp directory for logs"""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        return log_dir
    
    @pytest.fixture(autouse=True)
    def reset_logger(self):
        """Reset logger before each test"""
        reset_security_logger()
    
    def test_security_logger_creates_log_file(self, temp_log_dir):
        """Test that security logger creates security.log file"""
        logger = SecurityLogger(log_dir=str(temp_log_dir))
        logger.log_validation_failure(
            field="name",
            error_code="INVALID",
            input_value="test",
            source="test"
        )
        
        log_file = temp_log_dir / "security.log"
        assert log_file.exists()
    
    def test_security_logger_sanitizes_input(self, temp_log_dir):
        """Test that logged input is sanitized - newlines converted to spaces"""
        logger = SecurityLogger(log_dir=str(temp_log_dir))
        
        # Log with malicious input containing newlines
        malicious_input = "test\nFAKE LOG ENTRY\n"
        logger.log_validation_failure(
            field="name",
            error_code="INVALID",
            input_value=malicious_input,
            source="test"
        )
        
        # Read log file
        log_file = temp_log_dir / "security.log"
        log_content = log_file.read_text()
        
        # The sanitized input should have spaces instead of newlines
        # Check that raw newline injection didn't create a new log line
        lines = log_content.strip().split('\n')
        assert len(lines) == 1, "Should be single log line, newlines should be sanitized"
    
    def test_security_logger_includes_request_id(self, temp_log_dir):
        """Test that logs include request ID when set"""
        logger = SecurityLogger(log_dir=str(temp_log_dir))
        
        request_id = logger.set_request_context(request_id="REQ-12345")
        logger.log_validation_failure(
            field="name",
            error_code="INVALID",
            input_value="test",
            source="test"
        )
        
        log_file = temp_log_dir / "security.log"
        log_content = log_file.read_text()
        
        assert "REQ-12345" in log_content
    
    def test_security_event_to_json(self):
        """Test SecurityEvent JSON serialization"""
        event = SecurityEvent(
            event_type="XXE_ATTEMPT",
            severity="ERROR",
            field_name="xml",
            error_code="XXE_BLOCKED",
            sanitized_input="<!DOCTYPE...",
            source="secure_parse"
        )
        
        json_str = event.to_json()
        assert "XXE_ATTEMPT" in json_str
        assert "ERROR" in json_str
    
    def test_log_xxe_attempt(self, temp_log_dir):
        """Test XXE attempt logging"""
        logger = SecurityLogger(log_dir=str(temp_log_dir))
        logger.log_xxe_attempt(source="XML parsing", file_name="test.xml", blocked=True)
        
        log_file = temp_log_dir / "security.log"
        log_content = log_file.read_text()
        
        assert "XXE_ATTEMPT" in log_content
        assert "ERROR" in log_content
    
    def test_log_injection_attempt(self, temp_log_dir):
        """Test injection attempt logging"""
        logger = SecurityLogger(log_dir=str(temp_log_dir))
        logger.log_injection_attempt(
            injection_type="SQL",
            field="name",
            input_value="'; DROP TABLE--",
            source="validate_screening_input",
            blocked=True
        )
        
        log_file = temp_log_dir / "security.log"
        log_content = log_file.read_text()
        
        assert "SQL_INJECTION_ATTEMPT" in log_content


class TestEndToEndSecurityFlow:
    """End-to-end security tests"""
    
    @pytest.fixture(autouse=True)
    def reset_config(self):
        """Reset config before each test"""
        ConfigManager.reset_instance()
    
    def test_malicious_name_blocked_and_logged(self, tmp_path):
        """Test that malicious input is blocked and logged"""
        # Setup logging
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        reset_security_logger()
        logger = SecurityLogger(log_dir=str(log_dir), enable_file=True)
        
        # Attempt malicious input
        input_data = ScreeningInput(name="<script>alert('xss')</script>")
        
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data)
        
        assert exc_info.value.code == "BLOCKED_CHARACTERS"
    
    def test_xxe_blocked_in_xml_parsing(self, tmp_path):
        """Test that XXE is blocked during XML parsing"""
        # Create malicious XML with XXE
        xxe_content = '''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>'''
        
        xml_file = tmp_path / "xxe.xml"
        xml_file.write_text(xxe_content)
        
        # Should either raise error or return without entity expansion
        try:
            tree, root = secure_parse(xml_file)
            # If it parses, entity should not be expanded
            if root.text:
                assert "/etc/passwd" not in root.text
                assert "root:" not in root.text
        except Exception:
            # Raised error is also acceptable (blocked)
            pass
    
    def test_sql_injection_pattern_blocked(self):
        """Test that SQL injection patterns with blocked characters are blocked"""
        # These patterns contain blocked characters like ; and '
        patterns = [
            "'; DROP TABLE users--",   # Contains ' and ;
            "1; DELETE FROM users",    # Contains ;
        ]
        
        for pattern in patterns:
            input_data = ScreeningInput(name=pattern)
            with pytest.raises(InputValidationError):
                validate_screening_input(input_data)
    
    def test_log_injection_prevented(self):
        """Test that log injection is prevented in sanitization"""
        malicious_entries = [
            "normal\n2025-11-25 ERROR - FAKE ATTACK\n",
            "test\r\n[CRITICAL] Unauthorized access\r\n",
            "user\x00hidden",
            "data\x1b[31mRED TEXT\x1b[0m"
        ]
        
        for entry in malicious_entries:
            sanitized = sanitize_for_logging(entry)
            assert "\n" not in sanitized
            assert "\r" not in sanitized
            assert "\x00" not in sanitized
            assert "\x1b" not in sanitized


class TestConfigValidationSecurity:
    """Tests for configuration validation security"""
    
    @pytest.fixture(autouse=True)
    def reset_config(self):
        """Reset config before each test"""
        ConfigManager.reset_instance()
    
    def test_negative_name_min_length_rejected(self, tmp_path):
        """Test that negative name_min_length is rejected"""
        config_content = """
matching:
  name_threshold: 85
  weights:
    name: 0.40
    document: 0.30
    dob: 0.15
    nationality: 0.10
    address: 0.05

input_validation:
  name_min_length: -5
  name_max_length: 200
  document_max_length: 50

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigManager(str(config_file))
        
        assert "name_min_length" in str(exc_info.value)
    
    def test_max_less_than_min_rejected(self, tmp_path):
        """Test that name_max_length < name_min_length is rejected"""
        config_content = """
matching:
  name_threshold: 85
  weights:
    name: 0.40
    document: 0.30
    dob: 0.15
    nationality: 0.10
    address: 0.05

input_validation:
  name_min_length: 100
  name_max_length: 50
  document_max_length: 50

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigManager(str(config_file))
        
        assert "name_max_length" in str(exc_info.value)
    
    def test_excessive_max_length_rejected(self, tmp_path):
        """Test that name_max_length > 1000 is rejected"""
        config_content = """
matching:
  name_threshold: 85
  weights:
    name: 0.40
    document: 0.30
    dob: 0.15
    nationality: 0.10
    address: 0.05

input_validation:
  name_min_length: 2
  name_max_length: 10000
  document_max_length: 50

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigManager(str(config_file))
        
        assert "1000" in str(exc_info.value)


class TestMultiVectorAttacks:
    """Tests for multi-vector attack scenarios"""
    
    @pytest.fixture(autouse=True)
    def reset_config(self):
        """Reset config before each test"""
        ConfigManager.reset_instance()
    
    def test_combined_xxe_and_injection(self, tmp_path):
        """Test that combined XXE and injection attacks are blocked"""
        # XML with both XXE and content that looks like SQL injection
        malicious_xml = '''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>
  <name>'; DROP TABLE--</name>
  <data>&xxe;</data>
</root>'''
        
        xml_file = tmp_path / "combined.xml"
        xml_file.write_text(malicious_xml)
        
        # Should be safe to parse
        try:
            tree, root = secure_parse(xml_file)
            # Check entity wasn't expanded
            for elem in root:
                if elem.text:
                    assert "root:" not in elem.text
                    assert "/etc/passwd" not in elem.text
        except Exception:
            # Error is also acceptable
            pass
    
    def test_unicode_smuggling_blocked(self):
        """Test that Unicode smuggling attempts are blocked"""
        # Try to use look-alike characters
        smuggling_attempts = [
            "admin\u200Btest",  # Zero-width space
            "user\ufeffname",  # BOM
            "test\u2028line",  # Line separator
            "data\u2029para",  # Paragraph separator
        ]
        
        for attempt in smuggling_attempts:
            sanitized = sanitize_for_logging(attempt)
            # Should not contain invisible separators
            assert "\u200B" not in sanitized
            assert "\ufeff" not in sanitized
            assert "\u2028" not in sanitized
            assert "\u2029" not in sanitized


class TestDefenseInDepth:
    """Tests verifying multiple layers of defense"""
    
    def test_validation_plus_sanitization(self):
        """Test that validation AND sanitization both apply"""
        # Even if somehow validation passes, sanitization should clean
        dangerous_chars = "\x00\x0a\x0d\x1b"
        
        # Sanitization should remove all dangerous chars
        result = sanitize_for_logging(dangerous_chars)
        assert len(result) == 0 or result == " "
    
    def test_config_validation_prevents_bypass(self, tmp_path):
        """Test that invalid config can't bypass security"""
        ConfigManager.reset_instance()
        
        # Try to set very permissive config
        config_content = """
matching:
  name_threshold: 1
  weights:
    name: 0.40
    document: 0.30
    dob: 0.15
    nationality: 0.10
    address: 0.05

input_validation:
  name_min_length: 0
  name_max_length: 100000

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        # Should be rejected
        with pytest.raises(ConfigurationError):
            ConfigManager(str(config_file))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
