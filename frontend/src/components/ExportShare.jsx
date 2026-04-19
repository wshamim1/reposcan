import { useState } from 'react';

export default function ExportShare({ scan }) {
  const [copied, setCopied] = useState(false);

  if (!scan) return null;

  const repoUrl = scan?.repo?.html_url || '';
  const shareUrl = repoUrl
    ? `${window.location.origin}?repo=${encodeURIComponent(repoUrl)}`
    : window.location.href;

  function handleCopy() {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleDownloadJSON() {
    // Exclude large graph data to keep file small
    const { graphs: _graphs, ...exportData } = scan;
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reposcan-${(scan?.repo?.full_name || 'report').replace('/', '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="export-share-bar">
      <button className="export-btn export-btn--copy" onClick={handleCopy}>
        {copied ? '✅ Copied!' : '🔗 Copy Share Link'}
      </button>
      <button className="export-btn export-btn--json" onClick={handleDownloadJSON}>
        ⬇️ Download JSON
      </button>
    </div>
  );
}
