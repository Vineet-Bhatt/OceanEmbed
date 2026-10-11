import React, { useEffect } from 'react';
import DashboardPage from './Dashboard.jsx';

export default function App() {
  const isDashboard = /^\/(today|custom|about-us|about-project)(\/|$)/.test(window.location.pathname);

  useEffect(() => {
    if (isDashboard) {
      import('./dashboard.css');
    } else {
      import('./App.css');
      import('./App.js');
    }
  }, [isDashboard]);

  if (isDashboard) return <DashboardPage />;

  return (
    <div className="shell">
      <a className="brand" href="/">OCEAN<span>EMBED</span></a>
      <main>
        <section className="earth-hero" id="earth-hero">
          <header className="page-heading">
            <h1>Subsurface<br />Intelligence</h1>
            <p className="hero-copy">Satellite observations. Ocean intelligence. A clearer view of temperature below.</p>
            <a className="scroll-cue" href="/today" aria-label="Open today's prediction dashboard">
              <span className="scroll-cue-link">Predict <span className="arrow" aria-hidden="true">→</span></span>
            </a>
          </header>
          <section id="prediction-result" className="result-panel" aria-live="polite" hidden />
        </section>
      </main>
      {/*
      <dialog id="prediction-modal" className="prediction-modal" aria-labelledby="modal-title" aria-describedby="modal-description">
        <div className="modal-layout">
          <section className="modal-map-pane">
            <h2 id="modal-title">Choose where to explore</h2>
            <div id="location-map" className="location-map" aria-label="Map of the North Indian Ocean prediction area" />
            <p id="map-status" className="map-status" aria-live="polite" />
          </section>
          <section className="modal-form-pane" aria-labelledby="form-title">
            <div className="modal-form-content">
              <h3 id="form-title">Prediction details</h3>
              <p id="modal-description" className="sr-only">Choose a location and date for an ocean temperature prediction.</p>
              <form id="prediction-form">
                <label htmlFor="latitude">Latitude</label>
                <div className="coordinate-input">
                  <input id="latitude" name="latitude" type="number" min="5" max="30" step="0.25" defaultValue="15" required />
                  <span>°N</span>
                </div>
                <label htmlFor="longitude">Longitude</label>
                <div className="coordinate-input">
                  <input id="longitude" name="longitude" type="number" min="45" max="105" step="0.25" defaultValue="75" required />
                  <span>°E</span>
                </div>
                <label htmlFor="target-date">Date</label>
                <div className="date-field">
                  <input id="target-date" name="date" type="date" required />
                  <button id="today-button" className="today-button" type="button" aria-label="Set date to today" title="Today">
                    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="4.5" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M6.5 2.5v4M13.5 2.5v4M3.5 8h13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      <circle cx="10" cy="12.5" r="1.5" fill="currentColor" />
                    </svg>
                    <span>Today</span>
                  </button>
                </div>
                <p id="prediction-status" className="status" aria-live="polite" />
              </form>
              <div className="modal-actions">
                <button id="cancel-prediction" className="modal-cancel" type="button">Cancel</button>
                <button id="predict-button" className="modal-submit" type="submit" form="prediction-form">
                  <span>Make a prediction</span><span aria-hidden="true">→</span>
                </button>
              </div>
            </div>
          </section>
        </div>
      </dialog>
      */}
    </div>
  );
}
