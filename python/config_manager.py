from dataclasses import dataclass, field

@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str = "localhost"
    port: int = 5432
    user: str = "sdn_user"
    password: str = "sdn_password"
    name: str = "sdn_database"
"""
Configuration Management Module
Loads and validates configuration from config.yaml
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveThresholdConfig:
    """Adaptive thresholds by Unicode script"""
    enabled: bool = True
    chinese: int = 85
    arabic: int = 90
    cyrillic: int = 90
    latin_initials: int = 98


@dataclass
class HashVerificationConfig:
    """Hash verification settings"""
    enabled: bool = True
    max_retry_attempts: int = 3
    known_hashes_file: str = "known_hashes.json"
    alert_on_mismatch: bool = True


@dataclass
class MatchingConfig:
    """Matching configuration parameters"""
    name_threshold: int = 85
    short_name_threshold: int = 95
    common_names: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=lambda: {
        'name': 0.40,
        'document': 0.30,
        'dob': 0.15,
        'nationality': 0.10,
        'address': 0.05
    })
    layers: Dict[str, int] = field(default_factory=lambda: {
        'exact_match': 100,
        'high_confidence': 85,
        'moderate_match': 70,
        'low_match': 60
    })
    adaptive_thresholds: AdaptiveThresholdConfig = field(default_factory=AdaptiveThresholdConfig)


@dataclass
class DataConfig:
    """Data source configuration"""
    ofac_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.ZIP"
    un_url: str = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    update_frequency_days: int = 7
    xsd_validation: bool = True
    xsd_strictness: str = "normal"  # strict, normal, lenient
    data_directory: str = "sanctions_data"
    entity_count_variance_threshold: float = 0.5
    malformed_entity_threshold: float = 1.0
    hash_verification: HashVerificationConfig = field(default_factory=HashVerificationConfig)


@dataclass
class ReportingConfig:
    """Reporting configuration"""
    include_low_confidence: bool = False
    minimum_report_score: int = 60
    recommendation_thresholds: Dict[str, int] = field(default_factory=lambda: {
        'auto_clear': 60,
        'manual_review': 85,
        'auto_escalate': 95
    })
    output_directory: str = "reports"
    include_audit_trail: bool = True
    data_freshness_warning_days: int = 7


@dataclass
class ValidationConfig:
    """Validation configuration"""
    required_entity_fields: List[str] = field(default_factory=lambda: ['id', 'name', 'source'])
    required_individual_fields: List[str] = field(default_factory=lambda: ['id', 'name', 'source', 'type'])
    log_validation_errors: bool = True
    abort_on_high_malformation: bool = True


@dataclass
class InputValidationConfig:
    """Input validation configuration for user-provided data"""
    name_min_length: int = 2
    name_max_length: int = 200
    document_max_length: int = 50
    allow_unicode_names: bool = True
    blocked_characters: str = "<>{}[]|\\;`$"


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    file: str = "logs/screening.log"
    console: bool = True
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class PerformanceConfig:
    """Performance configuration"""
    memory_limit_gb: int = 2
    concurrent_searches: bool = True
    max_threads: int = 4
    batch_size: int = 100


@dataclass
class AlgorithmConfig:
    """Algorithm version information"""
    version: str = "2.0.0"
    name: str = "Multi-Layer Fuzzy Matcher"
    last_updated: str = "2024-01-01"


class ConfigurationError(Exception):
    """Raised when configuration is invalid"""
    pass


class ConfigManager:
    """Manages system configuration"""
    
    _instance: Optional['ConfigManager'] = None
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration manager
        
        Args:
            config_path: Path to config.yaml file
        """
        self.config_path = Path(config_path) if config_path else self._find_config()
        self._raw_config: Dict[str, Any] = {}
        self.matching: MatchingConfig = MatchingConfig()
        self.data: DataConfig = DataConfig()
        self.reporting: ReportingConfig = ReportingConfig()
        self.validation: ValidationConfig = ValidationConfig()
        self.input_validation: InputValidationConfig = InputValidationConfig()
        self.logging: LoggingConfig = LoggingConfig()
        self.performance: PerformanceConfig = PerformanceConfig()
        self.algorithm: AlgorithmConfig = AlgorithmConfig()
        self.database: DatabaseConfig = DatabaseConfig()
        
        if self.config_path and self.config_path.exists():
            self.load()
        else:
            logger.warning(f"Config file not found at {self.config_path}, using defaults")
    
    def _find_config(self) -> Path:
        """Find config.yaml in common locations"""
        search_paths = [
            Path(__file__).parent / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.cwd() / "python" / "config.yaml",
        ]
        
        for path in search_paths:
            if path.exists():
                return path
        
        return search_paths[0]
    
    def load(self) -> None:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._raw_config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}")
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {self.config_path}")

        self._parse_matching()
        self._parse_data()
        self._parse_reporting()
        self._parse_validation()
        self._parse_input_validation()
        self._parse_logging()
        self._parse_performance()
        self._parse_algorithm()
        self._parse_database()
        self._validate()

    def _parse_database(self) -> None:
        """Parse database configuration"""
        cfg = self._raw_config.get('database', {})
        self.database = DatabaseConfig(
            host=cfg.get('host', self.database.host),
            port=cfg.get('port', self.database.port),
            user=cfg.get('user', self.database.user),
            password=cfg.get('password', self.database.password),
            name=cfg.get('name', self.database.name)
        )
    
    def _parse_matching(self) -> None:
        """Parse matching configuration"""
        cfg = self._raw_config.get('matching', {})
        
        # Parse adaptive thresholds
        adaptive_cfg = cfg.get('adaptive_thresholds', {})
        adaptive = AdaptiveThresholdConfig(
            enabled=adaptive_cfg.get('enabled', True),
            chinese=adaptive_cfg.get('chinese', 85),
            arabic=adaptive_cfg.get('arabic', 90),
            cyrillic=adaptive_cfg.get('cyrillic', 90),
            latin_initials=adaptive_cfg.get('latin_initials', 98)
        )
        
        self.matching = MatchingConfig(
            name_threshold=cfg.get('name_threshold', 85),
            short_name_threshold=cfg.get('short_name_threshold', 95),
            common_names=cfg.get('common_names', []),
            weights=cfg.get('weights', self.matching.weights),
            layers=cfg.get('layers', self.matching.layers),
            adaptive_thresholds=adaptive
        )
    
    def _parse_data(self) -> None:
        """Parse data configuration"""
        cfg = self._raw_config.get('data', {})
        
        # Parse hash verification config
        hash_cfg = cfg.get('hash_verification', {})
        hash_verification = HashVerificationConfig(
            enabled=hash_cfg.get('enabled', True),
            max_retry_attempts=hash_cfg.get('max_retry_attempts', 3),
            known_hashes_file=hash_cfg.get('known_hashes_file', 'known_hashes.json'),
            alert_on_mismatch=hash_cfg.get('alert_on_mismatch', True)
        )
        
        self.data = DataConfig(
            ofac_url=cfg.get('ofac_url', self.data.ofac_url),
            un_url=cfg.get('un_url', self.data.un_url),
            update_frequency_days=cfg.get('update_frequency_days', 7),
            xsd_validation=cfg.get('xsd_validation', True),
            xsd_strictness=cfg.get('xsd_strictness', 'normal'),
            data_directory=cfg.get('data_directory', 'sanctions_data'),
            entity_count_variance_threshold=cfg.get('entity_count_variance_threshold', 0.5),
            malformed_entity_threshold=cfg.get('malformed_entity_threshold', 1.0),
            hash_verification=hash_verification
        )
    
    def _parse_reporting(self) -> None:
        """Parse reporting configuration"""
        cfg = self._raw_config.get('reporting', {})
        self.reporting = ReportingConfig(
            include_low_confidence=cfg.get('include_low_confidence', False),
            minimum_report_score=cfg.get('minimum_report_score', 60),
            recommendation_thresholds=cfg.get('recommendation_thresholds', 
                                               self.reporting.recommendation_thresholds),
            output_directory=cfg.get('output_directory', 'reports'),
            include_audit_trail=cfg.get('include_audit_trail', True),
            data_freshness_warning_days=cfg.get('data_freshness_warning_days', 7)
        )
    
    def _parse_validation(self) -> None:
        """Parse validation configuration"""
        cfg = self._raw_config.get('validation', {})
        self.validation = ValidationConfig(
            required_entity_fields=cfg.get('required_entity_fields', 
                                           self.validation.required_entity_fields),
            required_individual_fields=cfg.get('required_individual_fields', 
                                               self.validation.required_individual_fields),
            log_validation_errors=cfg.get('log_validation_errors', True),
            abort_on_high_malformation=cfg.get('abort_on_high_malformation', True)
        )
    
    def _parse_input_validation(self) -> None:
        """Parse input validation configuration"""
        cfg = self._raw_config.get('input_validation', {})
        self.input_validation = InputValidationConfig(
            name_min_length=cfg.get('name_min_length', 2),
            name_max_length=cfg.get('name_max_length', 200),
            document_max_length=cfg.get('document_max_length', 50),
            allow_unicode_names=cfg.get('allow_unicode_names', True),
            blocked_characters=cfg.get('blocked_characters', "<>{}[]|\\;`$")
        )
    
    def _parse_logging(self) -> None:
        """Parse logging configuration"""
        cfg = self._raw_config.get('logging', {})
        self.logging = LoggingConfig(
            level=cfg.get('level', 'INFO'),
            file=cfg.get('file', 'logs/screening.log'),
            console=cfg.get('console', True),
            format=cfg.get('format', self.logging.format)
        )
    
    def _parse_performance(self) -> None:
        """Parse performance configuration"""
        cfg = self._raw_config.get('performance', {})
        self.performance = PerformanceConfig(
            memory_limit_gb=cfg.get('memory_limit_gb', 2),
            concurrent_searches=cfg.get('concurrent_searches', True),
            max_threads=cfg.get('max_threads', 4),
            batch_size=cfg.get('batch_size', 100)
        )
    
    def _parse_algorithm(self) -> None:
        """Parse algorithm configuration"""
        cfg = self._raw_config.get('algorithm', {})
        self.algorithm = AlgorithmConfig(
            version=cfg.get('version', '2.0.0'),
            name=cfg.get('name', 'Multi-Layer Fuzzy Matcher'),
            last_updated=cfg.get('last_updated', '2024-01-01')
        )
    
    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> 'ConfigManager':
        """Get singleton instance of ConfigManager"""
        if cls._instance is None:
            cls._instance = ConfigManager(config_path)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)"""
        cls._instance = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary"""
        return {
            'matching': {
                'name_threshold': self.matching.name_threshold,
                'short_name_threshold': self.matching.short_name_threshold,
                'common_names': self.matching.common_names,
                'weights': self.matching.weights,
                'layers': self.matching.layers
            },
            'data': {
                'ofac_url': self.data.ofac_url,
                'un_url': self.data.un_url,
                'update_frequency_days': self.data.update_frequency_days,
                'xsd_validation': self.data.xsd_validation,
                'data_directory': self.data.data_directory
            },
            'reporting': {
                'include_low_confidence': self.reporting.include_low_confidence,
                'minimum_report_score': self.reporting.minimum_report_score,
                'recommendation_thresholds': self.reporting.recommendation_thresholds,
                'output_directory': self.reporting.output_directory
            },
            'algorithm': {
                'version': self.algorithm.version,
                'name': self.algorithm.name,
                'last_updated': self.algorithm.last_updated
            },
            'database': {
                'host': self.database.host,
                'port': self.database.port,
                'user': self.database.user,
                'password': self.database.password,
                'name': self.database.name
            }
        }

    def _validate(self) -> None:
        """Validate configuration values (dummy implementation)"""
        # TODO: Implement real validation logic if needed
        pass


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """Convenience function to get configuration instance"""
    return ConfigManager.get_instance(config_path)
