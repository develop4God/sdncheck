import React, { useState, useRef } from 'react';
import PropTypes from 'prop-types';

/**
 * BulkScreening - Componente para screening masivo por CSV
 * Incluye: descarga de plantilla, carga de archivo, visualización de resultados
 */

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Plantilla CSV para descargar
const CSV_TEMPLATE = `nombre,cedula,pais,fecha_nacimiento,nacionalidad
Juan Pérez García,8-888-8888,PA,1985-03-15,PA
María López Rodríguez,9-999-9999,PA,1990-07-22,CO
Carlos Hernández,,CO,,VE`;

function BulkScreening({ disabled }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

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
    // Validar tipo de archivo
    if (!selectedFile.name.endsWith('.csv')) {
      setError('Por favor, seleccione un archivo CSV');
      return;
    }

    // Validar tamaño (máximo 10MB)
    if (selectedFile.size > 10 * 1024 * 1024) {
      setError('El archivo no debe exceder 10MB');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setResults(null);
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
        const errorText = await response.text();
        throw new Error(`Error del servidor (${response.status}): ${errorText}`);
      }

      const data = await response.json();
      setResults(data);
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
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Exportar resultados
  const exportResults = () => {
    if (!results?.results) return;

    const csvRows = [
      ['Nombre', 'Documento', 'País', 'Resultado', 'Coincidencias', 'Recomendación']
    ];

    results.results.forEach(r => {
      const recommendation = r.is_hit && r.matches?.[0]?.recommendation 
        ? r.matches[0].recommendation 
        : 'APPROVE';
      
      csvRows.push([
        r.input?.nombre || '',
        r.input?.cedula || '',
        r.input?.pais || '',
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
  };

  return (
    <div className="bulk-screening">
      <div className="bulk-header">
        <h2>📋 Screening Masivo</h2>
        <p className="bulk-description">
          Cargue un archivo CSV con múltiples personas para verificar simultáneamente
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
        onClick={() => fileInputRef.current?.click()}
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
          <div className="file-selected">
            <span className="file-icon">📄</span>
            <div className="file-info">
              <span className="file-name">{file.name}</span>
              <span className="file-size">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
            <button
              type="button"
              className="btn-remove"
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
            >
              ✕
            </button>
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

          {/* Botón de exportar */}
          <div className="export-section">
            <button
              type="button"
              onClick={exportResults}
              className="btn btn-outline"
            >
              📥 Exportar Resultados CSV
            </button>
          </div>

          {/* Tabla de resultados */}
          <div className="results-table-container">
            <table className="results-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nombre</th>
                  <th>Documento</th>
                  <th>País</th>
                  <th>Resultado</th>
                  <th>Coincidencias</th>
                  <th>Recomendación</th>
                </tr>
              </thead>
              <tbody>
                {results.results?.map((r, index) => (
                  <BulkResultRow key={r.screening_id || index} result={r} index={index} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * BulkResultRow - Fila de resultado en la tabla
 */
function BulkResultRow({ result, index }) {
  const { input, is_hit, hit_count, matches } = result;
  const recommendation = is_hit && matches?.[0]?.recommendation 
    ? matches[0].recommendation 
    : 'APPROVE';

  const getRecommendationClass = () => {
    switch (recommendation) {
      case 'REJECT': return 'badge-reject';
      case 'REVIEW':
      case 'MANUAL_REVIEW': return 'badge-review';
      default: return 'badge-approve';
    }
  };

  const getRecommendationText = () => {
    switch (recommendation) {
      case 'REJECT': return 'RECHAZAR';
      case 'REVIEW':
      case 'MANUAL_REVIEW': return 'REVISAR';
      default: return 'APROBAR';
    }
  };

  return (
    <tr className={is_hit ? 'row-hit' : 'row-clear'}>
      <td>{index + 1}</td>
      <td>{input?.nombre || '-'}</td>
      <td>{input?.cedula || '-'}</td>
      <td>{input?.pais || '-'}</td>
      <td>
        <span className={`result-badge ${is_hit ? 'hit' : 'clear'}`}>
          {is_hit ? '⚠️ HIT' : '✅ OK'}
        </span>
      </td>
      <td>{hit_count || 0}</td>
      <td>
        <span className={`recommendation-badge-small ${getRecommendationClass()}`}>
          {getRecommendationText()}
        </span>
      </td>
    </tr>
  );
}

BulkScreening.propTypes = {
  disabled: PropTypes.bool
};

BulkResultRow.propTypes = {
  result: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired
};

export default BulkScreening;
