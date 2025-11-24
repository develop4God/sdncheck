import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from rapidfuzz import fuzz, process
from datetime import datetime
import re

class SanctionsScreener:
    def __init__(self, data_dir="sanctions_data", match_threshold=80):
        self.data_dir = Path(data_dir)
        self.entities = []
        self.match_threshold = match_threshold
        
    def load_ofac(self):
        """Parse OFAC SDN Enhanced XML (sdn_enhanced.xml) - FIXED VERSION"""
        xml_file = self.data_dir / "sdn_enhanced.xml"
        if not xml_file.exists():
            print(f"⚠ {xml_file} not found")
            return
        
        NAMESPACE = '{https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML}'
        tree = ET.parse(xml_file)
        root = tree.getroot()
        count = 0
        
        for entity in root.findall(f'.//{NAMESPACE}entity'):
            names_section = entity.find(f'{NAMESPACE}names')
            if names_section is None:
                continue
            
            all_names = []
            
            for name_tag in names_section.findall(f'{NAMESPACE}name'):
                # Extract from translations
                translations = name_tag.find(f'{NAMESPACE}translations')
                if translations is not None:
                    for translation in translations.findall(f'{NAMESPACE}translation'):
                        formatted_full = translation.find(f'{NAMESPACE}formattedFullName')
                        if formatted_full is not None and formatted_full.text:
                            all_names.append(formatted_full.text.strip())
                
                # Also check direct text
                if name_tag.text and name_tag.text.strip():
                    all_names.append(name_tag.text.strip())
            
            # Skip if no names found
            if not all_names:
                continue
            
            # Remove duplicates while preserving order
            seen = set()
            unique_names = []
            for name in all_names:
                if name not in seen:
                    seen.add(name)
                    unique_names.append(name)
            
            # Extract countries from addresses
            countries = []
            addresses = entity.find(f'{NAMESPACE}addresses')
            if addresses is not None:
                for address in addresses.findall(f'{NAMESPACE}address'):
                    country = address.find(f'{NAMESPACE}country')
                    if country is not None and country.text:
                        countries.append(country.text.strip())
            
            # Extract countries from features (Nationality, Citizenship, etc.)
            features = entity.find(f'{NAMESPACE}features')
            if features is not None:
                for feature in features.findall(f'{NAMESPACE}feature'):
                    feature_type = feature.find(f'{NAMESPACE}type')
                    if feature_type is not None and feature_type.text:
                        type_text = feature_type.text.upper()
                        if 'NATIONAL' in type_text or 'CITIZEN' in type_text or 'COUNTRY' in type_text:
                            value = feature.find(f'{NAMESPACE}value')
                            if value is not None and value.text:
                                countries.append(value.text.strip())
            
            # Remove duplicates
            countries = list(set(countries))
            
            entry = {
                'name': unique_names[0],
                'all_names': unique_names,
                'aliases': unique_names[1:] if len(unique_names) > 1 else [],
                'type': entity.find(f'{NAMESPACE}entityType').text if entity.find(f'{NAMESPACE}entityType') is not None else 'entity',
                'source': 'OFAC',
                'id': entity.get('id'),
                'countries': countries,
                'nationality': None,
                'title': None,
                'citizenship': None,
                'dateOfBirth': None,
                'placeOfBirth': None,
                'gender': None,
                'addresses': []
            }
            
            # Get program
            programs = entity.find(f'{NAMESPACE}sanctionsPrograms')
            if programs is not None:
                entry['program'] = '; '.join([p.text for p in programs.findall(f'{NAMESPACE}sanctionsProgram') if p.text])
            else:
                entry['program'] = None
            
            self.entities.append(entry)
            count += 1
        
        print(f"✓ Loaded {count} OFAC entities from XML")
    
    def load_un(self):
        """Parse UN Consolidated XML"""
        un_file = self.data_dir / "un_consolidated.xml"
        if not un_file.exists():
            print(f"⚠ {un_file} not found")
            return
        
        tree = ET.parse(un_file)
        root = tree.getroot()
        count = 0
        
        for individual in root.findall('.//INDIVIDUAL'):
            first = individual.find('FIRST_NAME')
            last = individual.find('SECOND_NAME')
            
            if first is not None and last is not None:
                full_name = f"{first.text} {last.text}".strip()
            else:
                continue
            
            self.entities.append({
                'name': full_name,
                'all_names': [full_name],
                'aliases': [],
                'type': 'individual',
                'program': 'UN',
                'source': 'UN',
                'id': individual.find('DATAID').text if individual.find('DATAID') is not None else ''
            })
            count += 1
        
        print(f"✓ Loaded {count} UN entities")
    
    def normalize_name(self, name):
        """Normalize for better matching"""
        import unicodedata
        if not name:
            return ""
        # Remove accents
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        # Remove special chars, keep alphanumeric and spaces
        name = re.sub(r'[^\w\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name)
        return name.upper().strip()
    
    def search(self, query, limit=10, country_filter=None):
        """Fuzzy search entities against all names and aliases with optional country filter"""
        query_norm = self.normalize_name(query)
        matches = []
        
        # High-risk sanctioned countries - always search regardless of filter
        HIGH_RISK = ['VE', 'RU', 'CU', 'IR', 'KP', 'SY', 'VENEZUELA', 'RUSSIA', 'CUBA', 'IRAN', 'NORTH KOREA', 'SYRIA']
        
        for idx, entity in enumerate(self.entities):
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
            
            if best_score >= self.match_threshold:
                entity_countries = entity.get('countries', [])
                
                # Apply country filter logic
                if country_filter:
                    # Always include high-risk countries
                    is_high_risk = any(c.upper() in HIGH_RISK for c in entity_countries)
                    
                    # Check if input country matches entity countries
                    country_match = not entity_countries or country_filter.upper() in [c.upper() for c in entity_countries]
                    
                    # Skip if not high-risk and no country match
                    if not is_high_risk and not country_match:
                        continue
                
                matches.append({
                    'name': best_name,
                    'match_score': round(best_score, 2),
                    'source': entity['source'],
                    'type': entity['type'],
                    'program': entity['program'],
                    'id': entity['id'],
                    'countries': entity_countries
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        return matches[:limit]
    
    def bulk_screen(self, csv_file, output_json="results.json", output_csv="results_detailed.csv"):
        """Screen bulk CSV (nombre,cedula,pais) and save detailed CSV report"""
        results = []
        detailed_rows = []
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                nombre = row.get('nombre', '').strip()
                cedula = row.get('cedula', '').strip()
                pais = row.get('pais', '').strip()
                
                matches = self.search(nombre, limit=10)
                hit = any(float(m.get('match_score', 0)) >= self.match_threshold for m in matches)
                
                results.append({
                    'input': {'nombre': nombre, 'cedula': cedula, 'pais': pais},
                    'matches': matches,
                    'hit': hit,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Para cada match, guardar fila detallada
                for m in matches:
                    detailed_rows.append({
                        'input_nombre': nombre,
                        'input_cedula': cedula,
                        'input_pais': pais,
                        'match_name': m.get('name',''),
                        'match_score': m.get('match_score',''),
                        'source': m.get('source',''),
                        'type': m.get('type',''),
                        'program': m.get('program',''),
                        'id': m.get('id',''),
                        'timestamp': datetime.now().isoformat()
                    })
        
        # Save results JSON
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Save detailed CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['input_nombre','input_cedula','input_pais','match_name','match_score','source','type','program','id','timestamp']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in detailed_rows:
                writer.writerow(row)
        
        print(f"\n✓ Screened {len(results)} records")
        print(f"✓ Hits: {sum(1 for r in results if r['hit'])}")
        print(f"✓ Results saved to {output_json}")
        print(f"✓ Detailed CSV saved to {output_csv}")
        return results

if __name__ == "__main__":
    print("=== SDN Screener Test ===\n")
    
    screener = SanctionsScreener()  # Uses default threshold from __init__
    screener.load_ofac()
    screener.load_un()
    
    print(f"\nTotal entities loaded: {len(screener.entities)}\n")

    # Test searches
    print("Test search: 'Nicolas Maduro'")
    matches = screener.search("Nicolas Maduro", limit=10)
    if matches:
        for m in matches:
            print(f"  {m['match_score']}% - {m['name']} (ID: {m['id']}, {m['source']})")
    else:
        print("  No matches found")

    print("\nTest search: 'BANCO NACIONAL DE CUBA'")
    matches2 = screener.search("BANCO NACIONAL DE CUBA", limit=5)
    for m in matches2:
        print(f"  {m['match_score']}% - {m['name']} ({m['source']})")

    # Bulk screening if input.csv exists
    input_file = Path("input.csv")
    if input_file.exists():
        print("\n=== Running Bulk Screening ===")
        screener.bulk_screen('input.csv', 'results.json', 'results_detailed.csv')
    else:
        print("\n--- Ready for bulk screening ---")
        print("Create input.csv with: nombre,cedula,pais")