import { useState, useEffect } from 'react';

export default function SearchBar({ onSubmit, loading, prefillUrl = '', compact = false }) {
  const [url, setUrl] = useState('');
  const [useCase, setUseCase] = useState('');
  const [forceRefresh, setForceRefresh] = useState(false);

  useEffect(() => {
    if (prefillUrl) setUrl(prefillUrl);
  }, [prefillUrl]);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onSubmit(trimmed, useCase.trim(), forceRefresh);
  }

  return (
    <form onSubmit={handleSubmit} className="search-form">
      <div className="search-bar">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          disabled={loading}
          className="search-input"
          aria-label="GitHub repository URL"
        />
        <button type="submit" disabled={loading || !url.trim()} className="search-btn">
          {loading ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Scanning…
            </>
          ) : (
            '🔍 Scan'
          )}
        </button>
      </div>
      {!compact && (
        <>
          <input
            type="text"
            value={useCase}
            onChange={(e) => setUseCase(e.target.value)}
            placeholder="Optional use case (e.g. vector search for RAG)"
            disabled={loading}
            className="search-input use-case-input"
            aria-label="Desired use case"
          />
          <label className="force-refresh-row">
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              disabled={loading}
            />
            Force fresh scan (ignore cache)
          </label>
        </>
      )}
    </form>
  );
}
