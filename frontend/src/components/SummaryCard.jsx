import { useMemo, useState } from 'react';
import { executeSetupScript } from '../utils/api';

function Stat({ label, value, accent }) {
  return (
    <div className={`stat-card ${accent ? 'stat-card--accent' : ''}`}>
      <span className="stat-value">{value?.toLocaleString() ?? '—'}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

export default function SummaryCard({ scan }) {
  const repo = scan?.repo ?? {};
  const repoUrl = repo?.html_url || '';
  const topics = repo.topics ?? [];
  const health = scan?.health;
  const useCaseMatch = scan?.use_case_match;
  const cache = scan?.cache;
  const [scriptState, setScriptState] = useState({ loading: false, result: null, error: null });
  const [copyDone, setCopyDone] = useState(false);

  const commandPrefixes = useMemo(
    () => ['git ', 'cd ', 'python ', 'python3 ', 'pip ', 'pip3 ', 'npm ', 'yarn ', 'pnpm ', 'poetry ', 'uv ', 'uvicorn ', 'make ', 'source ', 'docker '],
    []
  );

  const scriptLines = useMemo(() => {
    const lines = [];
    const steps = Array.isArray(scan?.getting_started) ? scan.getting_started : [];
    for (const raw of steps) {
      const parts = String(raw).split('\n');
      for (const p of parts) {
        const line = p
          .trim()
          .replace(/^\*\*|\*\*$/g, '')
          .replace(/^[\-*]\s+/, '')
          .replace(/<repository-url>/gi, repoUrl || '<repository-url>');
        if (!line) continue;
        const lower = line.toLowerCase();
        if (commandPrefixes.some((pref) => lower.startsWith(pref))) {
          lines.push(line.replace(/\s+#\s+On Windows:.*/i, ''));
        }
      }
    }
    return lines;
  }, [scan?.getting_started, commandPrefixes, repoUrl]);

  const formattedGettingStarted = useMemo(() => {
    const steps = Array.isArray(scan?.getting_started) ? scan.getting_started : [];
    return steps.map((step) =>
      String(step).replace(/<repository-url>/gi, repoUrl || '<repository-url>')
    );
  }, [scan?.getting_started, repoUrl]);

  const scriptText = useMemo(() => {
    if (scriptLines.length === 0) return '';
    return ['#!/usr/bin/env bash', 'set -e', '', ...scriptLines].join('\n');
  }, [scriptLines]);

  async function handleCopyScript() {
    if (!scriptText) return;
    await navigator.clipboard.writeText(scriptText);
    setCopyDone(true);
    setTimeout(() => setCopyDone(false), 1500);
  }

  async function handleRunScript() {
    if (!scriptText || scriptState.loading) return;
    setScriptState({ loading: true, result: null, error: null });
    try {
      const result = await executeSetupScript(scriptText, 120);
      setScriptState({ loading: false, result, error: null });
    } catch (err) {
      setScriptState({
        loading: false,
        result: null,
        error: err?.response?.data?.detail || err?.message || 'Failed to execute script',
      });
    }
  }

  return (
    <section className="card summary-card">
      {/* ── 1. Summary ── */}
      <div className="summary-header">
        <div>
          <h2 className="summary-title">
            <a href={repo.html_url} target="_blank" rel="noreferrer">
              {repo.full_name}
            </a>
          </h2>
          <p className="summary-description">{repo.description}</p>
        </div>
        {repo.language && (
          <span className="lang-badge">{repo.language}</span>
        )}
      </div>

      <p className="summary-text">{scan?.summary}</p>

      {cache && (
        <div className={`scan-status ${cache.hit ? 'scan-status--cached' : 'scan-status--fresh'}`}>
          <strong>{cache.hit ? 'Cached Result' : 'Fresh Scan'}</strong>
          <span>{cache.message}</span>
        </div>
      )}

      {useCaseMatch && (
        <div className="health-block">
          <h3>Use-Case Match</h3>
          <p className="health-line">
            Query: <strong>{useCaseMatch.query}</strong> · Fit: <strong>{useCaseMatch.fit}</strong> · Score: <strong>{useCaseMatch.score}/100</strong> · Intent: <strong>{useCaseMatch.intent_score ?? 0}/100</strong>
          </p>
          {useCaseMatch?.requested_intents?.length > 0 && (
            <p className="health-line">
              Requested intents: {useCaseMatch.requested_intents.join(', ')}
            </p>
          )}
          {useCaseMatch?.top_intents?.length > 0 && (
            <p className="health-line">
              Top inferred intents: {useCaseMatch.top_intents.map((x) => `${x.intent} (${x.score})`).join(', ')}
            </p>
          )}
          <p className="health-line">{useCaseMatch.explanation}</p>
        </div>
      )}

      {scan?.key_features?.length > 0 && (
        <div className="features-block">
          <h3>Key Features</h3>
          <ul>
            {scan.key_features.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {scan?.tech_stack?.length > 0 && (
        <div className="tech-stack">
          {scan.tech_stack.map((t) => (
            <span key={t} className="tech-badge">{t}</span>
          ))}
        </div>
      )}

      {topics.length > 0 && (
        <div className="topic-list">
          {topics.map((t) => (
            <span key={t} className="topic-badge">#{t}</span>
          ))}
        </div>
      )}

      {repo.license && (
        <p className="license-line">📄 License: {repo.license}</p>
      )}

      {/* ── 2. Getting Started ── */}
      {scan?.getting_started?.length > 0 && (
        <div className="features-block getting-started-block">
          <h3>
            🚀 How To Get Started
            {scan?.getting_started_source === 'generated' && (
              <span className="generated-badge">AI-generated</span>
            )}
          </h3>
          <ol>
            {formattedGettingStarted.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>

          {scriptText && (
            <div className="script-runner">
              <div className="script-runner-header">
                <span className="script-runner-title">Runnable Setup Script</span>
                <div className="script-actions">
                  <button type="button" className="script-btn" onClick={handleCopyScript}>
                    {copyDone ? 'Copied' : 'Copy Script'}
                  </button>
                  <button
                    type="button"
                    className="script-btn script-btn--run"
                    onClick={handleRunScript}
                    disabled={scriptState.loading}
                  >
                    {scriptState.loading ? 'Running...' : 'Execute from UI'}
                  </button>
                </div>
              </div>

              <pre className="script-code"><code>{scriptText}</code></pre>

              {scriptState.error && (
                <p className="script-error">Execution failed: {scriptState.error}</p>
              )}

              {scriptState.result && (
                <div className="script-output">
                  <p className="script-output-status">
                    {scriptState.result.ok ? 'Execution succeeded' : `Execution failed (exit ${scriptState.result.exit_code})`}
                  </p>
                  {scriptState.result.stdout ? (
                    <pre className="script-output-box"><code>{scriptState.result.stdout}</code></pre>
                  ) : null}
                  {scriptState.result.stderr ? (
                    <pre className="script-output-box script-output-box--err"><code>{scriptState.result.stderr}</code></pre>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── 3. Stats & Health ── */}
      <div className="stat-row">
        <Stat label="⭐ Stars" value={repo.stars} accent />
        <Stat label="🍴 Forks" value={repo.forks} />
        <Stat label="🐛 Issues" value={repo.open_issues} />
        <Stat label="👁 Watchers" value={repo.watchers} />
      </div>

      {health?.score !== undefined && (
        <div className="health-block">
          <h3>Repository Health</h3>
          <p className="health-line">
            Score: <strong>{health.score}/100</strong> · Grade: <strong>{health.grade}</strong> · Status: <strong>{health.status}</strong>
          </p>
        </div>
      )}
    </section>
  );
}
