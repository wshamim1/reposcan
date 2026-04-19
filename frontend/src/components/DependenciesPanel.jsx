const FILE_ICONS = {
  'requirements.txt': '🐍',
  'requirements-dev.txt': '🐍',
  'pyproject.toml': '🐍',
  'setup.cfg': '🐍',
  'Pipfile': '🐍',
  'package.json': '📦',
  'yarn.lock': '📦',
  'pnpm-lock.yaml': '📦',
  'go.mod': '🐹',
  'Gemfile': '💎',
  'Cargo.toml': '🦀',
  'build.gradle': '🐘',
  'pom.xml': '☕',
};

export default function DependenciesPanel({ dependencies }) {
  if (!dependencies?.files || Object.keys(dependencies.files).length === 0) return null;

  const files = Object.entries(dependencies.files);

  return (
    <section className="card deps-panel">
      <h2 className="section-title">📦 Dependencies</h2>
      <div className="deps-grid">
        {files.map(([filename, deps]) => (
          <div key={filename} className="deps-file-block">
            <h3 className="deps-filename">
              {FILE_ICONS[filename] || '📄'} {filename}
              <span className="deps-count">{deps.length} packages</span>
            </h3>
            <div className="deps-list">
              {deps.slice(0, 20).map((dep) => (
                <span key={dep} className="dep-badge">{dep}</span>
              ))}
              {deps.length > 20 && (
                <span className="dep-badge dep-badge--more">+{deps.length - 20} more</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
