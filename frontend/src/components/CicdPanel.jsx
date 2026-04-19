const TOOL_ICONS = {
  'GitHub Actions': '⚡',
  'Travis CI': '🔧',
  'CircleCI': '🔄',
  'Jenkins': '🤖',
  'GitLab CI': '🦊',
  'Azure Pipelines': '☁️',
  'Docker': '🐳',
  'Docker Compose': '🐳',
  'Make': '⚙️',
  'Tox': '🧪',
  'Pre-commit': '🪝',
  'SonarQube': '🔍',
  'Codecov': '📊',
  'Dependabot': '🤖',
};

export default function CicdPanel({ cicd }) {
  if (!cicd || (!cicd.has_ci && !cicd.tools?.length)) return null;

  return (
    <section className="card cicd-panel">
      <h2 className="section-title">
        {cicd.has_ci ? '✅ CI/CD Detected' : '⚠️ No CI/CD Detected'}
      </h2>

      {cicd.tools?.length > 0 && (
        <div className="cicd-tools">
          {cicd.tools.map((tool) => (
            <span key={tool} className="cicd-badge">
              {TOOL_ICONS[tool] || '🔧'} {tool}
            </span>
          ))}
        </div>
      )}

      {cicd.workflows?.length > 0 && (
        <div className="cicd-workflows">
          <h3>GitHub Actions Workflows</h3>
          <ul className="workflow-list">
            {cicd.workflows.map((wf) => (
              <li key={wf} className="workflow-item">⚡ {wf}</li>
            ))}
          </ul>
        </div>
      )}

      {!cicd.has_ci && (
        <p className="cicd-empty">
          No CI/CD configuration files were found. Consider adding GitHub Actions, a Dockerfile, or another automation tool.
        </p>
      )}
    </section>
  );
}
