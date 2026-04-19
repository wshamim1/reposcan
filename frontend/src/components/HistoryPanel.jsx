import { useEffect, useState } from 'react';
import { fetchHistory } from '../utils/api';

const GRADE_COLOR = {
  A: '#10b981', B: '#0ea5e9', C: '#f59e0b', D: '#f97316', F: '#ef4444',
};

export default function HistoryPanel({ onSelect }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetchHistory()
      .then((d) => setHistory(d.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, []);

  if (!loading && history.length === 0) return null;

  return (
    <div className="history-panel">
      <button className="history-toggle" onClick={() => setOpen((v) => !v)}>
        🕓 Scan History {history.length > 0 && `(${history.length})`} {open ? '▲' : '▼'}
      </button>

      {open && (
        <div className="history-list">
          {loading ? (
            <p className="history-empty">Loading history…</p>
          ) : (
            history.map((item) => (
              <button
                key={item.github_url}
                className="history-item"
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
            ))
          )}
        </div>
      )}
    </div>
  );
}
