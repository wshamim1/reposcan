function RepoTile({ r }) {
  return (
    <a
      key={r.full_name}
      href={r.html_url}
      target="_blank"
      rel="noreferrer"
      className="repo-card"
    >
      <div className="repo-card-header">
        <span className="repo-name">{r.full_name}</span>
        {r.language && <span className="lang-badge">{r.language}</span>}
      </div>
      <p className="repo-description">{r.description || 'No description'}</p>
      <div className="repo-meta">
        <span>⭐ {r.stars?.toLocaleString()}</span>
        <span>🍴 {r.forks?.toLocaleString()}</span>
      </div>
      {r.topics?.length > 0 && (
        <div className="topic-list">
          {r.topics.slice(0, 4).map((t) => (
            <span key={t} className="topic-badge">#{t}</span>
          ))}
        </div>
      )}
    </a>
  );
}

export default function SimilarRepos({ repos, clusters }) {
  const hasClusters = Array.isArray(clusters) && clusters.length > 0;
  const hasRepos = Array.isArray(repos) && repos.length > 0;
  const normalizedClusters = hasClusters
    ? clusters
    : hasRepos
      ? [{ name: 'General Similar Repos', count: repos.length, repos }]
      : [];

  return (
    <section className="card similar-repos">
      <h2 className="section-title">🔗 Similar Repositories</h2>
      {normalizedClusters.length === 0 ? (
        <p className="empty-note">No similar repositories found for this scan.</p>
      ) : (
        <div className="cluster-list">
          {normalizedClusters.map((cluster) => (
            <div key={cluster.name} className="cluster-block">
              <h3 className="cluster-title">
                {cluster.name} <span className="cluster-count">({cluster.count})</span>
              </h3>
              <div className="repos-grid">
                {(cluster.repos || []).map((r) => (
                  <RepoTile key={r.full_name} r={r} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
