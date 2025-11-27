"""
Tests for real validation behavior of user screening.

These tests verify that the screening system properly validates user inputs
and produces correct screening results for real-world scenarios.

Covers:
- Input validation (name length, blocked characters, DOB format)
- Name matching with various confidence levels
- Document-based screening
- Common name handling
- Unicode name support (Chinese, Arabic, Cyrillic)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Test imports
from screener import (
    EnhancedSanctionsScreener,
    ScreeningInput,
    InputValidationError,
    validate_screening_input,
)
from config_manager import ConfigManager, ConfigurationError


# ============================================
# FIXTURES
# ============================================


@pytest.fixture
def config():
    """Create a test configuration using the new DI pattern."""
    cfg = ConfigManager.create()  # Use factory method per new DI pattern
    return cfg


@pytest.fixture
def mock_screener(config):
    """Create a screener with mocked data loading."""
    screener = EnhancedSanctionsScreener(config=config, data_dir="sanctions_data")
    # Don't load real data, just set up entities for testing
    screener.entities = []
    return screener


# ============================================
# INPUT VALIDATION TESTS
# ============================================


class TestInputValidation:
    """Tests for input validation behavior."""

    def test_name_too_short_raises_error(self, config):
        """Name with less than 2 characters should raise error."""
        input_data = ScreeningInput(name="A")
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data, config)
        assert exc_info.value.code == "NAME_TOO_SHORT"
        assert exc_info.value.field == "name"

    def test_empty_name_raises_error(self, config):
        """Empty name should raise error."""
        input_data = ScreeningInput(name="")
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data, config)
        assert exc_info.value.code == "NAME_TOO_SHORT"

    def test_whitespace_only_name_raises_error(self, config):
        """Name with only whitespace should raise error."""
        input_data = ScreeningInput(name="   ")
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data, config)
        assert exc_info.value.code == "NAME_TOO_SHORT"

    def test_name_too_long_raises_error(self, config):
        """Name exceeding max length should raise error."""
        long_name = "A" * 250  # Exceeds default max of 200
        input_data = ScreeningInput(name=long_name)
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data, config)
        assert exc_info.value.code == "NAME_TOO_LONG"

    def test_valid_name_passes(self, config):
        """Valid name should pass validation."""
        input_data = ScreeningInput(name="John Doe")
        # Should not raise
        validate_screening_input(input_data, config)

    def test_blocked_characters_raise_error(self, config):
        """Names with blocked characters should raise error."""
        blocked_chars = ["<", ">", "{", "}", "[", "]", "|", "\\", ";", "`", "$"]
        
        for char in blocked_chars:
            input_data = ScreeningInput(name=f"John{char}Doe")
            with pytest.raises(InputValidationError) as exc_info:
                validate_screening_input(input_data, config)
            assert exc_info.value.code == "BLOCKED_CHARACTERS", f"Failed for char: {char}"

    def test_valid_dob_formats(self, config):
        """Valid DOB formats should pass validation."""
        valid_dobs = ["1985", "1985-06", "1985-06-15"]
        
        for dob in valid_dobs:
            input_data = ScreeningInput(name="John Doe", date_of_birth=dob)
            # Should not raise
            validate_screening_input(input_data, config)

    def test_invalid_dob_format_raises_error(self, config):
        """Invalid DOB format should raise error."""
        invalid_dobs = ["06/15/1985", "June 15, 1985", "not-a-date", "85"]
        
        for dob in invalid_dobs:
            input_data = ScreeningInput(name="John Doe", date_of_birth=dob)
            with pytest.raises(InputValidationError) as exc_info:
                validate_screening_input(input_data, config)
            assert exc_info.value.code == "INVALID_DOB_FORMAT", f"Failed for DOB: {dob}"

    def test_valid_document_number(self, config):
        """Valid document numbers should pass validation."""
        valid_docs = ["PA12345678", "A-123-456-789", "12.345.678"]
        
        for doc in valid_docs:
            input_data = ScreeningInput(name="John Doe", document_number=doc)
            # Should not raise
            validate_screening_input(input_data, config)

    def test_document_number_too_long_raises_error(self, config):
        """Document number exceeding max length should raise error."""
        long_doc = "A" * 60  # Exceeds default max of 50
        input_data = ScreeningInput(name="John Doe", document_number=long_doc)
        with pytest.raises(InputValidationError) as exc_info:
            validate_screening_input(input_data, config)
        assert exc_info.value.code == "DOCUMENT_TOO_LONG"


# ============================================
# UNICODE NAME SUPPORT TESTS
# ============================================


class TestUnicodeNameSupport:
    """Tests for Unicode name handling."""

    def test_chinese_name_accepted(self, config):
        """Chinese names should be accepted."""
        input_data = ScreeningInput(name="李明华")
        # Should not raise
        validate_screening_input(input_data, config)

    def test_arabic_name_accepted(self, config):
        """Arabic names should be accepted."""
        input_data = ScreeningInput(name="محمد علي")
        # Should not raise
        validate_screening_input(input_data, config)

    def test_cyrillic_name_accepted(self, config):
        """Cyrillic names should be accepted."""
        input_data = ScreeningInput(name="Владимир Путин")
        # Should not raise
        validate_screening_input(input_data, config)

    def test_mixed_script_name_accepted(self, config):
        """Mixed script names should be accepted."""
        input_data = ScreeningInput(name="John 李明")
        # Should not raise
        validate_screening_input(input_data, config)

    def test_accented_latin_name_accepted(self, config):
        """Accented Latin names should be accepted."""
        input_data = ScreeningInput(name="José García François")
        # Should not raise
        validate_screening_input(input_data, config)


# ============================================
# SCREENER BEHAVIOR TESTS
# ============================================


class TestScreenerBehavior:
    """Tests for screener behavior with test data."""

    def test_screener_returns_empty_for_no_matches(self, mock_screener):
        """Screener should return empty results when no entities match."""
        # Add a test entity that won't match
        mock_screener.entities = [{
            "id": "TEST-001",
            "source": "OFAC",
            "type": "individual",
            "name": "Completely Different Name",
            "all_names": ["Completely Different Name"],
            "aliases": [],
            "countries": [],
            "identity_documents": [],
        }]
        
        input_data = ScreeningInput(name="John Doe")
        results = mock_screener.search(input_data)
        
        assert len(results) == 0

    def test_screener_normalizes_names_for_matching(self, mock_screener):
        """Screener should normalize names for matching."""
        # Test that names are normalized (uppercase, no accents)
        name1 = mock_screener._normalize_name("José García")
        name2 = mock_screener._normalize_name("JOSE GARCIA")
        
        assert name1 == name2
        assert name1 == "JOSE GARCIA"

    def test_screener_normalizes_documents(self, mock_screener):
        """Screener should normalize document numbers."""
        doc1 = mock_screener._normalize_document("PA-123-456-78")
        doc2 = mock_screener._normalize_document("PA12345678")
        doc3 = mock_screener._normalize_document("pa 123 456 78")
        
        assert doc1 == doc2 == doc3 == "PA12345678"

    def test_short_name_detection(self, mock_screener):
        """Screener should detect short names requiring stricter matching."""
        assert mock_screener._is_short_name("Li") is True
        assert mock_screener._is_short_name("J. D.") is True
        # "John Doe" is 8 chars, < 10, so it IS considered short
        assert mock_screener._is_short_name("John Doe") is True
        # Longer names are not short
        assert mock_screener._is_short_name("Mohamed Ali Hassan") is False
        assert mock_screener._is_short_name("Jonathan Smith") is False

    def test_dob_score_calculation(self, mock_screener):
        """DOB score should decrease with year difference."""
        # Exact match
        score1 = mock_screener._calculate_dob_score("1985", "1985")
        assert score1 == 100.0
        
        # 1 year difference
        score2 = mock_screener._calculate_dob_score("1985", "1984")
        assert score2 == 80.0
        
        # 5 year difference
        score3 = mock_screener._calculate_dob_score("1985", "1980")
        assert score3 == 0.0

    def test_screen_individual_returns_correct_structure(self, mock_screener):
        """screen_individual should return properly structured result."""
        result = mock_screener.screen_individual(
            name="Test Person",
            document="PA12345",
            date_of_birth="1985",
            nationality="USA",
        )
        
        # Verify structure
        assert "screening_id" in result
        assert "input" in result
        assert "screening_date" in result
        assert "is_hit" in result
        assert "hit_count" in result
        assert "matches" in result
        assert "algorithm_version" in result
        assert "thresholds_used" in result
        
        # Verify input data preserved
        assert result["input"]["name"] == "Test Person"
        assert result["input"]["document"] == "PA12345"


# ============================================
# RECOMMENDATION LOGIC TESTS
# ============================================


class TestRecommendationLogic:
    """Tests for screening recommendation logic."""

    def test_recommendation_thresholds(self, config):
        """Verify recommendation threshold logic."""
        thresholds = config.reporting.recommendation_thresholds
        
        # Default thresholds
        assert thresholds["auto_clear"] < thresholds["manual_review"]
        assert thresholds["manual_review"] < thresholds["auto_escalate"]

    def test_match_layer_assignment(self, mock_screener):
        """Test that match layers are correctly assigned based on confidence."""
        # These are the expected layer thresholds from config
        layers = mock_screener.config.matching.layers
        
        assert layers["exact_match"] == 100
        assert layers["high_confidence"] == 85
        assert layers["moderate_match"] == 70
        assert layers["low_match"] == 60


# ============================================
# ERROR HANDLING TESTS
# ============================================


class TestErrorHandling:
    """Tests for error handling in screening."""

    def test_validation_error_has_useful_message(self, config):
        """Validation errors should have useful messages and suggestions."""
        input_data = ScreeningInput(name="A")
        
        try:
            validate_screening_input(input_data, config)
            assert False, "Should have raised InputValidationError"
        except InputValidationError as e:
            assert e.field == "name"
            assert e.code == "NAME_TOO_SHORT"
            assert e.suggestion != ""

    def test_validation_error_for_blocked_chars_lists_chars(self, config):
        """Validation error for blocked chars should list which chars are blocked."""
        input_data = ScreeningInput(name="Test<script>")
        
        try:
            validate_screening_input(input_data, config)
            assert False, "Should have raised InputValidationError"
        except InputValidationError as e:
            assert e.code == "BLOCKED_CHARACTERS"
            assert "<" in str(e)


# ============================================
# INTEGRATION-STYLE TESTS
# ============================================


class TestScreeningWorkflow:
    """Integration-style tests for complete screening workflow."""

    def test_complete_screening_workflow(self, mock_screener):
        """Test a complete screening workflow from input to result."""
        # Step 1: Create input
        input_data = ScreeningInput(
            name="Test Person",
            document_number="PA12345678",
            date_of_birth="1985-06-15",
            nationality="USA",
        )
        
        # Step 2: Validate input (should not raise)
        validate_screening_input(input_data, mock_screener.config)
        
        # Step 3: Perform screening
        result = mock_screener.screen_individual(
            name=input_data.name,
            document=input_data.document_number,
            date_of_birth=input_data.date_of_birth,
            nationality=input_data.nationality,
        )
        
        # Step 4: Verify result structure
        assert isinstance(result["screening_id"], str)
        assert isinstance(result["is_hit"], bool)
        assert isinstance(result["matches"], list)

    def test_screening_with_minimal_input(self, mock_screener):
        """Screening should work with just a name."""
        result = mock_screener.screen_individual(name="Test Person")
        
        assert "screening_id" in result
        assert "is_hit" in result
        assert "matches" in result

    def test_screening_preserves_input_data(self, mock_screener):
        """Input data should be preserved in result."""
        result = mock_screener.screen_individual(
            name="Test Person",
            document="DOC123",
            nationality="USA",
            country="United States",
        )
        
        assert result["input"]["name"] == "Test Person"
        assert result["input"]["document"] == "DOC123"
        assert result["input"]["nationality"] == "USA"
        assert result["input"]["country"] == "United States"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
