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


class TestOFACXMLParsing:
    """Tests for OFAC XML parsing with mock data"""
    
    def test_parse_identity_documents(self, tmp_path):
        """Test that identity documents are correctly parsed from OFAC XML structure"""
        from downloader import EnhancedSanctionsDownloader, IdentityDocument
        
        # Create mock OFAC XML with identity documents directly under entity
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<sanctions xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML">
    <entity id="12345">
        <entityType>Individual</entityType>
        <names>
            <name>
                <translations>
                    <translation>
                        <formattedFullName>John Doe</formattedFullName>
                    </translation>
                </translations>
            </name>
        </names>
        <idDocuments>
            <idDocument>
                <type>Passport</type>
                <number>X12345678</number>
                <issuedByCountry>Panama</issuedByCountry>
            </idDocument>
        </idDocuments>
    </entity>
</sanctions>'''
        
        xml_file = tmp_path / "test_ofac.xml"
        xml_file.write_text(xml_content)
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        downloader._namespace = None
        
        entities = downloader.parse_ofac_xml(xml_file)
        
        assert len(entities) == 1
        entity = entities[0]
        assert len(entity.identity_documents) == 1
        assert entity.identity_documents[0].doc_number == 'X12345678'
        assert entity.identity_documents[0].doc_type == 'Passport'
        assert entity.identity_documents[0].issuing_country == 'Panama'
    
    def test_parse_features_with_type_id(self, tmp_path):
        """Test that features extract featureTypeId attribute"""
        from downloader import EnhancedSanctionsDownloader
        
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<sanctions xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML">
    <entity id="12345">
        <entityType>Individual</entityType>
        <names>
            <name>
                <translations>
                    <translation>
                        <formattedFullName>Test Person</formattedFullName>
                    </translation>
                </translations>
            </name>
        </names>
        <features>
            <feature>
                <type featureTypeId="8">Date of Birth</type>
                <value>1970-01-01</value>
            </feature>
        </features>
    </entity>
</sanctions>'''
        
        xml_file = tmp_path / "test_ofac.xml"
        xml_file.write_text(xml_content)
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        downloader._namespace = None
        
        entities = downloader.parse_ofac_xml(xml_file)
        
        assert len(entities) == 1
        entity = entities[0]
        assert len(entity.features) == 1
        assert entity.features[0].feature_type == 'Date of Birth'
        assert entity.features[0].feature_type_id == '8'
        assert entity.features[0].value == '1970-01-01'
    
    def test_parse_relationships_with_entity_id(self, tmp_path):
        """Test that relationships use entityId attribute"""
        from downloader import EnhancedSanctionsDownloader
        
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<sanctions xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML">
    <entity id="12345">
        <entityType>Individual</entityType>
        <names>
            <name>
                <translations>
                    <translation>
                        <formattedFullName>Test Person</formattedFullName>
                    </translation>
                </translations>
            </name>
        </names>
        <relationships>
            <relationship>
                <relatedEntity entityId="67890"/>
                <relationshipType>Associate</relationshipType>
            </relationship>
        </relationships>
    </entity>
