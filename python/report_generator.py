def generate_auditlog_html(audit_log_path=None, output_path=None):
    """Genera un reporte HTML visualizando el audit log"""
    import json
    from pathlib import Path
    audit_log_path = audit_log_path or Path("reports/audit_log/screening_audit.log")
    output_path = output_path or Path("reports/audit_log/auditlog_report.html")
    entries = []
    if Path(audit_log_path).exists():
        with open(audit_log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    html = """
    <html>
    <head>
        <title>Audit Log Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 2em; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 8px; }
            th { background: #eee; }
        </style>
    </head>
    <body>
        <h2>Audit Log Report</h2>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>Screening ID</th>
                <th>Name</th>
                <th>Document</th>
                <th>Country</th>
                <th>Is Hit</th>
                <th>Decision</th>
            </tr>
    """
    for entry in entries:
        html += f"<tr><td>{entry.get('timestamp','')}</td>"
        html += f"<td>{entry.get('screening_id','')}</td>"
        html += f"<td>{entry.get('input',{}).get('name','')}</td>"
        html += f"<td>{entry.get('input',{}).get('document','')}</td>"
        html += f"<td>{entry.get('input',{}).get('country','')}</td>"
        html += f"<td>{'✔️' if entry.get('is_hit',False) else ''}</td>"
        html += f"<td>{entry.get('decision','')}</td></tr>"
    html += """
        </table>
    </body>
    </html>
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return str(output_path)
"""
Enhanced Report Generation System v2.0
Generates official screening reports with comprehensive metadata and audit trail

Features:
- Pre-generation validation checks
- Enhanced metadata section (algorithm version, thresholds, processing time)
- Audit trail with unique screening IDs
- Data freshness warnings
- Configurable reporting options
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import json
import hashlib
from jinja2 import Template
import xml.etree.ElementTree as ET

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ReportValidationError(Exception):
    """Raised when report validation fails"""
    pass


@dataclass
class ListMetadata:
    """Metadata de lista de sanciones"""
    source: str
    file_path: str
    download_date: datetime
    last_update: datetime
    record_count: int
    file_size: int
    file_hash: str
    version: Optional[str] = None


@dataclass
class ConfidenceBreakdown:
    """Detailed confidence score breakdown for a match"""
    overall: float
    name: float = 0.0
    document: float = 0.0
    dob: float = 0.0
    nationality: float = 0.0
    address: float = 0.0


@dataclass
class ScreeningMatch:
    """Resultado de un match individual with enhanced fields"""
    matched_name: str
    match_score: float
    entity_id: str
    source: str
    entity_type: str
    program: str
    countries: List[str]
    all_names: List[str]
    
    # Confidence breakdown
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    
    # Flags and recommendation
    flags: List[str] = field(default_factory=list)
    recommendation: str = 'MANUAL_REVIEW'
    match_layer: int = 4  # 1=exact, 2=high, 3=moderate, 4=low
    
    # Additional fields
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    nationality: Optional[str] = None
    title: Optional[str] = None
    citizenship: Optional[str] = None
    date_of_birth: Optional[str] = None
    place_of_birth: Optional[str] = None
    gender: Optional[str] = None
    identifications: List[Dict] = field(default_factory=list)
    addresses: List[Dict] = field(default_factory=list)
    remarks: Optional[str] = None


@dataclass
class ScreeningConfig:
    """Configuration snapshot for audit trail"""
    algorithm_version: str = "2.0.0"
    algorithm_name: str = "Multi-Layer Fuzzy Matcher"
    name_threshold: int = 85
    short_name_threshold: int = 95
    weights: Dict[str, float] = field(default_factory=lambda: {
        'name': 0.40,
        'document': 0.30,
        'dob': 0.15,
        'nationality': 0.10,
        'address': 0.05
    })
    recommendation_thresholds: Dict[str, int] = field(default_factory=lambda: {
        'auto_clear': 60,
        'manual_review': 85,
        'auto_escalate': 95
    })


@dataclass
class ScreeningResult:
    """Complete screening result with audit trail support"""
    input_name: str
    input_document: str
    input_country: str
    screening_date: datetime
    matches: List[ScreeningMatch]
    is_hit: bool
    
    # Audit trail fields
    screening_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    analyst_name: Optional[str] = None
    operator_id: Optional[str] = None
    
    # Decision fields
    decision: Optional[str] = None
    notes: Optional[str] = None
    
    # Configuration snapshot
    config: Optional[ScreeningConfig] = None
    
    # Processing metrics
    processing_time_ms: Optional[float] = None
    total_entities_searched: Optional[int] = None
    
    # Additional input fields
    input_dob: Optional[str] = None
    input_nationality: Optional[str] = None


class ReportMetadataCollector:
    """Collects metadata from sanctions data files"""
    
    def __init__(self, data_dir: Path = Path("sanctions_data")):
        self.data_dir = Path(data_dir)
    
    def get_file_hash(self, filepath: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def extract_ofac_metadata(self) -> Optional[ListMetadata]:
        """Extract metadata from OFAC file with dynamic namespace"""
        # Import shared utility to avoid code duplication
        from xml_utils import extract_xml_namespace
        
        xml_file = self.data_dir / "sdn_enhanced.xml"
        if not xml_file.exists():
            return None
        
        try:
            # Extract namespace dynamically using shared utility
            namespace = extract_xml_namespace(xml_file)
            
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Find publication date
            publish_info = root.find(f'{namespace}publishInformation')
            last_update_str = None
            if publish_info is not None:
                publish_date = publish_info.find(f'{namespace}publishDate')
                if publish_date is not None:
                    last_update_str = publish_date.text
            
            # Count entities
            entities = root.findall(f'.//{namespace}entity')
            record_count = len(entities)
            
            # File metadata
            stat = xml_file.stat()
            
            return ListMetadata(
                source="OFAC SDN Enhanced",
                file_path=str(xml_file),
                download_date=datetime.fromtimestamp(stat.st_ctime),
                last_update=datetime.fromisoformat(last_update_str) if last_update_str else datetime.fromtimestamp(stat.st_mtime),
                record_count=record_count,
                file_size=stat.st_size,
                file_hash=self.get_file_hash(xml_file),
                version="Enhanced XML"
            )
        except Exception as e:
            logger.error(f"Error extracting OFAC metadata: {e}")
            return None
    
    def extract_un_metadata(self) -> Optional[ListMetadata]:
        """Extract metadata from UN file"""
        xml_file = self.data_dir / "un_consolidated.xml"
        if not xml_file.exists():
            return None
        
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Count individuals and entities
            individuals = len(root.findall('.//INDIVIDUAL'))
            entities = len(root.findall('.//ENTITY'))
            record_count = individuals + entities
            
            # Get file stat first
            stat = xml_file.stat()
            
            # Find update date
            dategenerated = root.get('dateGenerated')
            last_update = None
            if dategenerated:
                try:
                    # Support ISO format with time and milliseconds
                    last_update = datetime.fromisoformat(dategenerated.replace('Z', ''))
                except Exception:
                    try:
                        last_update = datetime.strptime(dategenerated[:10], "%Y-%m-%d")
                    except Exception:
                        last_update = datetime.fromtimestamp(stat.st_mtime)
            
            return ListMetadata(
                source="UN Consolidated Sanctions List",
                file_path=str(xml_file),
                download_date=datetime.fromtimestamp(stat.st_ctime),
                last_update=last_update or datetime.fromtimestamp(stat.st_mtime),
                record_count=record_count,
                file_size=stat.st_size,
                file_hash=self.get_file_hash(xml_file)
            )
        except Exception as e:
            logger.error(f"Error extracting UN metadata: {e}")
            return None
    
    def collect_all_metadata(self) -> List[ListMetadata]:
        """Collect metadata from all sanctions lists"""
        metadata_list = []
        
        ofac_meta = self.extract_ofac_metadata()
        if ofac_meta:
            metadata_list.append(ofac_meta)
        
        un_meta = self.extract_un_metadata()
        if un_meta:
            metadata_list.append(un_meta)
        
        return metadata_list
    
    def check_data_freshness(self, warning_days: int = 7) -> List[str]:
        """Check if sanctions data is stale
        
        Args:
            warning_days: Days after which data is considered stale
            
        Returns:
            List of warning messages for stale data
        """
        warnings = []
        metadata_list = self.collect_all_metadata()
        cutoff = datetime.now() - timedelta(days=warning_days)
        
        for meta in metadata_list:
            if meta.last_update < cutoff:
                days_old = (datetime.now() - meta.last_update).days
                warnings.append(
                    f"{meta.source} data is {days_old} days old "
                    f"(last update: {meta.last_update.strftime('%Y-%m-%d')})"
                )
        
        return warnings


class ReportValidator:
    """Validates screening results before report generation"""
    
    REQUIRED_FIELDS = ['input_name', 'screening_date', 'is_hit', 'matches']
    
    def __init__(self, data_freshness_warning_days: int = 7):
        self.data_freshness_warning_days = data_freshness_warning_days
    
    def validate(self, result: ScreeningResult, 
                list_metadata: List[ListMetadata]) -> Dict[str, Any]:
        """Validate screening result before report generation
        
        Args:
            result: Screening result to validate
            list_metadata: List metadata for freshness check
            
        Returns:
            Validation result with 'valid', 'errors', 'warnings' keys
            
        Raises:
            ReportValidationError: If validation fails critically
        """
        errors = []
        warnings = []
        
        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if not hasattr(result, field) or getattr(result, field) is None:
                if field == 'matches':
                    # matches can be empty list
                    if not hasattr(result, field):
                        errors.append(f"Missing required field: {field}")
                else:
                    errors.append(f"Missing required field: {field}")
        
        # Check screening ID
        if not result.screening_id:
            warnings.append("No screening_id provided, generating one")
        
        # Check for scoring breakdown in matches
        for i, match in enumerate(result.matches):
            if match.confidence_breakdown is None:
                warnings.append(f"Match {i+1} missing confidence breakdown")
        
        # Check list metadata freshness
        cutoff = datetime.now() - timedelta(days=self.data_freshness_warning_days)
        for meta in list_metadata:
            if meta.last_update < cutoff:
                days_old = (datetime.now() - meta.last_update).days
                warnings.append(
                    f"⚠️ STALE DATA: {meta.source} is {days_old} days old"
                )
        
        # Check for empty/null critical fields in matches
        for i, match in enumerate(result.matches):
            if not match.matched_name:
                errors.append(f"Match {i+1} has empty matched_name")
            if not match.entity_id:
                warnings.append(f"Match {i+1} has no entity_id")
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.error(f"Report validation failed: {errors}")
        if warnings:
            logger.warning(f"Report validation warnings: {warnings}")
        
        return {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings
        }


class ConstanciaReportGenerator:
    """Enhanced report generator with validation and audit trail"""
    
    def __init__(self, output_dir: Path = Path("reports"), 
                 data_dir: Path = Path("sanctions_data"),
                 validate_before_generate: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.metadata_collector = ReportMetadataCollector(data_dir)
        self.validator = ReportValidator()
        self.validate_before_generate = validate_before_generate
        # Audit log file (append-only) en reports/audit_log
        self.audit_log_path = self.output_dir / "audit_log" / "screening_audit.log"
        (self.output_dir / "audit_log").mkdir(exist_ok=True)
    
    def _log_audit(self, result: ScreeningResult, list_metadata: List[ListMetadata]) -> None:
        """Write immutable audit log entry"""
        audit_entry = {
            'screening_id': result.screening_id,
            'timestamp': datetime.now().isoformat(),
            'input': {
                'name': result.input_name,
                'document': result.input_document,
                'country': result.input_country,
                'dob': result.input_dob,
                'nationality': result.input_nationality
            },
            'operator': result.operator_id or result.analyst_name or 'system',
            'is_hit': result.is_hit,
            'match_count': len(result.matches),
            'decision': result.decision,
            'list_versions': [
                {
                    'source': m.source,
                    'hash': m.file_hash[:16],
                    'last_update': m.last_update.isoformat()
                } for m in list_metadata
            ],
            'config': {
                'algorithm_version': result.config.algorithm_version if result.config else '2.0.0',
                'name_threshold': result.config.name_threshold if result.config else 85
            } if result.config else None
        }
        
        # Append to audit log
        with open(self.audit_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(audit_entry) + '\n')
        
        logger.info(f"Audit entry logged: {result.screening_id}")
    
    def generate_html_report(self, result: ScreeningResult, 
                            list_metadata: List[ListMetadata],
                            skip_validation: bool = False) -> str:
        """Generate professional HTML report with validation
        
        Args:
            result: Screening result
            list_metadata: List metadata
            skip_validation: Skip pre-generation validation
            
        Returns:
            Path to generated HTML file
            
        Raises:
            ReportValidationError: If validation fails and not skipped
        """
        # Validate before generation
        if self.validate_before_generate and not skip_validation:
            validation = self.validator.validate(result, list_metadata)
            if not validation['valid']:
                raise ReportValidationError(
                    f"Report validation failed: {validation['errors']}"
                )
            if validation['warnings']:
                logger.warning(f"Report warnings: {validation['warnings']}")
        
        # Log audit entry
        self._log_audit(result, list_metadata)
        
        template = Template("""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Constancia de Screening - {{ result.input_name }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 210mm;
            margin: 0 auto;
            padding: 20mm;
            background: #f5f5f5;
        }
        .report-container {
            background: white;
            padding: 40px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        .header {
            border-bottom: 3px solid #2c3e50;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #2c3e50;
            font-size: 24px;
            margin-bottom: 10px;
        }
        .header .subtitle {
            color: #7f8c8d;
            font-size: 14px;
        }
        .status-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            margin: 20px 0;
        }
        .status-hit { background: #e74c3c; color: white; }
        .status-clear { background: #27ae60; color: white; }
        .section {
            margin: 30px 0;
        }
        .section h2 {
            color: #34495e;
            font-size: 18px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .info-grid {
            display: grid;
            grid-template-columns: 200px 1fr;
            gap: 10px;
            margin: 15px 0;
        }
        .info-label {
            font-weight: bold;
            color: #7f8c8d;
        }
        .match-card {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            background: #f9f9f9;
        }
        .match-score {
            font-size: 24px;
            font-weight: bold;
            color: #e74c3c;
            float: right;
        }
        .metadata-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 12px;
        }
        .metadata-table th {
            background: #34495e;
            color: white;
            padding: 10px;
            text-align: left;
        }
        .metadata-table td {
            padding: 8px;
            border-bottom: 1px solid #e0e0e0;
        }
        .metadata-table tr:nth-child(even) {
            background: #f9f9f9;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            font-size: 12px;
            color: #7f8c8d;
        }
        .hash { 
            font-family: monospace; 
            font-size: 13px; 
            word-break: break-all;
            max-width: 400px;
            white-space: pre-wrap;
        }
        @media print {
            body { background: white; }
            .report-container { box-shadow: none; }
        }
    </style>
</head>
<body>
    <button onclick="window.print()" style="position:fixed;top:30px;right:40px;padding:10px 18px;font-size:16px;background:#34495e;color:#fff;border:none;border-radius:6px;cursor:pointer;z-index:1000;">🖨️ Imprimir Reporte</button>
    <div class="report-container">
        <div class="header" style="text-align:center;">
            <div style="display: flex; justify-content: center; align-items: center; gap: 40px; margin-bottom: 10px;">
                <img src="UN_logo_es.svg" alt="Logo Naciones Unidas" style="height:48px;">
                <img src="OFAC_Logo.png" alt="Logo OFAC" style="height:64px;">
            </div>
            <h1 style="margin-top:10px; font-size:24px;">CONSTANCIA DE VERIFICACIÓN DE LISTAS DE SANCIONES</h1>
            <div class="subtitle" style="margin-top:5px; color:#7f8c8d; font-size:14px;">Screening contra listas OFAC y UN</div>
        </div>

        <div class="status-badge {{ 'status-hit' if result.is_hit else 'status-clear' }}">
            {{ 'COINCIDENCIA DETECTADA' if result.is_hit else 'SIN COINCIDENCIAS' }}
        </div>

        <div class="section">
            <h2>📋 Información del Sujeto Evaluado</h2>
            <div class="info-grid">
                <div class="info-label">Nombre:</div>
                <div>{{ result.input_name if result.input_name else 'No Ingresado' }}</div>

                <div class="info-label">Documento:</div>
                <div>{{ result.input_document if result.input_document else 'No Ingresado' }}</div>

                <div class="info-label">País:</div>
                <div>{{ result.input_country if result.input_country else 'No Ingresado' }}</div>
                
                <div class="info-label">Fecha de Screening:</div>
                <div>{{ result.screening_date.strftime('%d/%m/%Y %H:%M:%S') }}</div>
                
                {% if result.analyst_name %}
                <div class="info-label">Analista:</div>
                {% if result.analyst_name %}
                    <div>{{ result.analyst_name }}</div>
                {% else %}
                    <div>Proceso masivo</div>
                {% endif %}
                {% endif %}
            </div>
        </div>

        {% if result.matches %}
        <div class="section">
            <h2>⚠️ Coincidencias Detectadas ({{ result.matches|length }})</h2>
            
            {% for match in result.matches %}
                <div class="match-card">
                    <div class="match-score">{{ '%.2f' % match.match_score }}%</div>
                    <h3 style="color: #e74c3c; margin-bottom: 10px;">{{ match.matched_name }}</h3>
                
                    <div class="info-grid" style="margin-top: 15px;">
                        <div class="info-label">Tipo:</div>
                        <div>{{ match.entity_type|upper }}</div>

                        <div class="info-label">Lista:</div>
                        <div><strong>{{ match.source }}</strong></div>

                        <div class="info-label">Identificación:</div>
                        <div style="font-size:1.2em;font-weight:bold;">
                            {% if match.identifications %}
                                {{ match.identifications | map(attribute='number') | select('string') | join(', ') }}
                            {% else %}
                                <span style="color:#e74c3c;">No disponible en la lista</span>
                            {% endif %}
                        </div>
                    
                        {% if match.last_name %}
                        <div class="info-label">Apellido:</div>
                        <div>{{ match.last_name }}</div>
                        {% endif %}
                    
                        {% if match.first_name %}
                        <div class="info-label">Nombre:</div>
                        <div>{{ match.first_name }}</div>
                        {% endif %}
                    
                        {% if match.nationality %}
                        <div class="info-label">Nacionalidad:</div>
                        <div>{{ match.nationality }}</div>
                        {% endif %}
                    
                        {% if match.title %}
                        <div class="info-label">Título:</div>
                        <div>{{ match.title }}</div>
                        {% endif %}
                    
                        {% if match.date_of_birth %}
                        <div class="info-label">Fecha de Nacimiento:</div>
                        <div>{{ match.date_of_birth }}</div>
                        {% endif %}
                    
                        {% if match.countries %}
                        <div class="info-label">Países:</div>
                        <div>{{ match.countries|join(', ') }}</div>
                        {% endif %}
                    
                        {% if 'SECONDARY_SANCTIONS_RISK' in match.flags %}
                        <div class="info-label" style="color:#d35400;font-weight:bold;">Riesgo de Sanciones Secundarias:</div>
                        <div style="color:#d35400;font-weight:bold;">⚠️ Este sujeto está vinculado a sanciones secundarias OFAC</div>
                        {% endif %}
                    </div>
                
                    {% if match.all_names|length > 1 %}
                    <div style="margin-top: 15px;">
                        <strong>Alias conocidos:</strong>
                        <ul style="margin-left: 20px; margin-top: 5px;">
                        {% for alias in match.all_names[1:] %}
                            <li>{{ alias }}</li>
                        {% endfor %}
                        </ul>
                    </div>
                    {% endif %}
                </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="section">
            <h2>✅ Resultado de Verificación</h2>
            <p style="color: #27ae60; font-size: 16px;">
                No se encontraron coincidencias en las listas de sanciones consultadas.
            </p>
        </div>
        {% endif %}

        <div class="section">
            <h2>📚 Listas Consultadas</h2>
            <table class="metadata-table">
                <thead>
                    <tr>
                        <th>Fuente</th>
                        <th>Última Actualización</th>
                        <th>Registros</th>
                        <th>Tamaño</th>
                        <th>🔐 Hash SHA256</th>
                    </tr>
                </thead>
                <tbody>
                {% for meta in list_metadata %}
                    <tr>
                        <td><strong>{{ meta.source }}</strong></td>
                        <td>{{ meta.last_update.strftime('%d/%m/%Y %H:%M') }}</td>
                        <td>{{ "{:,}".format(meta.record_count) }}</td>
                        <td>{{ "%.2f"|format(meta.file_size / 1024 / 1024) }} MB</td>
                        <td class="hash">🔐 {{ meta.file_hash }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>

        {% if result.decision or result.notes %}
        <div class="section">
            <h2>📝 Decisión y Observaciones</h2>
            {% if result.decision %}
            <div class="info-grid">
                <div class="info-label">Decisión:</div>
                <div><strong>{{ result.decision }}</strong></div>
            </div>
            {% endif %}
            {% if result.notes %}
            <p style="margin-top: 10px; padding: 15px; background: #fff3cd; border-left: 4px solid #ffc107;">
                {{ result.notes }}
            </p>
            {% endif %}
        </div>
        {% endif %}

        <div class="footer">
            <p><strong>Documento generado automáticamente</strong></p>
            <p>Fecha de generación: {{ datetime.now().strftime('%d/%m/%Y %H:%M:%S') }}</p>
            <p>Este reporte es válido únicamente para la fecha indicada. Las listas de sanciones se actualizan frecuentemente.</p>
        </div>
    </div>
</body>
</html>
        """)
        
        html_content = template.render(
            result=result,
            list_metadata=list_metadata,
            datetime=datetime
        )
        
        # Guardar archivo
        timestamp = result.screening_date.strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in result.input_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"constancia_{safe_name}_{timestamp}.html"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✓ Reporte HTML generado: {filepath}")
        return str(filepath)
    
    def generate_json_report(self, result: ScreeningResult, 
                            list_metadata: List[ListMetadata],
                            skip_validation: bool = False) -> str:
        """Generate structured JSON report with enhanced metadata
        
        Args:
            result: Screening result
            list_metadata: List metadata
            skip_validation: Skip pre-generation validation
            
        Returns:
            Path to generated JSON file
        """
        # Validate before generation
        if self.validate_before_generate and not skip_validation:
            validation = self.validator.validate(result, list_metadata)
            if not validation['valid']:
                raise ReportValidationError(
                    f"Report validation failed: {validation['errors']}"
                )
        
        report_data = {
            "screening_info": {
                "screening_id": result.screening_id,
                "input_name": result.input_name,
                "input_document": result.input_document,
                "input_country": result.input_country,
                "input_dob": result.input_dob,
                "input_nationality": result.input_nationality,
                "screening_date": result.screening_date.isoformat(),
                "analyst": result.analyst_name,
                "operator_id": result.operator_id,
                "is_hit": result.is_hit,
                "match_count": len(result.matches),
                "processing_time_ms": result.processing_time_ms,
                "total_entities_searched": result.total_entities_searched
            },
            "screening_configuration": {
                "algorithm_version": result.config.algorithm_version if result.config else "2.0.0",
                "algorithm_name": result.config.algorithm_name if result.config else "Multi-Layer Fuzzy Matcher",
                "name_threshold": result.config.name_threshold if result.config else 85,
                "short_name_threshold": result.config.short_name_threshold if result.config else 95,
                "weights": result.config.weights if result.config else None,
                "recommendation_thresholds": result.config.recommendation_thresholds if result.config else None
            } if result.config else {"algorithm_version": "2.0.0"},
            "matches": [
                {
                    "matched_name": m.matched_name,
                    "match_score": m.match_score,
                    "entity_id": m.entity_id,
                    "source": m.source,
                    "entity_type": m.entity_type,
                    "program": m.program,
                    "countries": m.countries,
                    "all_names": m.all_names,
                    "confidence_breakdown": {
                        "overall": m.confidence_breakdown.overall,
                        "name": m.confidence_breakdown.name,
                        "document": m.confidence_breakdown.document,
                        "dob": m.confidence_breakdown.dob,
                        "nationality": m.confidence_breakdown.nationality
                    } if m.confidence_breakdown else None,
                    "flags": m.flags,
                    "recommendation": m.recommendation,
                    "match_layer": m.match_layer,
                    "details": {
                        "last_name": m.last_name,
                        "first_name": m.first_name,
                        "nationality": m.nationality,
                        "title": m.title,
                        "citizenship": m.citizenship,
                        "date_of_birth": m.date_of_birth,
                        "place_of_birth": m.place_of_birth,
                        "gender": m.gender
                    },
                    "identifications": m.identifications,
                    "addresses": m.addresses
                }
                for m in result.matches
            ],
            "decision": {
                "decision": result.decision,
                "notes": result.notes
            },
            "lists_metadata": [
                {
                    "source": m.source,
                    "file_path": m.file_path,
                    "download_date": m.download_date.isoformat(),
                    "last_update": m.last_update.isoformat(),
                    "record_count": m.record_count,
                    "file_size_bytes": m.file_size,
                    "file_hash_sha256": m.file_hash,
                    "version": m.version
                }
                for m in list_metadata
            ],
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_version": "2.0",
                "screening_id": result.screening_id
            }
        }

        timestamp = result.screening_date.strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in result.input_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"constancia_{safe_name}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ JSON report generated: {filepath}")
        return str(filepath)


class AuditTrailManager:
    """Manages immutable audit trail for all screenings"""
    
    def __init__(self, audit_dir: Path = Path("reports/audit_log")):
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(exist_ok=True)
        self.audit_file = self.audit_dir / "screening_audit.jsonl"
    
    def log_screening(self, result: ScreeningResult, 
                     list_metadata: List[ListMetadata],
                     config_snapshot: Optional[Dict[str, Any]] = None) -> str:
        """Log screening to immutable audit trail
        
        Args:
            result: Screening result
            list_metadata: List metadata
            config_snapshot: Configuration snapshot
            
        Returns:
            Screening ID
        """
        entry = {
            "screening_id": result.screening_id,
            "timestamp": datetime.now().isoformat(),
            "input": {
                "name": result.input_name,
                "document": result.input_document,
                "country": result.input_country,
                "dob": result.input_dob,
                "nationality": result.input_nationality
            },
            "operator": result.operator_id or result.analyst_name or "system",
            "result": {
                "is_hit": result.is_hit,
                "match_count": len(result.matches),
                "top_score": max((m.match_score for m in result.matches), default=0)
            },
            "decision": result.decision,
            "list_versions": [
                {
                    "source": m.source,
                    "hash": m.file_hash,
                    "last_update": m.last_update.isoformat(),
                    "record_count": m.record_count
                }
                for m in list_metadata
            ],
            "config": config_snapshot
        }
        
        # Append to JSONL file (one JSON object per line)
        with open(self.audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        
        logger.info(f"Audit trail entry: {result.screening_id}")
        return result.screening_id
    
    def get_screening_by_id(self, screening_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve screening record by ID
        
        Args:
            screening_id: Screening ID to look up
            
        Returns:
            Screening record or None
        """
        if not self.audit_file.exists():
            return None
        
        with open(self.audit_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry.get('screening_id') == screening_id:
                        return entry
        
        return None
    
    def get_screenings_by_date_range(self, start: datetime, 
                                     end: datetime) -> List[Dict[str, Any]]:
        """Get all screenings within date range
        
        Args:
            start: Start datetime
            end: End datetime
            
        Returns:
            List of screening records
        """
        results = []
        
        if not self.audit_file.exists():
            return results
        
        with open(self.audit_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry['timestamp'])
                    if start <= entry_time <= end:
                        results.append(entry)
        
        return results


# Example usage
if __name__ == "__main__":
    # Example: Generate a test report
    analyst = "Proceso masivo"