import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';

/**
 * HealthCheck - Componente para mostrar el estado del backend
 * Muestra: estado del servicio, entidades cargadas, antigüedad de datos
 */

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function HealthCheck({ onHealthUpdate }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchHealth();
    // Refrescar cada 60 segundos
    const interval = setInterval(fetchHealth, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchHealth = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/health`);
      if (!response.ok) {
        throw new Error(`Error del servidor: ${response.status}`);
      }
      const data = await response.json();
      setHealth(data);
      setError(null);
      if (onHealthUpdate) {
        onHealthUpdate(data);
      }
    } catch (err) {
      const message = err.name === 'TypeError' 
        ? 'Error de red: No se puede conectar al servidor' 
        : err.message;
      setError(message);
      if (onHealthUpdate) {
        onHealthUpdate(null);
      }
    } finally {
      setLoading(false);
    }
  };

  // Determinar el estado visual
  const getStatusClass = () => {
    if (loading) return 'health-badge loading';
    if (error) return 'health-badge error';
    if (health?.status === 'healthy') return 'health-badge healthy';
    return 'health-badge warning';
  };

  const getStatusText = () => {
    if (loading) return 'Conectando...';
    if (error) return 'Sin conexión';
    return health?.status === 'healthy' ? 'En línea' : 'Degradado';
  };

  return (
    <div className="health-check">
      <div className={getStatusClass()}>
        <span className="status-dot"></span>
        <span className="status-text">{getStatusText()}</span>
      </div>
      
      {health && !error && (
        <div className="health-details">
          <span className="health-stat">
            <strong>{health.entities_loaded?.toLocaleString()}</strong> entidades
          </span>
          {health.data_age_days !== null && (
            <span className="health-stat">
              Datos: <strong>{health.data_age_days}</strong> días
            </span>
          )}
          <span className="health-stat">
            v{health.algorithm_version}
          </span>
        </div>
      )}
      
      {error && (
        <div className="health-error-tooltip">
          {error}
        </div>
      )}
    </div>
  );
}

HealthCheck.propTypes = {
  onHealthUpdate: PropTypes.func
};

export default HealthCheck;
