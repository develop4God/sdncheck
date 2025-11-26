import React, { useState, useCallback } from 'react';
import './App.css';

// Componentes
import HealthCheck from './components/HealthCheck';
import ScreeningForm from './components/ScreeningForm';
import ResultsDisplay from './components/ResultsDisplay';
import BulkScreening from './components/BulkScreening';

/**
 * SDNCheck PA - Aplicación de Screening de Sanciones
 * Sistema profesional de verificación contra listas OFAC y ONU para Panamá
 */

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Tabs/Pestañas disponibles
const TABS = {
  INDIVIDUAL: 'individual',
  BULK: 'bulk'
};

function App() {
  // Estado de la aplicación
  const [activeTab, setActiveTab] = useState(TABS.INDIVIDUAL);
  const [healthStatus, setHealthStatus] = useState(null);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningResult, setScreeningResult] = useState(null);

  // Determinar si el servicio está disponible
  const isServiceAvailable = healthStatus?.status === 'healthy';

  // Callback para actualización del estado de salud
  const handleHealthUpdate = useCallback((health) => {
    setHealthStatus(health);
  }, []);

  // Manejar screening individual
  const handleIndividualScreen = async (screeningData) => {
    setScreeningLoading(true);
    setScreeningResult(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/screen`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(screeningData),
      });

      if (!response.ok) {
        let errorMessage = `Error del servidor (${response.status})`;
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          // Si no es JSON, usar el texto
          const errorText = await response.text();
          if (errorText) errorMessage = errorText;
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setScreeningResult(data);
    } catch (err) {
      const message = err.name === 'TypeError'
        ? 'Error de red: No se puede conectar al servidor. Verifique su conexión.'
        : err.message;
      setScreeningResult({ error: message });
    } finally {
      setScreeningLoading(false);
    }
  };

  return (
    <div className="app">
      {/* Header con logo y estado */}
      <header className="header">
        <div className="header-content">
          <div className="logo-section">
            <h1>
              <span className="logo-flag">🇵🇦</span>
              <span className="logo-text">SDNCheck PA</span>
            </h1>
            <p className="tagline">Sistema de Verificación de Sanciones</p>
          </div>
          <HealthCheck onHealthUpdate={handleHealthUpdate} />
        </div>
      </header>

      {/* Navegación por tabs */}
      <nav className="tab-navigation">
        <button
          className={`tab-button ${activeTab === TABS.INDIVIDUAL ? 'active' : ''}`}
          onClick={() => setActiveTab(TABS.INDIVIDUAL)}
        >
          <span className="tab-icon">👤</span>
          <span className="tab-label">Screening Individual</span>
        </button>
        <button
          className={`tab-button ${activeTab === TABS.BULK ? 'active' : ''}`}
          onClick={() => setActiveTab(TABS.BULK)}
        >
          <span className="tab-icon">📋</span>
          <span className="tab-label">Screening Masivo</span>
        </button>
      </nav>

      {/* Contenido principal */}
      <main className="main-content">
        {/* Alerta si el servicio no está disponible */}
        {healthStatus === null && (
          <div className="service-alert connecting">
            <span className="alert-icon">🔄</span>
            <span>Conectando con el servidor...</span>
          </div>
        )}
        
        {healthStatus !== null && !isServiceAvailable && (
          <div className="service-alert error">
            <span className="alert-icon">⚠️</span>
            <span>El servicio no está disponible. Por favor, intente más tarde.</span>
          </div>
        )}

        {/* Tab de Screening Individual */}
        {activeTab === TABS.INDIVIDUAL && (
          <div className="tab-content">
            <div className="screening-container">
              <ScreeningForm
                onSubmit={handleIndividualScreen}
                loading={screeningLoading}
                disabled={!isServiceAvailable}
              />
              <ResultsDisplay
                result={screeningResult}
                loading={screeningLoading}
              />
            </div>
          </div>
        )}

        {/* Tab de Screening Masivo */}
        {activeTab === TABS.BULK && (
          <div className="tab-content">
            <BulkScreening disabled={!isServiceAvailable} />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-content">
          <p className="copyright">
            © {new Date().getFullYear()} SDNCheck Panama - Todos los derechos reservados
          </p>
          <p className="disclaimer">
            Este sistema verifica contra las listas OFAC (EE.UU.) y ONU de sanciones.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
