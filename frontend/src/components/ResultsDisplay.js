import React from 'react';
import PropTypes from 'prop-types';

/**
 * ResultsDisplay - Muestra los resultados del screening
 * Incluye: estado de coincidencia, confianza, detalles de entidad, recomendación
 */

// Mapeo de recomendaciones a colores y textos en español
const RECOMMENDATION_CONFIG = {
  APPROVE: {
    className: 'badge-approve',
    text: 'APROBAR',
    icon: '✅',
    description: 'No se encontraron coincidencias significativas'
  },
  REVIEW: {
    className: 'badge-review',
    text: 'REVISAR',
    icon: '⚠️',
    description: 'Se requiere revisión manual del caso'
  },
  REJECT: {
    className: 'badge-reject',
    text: 'RECHAZAR',
    icon: '🚫',
    description: 'Coincidencia alta con lista de sanciones'
  },
  MANUAL_REVIEW: {
    className: 'badge-review',
    text: 'REVISIÓN MANUAL',
    icon: '👁️',
    description: 'Se requiere análisis adicional'
  }
};

// Mapeo de fuentes
const SOURCE_LABELS = {
  OFAC: 'Lista OFAC (EE.UU.)',
  UN: 'Lista ONU',
  EU: 'Lista Unión Europea'
};

