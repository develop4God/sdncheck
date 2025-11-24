"""
Sistema de Generación de Reportes de Constancia
Genera reportes oficiales con información de screening y metadata de listas
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import json
import hashlib
from jinja2 import Template
import xml.etree.ElementTree as ET


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
class ScreeningMatch:
    """Resultado de un match individual"""
    matched_name: str
    match_score: float
    entity_id: str
    source: str
    entity_type: str
    program: str
    countries: List[str]
    all_names: List[str]
    
    # Campos adicionales del ejemplo
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
class ScreeningResult:
    """Resultado completo de screening"""
    input_name: str
    input_document: str
    input_country: str
    screening_date: datetime
    matches: List[ScreeningMatch]
    is_hit: bool
    analyst_name: Optional[str] = None
    decision: Optional[str] = None
    notes: Optional[str] = None


class ReportMetadataCollector:
    """Recolecta metadata de archivos de sanciones"""
    
    def __init__(self, data_dir: Path = Path("sanctions_data")):
        self.data_dir = data_dir
    
    def get_file_hash(self, filepath: Path) -> str:
        """Calcula SHA256 del archivo"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def extract_ofac_metadata(self) -> Optional[ListMetadata]:
        """Extrae metadata de archivo OFAC"""
        xml_file = self.data_dir / "sdn_enhanced.xml"
        if not xml_file.exists():
            return None
        
        try:
            # Parse XML para contar entidades
            NAMESPACE = '{https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML}'
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Buscar fecha de publicación
            publish_info = root.find(f'{NAMESPACE}publishInformation')
            last_update_str = None
            if publish_info is not None:
                publish_date = publish_info.find(f'{NAMESPACE}publishDate')
                if publish_date is not None:
                    last_update_str = publish_date.text
            
            # Contar entidades
            entities = root.findall(f'.//{NAMESPACE}entity')
            record_count = len(entities)
            
            # Metadata del archivo
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
            print(f"Error extracting OFAC metadata: {e}")
            return None
    
    def extract_un_metadata(self) -> Optional[ListMetadata]:
        """Extrae metadata de archivo UN"""
        xml_file = self.data_dir / "un_consolidated.xml"
        if not xml_file.exists():
            return None
        
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Contar individuos y entidades
            individuals = len(root.findall('.//INDIVIDUAL'))
            entities = len(root.findall('.//ENTITY'))
            record_count = individuals + entities
            
            # Buscar fecha de actualización
            dategenerated = root.get('dateGenerated')
            last_update = None
            if dategenerated:
                try:
                    # Soporta formato ISO con hora y milisegundos
                    last_update = datetime.fromisoformat(dategenerated.replace('Z', ''))
                except Exception:
                    try:
                        last_update = datetime.strptime(dategenerated[:10], "%Y-%m-%d")
                    except Exception:
                        last_update = datetime.fromtimestamp(stat.st_mtime)
            
            stat = xml_file.stat()
            
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
            print(f"Error extracting UN metadata: {e}")
            return None
    
    def collect_all_metadata(self) -> List[ListMetadata]:
        """Recolecta metadata de todas las listas"""
        metadata_list = []
        
        ofac_meta = self.extract_ofac_metadata()
        if ofac_meta:
            metadata_list.append(ofac_meta)
        
        un_meta = self.extract_un_metadata()
        if un_meta:
            metadata_list.append(un_meta)
        
        return metadata_list


class ConstanciaReportGenerator:
    """Genera reportes de constancia en múltiples formatos"""
    
    def __init__(self, output_dir: Path = Path("reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.metadata_collector = ReportMetadataCollector()
    
    def generate_html_report(self, result: ScreeningResult, 
                            list_metadata: List[ListMetadata]) -> str:
        """Genera reporte HTML profesional"""
        
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
                    <div class="match-score">{{ match.match_score }}%</div>
                    <h3 style="color: #e74c3c; margin-bottom: 10px;">{{ match.matched_name }}</h3>
                
                    <div class="info-grid" style="margin-top: 15px;">
                        <div class="info-label">Tipo:</div>
                        <div>{{ match.entity_type|upper }}</div>
                    
                        <div class="info-label">Lista:</div>
                        <div><strong>{{ match.source }}</strong></div>
                    
                        <div class="info-label">ID:</div>
                        <div class="hash">{{ match.entity_id if match.entity_id else 'No Ingresado' }}</div>
                    
                        <div class="info-label">Programa:</div>
                        <div>{{ match.program or 'N/A' }}</div>
                    
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
                            list_metadata: List[ListMetadata]) -> str:
        """Genera reporte JSON estructurado"""
        report_data = {
            "screening_info": {
                "input_name": result.input_name,
                "input_document": result.input_document,
                "input_country": result.input_country,
                "screening_date": result.screening_date.isoformat(),
                "analyst": result.analyst_name,
                "is_hit": result.is_hit,
                "match_count": len(result.matches)
            },
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
                    "details": {
                        "last_name": m.last_name,
                        "first_name": m.first_name,
                        "nationality": m.nationality,
                        "title": m.title,
                        "citizenship": m.citizenship,
                        "date_of_birth": m.date_of_birth,
                        "place_of_birth": m.place_of_birth,
                        "gender": m.gender
                    }
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
                "report_version": "2.0"
            }
        }

        timestamp = result.screening_date.strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in result.input_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"constancia_{safe_name}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Reporte JSON generado: {filepath}")
        return str(filepath)


# Ejemplo de uso
if __name__ == "__main__":
    # Analista fijo: Proceso masivo
    analista = "Proceso masivo"