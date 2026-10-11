import React, { useEffect, useRef, useState } from 'react';
import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const today = new Date().toISOString().slice(0, 10);

const navigation = [
  { label: 'Today', path: '/today', icon: '◷' },
  { label: 'Custom', path: '/custom', icon: '▦' },
  { label: 'About Us', path: '/about-us', icon: '◉' },
  { label: 'About the Project', path: '/about-project', icon: '◇' }
];

function Sidebar() {
  return (
    <aside className="sidebar">
      <NavLink className="brand" to="/">
        <span className="brand-mark">O</span>
        <span>OCEAN<span className="brand-light">EMBED</span></span>
      </NavLink>
      <nav aria-label="Main navigation">
        {navigation.map((item) => (
          <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon" aria-hidden="true">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function interpolateProfile(profile, depth, key) {
  if (depth <= profile[0].depth_m) return profile[0][key];
  const last = profile[profile.length - 1];
  if (depth >= last.depth_m) return last[key];

  const lowerIndex = profile.findIndex((point, index) => (
    index < profile.length - 1
    && point.depth_m <= depth
    && profile[index + 1].depth_m >= depth
  ));
  const lower = profile[lowerIndex];
  const upper = profile[lowerIndex + 1];
  const ratio = (depth - lower.depth_m) / (upper.depth_m - lower.depth_m);
  return lower[key] + (upper[key] - lower[key]) * ratio;
}

function DepthGraph({ profile, selectedDepth }) {
  if (!profile || profile.length === 0) return null;

  const width = 760;
  const height = 390;
  const padding = { top: 22, right: 28, bottom: 52, left: 72 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const ordered = [...profile].sort((a, b) => a.depth_m - b.depth_m);
  const maxDepth = Math.max(...ordered.map((point) => point.depth_m));
  const allTemps = ordered.flatMap((point) => [point.temperature_c, point.climatology_c]).filter(Number.isFinite);
  const xMin = Math.min(...allTemps);
  const xMax = Math.max(...allTemps);
  const xPad = Math.max(1, (xMax - xMin) * 0.2);
  const xDomainMin = xMin - xPad;
  const xDomainMax = xMax + xPad;

  const x = (temperature) => {
    const span = xDomainMax - xDomainMin || 1;
    return padding.left + ((temperature - xDomainMin) / span) * plotWidth;
  };

  const y = (depth) => {
    const span = maxDepth || 1;
    return padding.top + ((depth / span) * plotHeight);
  };

  const yTicks = [0, 50, 100, 200, 500, maxDepth].filter((tick, index, values) => {
    const next = values.slice(index + 1);
    return tick <= maxDepth && !next.includes(tick);
  });

  const xTicks = Array.from({ length: 6 }, (_, index) => {
    const value = xDomainMin + ((xDomainMax - xDomainMin) * index) / 5;
    return Number(value.toFixed(1));
  });

  const line = (key) => ordered
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(point[key])} ${y(point.depth_m)}`)
    .join(' ');
  const selectedTemperature = interpolateProfile(ordered, selectedDepth, 'temperature_c');
  const selectedClimatology = interpolateProfile(ordered, selectedDepth, 'climatology_c');

  return (
    <div className="graph-scroll">
      <svg className="depth-graph" role="img" aria-label="Depth graph of predicted temperature and climatology" viewBox={`0 0 ${width} ${height}`}>
        {xTicks.map((tick) => (
          <g key={tick}>
            <line x1={x(tick)} x2={x(tick)} y1={padding.top} y2={height - padding.bottom} className="grid-line" />
            <text x={x(tick)} y={height - padding.bottom + 22} textAnchor="middle" className="axis-label">{tick.toFixed(0)}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={tick}>
            <line x1={padding.left} x2={width - padding.right} y1={y(tick)} y2={y(tick)} className="grid-line" />
            <text x={padding.left - 12} y={y(tick) + 4} textAnchor="end" className="axis-label">{tick}</text>
          </g>
        ))}
        <path d={line('climatology_c')} className="graph-climatology" />
        <path d={line('temperature_c')} className="graph-prediction" />
        {ordered.map((point) => (
          <g key={`dots-${point.depth_m}`}>
            <circle cx={x(point.climatology_c)} cy={y(point.depth_m)} r="3.5" className="dot-climatology">
              <title>{`${point.depth_m} m climatology: ${point.climatology_c} °C`}</title>
            </circle>
            <circle cx={x(point.temperature_c)} cy={y(point.depth_m)} r="4" className="dot-prediction">
              <title>{`${point.depth_m} m predicted: ${point.temperature_c} °C`}</title>
            </circle>
          </g>
        ))}
        <line x1={padding.left} x2={width - padding.right} y1={y(selectedDepth)} y2={y(selectedDepth)} className="selected-depth-line" />
        <circle cx={x(selectedClimatology)} cy={y(selectedDepth)} r="5" className="selected-depth-climatology" />
        <circle cx={x(selectedTemperature)} cy={y(selectedDepth)} r="6" className="selected-depth-prediction" />
        <text x={padding.left + plotWidth / 2} y={height - 12} textAnchor="middle" className="axis-title">Temperature (°C)</text>
        <text x="18" y={padding.top + plotHeight / 2} textAnchor="middle" transform={`rotate(-90 18 ${padding.top + plotHeight / 2})`} className="axis-title">Depth (m)</text>
      </svg>
    </div>
  );
}

function PredictionPage({ mode }) {
  const isToday = mode === 'today';
  const [latitude, setLatitude] = useState('15');
  const [longitude, setLongitude] = useState('68');
  const [date, setDate] = useState(today);
  const [prediction, setPrediction] = useState(null);
  const [selectedDepth, setSelectedDepth] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const requestController = useRef(null);

  async function submit(event) {
    event?.preventDefault();
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ lat: latitude, lon: longitude, ...(!isToday && { date }) });
    try {
      const response = await fetch(`${API_URL}/predict?${params}`, { signal: controller.signal });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Prediction request failed (${response.status}).`);
      const profile = body.results?.[0]?.profile;
      if (!Array.isArray(profile) || profile.length === 0) throw new Error('The prediction service returned no depth profile.');
      setPrediction(body);
      setSelectedDepth(0);
    } catch (requestError) {
      if (requestError.name === 'AbortError') return;
      setPrediction(null);
      setError(requestError.message || 'Could not reach the prediction service.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    requestController.current?.abort();
    setLoading(false);
    setPrediction(null);
    setError('');
    if (isToday) submit();
    return () => requestController.current?.abort();
  }, [mode]);

  const profile = prediction?.results?.[0]?.profile || [];
  const orderedProfile = [...profile].sort((a, b) => a.depth_m - b.depth_m);
  const minDepth = orderedProfile[0]?.depth_m || 0;
  const maxDepth = orderedProfile[orderedProfile.length - 1]?.depth_m || 0;
  const activeDepth = Math.max(minDepth, Math.min(selectedDepth, maxDepth));
  const selectedTemperature = orderedProfile.length
    ? interpolateProfile(orderedProfile, activeDepth, 'temperature_c')
    : null;
  const selectedClimatology = orderedProfile.length
    ? interpolateProfile(orderedProfile, activeDepth, 'climatology_c')
    : null;

  return (
    <div className="page-content">
      <div className="page-heading">
        <div>
          <h1>{isToday ? "Today's prediction" : 'Custom prediction'}</h1>
        </div>
      </div>

      <section className="panel request-panel">
        <form className="request-form" onSubmit={submit}>
          <label>Latitude
            <div className="input-wrap"><input type="number" min="5" max="30" step="0.25" value={latitude} onChange={(event) => setLatitude(event.target.value)} required /><span>°N</span></div>
          </label>
          <label>Longitude
            <div className="input-wrap"><input type="number" min="45" max="105" step="0.25" value={longitude} onChange={(event) => setLongitude(event.target.value)} required /><span>°E</span></div>
          </label>
          {!isToday && <label>Prediction date
            <input type="date" value={date} max={today} onChange={(event) => setDate(event.target.value)} required />
          </label>}
          <button className="primary-button" type="submit" disabled={loading || !latitude || !longitude || (!isToday && !date)}>
            {loading ? <><span className="spinner" /> Loading…</> : isToday ? 'Refresh prediction →' : 'Get prediction →'}
          </button>
        </form>
        {error && <div className="error-message" role="alert"><strong>Prediction unavailable.</strong> {error}</div>}
      </section>

      {prediction && profile.length > 0 && <>
        <section className="panel depth-selector">
          <label htmlFor="depth-slider">Depth <strong>{activeDepth} m</strong></label>
          <input
            id="depth-slider"
            type="range"
            min={minDepth}
            max={maxDepth}
            step="5"
            value={activeDepth}
            onChange={(event) => setSelectedDepth(Number(event.target.value))}
            aria-label="Select depth in meters"
          />
          <div className="depth-reading">
            <strong>{selectedTemperature.toFixed(2)} °C</strong>
            <span>Climatology {selectedClimatology.toFixed(2)} °C</span>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div><h2>Temperature profile</h2><p>{prediction.target_date} · {prediction.results[0].requested.lat}°N, {prediction.results[0].requested.lon}°E</p></div>
          </div>
          <div className="legend"><span><i className="legend-prediction" /> Predicted temperature</span><span><i className="legend-climatology" /> Climatology</span></div>
          <DepthGraph profile={orderedProfile} selectedDepth={activeDepth} />
        </section>
        <section className="panel table-panel">
          <div className="panel-heading"><div><h2>Depth readings</h2></div></div>
          <div className="table-scroll"><table><thead><tr><th>Depth (m)</th><th>Predicted (°C)</th><th>Climatology (°C)</th><th>Anomaly (°C)</th></tr></thead>
            <tbody>{orderedProfile.map((point) => <tr key={point.depth_m}><td>{point.depth_m}</td><td>{point.temperature_c}</td><td>{point.climatology_c}</td><td className={point.anomaly_c >= 0 ? 'positive' : 'negative'}>{point.anomaly_c > 0 ? '+' : ''}{point.anomaly_c}</td></tr>)}</tbody>
          </table></div>
        </section>
      </>}
      {!prediction && !error && !loading && isToday && <section className="panel empty-state"><h2>Waiting for prediction data</h2></section>}
    </div>
  );
}

function AboutPage({ project = false }) {
  return (
    <div className="page-content">
      <div className="page-heading"><div><p className="eyebrow">OCEANEMBED</p><h1>{project ? 'About the project' : 'About us'}</h1><p className="muted">{project ? 'Making subsurface ocean information easier to explore.' : 'A multidisciplinary effort to make ocean insight more accessible.'}</p></div></div>
      {project ? <section className="panel about-panel"><span className="about-icon">⌁</span><h2>The challenge</h2><p>Satellite observations describe the ocean surface well, while many applications depend on understanding how temperature changes below it. Direct subsurface measurements are sparse.</p><p>OceanEmbed estimates subsurface temperature profiles for locations across the North Indian Ocean by combining recent ocean and satellite-derived inputs with a trained model and monthly climatology. Each daily profile includes predicted temperature, climatology, and anomaly at each model depth.</p><div className="info-strip"><strong>Model domain</strong><span>5–30°N · 45–105°E</span><span>Daily predictions, where valid ocean coverage is available</span></div></section> : <><section className="panel about-panel"><span className="about-icon">◉</span><h2>Ocean insight, made clearer</h2><p>OceanEmbed brings together ocean science, data and machine learning, and software engineering to make subsurface temperature information easier to explore.</p></section><section className="summary-grid team-grid"><article className="summary-card"><span>01 · Science</span><strong>Ocean science</strong><small>Oceanographic context for temperature profiles beneath the surface.</small></article><article className="summary-card"><span>02 · Modeling</span><strong>Data & machine learning</strong><small>Observational data and models transformed into useful insight.</small></article><article className="summary-card"><span>03 · Product</span><strong>Software engineering</strong><small>Tools that make ocean predictions accessible and understandable.</small></article></section></>}
    </div>
  );
}

function Dashboard() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">
        <main><Routes>
          <Route path="/" element={<Navigate to="/today" replace />} />
          <Route path="/today" element={<PredictionPage mode="today" />} />
          <Route path="/custom" element={<PredictionPage mode="custom" />} />
          <Route path="/about-us" element={<AboutPage />} />
          <Route path="/about-project" element={<AboutPage project />} />
          <Route path="*" element={<Navigate to="/today" replace />} />
        </Routes></main>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return <BrowserRouter><Dashboard /></BrowserRouter>;
}