function ResultsDisplay({ result, loading }) {
  if (loading) {
    return (
      <div className="results-container loading-state">
        <div className="loading-spinner-large"></div>
        <p>Verificando contra listas de sanciones...</p>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  // Error en el resultado
  if (result.error) {
    return (
      <div className="results-container error-state">
        <div className="error-icon">❌</div>
        <h3>Error en la verificación</h3>
        <p>{result.error}</p>
      </div>
    );
  }

  const { is_hit, hit_count, matches, screening_id, processing_time_ms } = result;

  return (
    <div className="results-container">
      {/* Encabezado del resultado */}
      <div className={`results-header ${is_hit ? 'hit' : 'clear'}`}>
        <div className="result-status">
          <span className="status-icon">
            {is_hit ? '⚠️' : '✅'}
          </span>
          <div className="status-text">
            <h3>{is_hit ? 'COINCIDENCIA ENCONTRADA' : 'SIN COINCIDENCIAS'}</h3>
            <p>
              {is_hit 
                ? `Se encontraron ${hit_count} coincidencia(s) potencial(es)`
                : 'No se encontraron coincidencias en las listas de sanciones'
              }
            </p>
          </div>
        </div>
        <div className="result-meta">
          <span className="meta-item">ID: {screening_id?.slice(0, 8)}...</span>
          <span className="meta-item">{processing_time_ms}ms</span>
        </div>
      </div>

      {/* Lista de coincidencias */}
      {is_hit && matches && matches.length > 0 && (
        <div className="matches-list">
          <h4>Detalles de las Coincidencias</h4>
          {matches.map((match, index) => (
            <MatchCard key={index} match={match} index={index} />
          ))}
        </div>
      )}

      {/* Mensaje para sin coincidencias */}
      {!is_hit && (
        <div className="no-match-details">
          <div className="recommendation-badge badge-approve">
            <span className="badge-icon">✅</span>
            <span className="badge-text">APROBAR</span>
          </div>
          <p className="recommendation-description">
            La persona verificada no aparece en las listas de sanciones OFAC ni ONU.
            Se recomienda continuar con el proceso.
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * MatchCard - Tarjeta individual de coincidencia
 */
function MatchCard({ match, index }) {
  const { entity, confidence, recommendation, flags, matched_name } = match;
  const recConfig = RECOMMENDATION_CONFIG[recommendation] || RECOMMENDATION_CONFIG.REVIEW;

  // Calcular el nivel de confianza visual
  const confidenceLevel = confidence?.overall || 0;
  const confidenceClass = 
    confidenceLevel >= 90 ? 'high' :
    confidenceLevel >= 70 ? 'medium' : 'low';

  return (
    <div className="match-card">
      {/* Cabecera de la tarjeta */}
      <div className="match-card-header">
        <span className="match-number">#{index + 1}</span>
        <div className={`recommendation-badge ${recConfig.className}`}>
          <span className="badge-icon">{recConfig.icon}</span>
          <span className="badge-text">{recConfig.text}</span>
        </div>
      </div>

      {/* Barra de confianza */}
      <div className="confidence-section">
        <div className="confidence-header">
          <span>Nivel de Coincidencia</span>
          <span className={`confidence-value ${confidenceClass}`}>
            {confidenceLevel.toFixed(1)}%
          </span>
        </div>
        <div className="confidence-bar">
          <div 
            className={`confidence-fill ${confidenceClass}`}
            style={{ width: `${Math.min(confidenceLevel, 100)}%` }}
          ></div>
        </div>
      </div>

      {/* Detalles de la entidad */}
      <div className="entity-details">
        <div className="detail-row primary">
          <span className="detail-label">Nombre en Lista</span>
          <span className="detail-value">{entity?.name || 'N/A'}</span>
        </div>

        {matched_name && matched_name !== entity?.name && (
          <div className="detail-row">
            <span className="detail-label">Nombre Coincidente</span>
            <span className="detail-value">{matched_name}</span>
          </div>
        )}

        <div className="detail-row">
          <span className="detail-label">Fuente</span>
          <span className="detail-value source-badge">
            {SOURCE_LABELS[entity?.source] || entity?.source || 'Desconocida'}
          </span>
        </div>

        {entity?.program && (
          <div className="detail-row">
            <span className="detail-label">Programa</span>
            <span className="detail-value">{entity.program}</span>
          </div>
        )}

        {entity?.type && (
          <div className="detail-row">
            <span className="detail-label">Tipo</span>
            <span className="detail-value">
              {entity.type === 'individual' ? 'Persona' : 'Entidad'}
            </span>
          </div>
        )}

        {entity?.countries && entity.countries.length > 0 && (
          <div className="detail-row">
            <span className="detail-label">Países</span>
            <span className="detail-value">{entity.countries.join(', ')}</span>
          </div>
        )}

        {entity?.aliases && entity.aliases.length > 0 && (
          <div className="detail-row">
            <span className="detail-label">Alias</span>
            <span className="detail-value aliases">
              {entity.aliases.slice(0, 3).join(', ')}
              {entity.aliases.length > 3 && ` (+${entity.aliases.length - 3} más)`}
            </span>
          </div>
        )}
      </div>

      {/* Flags/Advertencias */}
      {flags && flags.length > 0 && (
        <div className="flags-section">
          <span className="flags-label">Indicadores:</span>
          <div className="flags-list">
            {flags.map((flag, i) => (
              <span key={i} className="flag-tag">{flag}</span>
            ))}
          </div>
        </div>
      )}

      {/* Desglose de confianza */}
      {confidence && (
        <details className="confidence-breakdown">
          <summary>Ver desglose de coincidencia</summary>
          <div className="breakdown-grid">
            <ConfidenceItem label="Nombre" value={confidence.name} />
            <ConfidenceItem label="Documento" value={confidence.document} />
            <ConfidenceItem label="Fecha Nac." value={confidence.dob} />
            <ConfidenceItem label="Nacionalidad" value={confidence.nationality} />
            <ConfidenceItem label="Dirección" value={confidence.address} />
          </div>
        </details>
      )}

      {/* Descripción de recomendación */}
      <div className="recommendation-description">
        <p>{recConfig.description}</p>
      </div>
    </div>
  );
}

/**
 * ConfidenceItem - Item del desglose de confianza
 */
function ConfidenceItem({ label, value }) {
  if (value === undefined || value === null) return null;
  
  const percentage = value * 100;
  const levelClass = 
    percentage >= 80 ? 'high' :
    percentage >= 50 ? 'medium' : 'low';

  return (
    <div className="breakdown-item">
      <span className="breakdown-label">{label}</span>
      <span className={`breakdown-value ${levelClass}`}>
        {percentage.toFixed(0)}%
      </span>
    </div>
  );
}

ResultsDisplay.propTypes = {
  result: PropTypes.shape({
    screening_id: PropTypes.string,
    is_hit: PropTypes.bool,
    hit_count: PropTypes.number,
    matches: PropTypes.array,
    processing_time_ms: PropTypes.number,
    error: PropTypes.string
  }),
  loading: PropTypes.bool
};

MatchCard.propTypes = {
  match: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired
};

ConfidenceItem.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.number
};

export default ResultsDisplay;