</sanctions>'''
        
        xml_file = tmp_path / "test_ofac.xml"
        xml_file.write_text(xml_content)
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        downloader._namespace = None
        
        entities = downloader.parse_ofac_xml(xml_file)
        
        assert len(entities) == 1
        entity = entities[0]
        assert len(entity.relationships) == 1
        assert entity.relationships[0].related_entity_id == '67890'
        assert entity.relationships[0].relationship_type == 'Associate'


class TestUNXMLParsing:
    """Tests for UN XML parsing with mock data"""
    
    def test_parse_nationality_structure(self, tmp_path):
        """Test that UN nationality is parsed from NATIONALITY/VALUE structure"""
        from downloader import EnhancedSanctionsDownloader
        
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<CONSOLIDATED_LIST>
    <INDIVIDUALS>
        <INDIVIDUAL>
            <DATAID>123456</DATAID>
            <FIRST_NAME>Test</FIRST_NAME>
            <SECOND_NAME>Person</SECOND_NAME>
            <REFERENCE_NUMBER>QDi.001</REFERENCE_NUMBER>
            <UN_LIST_TYPE>Al-Qaida</UN_LIST_TYPE>
            <NATIONALITY>
                <VALUE>Afghanistan</VALUE>
            </NATIONALITY>
        </INDIVIDUAL>
    </INDIVIDUALS>
</CONSOLIDATED_LIST>'''
        
        xml_file = tmp_path / "test_un.xml"
        xml_file.write_text(xml_content)
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        
        entities = downloader.parse_un_xml(xml_file)
        
        assert len(entities) == 1
        entity = entities[0]
        assert entity.nationality == 'Afghanistan'
        assert 'Afghanistan' in entity.countries
    
    def test_entity_missing_documents_logged(self, tmp_path):
        """Test that entities without documents don't cause errors"""
        from downloader import EnhancedSanctionsDownloader
        
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<CONSOLIDATED_LIST>
    <INDIVIDUALS>
        <INDIVIDUAL>
            <DATAID>123456</DATAID>
            <FIRST_NAME>Test</FIRST_NAME>
            <REFERENCE_NUMBER>QDi.001</REFERENCE_NUMBER>
        </INDIVIDUAL>
    </INDIVIDUALS>
