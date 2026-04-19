import { useEffect, useState } from 'react';
import { fetchHistory, deleteHistoryEntry, clearHistory } from '../utils/api';

const GRADE_COLOR = {
  A: '#10b981', B: '#0ea5e9', C: '#f59e0b', D: '#f97316', F: '#ef4444',
};

export default function HistoryPanel({ onSelect }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [deletingUrl, setDeletingUrl] = useState('');
  const [clearing, setClearing] = useState(false);

  function loadHistory() {
    setLoading(true);
    fetchHistory()
      .then((d) => setHistory(d.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadHistory();
  }, []);

  async function handleDelete(githubUrl) {
    const confirmed = window.confirm('Delete this history entry?');
    if (!confirmed) return;

    setDeletingUrl(githubUrl);
    try {
      await deleteHistoryEntry(githubUrl);
      setHistory((prev) => prev.filter((item) => item.github_url !== githubUrl));
    } finally {
      setDeletingUrl('');
    }
  }

  async function handleClearAll() {
    const confirmed = window.confirm('Clear all scan history?');
    if (!confirmed) return;

    setClearing(true);
    try {
      await clearHistory();
      setHistory([]);
      setOpen(false);
    } finally {
      setClearing(false);
    }
  }

  if (!loading && history.length === 0) return null;

  return (
    <div className="history-panel">
      <button className="history-toggle" onClick={() => setOpen((v) => !v)}>
        🕓 Scan History {history.length > 0 && `(${history.length})`} {open ? '▲' : '▼'}
      </button>

      {open && (
        <>
          {history.length > 0 && (
            <div className="history-toolbar">
              <button
                className="history-clear-btn"
                onClick={handleClearAll}
                disabled={clearing || loading}
              >
                {clearing ? 'Clearing…' : 'Clear All'}
              </button>
            </div>
          )}

          <div className="history-list">
          {loading ? (
            <p className="history-empty">Loading history…</p>
          ) : (
            history.map((item) => (
              <div
                key={item.github_url}
                className="history-item"
              >
                <button
                  className="history-open-btn"
                  onClick={() => onSelect(item.github_url)}
                >
                  <div className="history-item-left">
                    <span className="history-name">{item.full_name}</span>
                    {item.description && (
                      <span className="history-desc">{item.description}</span>
                    )}
                  </div>
                  <div className="history-item-right">
                    {item.language && (
                      <span className="history-lang">{item.language}</span>
                    )}
                    <span
                      className="history-grade"
                      style={{ color: GRADE_COLOR[item.health_grade] || '#64748b' }}
                    >
                      {item.health_grade}
                    </span>
                    {item.scanned_at && (
                      <span className="history-date">
                        {new Date(item.scanned_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </button>

                <button
                  className="history-delete-btn"
                  onClick={() => handleDelete(item.github_url)}
                  disabled={deletingUrl === item.github_url || clearing}
                  aria-label={`Delete ${item.full_name} from history`}
                >
                  {deletingUrl === item.github_url ? '…' : 'Delete'}
                </button>
              </div>
            ))
          )}
          </div>
        </>
      )}
    </div>
  );
}
