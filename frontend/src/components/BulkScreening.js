import React, { useState, useRef, useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';

/**
 * BulkScreening - Componente para screening masivo por CSV
 * Versión 3.0: Incluye paginación, selección masiva, guardado, visor de reportes HTML
 */

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Configuración de paginación
const PAGE_SIZES = [10, 25, 50, 100];
const DEFAULT_PAGE_SIZE = 10;

// Plantilla CSV para descargar
const CSV_TEMPLATE = `nombre,cedula,pais,fecha_nacimiento,nacionalidad
Juan Pérez García,8-888-8888,PA,1985-03-15,PA
María López Rodríguez,9-999-9999,PA,1990-07-22,CO
Carlos Hernández,,CO,,VE`;

/**
 * Genera HTML profesional para un reporte de screening individual
 * Estilo basado en report_generator.py del backend
 */
function generateReportHTML(result) {
  const { input, is_hit, hit_count, matches, screening_id } = result;
  const dateFormatted = new Date().toLocaleDateString('es-PA', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  
  // Get input fields with fallbacks
  const nombre = input?.nombre || input?.name || 'No especificado';
  const documento = input?.cedula || input?.document || input?.documento || 'No especificado';
  const pais = input?.pais || input?.country || 'No especificado';
  const nacionalidad = input?.nacionalidad || input?.nationality || '';
  const fechaNacimiento = input?.fecha_nacimiento || input?.dob || '';
  
  const matchesHTML = is_hit && matches?.length > 0 
    ? matches.map((match, i) => {
        const entity = match.entity || {};
        const confidence = match.confidence || {};
        const confidenceLevel = confidence.overall || 0;
        const matchedName = match.matched_name || entity.name || 'N/A';
        
        // Get identifications
        const identifications = entity.identity_documents || [];
        const idNumbers = identifications.map(id => id.number || id.id_number).filter(Boolean);
        
        return `
          <div class="match-card">
            <div class="match-score">${confidenceLevel.toFixed(2)}%</div>
            <h3 style="color: #e74c3c; margin-bottom: 10px;">${matchedName}</h3>
            
            <div class="info-grid" style="margin-top: 15px;">
              <div class="info-label">Tipo:</div>
              <div>${(entity.type || 'individual').toUpperCase()}</div>
              
              <div class="info-label">Lista:</div>
              <div><strong>${entity.source || 'N/A'}</strong></div>
              
              <div class="info-label">ID Entidad:</div>
              <div style="font-family: monospace; font-size: 0.9em;">${entity.id || 'N/A'}</div>
              
              ${entity.program ? `
              <div class="info-label">Programa:</div>
              <div>${entity.program}</div>
              ` : ''}
              
              <div class="info-label">Identificación:</div>
              <div style="font-size: 1.1em; font-weight: bold;">
                ${idNumbers.length > 0 ? idNumbers.join(', ') : '<span style="color:#e74c3c;">No disponible en la lista</span>'}
              </div>
              
              ${entity.firstName || entity.first_name ? `
              <div class="info-label">Nombre:</div>
              <div>${entity.firstName || entity.first_name}</div>
              ` : ''}
              
              ${entity.lastName || entity.last_name ? `
              <div class="info-label">Apellido:</div>
              <div>${entity.lastName || entity.last_name}</div>
              ` : ''}
              
              ${entity.nationality ? `
              <div class="info-label">Nacionalidad:</div>
              <div>${entity.nationality}</div>
              ` : ''}
              
              ${entity.dateOfBirth || entity.date_of_birth ? `
              <div class="info-label">Fecha de Nacimiento:</div>
              <div>${entity.dateOfBirth || entity.date_of_birth}</div>
              ` : ''}
              
              ${entity.countries?.length ? `
              <div class="info-label">Países:</div>
              <div>${entity.countries.join(', ')}</div>
              ` : ''}
              
              ${match.flags?.includes('SECONDARY_SANCTIONS_RISK') ? `
              <div class="info-label" style="color:#d35400;font-weight:bold;">Riesgo de Sanciones Secundarias:</div>
              <div style="color:#d35400;font-weight:bold;">⚠️ Este sujeto está vinculado a sanciones secundarias OFAC</div>
              ` : ''}
            </div>
            
            ${entity.aliases?.length > 0 || entity.all_names?.length > 1 ? `
            <div style="margin-top: 15px;">
              <strong>Alias conocidos:</strong>
              <ul style="margin-left: 20px; margin-top: 5px;">
                ${(entity.aliases || entity.all_names?.slice(1) || []).slice(0, 10).map(alias => `<li>${alias}</li>`).join('')}
                ${(entity.aliases?.length || entity.all_names?.length - 1 || 0) > 10 ? `<li>... y ${(entity.aliases?.length || entity.all_names?.length - 1) - 10} más</li>` : ''}
              </ul>
            </div>
            ` : ''}
            
            <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
              <strong>Recomendación:</strong>
              <span style="margin-left: 10px; padding: 4px 12px; border-radius: 4px; font-weight: bold;
                ${match.recommendation === 'AUTO_ESCALATE' || match.recommendation === 'REJECT' ? 'background: #fee2e2; color: #dc2626;' : 
                  match.recommendation === 'AUTO_CLEAR' || match.recommendation === 'APPROVE' ? 'background: #dcfce7; color: #16a34a;' :
                  'background: #fef3c7; color: #d97706;'}">
                ${match.recommendation === 'AUTO_ESCALATE' ? '⚠️ ESCALACIÓN AUTOMÁTICA' :
                  match.recommendation === 'REJECT' ? '🚫 RECHAZAR' :
                  match.recommendation === 'AUTO_CLEAR' ? '✅ APROBACIÓN AUTOMÁTICA' :
                  match.recommendation === 'APPROVE' ? '✅ APROBAR' :
                  '⚠️ REVISIÓN MANUAL REQUERIDA'}
              </span>
            </div>
          </div>
        `;
      }).join('')
    : '';

  return `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Constancia de Screening - ${nombre}</title>
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
      border-radius: 8px;
    }
    .header {
      border-bottom: 3px solid #2c3e50;
      padding-bottom: 20px;
      margin-bottom: 30px;
      text-align: center;
    }
    .header h1 {
      color: #2c3e50;
      font-size: 22px;
      margin-bottom: 10px;
    }
    .header .subtitle {
      color: #7f8c8d;
      font-size: 14px;
    }
    .status-badge {
      display: inline-block;
      padding: 10px 20px;
      border-radius: 6px;
      font-weight: bold;
      font-size: 16px;
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
      grid-template-columns: 180px 1fr;
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
    .footer {
      margin-top: 40px;
      padding-top: 20px;
      border-top: 1px solid #e0e0e0;
      font-size: 12px;
      color: #7f8c8d;
    }
    .screening-id {
      font-family: monospace;
      font-size: 11px;
      color: #95a5a6;
      word-break: break-all;
    }
    @media print {
      body { background: white; padding: 10mm; }
      .report-container { box-shadow: none; }
      .no-print { display: none !important; }
    }
  </style>
</head>
<body>
  <button onclick="window.print()" class="no-print" style="position:fixed;top:30px;right:40px;padding:10px 18px;font-size:16px;background:#34495e;color:#fff;border:none;border-radius:6px;cursor:pointer;z-index:1000;">🖨️ Imprimir Reporte</button>
  
  <div class="report-container">
    <div class="header">
      <div style="margin-bottom: 15px;">
        <span style="font-size: 48px;">🛡️</span>
      </div>
      <h1>CONSTANCIA DE VERIFICACIÓN DE LISTAS DE SANCIONES</h1>
      <div class="subtitle">SDNCheck PA - Screening contra listas OFAC y UN</div>
    </div>
    
    <div class="status-badge ${is_hit ? 'status-hit' : 'status-clear'}">
      ${is_hit ? '⚠️ COINCIDENCIA DETECTADA' : '✅ SIN COINCIDENCIAS'}
    </div>
    
    <div class="section">
      <h2>📋 Información del Sujeto Evaluado</h2>
      <div class="info-grid">
        <div class="info-label">Nombre:</div>
        <div><strong>${nombre}</strong></div>
        
        <div class="info-label">Documento:</div>
        <div>${documento}</div>
        
        <div class="info-label">País:</div>
        <div>${pais}</div>
        
        ${nacionalidad ? `
        <div class="info-label">Nacionalidad:</div>
        <div>${nacionalidad}</div>
        ` : ''}
        
        ${fechaNacimiento ? `
        <div class="info-label">Fecha de Nacimiento:</div>
        <div>${fechaNacimiento}</div>
        ` : ''}
        
        <div class="info-label">Fecha de Screening:</div>
        <div>${dateFormatted}</div>
        
        <div class="info-label">ID Screening:</div>
        <div class="screening-id">${screening_id || 'N/A'}</div>
      </div>
    </div>
    
    ${is_hit ? `
    <div class="section">
      <h2>⚠️ Coincidencias Detectadas (${hit_count || matches?.length || 0})</h2>
      ${matchesHTML}
    </div>
    ` : `
    <div class="section">
      <h2>✅ Resultado de Verificación</h2>
      <p style="color: #27ae60; font-size: 16px; padding: 20px; background: #f0fff4; border-radius: 8px; text-align: center;">
        <span style="font-size: 48px; display: block; margin-bottom: 10px;">✅</span>
        No se encontraron coincidencias en las listas de sanciones consultadas (OFAC y ONU).
      </p>
    </div>
    `}
    
    <div class="section">
      <h2>📚 Listas Consultadas</h2>
      <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
        <thead>
          <tr style="background: #34495e; color: white;">
            <th style="padding: 10px; text-align: left;">Fuente</th>
            <th style="padding: 10px; text-align: left;">Descripción</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 10px;"><strong>OFAC SDN</strong></td>
            <td style="padding: 10px;">Lista de Nacionales Especialmente Designados del Departamento del Tesoro de EE.UU.</td>
          </tr>
          <tr style="border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 10px;"><strong>ONU</strong></td>
            <td style="padding: 10px;">Lista Consolidada de Sanciones del Consejo de Seguridad de las Naciones Unidas</td>
          </tr>
        </tbody>
      </table>
    </div>
    
    <div class="footer">
      <p><strong>Documento generado automáticamente por SDNCheck PA</strong></p>
      <p>Fecha de generación: ${dateFormatted}</p>
      <p style="margin-top: 10px;">Este reporte es válido únicamente para la fecha indicada. Las listas de sanciones se actualizan frecuentemente.</p>
      <p style="margin-top: 5px; font-size: 10px; color: #bdc3c7;">ID: ${screening_id || 'N/A'}</p>
    </div>
  </div>
</body>
</html>
  `;
}

/**
 * Genera HTML para múltiples reportes (impresión masiva)
 */
function generateBulkReportHTML(results) {
  const timestamp = new Date().toLocaleString('es-PA');
  const hits = results.filter(r => r.is_hit);
  const clears = results.filter(r => !r.is_hit);
  
  return `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reporte Masivo de Screening - SDNCheck PA</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.5;
      color: #1e293b;
      background: #f8fafc;
      padding: 20px;
    }
    .report {
      max-width: 900px;
      margin: 0 auto;
      background: white;
      border-radius: 16px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.1);
      overflow: hidden;
    }
    .header {
      padding: 30px;
      text-align: center;
      color: white;
      background: linear-gradient(135deg, #0d1b2a 0%, #1b3a5c 100%);
    }
    .header h1 { font-size: 28px; margin-bottom: 8px; }
    .header .subtitle { opacity: 0.9; font-size: 14px; }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 15px;
      padding: 25px;
      background: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
    }
    .summary-card {
      text-align: center;
      padding: 15px;
      background: white;
      border-radius: 10px;
      border: 1px solid #e2e8f0;
    }
    .summary-card.hit { background: #fee2e2; border-color: #fecaca; }
    .summary-value { font-size: 28px; font-weight: 800; color: #0d1b2a; }
    .summary-card.hit .summary-value { color: #dc2626; }
    .summary-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
    .content { padding: 25px; }
    .section-title {
      font-size: 18px;
      color: #0d1b2a;
      margin: 25px 0 15px;
      padding-bottom: 10px;
      border-bottom: 2px solid #e2e8f0;
    }
    .results-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .results-table th {
      background: #0d1b2a;
      color: white;
      padding: 12px 10px;
      text-align: left;
      font-weight: 600;
    }
    .results-table td {
      padding: 10px;
      border-bottom: 1px solid #e2e8f0;
    }
    .results-table tr:hover { background: #f8fafc; }
    .results-table tr.row-hit { background: #fee2e2; }
    .results-table tr.row-hit:hover { background: #fecaca; }
    .badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }
    .badge.hit { background: #dc2626; color: white; }
    .badge.clear { background: #16a34a; color: white; }
    .badge.reject { background: #fee2e2; color: #dc2626; }
    .badge.review { background: #fef3c7; color: #d97706; }
    .badge.approve { background: #dcfce7; color: #16a34a; }
    .footer {
      padding: 20px;
      background: #f8fafc;
      font-size: 11px;
      color: #64748b;
      text-align: center;
      border-top: 1px solid #e2e8f0;
    }
    .page-break { page-break-after: always; }
    @media print {
      body { padding: 0; background: white; }
      .report { box-shadow: none; }
      .no-print { display: none !important; }
    }
  </style>
</head>
<body>
  <div class="report">
    <div class="header">
      <h1>🛡️ SDNCheck PA</h1>
      <div class="subtitle">Reporte Masivo de Verificación de Sanciones</div>
    </div>
    
    <div class="summary">
      <div class="summary-card">
        <div class="summary-value">${results.length}</div>
        <div class="summary-label">Total Procesados</div>
      </div>
      <div class="summary-card hit">
        <div class="summary-value">${hits.length}</div>
        <div class="summary-label">Coincidencias</div>
      </div>
      <div class="summary-card">
        <div class="summary-value">${clears.length}</div>
        <div class="summary-label">Sin Coincidencias</div>
      </div>
      <div class="summary-card">
        <div class="summary-value">${results.length > 0 ? ((hits.length / results.length) * 100).toFixed(1) : 0}%</div>
        <div class="summary-label">Tasa de Hits</div>
      </div>
    </div>
    
    <div class="content">
      <div class="section-title">📊 Detalle de Resultados</div>
      <table class="results-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Nombre</th>
            <th>Documento</th>
            <th>País</th>
            <th>Estado</th>
            <th>Hits</th>
            <th>Recomendación</th>
          </tr>
        </thead>
        <tbody>
          ${results.map((r, i) => {
            const rec = r.is_hit && r.matches?.[0]?.recommendation 
              ? r.matches[0].recommendation 
              : 'APPROVE';
            const nombre = r.input?.nombre || r.input?.name || '-';
            const documento = r.input?.cedula || r.input?.document || r.input?.documento || '-';
            const pais = r.input?.pais || r.input?.country || '-';
            return `
              <tr class="${r.is_hit ? 'row-hit' : ''}">
                <td>${i + 1}</td>
                <td><strong>${nombre}</strong></td>
                <td>${documento}</td>
                <td>${pais}</td>
                <td><span class="badge ${r.is_hit ? 'hit' : 'clear'}">${r.is_hit ? '⚠️ HIT' : '✅ OK'}</span></td>
                <td>${r.hit_count || 0}</td>
                <td><span class="badge ${rec.toLowerCase().replace('_', '-')}">${
                  rec === 'AUTO_ESCALATE' ? 'ESCALAR' :
                  rec === 'REJECT' ? 'RECHAZAR' :
                  rec === 'AUTO_CLEAR' ? 'AUTO OK' :
                  rec === 'APPROVE' ? 'APROBAR' : 'REVISAR'
                }</span></td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
    
    <div class="footer">
      <p><strong>Generado: ${timestamp}</strong> | SDNCheck PA - Verificación OFAC & ONU</p>
    </div>
  </div>
  
  <div class="no-print" style="text-align: center; margin-top: 20px;">
    <button onclick="window.print()" style="
      padding: 12px 30px;
      background: linear-gradient(135deg, #00b4d8 0%, #0096c7 100%);
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
    ">🖨️ Imprimir Reporte</button>
  </div>
</body>
</html>
  `;
}

function BulkScreening({ disabled }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedResults, setSelectedResults] = useState(new Set());
  const [filePreview, setFilePreview] = useState(null); // Preview of CSV records
  
  // Estados de paginación
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  
  // Estado de filtro
  const [filterType, setFilterType] = useState('all'); // 'all', 'hits', 'clear'
  
  const fileInputRef = useRef(null);

  // Parse CSV file for preview
  const parseCSVPreview = useCallback((file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target.result;
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length === 0) {
          setFilePreview({ headers: [], rows: [], totalRows: 0 });
          return;
        }
        
        // Parse headers
        const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
        
        // Parse rows (max 5 for preview)
        const rows = [];
        for (let i = 1; i < Math.min(lines.length, 6); i++) {
          const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
          const row = {};
          headers.forEach((h, idx) => {
            row[h] = values[idx] || '';
          });
          rows.push(row);
        }
        
        setFilePreview({
          headers,
          rows,
          totalRows: lines.length - 1 // Exclude header
        });
      } catch (err) {
        console.error('Error parsing CSV:', err);
        setFilePreview(null);
      }
    };
    reader.readAsText(file);
  }, []);

  // Filtrar resultados
  const filteredResults = useMemo(() => {
    if (!results?.results) return [];
    switch (filterType) {
      case 'hits':
        return results.results.filter(r => r.is_hit);
      case 'clear':
        return results.results.filter(r => !r.is_hit);
      default:
        return results.results;
    }
  }, [results, filterType]);

  // Calcular paginación
  const totalPages = Math.ceil(filteredResults.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, filteredResults.length);
  const paginatedResults = filteredResults.slice(startIndex, endIndex);

  // Reset página cuando cambia el filtro
  const handleFilterChange = (newFilter) => {
    setFilterType(newFilter);
    setCurrentPage(1);
  };

  // Cambiar tamaño de página
  const handlePageSizeChange = (newSize) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  // Descargar plantilla CSV
  const downloadTemplate = () => {
    const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'sdncheck_template.csv';
    link.click();
    URL.revokeObjectURL(link.href);
  };

  // Manejar selección de archivo
  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      validateAndSetFile(selectedFile);
    }
  };

  // Validar y establecer archivo
  const validateAndSetFile = (selectedFile) => {
    if (!selectedFile.name.endsWith('.csv')) {
      setError('Por favor, seleccione un archivo CSV');
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError('El archivo no debe exceder 10MB');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setResults(null);
    setSelectedResults(new Set());
    setCurrentPage(1);
    // Parse CSV for preview
    parseCSVPreview(selectedFile);
  };

  // Manejar drag & drop
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      validateAndSetFile(droppedFile);
    }
  };

  // Procesar archivo
  const handleSubmit = async () => {
    if (!file || loading) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/api/v1/screen/bulk`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        let errorMessage = `Error del servidor (${response.status})`;
        try {
          const errorText = await response.text();
          if (errorText) errorMessage = `${errorMessage}: ${errorText}`;
        } catch {
          // Ignorar error al leer texto
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setResults(data);
      setSelectedResults(new Set());
      setCurrentPage(1);
      setFilterType('all');
    } catch (err) {
      const message = err.name === 'TypeError'
        ? 'Error de red: No se puede conectar al servidor'
        : err.message;
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // Limpiar selección
  const handleClear = () => {
    setFile(null);
    setResults(null);
    setError(null);
    setSelectedResults(new Set());
    setCurrentPage(1);
    setFilterType('all');
    setFilePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Escapar campo CSV
  const escapeCSVField = (field) => {
    if (field === null || field === undefined) return '';
    const str = String(field);
    if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  // Exportar resultados CSV
  const exportResults = useCallback(() => {
    if (!results?.results) return;

    const csvRows = [
      ['Nombre', 'Documento', 'País', 'Resultado', 'Coincidencias', 'Recomendación']
    ];

    results.results.forEach(r => {
      const recommendation = r.is_hit && r.matches?.[0]?.recommendation 
        ? r.matches[0].recommendation 
        : 'APPROVE';
      
      csvRows.push([
        escapeCSVField(r.input?.nombre || ''),
        escapeCSVField(r.input?.cedula || ''),
        escapeCSVField(r.input?.pais || ''),
        r.is_hit ? 'COINCIDENCIA' : 'LIMPIO',
        r.hit_count || 0,
        recommendation
      ]);
    });

    const csvContent = csvRows.map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `sdncheck_resultados_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }, [results]);

  // Guardar resultados como JSON
  const saveResultsJSON = useCallback(() => {
    if (!results) return;
    
    const dataStr = JSON.stringify(results, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `sdncheck_resultados_${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }, [results]);

  // Ver reporte individual
  const viewReport = useCallback((result) => {
    const html = generateReportHTML(result);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, []);

  // Obtener índice real en results.results
  const getRealIndex = useCallback((filteredIndex) => {
    const item = filteredResults[filteredIndex];
    return results?.results?.indexOf(item) ?? filteredIndex;
  }, [filteredResults, results]);

  // Seleccionar/deseleccionar resultado (usando índice real)
  const toggleSelection = useCallback((filteredIndex) => {
    const realIndex = getRealIndex(filteredIndex);
    setSelectedResults(prev => {
      const next = new Set(prev);
      if (next.has(realIndex)) {
        next.delete(realIndex);
      } else {
        next.add(realIndex);
      }
      return next;
    });
  }, [getRealIndex]);

  // Verificar si un resultado está seleccionado
  const isSelected = useCallback((filteredIndex) => {
    const realIndex = getRealIndex(filteredIndex);
    return selectedResults.has(realIndex);
  }, [getRealIndex, selectedResults]);

  // Seleccionar todos los de la página actual
  const selectAllOnPage = useCallback(() => {
    const newSelected = new Set(selectedResults);
    for (let i = startIndex; i < endIndex; i++) {
      const realIndex = results?.results?.indexOf(filteredResults[i]);
      if (realIndex !== undefined && realIndex !== -1) {
        newSelected.add(realIndex);
      }
    }
    setSelectedResults(newSelected);
  }, [selectedResults, startIndex, endIndex, filteredResults, results]);

  // Deseleccionar todos los de la página actual
  const deselectAllOnPage = useCallback(() => {
    const newSelected = new Set(selectedResults);
    for (let i = startIndex; i < endIndex; i++) {
      const realIndex = results?.results?.indexOf(filteredResults[i]);
      if (realIndex !== undefined && realIndex !== -1) {
        newSelected.delete(realIndex);
      }
    }
    setSelectedResults(newSelected);
  }, [selectedResults, startIndex, endIndex, filteredResults, results]);

  // Seleccionar todos los resultados
  const selectAll = useCallback(() => {
    if (!results?.results) return;
    setSelectedResults(new Set(results.results.map((_, i) => i)));
  }, [results]);

  // Seleccionar todos los hits
  const selectAllHits = useCallback(() => {
    if (!results?.results) return;
    const hitIndices = results.results
      .map((r, i) => r.is_hit ? i : -1)
      .filter(i => i !== -1);
    setSelectedResults(new Set(hitIndices));
  }, [results]);

  // Deseleccionar todos
  const clearSelection = useCallback(() => {
    setSelectedResults(new Set());
  }, []);

  // Verificar si todos en la página están seleccionados
  const allOnPageSelected = useMemo(() => {
    if (paginatedResults.length === 0) return false;
    for (let i = 0; i < paginatedResults.length; i++) {
      const realIndex = results?.results?.indexOf(paginatedResults[i]);
      if (!selectedResults.has(realIndex)) return false;
    }
    return true;
  }, [paginatedResults, results, selectedResults]);

  // Imprimir seleccionados
  const printSelected = useCallback(() => {
    if (!results?.results || selectedResults.size === 0) return;
    
    const selectedData = Array.from(selectedResults)
      .sort((a, b) => a - b)
      .map(i => results.results[i])
      .filter(Boolean);
    
    const html = generateBulkReportHTML(selectedData);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [results, selectedResults]);

  // Imprimir todos
  const printAll = useCallback(() => {
    if (!results?.results) return;
    
    const html = generateBulkReportHTML(results.results);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [results]);

  // Generar rango de páginas para mostrar
  const getPageRange = () => {
    const range = [];
    const maxVisible = 5;
    let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    
    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }
    
    for (let i = start; i <= end; i++) {
      range.push(i);
    }
    return range;
  };

  return (
    <div className="bulk-screening">
      <div className="bulk-header">
        <h2>📋 Screening Masivo</h2>
        <p className="bulk-description">
          Cargue un archivo CSV con múltiples personas para verificar simultáneamente contra las listas OFAC y ONU
        </p>
      </div>

      {/* Sección de descarga de plantilla */}
      <div className="template-section">
        <button 
          onClick={downloadTemplate}
          className="btn btn-outline"
          type="button"
        >
          📥 Descargar Plantilla CSV
        </button>
        <span className="template-hint">
          Use esta plantilla para formatear correctamente sus datos
        </span>
      </div>

      {/* Área de carga de archivo */}
      <div
        className={`upload-area ${dragActive ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => !file && fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".csv"
          className="file-input-hidden"
          disabled={disabled || loading}
        />

        {file ? (
          <div className="file-selected" onClick={(e) => e.stopPropagation()}>
            <div className="file-selected-header">
              <span className="file-icon-success">✅</span>
              <div className="file-info">
                <span className="file-name">{file.name}</span>
                <span className="file-size">
                  {(file.size / 1024).toFixed(1)} KB
                  {filePreview && ` • ${filePreview.totalRows} registros`}
                </span>
              </div>
              <button
                type="button"
                className="btn-change-file"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClear();
                }}
                title="Cambiar archivo"
              >
                🔄 Cambiar
              </button>
            </div>
            
            {/* Vista previa de registros */}
            {filePreview && filePreview.rows.length > 0 && (
              <div className="file-preview">
                <div className="file-preview-header">
                  <span className="preview-title">📋 Vista previa ({Math.min(5, filePreview.rows.length)} de {filePreview.totalRows} registros)</span>
                </div>
                <div className="file-preview-table-container">
                  <table className="file-preview-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Nombre</th>
                        <th>Documento</th>
                        <th>País</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filePreview.rows.map((row, idx) => (
                        <tr key={idx}>
                          <td>{idx + 1}</td>
                          <td>{row.nombre || '-'}</td>
                          <td>{row.cedula || row.documento || '-'}</td>
                          <td>{row.pais || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filePreview.totalRows > 5 && (
                  <div className="preview-more">
                    ... y {filePreview.totalRows - 5} registros más
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="upload-placeholder">
            <span className="upload-icon">📤</span>
            <p className="upload-text">
              Arrastre un archivo CSV aquí o haga clic para seleccionar
            </p>
            <p className="upload-hint">Máximo 10MB</p>
          </div>
        )}
      </div>

      {/* Mensaje de error */}
      {error && (
        <div className="bulk-error">
          <span className="error-icon">❌</span>
          <span>{error}</span>
        </div>
      )}

      {/* Indicador de carga mejorado */}
      {loading && (
        <div className="loading-overlay">
          <div className="loading-content">
            <div className="loading-spinner-large"></div>
            <p className="loading-text">Procesando verificaciones...</p>
            <p className="loading-subtext">Consultando listas OFAC y ONU</p>
          </div>
        </div>
      )}

      {/* Botones de acción */}
      <div className="bulk-actions">
        <button
          type="button"
          onClick={handleClear}
          className="btn btn-secondary"
          disabled={loading || (!file && !results)}
        >
          Limpiar
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          className="btn btn-primary"
          disabled={disabled || loading || !file}
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Procesando...
            </>
          ) : (
            <>🚀 Procesar Archivo</>
          )}
        </button>
      </div>

      {/* Resultados */}
      {results && (
        <div className="bulk-results">
          <div className="results-summary">
            <h3>📊 Resumen de Resultados</h3>
            <div className="summary-stats">
              <div className="stat-card">
                <span className="stat-value">{results.total_processed}</span>
                <span className="stat-label">Procesados</span>
              </div>
              <div className="stat-card hit">
                <span className="stat-value">{results.hits}</span>
                <span className="stat-label">Coincidencias</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{results.hit_rate}</span>
                <span className="stat-label">Tasa de Hits</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{results.processing_time_ms}ms</span>
                <span className="stat-label">Tiempo</span>
              </div>
            </div>
          </div>

          {/* Barra de herramientas de acciones */}
          <div className="results-toolbar">
            {/* Sección de filtros */}
            <div className="toolbar-section">
              <label className="toolbar-label">Filtrar:</label>
              <div className="filter-buttons">
                <button
                  type="button"
                  className={`filter-btn ${filterType === 'all' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('all')}
                >
                  Todos ({results.total_processed})
                </button>
                <button
                  type="button"
                  className={`filter-btn filter-hits ${filterType === 'hits' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('hits')}
                >
                  ⚠️ Hits ({results.hits})
                </button>
                <button
                  type="button"
                  className={`filter-btn filter-clear ${filterType === 'clear' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('clear')}
                >
                  ✅ Limpios ({results.total_processed - results.hits})
                </button>
              </div>
            </div>

            {/* Sección de selección */}
            <div className="toolbar-section">
              <label className="toolbar-label">Selección:</label>
              <div className="selection-buttons">
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={selectAll}
                  title="Seleccionar todos los registros"
                >
                  ☑️ Todo ({results.total_processed})
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={selectAllHits}
                  disabled={results.hits === 0}
                  title="Seleccionar solo coincidencias"
                >
                  ⚠️ Hits ({results.hits})
                </button>
                {selectedResults.size > 0 && (
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={clearSelection}
                  >
                    ✕ Limpiar ({selectedResults.size})
                  </button>
                )}
              </div>
            </div>

            {/* Sección de exportación */}
            <div className="toolbar-section">
              <label className="toolbar-label">Guardar:</label>
              <div className="export-buttons">
                <button
                  type="button"
                  onClick={exportResults}
                  className="btn btn-sm btn-outline"
                  title="Exportar a CSV"
                >
                  📥 CSV
                </button>
                <button
                  type="button"
                  onClick={saveResultsJSON}
                  className="btn btn-sm btn-outline"
                  title="Guardar como JSON"
                >
                  💾 JSON
                </button>
                <button
                  type="button"
                  onClick={printAll}
                  className="btn btn-sm btn-outline"
                  title="Generar reporte HTML de todos"
                >
                  📄 Reporte
                </button>
                {selectedResults.size > 0 && (
                  <button
                    type="button"
                    onClick={printSelected}
                    className="btn btn-sm btn-primary"
                    title="Imprimir seleccionados"
                  >
                    🖨️ Imprimir ({selectedResults.size})
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Información de paginación y controles */}
          <div className="pagination-info">
            <div className="page-size-selector">
              <label>Mostrar:</label>
              <select 
                value={pageSize} 
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="page-size-select"
              >
                {PAGE_SIZES.map(size => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
              <span>registros</span>
            </div>
            <div className="results-count">
              Mostrando {startIndex + 1}-{endIndex} de {filteredResults.length} registros
              {filterType !== 'all' && ` (filtrado de ${results.total_processed})`}
            </div>
          </div>

          {/* Tabla de resultados mejorada */}
          <div className="results-table-container">
            <table className="results-table">
              <thead>
                <tr>
                  <th style={{width: '40px'}}>
                    <input 
                      type="checkbox" 
                      checked={allOnPageSelected && paginatedResults.length > 0}
                      onChange={(e) => {
                        if (e.target.checked) {
                          selectAllOnPage();
                        } else {
                          deselectAllOnPage();
                        }
                      }}
                      title="Seleccionar/deseleccionar página actual"
                    />
                  </th>
                  <th style={{width: '50px'}}>#</th>
                  <th>Nombre</th>
                  <th>Documento</th>
                  <th>País</th>
                  <th style={{width: '100px'}}>Estado</th>
                  <th style={{width: '60px'}}>Hits</th>
                  <th style={{width: '120px'}}>Recomendación</th>
                  <th style={{width: '80px'}}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {paginatedResults.map((r, pageIndex) => {
                  const globalIndex = startIndex + pageIndex;
                  return (
                    <BulkResultRow 
                      key={r.screening_id || globalIndex} 
                      result={r} 
                      displayIndex={globalIndex + 1}
                      selected={isSelected(globalIndex)}
                      onToggle={() => toggleSelection(globalIndex)}
                      onViewReport={() => viewReport(r)}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Controles de paginación */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <button
                type="button"
                className="pagination-btn"
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
                title="Primera página"
              >
                ⏮️
              </button>
              <button
                type="button"
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
                title="Página anterior"
              >
                ◀️
              </button>
              
              <div className="pagination-pages">
                {getPageRange().map(page => (
                  <button
                    key={page}
                    type="button"
                    className={`pagination-page ${page === currentPage ? 'active' : ''}`}
                    onClick={() => setCurrentPage(page)}
                  >
                    {page}
                  </button>
                ))}
              </div>

              <button
                type="button"
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
                title="Página siguiente"
              >
                ▶️
              </button>
              <button
                type="button"
                className="pagination-btn"
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
                title="Última página"
              >
                ⏭️
              </button>
              
              <div className="pagination-jump">
                <span>Ir a:</span>
                <input
                  type="number"
                  min={1}
                  max={totalPages}
                  value={currentPage}
                  onChange={(e) => {
                    const page = parseInt(e.target.value);
                    if (page >= 1 && page <= totalPages) {
                      setCurrentPage(page);
                    }
                  }}
                  className="page-jump-input"
                />
                <span>de {totalPages}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * BulkResultRow - Fila de resultado en la tabla con acciones
 */
function BulkResultRow({ result, displayIndex, selected, onToggle, onViewReport }) {
  const { input, is_hit, hit_count, matches } = result;
  const recommendation = is_hit && matches?.[0]?.recommendation 
    ? matches[0].recommendation 
    : 'APPROVE';

  // Handle different field name conventions
  const nombre = input?.nombre || input?.name || '-';
  const documento = input?.cedula || input?.document || input?.documento || '-';
  const pais = input?.pais || input?.country || '-';

  const getRecommendationClass = () => {
    switch (recommendation) {
      case 'AUTO_ESCALATE':
      case 'REJECT': return 'badge-reject';
      case 'REVIEW':
      case 'MANUAL_REVIEW':
      case 'LOW_CONFIDENCE_REVIEW': return 'badge-review';
      default: return 'badge-approve';
    }
  };

  const getRecommendationText = () => {
    switch (recommendation) {
      case 'AUTO_ESCALATE': return 'ESCALAR';
      case 'REJECT': return 'RECHAZAR';
      case 'REVIEW':
      case 'MANUAL_REVIEW':
      case 'LOW_CONFIDENCE_REVIEW': return 'REVISAR';
      case 'AUTO_CLEAR': return 'AUTO OK';
      default: return 'APROBAR';
    }
  };

  return (
    <tr className={`${is_hit ? 'row-hit' : 'row-clear'} ${selected ? 'row-selected' : ''}`}>
      <td>
        <input 
          type="checkbox" 
          checked={selected}
          onChange={onToggle}
        />
      </td>
      <td className="row-number">{displayIndex}</td>
      <td className="cell-name"><strong>{nombre}</strong></td>
      <td>{documento}</td>
      <td>{pais}</td>
      <td>
        <span className={`result-badge ${is_hit ? 'hit' : 'clear'}`}>
          {is_hit ? '⚠️ HIT' : '✅ OK'}
        </span>
      </td>
      <td className="text-center">{hit_count || 0}</td>
      <td>
        <span className={`recommendation-badge-small ${getRecommendationClass()}`}>
          {getRecommendationText()}
        </span>
      </td>
      <td>
        <button 
          type="button"
          className="btn-view-report"
          onClick={onViewReport}
          title="Ver reporte detallado"
        >
          👁️ Ver
        </button>
      </td>
    </tr>
  );
}

BulkScreening.propTypes = {
  disabled: PropTypes.bool
};

BulkResultRow.propTypes = {
  result: PropTypes.object.isRequired,
  displayIndex: PropTypes.number.isRequired,
  selected: PropTypes.bool.isRequired,
  onToggle: PropTypes.func.isRequired,
  onViewReport: PropTypes.func.isRequired
};

export default BulkScreening;
