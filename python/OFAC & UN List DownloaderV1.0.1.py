import requests
from pathlib import Path
from datetime import datetime
import zipfile
# Importamos la librería estándar para manejar XML
import xml.etree.ElementTree as ET 

# Download directory
DATA_DIR = Path("sanctions_data")
DATA_DIR.mkdir(exist_ok=True)

def download_ofac():
    """Download OFAC SDN list (Enhanced XML only)"""
    urls = {
        'enhanced': 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.ZIP', 
    }
    
    for name, url in urls.items():
        print(f"Downloading OFAC {name}...")
        
        with requests.get(url, stream=True, timeout=60) as response: 
            response.raise_for_status()
            
            filepath = DATA_DIR / f"ofac_{name}.zip"
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_bytes = filepath.stat().st_size 
            size_output = f"{size_bytes / 1024 / 1024:.1f} MB"
            print(f"✓ Saved {filepath} ({size_output})")
    
    return True

def unzip_enhanced_xml():
    """Descomprime el archivo OFAC 'ofac_enhanced.zip' y extrae el XML 'SDN_ENHANCED.XML'."""
    zip_filepath = DATA_DIR / "ofac_enhanced.zip"
    
    # ### CORRECCIÓN CLAVE: Nombre exacto dentro del ZIP
    xml_filename_inside_zip = "SDN_ENHANCED.XML" 
    xml_filename_final = "sdn_enhanced.xml"
    
    print(f"\nExtracting {zip_filepath.name}...")
    try:
        with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
            # Extrae el archivo usando el nombre interno confirmado
            zip_ref.extract(xml_filename_inside_zip, DATA_DIR) 
            
            # Renombramos el archivo extraído (SDN_ENHANCED.XML) a nuestro nombre estándar (sdn_enhanced.xml)
            extracted_path = DATA_DIR / xml_filename_inside_zip
            final_path = DATA_DIR / xml_filename_final
            
            if extracted_path.exists():
                extracted_path.rename(final_path)
            
        print(f"✓ Extracted and Renamed to {final_path.name}")
        return final_path
    except FileNotFoundError:
        print(f"✗ Error: Zip file not found at {zip_filepath}. Skipping extraction.")
        return None
    except KeyError:
        # Esto captura el error si el nombre del archivo dentro del ZIP aún es incorrecto
        print(f"✗ Extraction Error: Could not find '{xml_filename_inside_zip}' inside the zip file.")
        print("Please verify the file name inside the zip if this error persists.")
        return None
    except Exception as e:
        print(f"✗ Extraction Error: {e}")
        return None

def parse_ofac_xml(filepath):
    """Parses the OFAC SDN Enhanced XML and extracts key data."""
    print(f"\nParsing OFAC XML from {filepath.name}...")
    
    NAMESPACE = '{https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ENHANCED_XML}'
    target_tag = f'{NAMESPACE}entity'
    
    sanctions_list = []
    
    context = ET.iterparse(filepath, events=("end",)) 
    count = 0
    for event, elem in context:
        if event == "end" and elem.tag == target_tag:
            count += 1
            entry = {}
            entry['list'] = 'OFAC_SDN'
            entry['uid'] = elem.get('id')
            
            identity = elem.find(f'{NAMESPACE}identity')
            if identity is not None:
                entry['name'] = identity.find(f'{NAMESPACE}name').text if identity.find(f'{NAMESPACE}name') is not None else None
                entry['firstName'] = identity.find(f'{NAMESPACE}firstName').text if identity.find(f'{NAMESPACE}firstName') is not None else None
                entry['lastName'] = identity.find(f'{NAMESPACE}lastName').text if identity.find(f'{NAMESPACE}lastName') is not None else None
                
                aliases = []
                for alias_tag in identity.findall(f'{NAMESPACE}alias'):
                    alias_name = alias_tag.find(f'{NAMESPACE}name')
                    if alias_name is not None:
                        aliases.append(alias_name.text)
                entry['aliases'] = aliases
                
                entry['dateOfBirth'] = None
                id_data = identity.find(f'{NAMESPACE}idRegimeReference')
                if id_data is not None:
                    dob = id_data.find(f'{NAMESPACE}dateOfBirth')
                    if dob is not None and dob.find(f'{NAMESPACE}date') is not None:
                        entry['dateOfBirth'] = dob.find(f'{NAMESPACE}date').text
            
            sanctions_list.append(entry)
            elem.clear() 

    print(f"✓ Parsed {count} entries from OFAC XML.")
    return sanctions_list

