import React, { useState, useCallback } from 'react';
import './App.css';

// Componentes
import HealthCheck from './components/HealthCheck';
import ScreeningForm from './components/ScreeningForm';
import ResultsDisplay from './components/ResultsDisplay';
import BulkScreening from './components/BulkScreening';

// Import background image
import PanamaBackground from './assets/Panama.avif';

/**
 * SDNCheck PA - Aplicación de Screening de Sanciones
 * Sistema profesional de verificación contra listas OFAC y ONU para Panamá
 * Versión 2.0 - Diseño moderno y profesional
 */

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Tabs/Pestañas disponibles - Masivo primero (más útil para usuarios empresariales)
const TABS = {
  BULK: 'bulk',
  INDIVIDUAL: 'individual'
};

function App() {
  // Estado de la aplicación - Mostrar intro hasta que el usuario entre
  const [showIntro, setShowIntro] = useState(true);
  const [activeTab, setActiveTab] = useState(TABS.BULK); // Masivo por defecto
  const [healthStatus, setHealthStatus] = useState(null);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningResult, setScreeningResult] = useState(null);

  // Determinar si el servicio está disponible
  const isServiceAvailable = healthStatus?.status === 'healthy';

  // Callback para actualización del estado de salud
  const handleHealthUpdate = useCallback((health) => {
    setHealthStatus(health);
  }, []);

  // Entrar a la aplicación
  const handleEnterApp = () => {
    setShowIntro(false);
  };

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
          const errorData = await response.clone().json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          try {
            const errorText = await response.text();
            if (errorText) errorMessage = errorText;
          } catch {
            // Ignorar errores al leer el texto
          }
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

  // Pantalla de introducción con imagen de Panamá
  if (showIntro) {
    return (
      <div className="intro-screen" style={{ backgroundImage: `url(${PanamaBackground})` }}>
        <div className="intro-overlay">
          <div className="intro-content">
            <div className="intro-logo">
              <div className="logo-icon">
                <span className="shield-icon">🛡️</span>
              </div>
              <h1 className="intro-title">SDNCheck<span className="intro-pa">PA</span></h1>
              <div className="intro-subtitle">Sistema de Verificación de Sanciones</div>
            </div>
            
            <div className="intro-features">
              <div className="feature-item">
                <span className="feature-icon">🏛️</span>
                <span className="feature-text">Cumplimiento OFAC & ONU</span>
              </div>
              <div className="feature-item">
                <span className="feature-icon">⚡</span>
                <span className="feature-text">Procesamiento Masivo</span>
              </div>
              <div className="feature-item">
                <span className="feature-icon">📊</span>
                <span className="feature-text">Reportes Profesionales</span>
              </div>
            </div>

            <p className="intro-description">
              Plataforma de verificación de sanciones internacionales diseñada para 
              empresas, firmas de abogados y profesionales de compliance en Panamá.
            </p>

            <div className="intro-status">
              <HealthCheck onHealthUpdate={handleHealthUpdate} />
            </div>

            <button 
              className="btn-enter"
              onClick={handleEnterApp}
              disabled={!isServiceAvailable && healthStatus !== null}
            >
              {healthStatus === null ? (
                <>
                  <span className="btn-spinner"></span>
                  Conectando...
                </>
              ) : isServiceAvailable ? (
                <>
                  Ingresar al Sistema
                  <span className="btn-arrow">→</span>
                </>
              ) : (
                <>
                  Servicio No Disponible
                </>
              )}
            </button>

            <div className="intro-footer">
              <p>© {new Date().getFullYear()} SDNCheck Panama</p>
              <p className="intro-disclaimer">Verificación contra listas OFAC (EE.UU.) y ONU</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      {/* Header moderno y compacto */}
      <header className="header">
        <div className="header-content">
          <div className="logo-section" onClick={() => setShowIntro(true)} style={{cursor: 'pointer'}}>
            <div className="header-logo">
              <span className="header-shield">🛡️</span>
              <h1 className="header-title">SDNCheck<span className="header-pa">PA</span></h1>
            </div>
          </div>
          
          {/* Navegación integrada en header */}
          <nav className="header-nav">
            <button
              className={`nav-button ${activeTab === TABS.BULK ? 'active' : ''}`}
              onClick={() => setActiveTab(TABS.BULK)}
            >
              <span className="nav-icon">📋</span>
              <span className="nav-label">Masivo</span>
            </button>
            <button
              className={`nav-button ${activeTab === TABS.INDIVIDUAL ? 'active' : ''}`}
              onClick={() => setActiveTab(TABS.INDIVIDUAL)}
            >
              <span className="nav-icon">👤</span>
              <span className="nav-label">Individual</span>
            </button>
          </nav>

          <div className="header-status">
            <HealthCheck onHealthUpdate={handleHealthUpdate} />
          </div>
        </div>
      </header>

      {/* Contenido principal */}
      <main className="main-content">
        {/* Alerta de conexión */}
        {healthStatus === null && (
          <div className="service-alert connecting">
            <div className="alert-content">
              <span className="alert-spinner"></span>
              <span>Conectando con el servidor...</span>
            </div>
          </div>
        )}
        
        {healthStatus !== null && !isServiceAvailable && (
          <div className="service-alert error">
            <div className="alert-content">
              <span className="alert-icon">⚠️</span>
              <span>El servicio no está disponible. Por favor, intente más tarde.</span>
            </div>
          </div>
        )}

        {/* Tab de Screening Masivo (principal) */}
        {activeTab === TABS.BULK && (
          <div className="tab-content fade-in">
            <BulkScreening disabled={!isServiceAvailable} />
          </div>
        )}

        {/* Tab de Screening Individual */}
        {activeTab === TABS.INDIVIDUAL && (
          <div className="tab-content fade-in">
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
      </main>

      {/* Footer minimalista */}
      <footer className="footer">
        <div className="footer-content">
          <p className="copyright">
            © {new Date().getFullYear()} SDNCheck Panama
          </p>
          <p className="disclaimer">
            Verificación OFAC & ONU
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
