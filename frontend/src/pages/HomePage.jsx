import { useState } from 'react';
import { useScan } from '../hooks/useScan';
import SearchBar from '../components/SearchBar';
import SummaryCard from '../components/SummaryCard';
import GraphsPanel from '../components/GraphsPanel';
import SimilarRepos from '../components/SimilarRepos';
import DependenciesPanel from '../components/DependenciesPanel';
import CicdPanel from '../components/CicdPanel';
import ExportShare from '../components/ExportShare';
import HistoryPanel from '../components/HistoryPanel';
import CompareMode from '../components/CompareMode';

const STATUS_MESSAGES = {
  pending: '⏳ Job queued — starting agent…',
  running: '🤖 AI agent is analyzing the repository…',
  error: null,
};

export default function HomePage() {
  const { scan, status, error, loading, submit } = useScan();
  const [prefillUrl, setPrefillUrl] = useState('');
  const [compareOpen, setCompareOpen] = useState(false);

  function handleHistorySelect(url) {
    setPrefillUrl(url);
    submit(url, '', false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div className="page">
      {/* Header */}
      <header className="site-header">
        <div className="header-inner">
          <span className="logo">🔭 RepoScan</span>
          <div className="header-actions">
            <span className="tagline">AI-powered GitHub Repository Scanner</span>
            <button className="compare-trigger" onClick={() => setCompareOpen(true)}>
              ⚖️ Compare
            </button>
          </div>
        </div>
      </header>

      {/* Compare overlay */}
      {compareOpen && <CompareMode onClose={() => setCompareOpen(false)} />}

      {/* Search */}
      <main className="main-content">
        <div className="hero">
          <h1>Analyze any GitHub repository in seconds</h1>
          <p>Paste a GitHub URL and let the AI agent build a full report — summary, graphs, and similar repos.</p>
          <SearchBar onSubmit={submit} loading={loading} prefillUrl={prefillUrl} />
        </div>

        {/* Scan History */}
        <HistoryPanel onSelect={handleHistorySelect} />

        {/* Status banner */}
        {loading && STATUS_MESSAGES[status] && (
          <div className="status-banner">
            <span className="spinner" />
            {STATUS_MESSAGES[status]}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="error-banner">
            ❌ {error}
          </div>
        )}

        {/* Results */}
        {scan && (
          <>
            {/* Export / Share bar */}
            <ExportShare scan={scan} />

            <div className="results">
              {/* 1. Summary + Getting Started + Stats */}
              <SummaryCard scan={scan} />

              {/* 2. Graphs */}
              <GraphsPanel graphs={scan.graphs} />

              {/* 3. Dependencies */}
              <DependenciesPanel dependencies={scan.dependencies} />

              {/* 4. CI/CD */}
              <CicdPanel cicd={scan.cicd} />

              {/* 5. Risk Flags */}
              {scan.risk_flags?.length > 0 && (
                <section className="card risk-card">
                  <h2 className="section-title">⚠️ Risk Flags</h2>
                  <ul className="risk-list">
                    {scan.risk_flags.map((flag, i) => (
                      <li key={i} className="risk-item">{flag}</li>
                    ))}
                  </ul>
                </section>
              )}

              {/* 6. Similar Repos */}
              <SimilarRepos repos={scan.similar_repos} clusters={scan.similar_repo_clusters} />
            </div>
          </>
        )}
      </main>

      <footer className="site-footer">
        <p>Built with LangChain · FastAPI · React · Plotly</p>
      </footer>
    </div>
  );
}