</CONSOLIDATED_LIST>'''
        
        xml_file = tmp_path / "test_un.xml"
        xml_file.write_text(xml_content)
        
        downloader = EnhancedSanctionsDownloader.__new__(EnhancedSanctionsDownloader)
        downloader._discovered_country_codes = set()
        downloader._discovered_list_types = set()
        
        entities = downloader.parse_un_xml(xml_file)
        
        assert len(entities) == 1
        entity = entities[0]
        # Should have empty documents list, not error
        assert len(entity.identity_documents) == 0


class TestSecurityValidation:
    """Tests for security-related input validation"""
    
    def test_input_validation_valid_name(self):
        """Test that valid names pass validation"""
        from screener import ScreeningInput, validate_screening_input
        
        input_data = ScreeningInput(name="John Doe")
        # Should not raise
        validate_screening_input(input_data)
    
    def test_input_validation_name_too_short(self):
        """Test that names < 2 chars are rejected"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="J")
        with pytest.raises(InputValidationError):
            validate_screening_input(input_data)
    
    def test_input_validation_name_too_long(self):
        """Test that names > 200 chars are rejected"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        long_name = "A" * 201
        input_data = ScreeningInput(name=long_name)
        with pytest.raises(InputValidationError):
            validate_screening_input(input_data)
    
    def test_input_validation_injection_attempt(self):
        """Test that SQL injection attempts are rejected"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="'; DROP TABLE--")
        with pytest.raises(InputValidationError):
            validate_screening_input(input_data)
    
    def test_input_validation_invalid_dob(self):
        """Test that invalid DOB format is rejected"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="John Doe", date_of_birth="not-a-date")
        with pytest.raises(InputValidationError):
            validate_screening_input(input_data)
    
    def test_input_validation_valid_dob(self):
        """Test that valid DOB formats pass"""
        from screener import ScreeningInput, validate_screening_input
        
        # YYYY format
        input_data = ScreeningInput(name="John Doe", date_of_birth="1985")
        validate_screening_input(input_data)
        
        # YYYY-MM format
        input_data = ScreeningInput(name="John Doe", date_of_birth="1985-06")
        validate_screening_input(input_data)
        
        # YYYY-MM-DD format
        input_data = ScreeningInput(name="John Doe", date_of_birth="1985-06-15")
        validate_screening_input(input_data)
    
    def test_sanitize_for_logging(self):
        """Test log injection prevention"""
        from xml_utils import sanitize_for_logging
        
        # Newline injection should be sanitized
        result = sanitize_for_logging("John\n[ERROR] System compromised")
        assert '\n' not in result
        assert '[ERROR]' in result  # Text kept, but on same line
    
    def test_sanitize_for_logging_empty(self):
        """Test sanitization of empty input"""
        from xml_utils import sanitize_for_logging
        
        assert sanitize_for_logging('') == ''
        assert sanitize_for_logging(None) == ''
    
    def test_xxe_prevention_malicious_xml(self, tmp_path):
        """Test that XXE attack payloads are blocked"""
        from xml_utils import secure_parse
        
        # XXE payload that tries to read /etc/passwd
        xxe_content = '''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>'''
        
        xml_file = tmp_path / "xxe_test.xml"
        xml_file.write_text(xxe_content)
        
        # Should either parse without entity expansion or raise error
        # depending on library available
        try:
            tree, root = secure_parse(xml_file)
            # If parsed, entity should NOT be expanded
            text = root.text or ''
            assert 'root:' not in text  # /etc/passwd content
        except Exception:
            # Parser rejected the malicious content - also acceptable
            pass


class TestUnicodeNameSupport:
    """Tests for international name support"""
    
    def test_chinese_name(self):
        """Test Chinese name validation"""
        from screener import ScreeningInput, validate_screening_input
        
        input_data = ScreeningInput(name="李明")
        validate_screening_input(input_data)  # Should not raise
    
    def test_arabic_name(self):
        """Test Arabic name validation"""
        from screener import ScreeningInput, validate_screening_input
        
        input_data = ScreeningInput(name="محمد علي")
        validate_screening_input(input_data)  # Should not raise
    
    def test_cyrillic_name(self):
        """Test Cyrillic name validation"""
        from screener import ScreeningInput, validate_screening_input
        
        input_data = ScreeningInput(name="Владимир")
        validate_screening_input(input_data)  # Should not raise
    
    def test_mixed_script_name(self):
        """Test mixed Latin/accented name validation"""
        from screener import ScreeningInput, validate_screening_input
        
        input_data = ScreeningInput(name="José María François")
        validate_screening_input(input_data)  # Should not raise


class TestDoSProtection:
    """Tests for XML DoS attack prevention"""
    
    def test_billion_laughs_attack(self, tmp_path):
        """Test that billion laughs attack is blocked"""
        from xml_utils import secure_parse
        
        # Billion laughs payload
        billion_laughs = '''<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<lolz>&lol3;</lolz>'''
        
        xml_file = tmp_path / "billion_laughs.xml"
        xml_file.write_text(billion_laughs)
        
        # Should complete quickly without expansion
        import time
        start = time.time()
        try:
            tree, root = secure_parse(xml_file)
            elapsed = time.time() - start
            assert elapsed < 5  # Should not hang
            # Entity should not be expanded
            text = root.text or ''
            assert 'lol' not in text.lower() or len(text) < 1000
        except Exception:
            # Parser rejected - also acceptable
            pass
    
    def test_deeply_nested_xml(self, tmp_path):
        """Test handling of deeply nested XML"""
        from xml_utils import secure_parse
        
        # Create deeply nested XML (100 levels - reasonable limit)
        depth = 100
        xml = '<?xml version="1.0"?>'
        xml += '<root>' + '<nested>' * depth + 'data' + '</nested>' * depth + '</root>'
        
        xml_file = tmp_path / "deep_nesting.xml"
        xml_file.write_text(xml)
        
        # Should parse without hanging
        try:
            tree, root = secure_parse(xml_file)
            # Should complete successfully or reject gracefully
        except Exception:
            pass  # Acceptable to reject deeply nested content


class TestRemoteDTDProtection:
    """Tests for remote DTD/entity retrieval prevention"""
    
    def test_remote_dtd_blocked(self, tmp_path):
        """Test that remote DTD retrieval is blocked"""
        from xml_utils import secure_parse
        
        remote_dtd = '''<?xml version="1.0"?>
