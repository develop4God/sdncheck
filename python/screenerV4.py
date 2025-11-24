"""
Screener Mejorado v2.0 - Con generación automática de constancias
Integra la lógica de screening con reportes profesionales
"""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from rapidfuzz import fuzz
from datetime import datetime
import re
from typing import List, Dict, Optional
import unicodedata

# Importar el generador de reportes
import sys
sys.path.append(str(Path(__file__).parent))


class ImprovedSanctionsScreener:
    """Screener mejorado con logging, validación y reportes"""
    
    def __init__(self, data_dir="sanctions_data", match_threshold=80):
        self.data_dir = Path(data_dir)
        self.entities = []
        self.match_threshold = match_threshold
        self.screening_history = []
        
        # Crear directorio de reportes
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)
        
        print(f"🔧 Screener inicializado:")
        print(f"   - Directorio de datos: {self.data_dir}")
        print(f"   - Umbral de coincidencia: {self.match_threshold}%")
        print(f"   - Directorio de reportes: {self.reports_dir}")
    
    def load_ofac(self) -> int:
        """Carga entidades OFAC con extracción completa de campos"""
        xml_file = self.data_dir / "sdn_enhanced.xml"
        if not xml_file.exists():
            print(f"⚠  {xml_file} no encontrado")
            return 0
        
        NAMESPACE = '{https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML}'
        tree = ET.parse(xml_file)
        root = tree.getroot()
        count = 0
        
        for entity in root.findall(f'.//{NAMESPACE}entity'):
            # Extraer tipo de entidad
            entity_type_elem = entity.find(f'{NAMESPACE}entityType')
            entity_type = entity_type_elem.text if entity_type_elem is not None else 'entity'
            
            # Extraer todos los nombres
            names_section = entity.find(f'{NAMESPACE}names')
            if names_section is None:
                continue
            
            all_names = []
            for name_tag in names_section.findall(f'{NAMESPACE}name'):
                translations = name_tag.find(f'{NAMESPACE}translations')
                if translations is not None:
                    for translation in translations.findall(f'{NAMESPACE}translation'):
                        formatted_full = translation.find(f'{NAMESPACE}formattedFullName')
                        if formatted_full is not None and formatted_full.text:
                            all_names.append(formatted_full.text.strip())
            
            if not all_names:
                continue
            
            # Remover duplicados
            all_names = list(dict.fromkeys(all_names))
            
            # Extraer países
            countries = []
            addresses_elem = entity.find(f'{NAMESPACE}addresses')
            if addresses_elem is not None:
                for address in addresses_elem.findall(f'{NAMESPACE}address'):
                    country = address.find(f'{NAMESPACE}country')
                    if country is not None and country.text:
                        countries.append(country.text.strip())
            
            # Extraer características (nacionalidad, ciudadanía, etc.)
            features = entity.find(f'{NAMESPACE}features')
            nationality = None
            citizenship = None
            title = None
            date_of_birth = None
            place_of_birth = None
            gender = None
            
            if features is not None:
                for feature in features.findall(f'{NAMESPACE}feature'):
                    feature_type = feature.find(f'{NAMESPACE}type')
                    if feature_type is not None and feature_type.text:
                        type_text = feature_type.text.upper()
                        value_elem = feature.find(f'{NAMESPACE}value')
                        value = value_elem.text if value_elem is not None else None
                        
                        if 'NATIONAL' in type_text:
                            nationality = value
                            if value:
                                countries.append(value)
                        elif 'CITIZEN' in type_text:
                            citizenship = value
                            if value:
                                countries.append(value)
                        elif 'TITLE' in type_text:
                            title = value
                        elif 'DOB' in type_text or 'BIRTH' in type_text:
                            date_of_birth = value
                        elif 'POB' in type_text or 'PLACE' in type_text:
                            place_of_birth = value
                        elif 'GENDER' in type_text:
                            gender = value
            
            countries = list(set(countries))
            
            # Extraer programa de sanciones
            programs = entity.find(f'{NAMESPACE}sanctionsPrograms')
            program = None
            if programs is not None:
                program_list = [p.text for p in programs.findall(f'{NAMESPACE}sanctionsProgram') if p.text]
                program = '; '.join(program_list) if program_list else None
            
            # Extraer direcciones detalladas
            addresses_list = []
            if addresses_elem is not None:
                for address in addresses_elem.findall(f'{NAMESPACE}address'):
                    addr_dict = {}
                    for field in ['addressLine1', 'city', 'stateProvince', 'postalCode', 'country']:
                        elem = address.find(f'{NAMESPACE}{field}')
                        if elem is not None and elem.text:
                            addr_dict[field] = elem.text.strip()
                    if addr_dict:
                        addresses_list.append(addr_dict)
            
            # Extraer identificaciones
            identifications = []
            identity = entity.find(f'{NAMESPACE}identity')
            if identity is not None:
                id_docs = identity.find(f'{NAMESPACE}idDocuments')
                if id_docs is not None:
                    for id_doc in id_docs.findall(f'{NAMESPACE}idDocument'):
                        id_dict = {}
                        for field in ['type', 'number', 'issuedByCountry', 'issueDate', 'expirationDate']:
                            elem = id_doc.find(f'{NAMESPACE}{field}')
                            if elem is not None and elem.text:
                                id_dict[field] = elem.text.strip()
                        if id_dict:
                            identifications.append(id_dict)
            
            entry = {
                'name': all_names[0],
                'all_names': all_names,
                'aliases': all_names[1:] if len(all_names) > 1 else [],
                'type': entity_type,
                'source': 'OFAC',
                'id': entity.get('id'),
                'countries': countries,
                'nationality': nationality,
                'title': title,
                'citizenship': citizenship,
                'dateOfBirth': date_of_birth,
                'placeOfBirth': place_of_birth,
                'gender': gender,
                'program': program,
                'addresses': addresses_list,
                'identifications': identifications
            }
            
            # Extraer nombre y apellido si es individuo
            if entity_type.lower() == 'individual':
                if identity is not None:
                    first_name = identity.find(f'{NAMESPACE}firstName')
                    last_name = identity.find(f'{NAMESPACE}lastName')
                    entry['firstName'] = first_name.text if first_name is not None else None
                    entry['lastName'] = last_name.text if last_name is not None else None
            
            self.entities.append(entry)
            count += 1
        
        print(f"✓ Cargadas {count} entidades OFAC")
        return count
    
    def load_un(self) -> int:
        """Carga entidades UN incluyendo alias y nombres extendidos"""
        un_file = self.data_dir / "un_consolidated.xml"
        if not un_file.exists():
            print(f"⚠  {un_file} no encontrado")
            return 0

        tree = ET.parse(un_file)
        root = tree.getroot()
        count = 0

        for individual in root.findall('.//INDIVIDUAL'):
            names = []
            # Nombres principales
            first = individual.find('FIRST_NAME')
            second = individual.find('SECOND_NAME')
            third = individual.find('THIRD_NAME')
            fourth = individual.find('FOURTH_NAME')

            # Construir nombre completo
            name_parts = [n.text for n in [first, second, third, fourth] if n is not None and n.text]
            if name_parts:
                full_name = " ".join(name_parts).strip()
                names.append(full_name)
            else:
                continue

            # Agregar alias
            for alias in individual.findall('INDIVIDUAL_ALIAS'):
                alias_name = alias.find('ALIAS_NAME')
                if alias_name is not None and alias_name.text:
                    names.append(alias_name.text.strip())

            # Remover duplicados
            names = list(dict.fromkeys(names))

            self.entities.append({
                'name': names[0],
                'all_names': names,
                'aliases': names[1:] if len(names) > 1 else [],
                'type': 'individual',
                'program': 'UN',
                'source': 'UN',
                'id': individual.find('DATAID').text if individual.find('DATAID') is not None else ''
            })
            count += 1

        print(f"✓ Cargadas {count} entidades UN (con alias y nombres extendidos)")
        return count
    
    def normalize_name(self, name: str) -> str:
        """Normalización avanzada de nombres"""
        if not name:
            return ""
        # Remover acentos
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        # Remover caracteres especiales
        name = re.sub(r'[^\w\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name)
        return name.upper().strip()
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Búsqueda con scoring mejorado (sin filtro por país)"""
        query_norm = self.normalize_name(query)
        matches = []

        for entity in self.entities:
            all_names = entity.get('all_names', [entity.get('name', '')])
            best_score = 0
            best_name = None

            for candidate_name in all_names:
                if not candidate_name:
                    continue
                candidate_norm = self.normalize_name(candidate_name)
                score = fuzz.token_sort_ratio(query_norm, candidate_norm)
                if score > best_score:
                    best_score = score
                    best_name = candidate_name

            # Mejorar filtro para empresas: permitir coincidencias exactas y parciales relevantes
            if best_score >= self.match_threshold:
                match_dict = {
                    'name': best_name,
                    'match_score': round(best_score, 2),
                    'source': entity['source'],
                    'type': entity['type'],
                    'program': entity.get('program'),
                    'id': entity['id'],
                    'countries': entity.get('countries', []),
                    'all_names': all_names
                }

                # Agregar campos adicionales si existen
                for field in ['firstName', 'lastName', 'nationality', 'title',
                             'citizenship', 'dateOfBirth', 'placeOfBirth', 'gender',
                             'addresses', 'identifications']:
                    if field in entity:
                        match_dict[field] = entity[field]

                matches.append(match_dict)

        matches.sort(key=lambda x: x['match_score'], reverse=True)
        return matches[:limit]
    
    def screen_individual(self, name: str, document: str, country: str,
                         analyst: str = None,
                         generate_report: bool = True) -> Dict:
        """
        Screening individual con generación automática de constancia
        
        Args:
            name: Nombre a verificar
            document: Documento de identidad
            country: País (no se usa para filtro)
            analyst: Nombre del analista (opcional)
            generate_report: Si generar reporte automáticamente
        
        Returns:
            Dict con resultado del screening y rutas de reportes
        """
        screening_date = datetime.now()
        matches = self.search(name, limit=10)
        is_hit = len(matches) > 0
        
        result = {
            'input': {
                'name': name,
                'document': document,
                'country': country
            },
            'screening_date': screening_date.isoformat(),
            'matches': matches,
            'is_hit': is_hit,
            'hit_count': len(matches),
            'analyst': analyst
        }
        
        # Guardar en historial
        self.screening_history.append(result)
        
        # Generar reportes si se solicita
        report_files = {}
        if generate_report:
            try:
                from report_generator import (
                    ConstanciaReportGenerator, ScreeningResult, 
                    ScreeningMatch, ReportMetadataCollector
                )
                
                # Convertir matches a objetos ScreeningMatch
                screening_matches = []
                for m in matches:
                    screening_matches.append(ScreeningMatch(
                        matched_name=m['name'],
                        match_score=m['match_score'],
                        entity_id=m['id'],
                        source=m['source'],
                        entity_type=m['type'],
                        program=m.get('program', ''),
                        countries=m.get('countries', []),
                        all_names=m.get('all_names', []),
                        last_name=m.get('lastName'),
                        first_name=m.get('firstName'),
                        nationality=m.get('nationality'),
                        title=m.get('title'),
                        citizenship=m.get('citizenship'),
                        date_of_birth=m.get('dateOfBirth'),
                        place_of_birth=m.get('placeOfBirth'),
                        gender=m.get('gender'),
                        identifications=m.get('identifications', []),
                        addresses=m.get('addresses', [])
                    ))
                
                screening_result = ScreeningResult(
                    input_name=name,
                    input_document=document,
                    input_country=country,
                    screening_date=screening_date,
                    matches=screening_matches,
                    is_hit=is_hit,
                    analyst_name=analyst
                )
                
                generator = ConstanciaReportGenerator(self.reports_dir)
                metadata = ReportMetadataCollector(self.data_dir).collect_all_metadata()
                
                report_files['html'] = generator.generate_html_report(screening_result, metadata)
                report_files['json'] = generator.generate_json_report(screening_result, metadata)
                
                result['report_files'] = report_files
                
            except ImportError:
                print("⚠ Módulo de reportes no disponible. Instala dependencias: pip install jinja2")
        
        return result
    
    def bulk_screen_with_reports(self, csv_file: str,
                                analyst: str = None,
                                generate_individual_reports: bool = False):
        """
        Screening masivo con reportes consolidados
        
        Args:
            csv_file: Archivo CSV con columnas: nombre,cedula,pais
            analyst: Nombre del analista
            generate_individual_reports: Si generar reporte por cada persona
        """
        results = []
        hits = []
        
        print(f"\n{'='*60}")
        print(f"SCREENING MASIVO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total = sum(1 for _ in open(csv_file)) - 1  # Contar líneas
            
            f.seek(0)  # Resetear
            next(reader)  # Saltar header
            
            for idx, row in enumerate(reader, 1):
                nombre = row.get('nombre', '').strip()
                cedula = row.get('cedula', '').strip()
                pais = row.get('pais', '').strip()  # No se usa para filtro
                
                print(f"[{idx}/{total}] Verificando: {nombre}...", end=' ')
                
                result = self.screen_individual(
                    name=nombre,
                    document=cedula,
                    country=pais,
                    analyst=analyst,
                    generate_report=generate_individual_reports
                )
                
                results.append(result)
                
                if result['is_hit']:
                    hits.append(result)
                    print(f"⚠️  HIT ({result['hit_count']} coincidencias)")
                else:
                    print("✓ Sin coincidencias")
        
        # Guardar resumen consolidado
        summary = {
            'screening_info': {
                'date': datetime.now().isoformat(),
                'analyst': analyst,
                'total_screened': len(results),
                'total_hits': len(hits),
                'hit_rate': f"{len(hits)/len(results)*100:.2f}%" if results else "0%"
            },
            'results': results,
            'hits_only': hits
        }
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.reports_dir / f"bulk_screening_summary_{timestamp}.json"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print(f"RESUMEN DE SCREENING")
        print(f"{'='*60}")
        print(f"Total verificados: {len(results)}")
        print(f"Coincidencias (HITS): {len(hits)}")
        print(f"Tasa de coincidencia: {len(hits)/len(results)*100:.2f}%")
        print(f"\n✓ Resumen guardado en: {summary_file}")
        
        return summary


# Ejemplo de uso
if __name__ == "__main__":
    print("=== SDN Screener Mejorado v2.0 ===\n")
    
    screener = ImprovedSanctionsScreener(match_threshold=75)
    screener.load_ofac()
    screener.load_un()
    
    print(f"\nTotal entidades cargadas: {len(screener.entities)}\n")
    

    
    # Abrir ventana de diálogo para seleccionar el archivo CSV
    # Usar archivo CSV hardcodeado
    csv_path = "input.csv"
    print(f"Usando archivo CSV: {csv_path}")
    input_file = Path(csv_path)
    if csv_path and input_file.exists():
        print(f"\n{'='*60}")
        print(f"Iniciando Screening Masivo con umbral de coincidencia: {screener.match_threshold}%...")
        print(f"{'='*60}\n")
        summary = screener.bulk_screen_with_reports(
            csv_file=csv_path,
            analyst=None,
            generate_individual_reports=True  # Genera reportes individuales
        )
    else:
        print(f"\n💡 No se seleccionó un archivo válido. Por favor crea un CSV con las columnas: nombre,cedula,pais")