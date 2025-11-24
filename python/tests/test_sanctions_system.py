"""
Unit tests for the Enhanced Sanctions Screening System
Tests configuration, matching, validation, and report generation
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_manager import (
    ConfigManager, ConfigurationError, get_config,
    MatchingConfig, DataConfig, ReportingConfig
)


class TestConfigManager:
    """Tests for configuration management"""
    
    def test_default_config_values(self):
        """Test that default values are set correctly"""
        ConfigManager.reset_instance()
        config = ConfigManager(config_path=None)
        
        # Test matching defaults
        assert config.matching.name_threshold == 85
        assert config.matching.short_name_threshold == 95
        
        # Test weights sum to 1.0
        weights = config.matching.weights
        assert abs(sum(weights.values()) - 1.0) < 0.01
    
    def test_config_loads_from_yaml(self, tmp_path):
        """Test loading configuration from YAML file"""
        config_content = """
matching:
  name_threshold: 90
  short_name_threshold: 98
  weights:
    name: 0.50
    document: 0.25
    dob: 0.10
    nationality: 0.10
    address: 0.05
reporting:
  include_low_confidence: true
  recommendation_thresholds:
    auto_clear: 50
    manual_review: 80
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        ConfigManager.reset_instance()
        config = ConfigManager(str(config_file))
        
        assert config.matching.name_threshold == 90
        assert config.matching.short_name_threshold == 98
        assert config.matching.weights['name'] == 0.50
        assert config.reporting.include_low_confidence is True
    
    def test_invalid_weights_validation(self, tmp_path):
        """Test that invalid weights sum raises error"""
        config_content = """
matching:
  weights:
    name: 0.50
    document: 0.50
    dob: 0.50
    nationality: 0.10
    address: 0.05
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        ConfigManager.reset_instance()
        with pytest.raises(ConfigurationError):
            ConfigManager(str(config_file))
    
    def test_invalid_thresholds_order(self, tmp_path):
        """Test that invalid threshold order raises error"""
        config_content = """
matching:
  weights:
    name: 0.40
    document: 0.30
    dob: 0.15
    nationality: 0.10
    address: 0.05
reporting:
  recommendation_thresholds:
    auto_clear: 90
    manual_review: 80
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        ConfigManager.reset_instance()
        with pytest.raises(ConfigurationError):
            ConfigManager(str(config_file))
    
    def test_config_to_dict(self):
        """Test exporting configuration to dictionary"""
        ConfigManager.reset_instance()
        config = ConfigManager(config_path=None)
        
        config_dict = config.to_dict()
        
        assert 'matching' in config_dict
        assert 'data' in config_dict
        assert 'reporting' in config_dict
        assert 'algorithm' in config_dict


class TestNameNormalization:
    """Tests for name normalization functions"""
    
    def test_normalize_basic(self):
        """Test basic name normalization"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        # Test uppercase conversion
        assert screener._normalize_name("John Doe") == "JOHN DOE"
        
        # Test accent removal
        assert screener._normalize_name("José García") == "JOSE GARCIA"
        
        # Test multiple spaces
        assert screener._normalize_name("John   Doe") == "JOHN DOE"
    
    def test_normalize_special_characters(self):
        """Test normalization with special characters"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        # Test comma removal
        assert screener._normalize_name("Doe, John") == "DOE JOHN"
        
        # Test hyphen handling
        result = screener._normalize_name("Mary-Jane Watson")
        assert "MARY" in result
        assert "JANE" in result
    
    def test_normalize_unicode(self):
        """Test normalization with unicode characters"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        # Arabic diacritics
        assert screener._normalize_name("Muḥammad") == "MUHAMMAD"
        
        # German umlaut
        assert screener._normalize_name("Müller") == "MULLER"
    
    def test_normalize_empty_input(self):
        """Test normalization with empty/null input"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        assert screener._normalize_name("") == ""
        assert screener._normalize_name(None) == ""