def download_un():
    """Download UN Consolidated List (XML)"""
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    
    print("Downloading UN Consolidated List...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    
    filepath = DATA_DIR / "un_consolidated.xml"
    filepath.write_bytes(response.content)
    print(f"✓ Saved {filepath} ({len(response.content)/1024/1024:.1f} MB)")
    
    return filepath 

def parse_un_xml(filepath):
    """
    Parses the UN Consolidated List XML for individuals and entities.
    ### CORRECCIÓN: Se añaden múltiples verificaciones de None para evitar el error 'NoneType' object has no attribute 'text'
    """
    print(f"\nParsing UN XML from {filepath.name}...")
    sanctions_list = []
    
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception as e:
        print(f"✗ Error reading UN XML: {e}")
        return sanctions_list
    
    
    # 1. Parsear Individuos
    for individual in root.findall('./INDIVIDUALS/INDIVIDUAL'):
        entry = {}
        entry['list'] = 'UN_CONSOLIDATED'
        
        dataid_tag = individual.find('DATAID')
        entry['uid'] = dataid_tag.text if dataid_tag is not None else 'N/A'
        
        # Nombres (Todos pueden ser None)
        first_name_tag = individual.find('FIRST_NAME')
        second_name_tag = individual.find('SECOND_NAME')
        third_name_tag = individual.find('THIRD_NAME')
        fourth_name_tag = individual.find('FOURTH_NAME')
        dob_tag = individual.find('DATE_OF_BIRTH')

        first_name = first_name_tag.text if first_name_tag is not None else ''
        second_name = second_name_tag.text if second_name_tag is not None else ''
        third_name = third_name_tag.text if third_name_tag is not None else ''
        
        entry['firstName'] = first_name
        entry['lastName'] = fourth_name_tag.text if fourth_name_tag is not None else '' 
        entry['name'] = f"{first_name} {second_name} {third_name} {entry['lastName']}".strip()
        
        # Alias
        aliases = []
        for alias_tag in individual.findall('./INDIVIDUAL_ALIAS/ALIAS_NAME'):
             if alias_tag.text: aliases.append(alias_tag.text)
        entry['aliases'] = aliases

        # Fecha de Nacimiento
        entry['dateOfBirth'] = dob_tag.text if dob_tag is not None else None
        
        sanctions_list.append(entry)

    # 2. Parsear Entidades
    for entity in root.findall('./ENTITIES/ENTITY'):
        entry = {}
        entry['list'] = 'UN_CONSOLIDATED'
        
        dataid_tag = entity.find('DATAID')
        name_tag = entity.find('NAME')
        
        entry['uid'] = dataid_tag.text if dataid_tag is not None else 'N/A'
        entry['name'] = name_tag.text if name_tag is not None else 'N/A'
        
        entry['firstName'] = None
        entry['lastName'] = None
        
        # Alias
        aliases = []
        for alias_tag in entity.findall('./ENTITY_ALIAS/ALIAS_NAME'):
             if alias_tag.text: aliases.append(alias_tag.text)
        entry['aliases'] = aliases
        entry['dateOfBirth'] = None
        
        sanctions_list.append(entry)
        
    print(f"✓ Parsed {len(sanctions_list)} entries ({len(root.findall('./INDIVIDUALS/INDIVIDUAL'))} Inds, {len(root.findall('./ENTITIES/ENTITY'))} Ents).")
    return sanctions_list

if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n=== Sanctions List Downloader & Parser (Optimized) ===")
    print(f"Started: {timestamp}\n")
    
    try:
        # LÓGICA DE EJECUCIÓN: DESCARGA -> DESCOMPRESIÓN -> PARSEO
        
        # 1. DESCARGA OFAC
        download_ofac()
        
        # 2. DESCOMPRESIÓN (DEBE OCURRIR ANTES DEL PARSEO)
        ofac_xml_path = unzip_enhanced_xml() 
        
        # 3. DESCARGA UN
        print()
        un_xml_path = download_un()
        
        print(f"\n--- Starting Data Parsing ---")

        # 4. PARSEO
        ofac_data = []
        if ofac_xml_path and ofac_xml_path.exists():
            ofac_data = parse_ofac_xml(ofac_xml_path)
        else:
            print("✗ Skipping OFAC parsing: XML file not found or extraction failed.")
        
        un_data = []
        if un_xml_path and un_xml_path.exists():
            un_data = parse_un_xml(un_xml_path)
        else:
             print("✗ Skipping UN parsing: XML file not found.")
        
        # 5. CONSOLIDACIÓN
        master_list = ofac_data + un_data
        
        print(f"\n*** Data Consolidation Complete ***")
        print(f"Total entries parsed: {len(master_list)}")
        print(f"Data is now ready for your 1-a-1 screening logic (matching).")
        
    except Exception as e:
        print(f"\n✗ Script Execution Error: {e}")
