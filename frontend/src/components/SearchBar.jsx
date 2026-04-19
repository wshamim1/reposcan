import { useState, useEffect } from 'react';
import { searchRepos } from '../utils/api';

export default function SearchBar({ onSubmit, onSelectUrl, loading, prefillUrl = '', compact = false }) {
  const [url, setUrl] = useState('');
  const [useCase, setUseCase] = useState('');
  const [forceRefresh, setForceRefresh] = useState(false);
  const [keywords, setKeywords] = useState('');
  const [searchingRepos, setSearchingRepos] = useState(false);
  const [repoResults, setRepoResults] = useState([]);
  const [searchError, setSearchError] = useState('');

  useEffect(() => {
    if (prefillUrl) setUrl(prefillUrl);
  }, [prefillUrl]);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onSubmit(trimmed, useCase.trim(), forceRefresh);
  }

  async function handleKeywordSearch() {
    const query = keywords.trim();
    if (!query) return;

    setSearchError('');
    setSearchingRepos(true);
    try {
      const data = await searchRepos(query, 8);
      setRepoResults(data.results || []);
    } catch (err) {
      setRepoResults([]);
      setSearchError(err.response?.data?.detail || err.message || 'Failed to search repositories');
    } finally {
      setSearchingRepos(false);
    }
  }

  function handleSelectRepo(repoUrl) {
    setUrl(repoUrl);
    setRepoResults([]);
    setSearchError('');
    if (onSelectUrl) {
      onSelectUrl(repoUrl, useCase.trim(), forceRefresh);
      return;
    }
    onSubmit(repoUrl, useCase.trim(), forceRefresh);
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
          <div className="keyword-row">
            <input
              type="text"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleKeywordSearch();
                }
              }}
              placeholder="Or search by keywords (e.g. rag vector database)"
              disabled={loading || searchingRepos}
              className="search-input keyword-input"
              aria-label="Repository keyword search"
            />
            <button
              type="button"
              disabled={loading || searchingRepos || !keywords.trim()}
              onClick={handleKeywordSearch}
              className="search-btn keyword-btn"
            >
              {searchingRepos ? 'Searching…' : 'Find Repos'}
            </button>
          </div>

          {searchError && <div className="error-banner search-error">❌ {searchError}</div>}

          {repoResults.length > 0 && (
            <div className="repo-results" role="list" aria-label="Repository search results">
              {repoResults.map((repo) => (
                <button
                  key={repo.html_url}
                  type="button"
                  className="repo-result"
                  onClick={() => handleSelectRepo(repo.html_url)}
                  disabled={loading}
                >
                  <div className="repo-result-top">
                    <span className="search-repo-name">{repo.full_name}</span>
                    <span className="search-repo-meta">⭐ {repo.stars.toLocaleString()} · {repo.language}</span>
                  </div>
                  {repo.description && <p className="search-repo-desc">{repo.description}</p>}
                  <span className="search-repo-url">{repo.html_url}</span>
                </button>
              ))}
            </div>
          )}

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
