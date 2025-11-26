import React, { useState, useEffect } from 'react';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [screeningName, setScreeningName] = useState('');
  const [screeningResult, setScreeningResult] = useState(null);
  const [screeningLoading, setScreeningLoading] = useState(false);

  useEffect(() => {
    fetchHealth();
  }, []);

  const fetchHealth = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/health`);
      if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
      }
      const data = await response.json();
      setHealth(data);
      setError(null);
    } catch (err) {
      const message = err.name === 'TypeError' 
        ? 'Network error: Unable to reach API' 
        : err.message;
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleScreen = async (e) => {
    e.preventDefault();
    if (!screeningName.trim()) return;

    setScreeningLoading(true);
    setScreeningResult(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/screen`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: screeningName,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Screening failed (${response.status}): ${errorText}`);
      }
      const data = await response.json();
      setScreeningResult(data);
    } catch (err) {
      const message = err.name === 'TypeError'
        ? 'Network error: Unable to reach API'
        : err.message;
      setScreeningResult({ error: message });
    } finally {
      setScreeningLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>🇵🇦 SDNCheck PA</h1>
        <p>Sanctions Screening for Panama</p>
      </header>

      <main className="main">
        <section className="status-section">
          <h2>API Status</h2>
          {loading && <p className="loading">Connecting to API...</p>}
          {error && <p className="error">{error}</p>}
          {health && (
            <div className="health-info">
              <p className="status-healthy">✓ {health.status}</p>
              <p>Entities loaded: {health.entities_loaded?.toLocaleString()}</p>
              <p>Algorithm version: {health.algorithm_version}</p>
            </div>
          )}
        </section>

        <section className="screening-section">
          <h2>Quick Screening</h2>
          <form onSubmit={handleScreen} className="screening-form">
            <input
              type="text"
              value={screeningName}
              onChange={(e) => setScreeningName(e.target.value)}
              placeholder="Enter name to screen..."
              className="screening-input"
            />
            <button
              type="submit"
              disabled={screeningLoading || !screeningName.trim()}
              className="screening-button"
            >
              {screeningLoading ? 'Screening...' : 'Screen'}
            </button>
          </form>

          {screeningResult && (
            <div className="screening-result">
              {screeningResult.error ? (
                <p className="error">{screeningResult.error}</p>
              ) : (
                <div>
                  <p className={screeningResult.is_hit ? 'hit' : 'clear'}>
                    {screeningResult.is_hit ? '⚠️ MATCH FOUND' : '✓ NO MATCHES'}
                  </p>
                  <p>Hits: {screeningResult.hit_count}</p>
                  <p>Processing time: {screeningResult.processing_time_ms}ms</p>
                </div>
              )}
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <p>SDNCheck Panama © 2025</p>
      </footer>
    </div>
  );
}

export default App;