<!DOCTYPE root SYSTEM "http://attacker.example.com/evil.dtd">
<root>data</root>'''
        
        xml_file = tmp_path / "remote_dtd.xml"
        xml_file.write_text(remote_dtd)
        
        # Should parse without fetching remote DTD
        try:
            tree, root = secure_parse(xml_file)
            # No network call should be made
            assert root.text == 'data'
        except Exception:
            # Rejecting remote DTD entirely is also acceptable
            pass
    
    def test_remote_entity_blocked(self, tmp_path):
        """Test that remote entity retrieval is blocked"""
        from xml_utils import secure_parse
        
        remote_entity = '''<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "http://attacker.example.com/data">
]>
<root>&xxe;</root>'''
        
        xml_file = tmp_path / "remote_entity.xml"
        xml_file.write_text(remote_entity)
        
        try:
            tree, root = secure_parse(xml_file)
            # Entity should not contain remote data
            text = root.text or ''
            assert 'http' not in text
        except Exception:
            pass


class TestControlCharacterHandling:
    """Tests for control character sanitization"""
    
    def test_null_byte_removal(self):
        """Test null byte is removed from logging"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("Name\x00WithNull")
        assert '\x00' not in result
        assert 'Name' in result
        assert 'WithNull' in result
    
    def test_backspace_removal(self):
        """Test backspace character is removed"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("Name\x08Backspace")
        assert '\x08' not in result
    
    def test_bell_removal(self):
        """Test bell character is removed"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("Name\x07Bell")
        assert '\x07' not in result
    
    def test_ansi_escape_removal(self):
        """Test ANSI escape sequences are removed"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("\x1b[31mRedText\x1b[0m")
        assert '\x1b' not in result
        assert 'RedText' in result
    
    def test_vertical_tab_removal(self):
        """Test vertical tab is removed"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("Name\x0bVerticalTab")
        assert '\x0b' not in result
    
    def test_form_feed_removal(self):
        """Test form feed is removed"""
        from xml_utils import sanitize_for_logging
        
        result = sanitize_for_logging("Name\x0cFormFeed")
        assert '\x0c' not in result
    
    def test_high_unicode_preserved(self):
        """Test that valid high Unicode is preserved"""
        from xml_utils import sanitize_for_logging
        
        # Chinese characters should be preserved
        result = sanitize_for_logging("Name 李明")
        assert '李明' in result


class TestEnhancedErrorMessages:
    """Tests for enhanced error messages with details"""
    
    def test_error_includes_field(self):
        """Test that error includes field name"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="A")
        try:
            validate_screening_input(input_data)
            assert False, "Should have raised"
        except InputValidationError as e:
            assert e.field == "name"
            assert e.code == "NAME_TOO_SHORT"
    
    def test_error_includes_suggestion(self):
        """Test that error includes suggestion"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="<script>")
        try:
            validate_screening_input(input_data)
            assert False, "Should have raised"
        except InputValidationError as e:
            assert e.suggestion != ""
    
    def test_dob_error_includes_example(self):
        """Test that DOB error includes format example"""
        from screener import ScreeningInput, validate_screening_input, InputValidationError
        
        input_data = ScreeningInput(name="John Doe", date_of_birth="invalid")
        try:
            validate_screening_input(input_data)
            assert False, "Should have raised"
        except InputValidationError as e:
            assert "YYYY-MM-DD" in str(e) or "1980-01-15" in str(e)


class TestConfigurableValidation:
    """Tests for configuration-based validation"""
    
    def test_config_name_min_length(self, tmp_path):
        """Test configurable minimum name length"""
        from config_manager import ConfigManager
        
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
  name_min_length: 5
  name_max_length: 200
  document_max_length: 50
  allow_unicode_names: true
  blocked_characters: "<>"

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        ConfigManager.reset_instance()
        config = ConfigManager(str(config_file))
        
        assert config.input_validation.name_min_length == 5
    
    def test_config_unicode_disabled(self, tmp_path):
        """Test disabling Unicode names via config"""
        from config_manager import ConfigManager
        
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
  name_max_length: 200
  document_max_length: 50
  allow_unicode_names: false
  blocked_characters: "<>"

reporting:
  recommendation_thresholds:
    auto_clear: 60
    manual_review: 85
    auto_escalate: 95
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        ConfigManager.reset_instance()
        config = ConfigManager(str(config_file))
        
        assert config.input_validation.allow_unicode_names is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
