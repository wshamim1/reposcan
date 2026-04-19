import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ReadmePanel({ readme }) {
  const [expanded, setExpanded] = useState(false);

  if (!readme || readme.startsWith('Error:')) return null;

  const preview = readme.length > 1200 && !expanded ? readme.slice(0, 1200) + '\n\n…' : readme;

  return (
    <section className="card readme-panel">
      <div className="section-header">
        <h2 className="section-title">📄 README</h2>
        {readme.length > 1200 && (
          <button className="toggle-btn" onClick={() => setExpanded((v) => !v)}>
            {expanded ? 'Show less ▲' : 'Show full README ▼'}
          </button>
        )}
      </div>
      <div className="readme-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Open all links in new tab safely
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            ),
            // Prevent raw HTML injection
            html: () => null,
          }}
        >
          {preview}
        </ReactMarkdown>
      </div>
    </section>
  );
}
