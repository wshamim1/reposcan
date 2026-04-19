import { useState } from 'react';
import { useScan } from '../hooks/useScan';
import SearchBar from './SearchBar';
import SummaryCard from './SummaryCard';
import GraphsPanel from './GraphsPanel';

const STATUS_MESSAGES = {
  pending: '⏳ Queued…',
  running: '🤖 Analyzing…',
};

function ComparePane({ label }) {
  const { scan, status, error, loading, submit } = useScan();

  return (
    <div className="compare-pane">
      <div className="compare-pane-header">
        <span className="compare-label">{label}</span>
      </div>
      <SearchBar onSubmit={submit} loading={loading} compact />

      {loading && STATUS_MESSAGES[status] && (
        <div className="status-banner" style={{ marginTop: 12 }}>
          <span className="spinner" />
          {STATUS_MESSAGES[status]}
        </div>
      )}
      {error && (
        <div className="error-banner" style={{ marginTop: 12 }}>❌ {error}</div>
      )}
      {scan && (
        <div style={{ marginTop: 16 }}>
          <SummaryCard scan={scan} compact />
          <GraphsPanel graphs={scan.graphs} compact />
        </div>
      )}
    </div>
  );
}

export default function CompareMode({ onClose }) {
  return (
    <div className="compare-overlay">
      <div className="compare-header">
        <h2>⚖️ Compare Repositories</h2>
        <button className="compare-close" onClick={onClose}>✕ Close</button>
      </div>
      <div className="compare-grid">
        <ComparePane label="Repo A" />
        <ComparePane label="Repo B" />
      </div>
    </div>
  );
}