class TestDocumentNormalization:
    """Tests for document number normalization"""
    
    def test_normalize_document_spaces(self):
        """Test document normalization removes spaces"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        assert screener._normalize_document("PA 12 345 678") == "PA12345678"
    
    def test_normalize_document_dashes(self):
        """Test document normalization removes dashes"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        assert screener._normalize_document("PA-8-1234") == "PA81234"
    
    def test_normalize_document_case(self):
        """Test document normalization uppercase"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        assert screener._normalize_document("abc123def") == "ABC123DEF"


class TestShortNameDetection:
    """Tests for short name detection"""
    
    def test_short_name_by_word_count(self):
        """Test short name detection by word count"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        # Two words, short total length
        assert screener._is_short_name("Li Wei") is True
        
        # Three words
        assert screener._is_short_name("John Michael Smith") is False
    
    def test_short_name_by_word_length(self):
        """Test short name detection by individual word length"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        # Contains very short word
        assert screener._is_short_name("Li Chen Wang") is True


class TestConfidenceScoring:
    """Tests for confidence score calculation"""
    
    def test_dob_score_exact_match(self):
        """Test DOB score for exact year match"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        score = screener._calculate_dob_score("1985-01-15", "1985-06-20")
        assert score == 100.0
    
    def test_dob_score_one_year_diff(self):
        """Test DOB score for 1 year difference"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        score = screener._calculate_dob_score("1985", "1986")
        assert score == 80.0  # 100 - (1 * 20)
    
    def test_dob_score_five_year_diff(self):
        """Test DOB score for 5+ year difference"""
        from screener import EnhancedSanctionsScreener
        
        screener = EnhancedSanctionsScreener.__new__(EnhancedSanctionsScreener)
        
        score = screener._calculate_dob_score("1985", "1990")
        assert score == 0.0  # 100 - (5 * 20) = 0


class TestReportValidation:
    """Tests for report validation"""
    
    def test_valid_result_passes(self):
        """Test that valid result passes validation"""
        from report_generator import (
            ReportValidator, ScreeningResult, ScreeningMatch, ListMetadata
        )
        
        validator = ReportValidator()
        
        result = ScreeningResult(
            input_name="John Doe",
            input_document="12345",
            input_country="USA",
            screening_date=datetime.now(),
            matches=[],
            is_hit=False
        )
        
        metadata = [ListMetadata(
            source="OFAC",
            file_path="/path/to/file",
            download_date=datetime.now(),
            last_update=datetime.now(),
            record_count=1000,
            file_size=1000000,
            file_hash="abc123"
        )]
        
        validation = validator.validate(result, metadata)
        assert validation['valid'] is True
        assert len(validation['errors']) == 0
    
    def test_stale_data_warning(self):
        """Test that stale data generates warning"""
        from report_generator import (
            ReportValidator, ScreeningResult, ListMetadata
        )
        
        validator = ReportValidator(data_freshness_warning_days=7)
        
        result = ScreeningResult(
            input_name="John Doe",
            input_document="12345",
            input_country="USA",
            screening_date=datetime.now(),
            matches=[],
            is_hit=False
        )
        
        # Metadata from 30 days ago
        old_date = datetime.now() - timedelta(days=30)
        metadata = [ListMetadata(
            source="OFAC",
            file_path="/path/to/file",
            download_date=old_date,
            last_update=old_date,
            record_count=1000,
            file_size=1000000,
            file_hash="abc123"
        )]
        
        validation = validator.validate(result, metadata)
        assert any("STALE DATA" in w for w in validation['warnings'])


class TestUNReferenceParser:
    """Tests for UN reference number parsing"""
    
    def test_parse_individual_reference(self):
        """Test parsing individual reference number"""
        from downloader import EnhancedSanctionsDownloader
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        
        list_type, country_code, committee = downloader._parse_un_reference(
            "12345", "QDi.001", "Al-Qaida"
        )
        
        assert list_type == "QDi"
        assert country_code == "QD"
        assert committee == "Al-Qaida"
    
    def test_parse_entity_reference(self):
        """Test parsing entity reference number"""
        from downloader import EnhancedSanctionsDownloader
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        
        list_type, country_code, committee = downloader._parse_un_reference(
            "67890", "KPe.015", "DPRK"
        )
        
        assert list_type == "KPe"
        assert country_code == "KP"
        assert committee == "DPRK"
    
    def test_new_country_code_logged(self):
        """Test that new country codes are tracked"""
        from downloader import EnhancedSanctionsDownloader
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        
        downloader._parse_un_reference("12345", "XXi.001", "New Sanctions")
        
        assert "XX" in downloader._discovered_country_codes


class TestMatchResult:
    """Tests for match result structure"""
    
    def test_match_result_to_dict(self):
        """Test MatchResult serialization"""
        from screener import MatchResult, ConfidenceBreakdown
        
        confidence = ConfidenceBreakdown(
            overall=87.5,
            name_score=92.0,
            document_score=0.0,
            dob_score=80.0,
            nationality_score=100.0
        )
        
        result = MatchResult(
            entity={'id': '123', 'name': 'Test Entity'},
            confidence=confidence,
            flags=['COMMON_NAME', 'NO_DOCUMENT_MATCH'],
            recommendation='MANUAL_REVIEW',
            match_layer=2,
            matched_name='Test Entity'
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['confidence']['overall'] == 87.5
        assert 'COMMON_NAME' in result_dict['flags']
        assert result_dict['recommendation'] == 'MANUAL_REVIEW'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
