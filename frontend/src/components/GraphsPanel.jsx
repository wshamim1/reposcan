import createPlotlyComponentModule from 'react-plotly.js/factory';
import PlotlyModule from 'plotly.js/dist/plotly.min.js';

const createPlotlyComponent =
  createPlotlyComponentModule?.default ?? createPlotlyComponentModule;
const Plotly = PlotlyModule?.default ?? PlotlyModule;
const Plot = createPlotlyComponent(Plotly);

function PlotCard({ title, figure }) {
  if (!figure || !figure.data) return null;
  return (
    <div className="card plot-card">
      <h3>{title}</h3>
      <Plot
        data={figure.data}
        layout={{ ...figure.layout, autosize: true }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </div>
  );
}

export default function GraphsPanel({ graphs }) {
  if (!graphs) return null;

  return (
    <section className="graphs-panel">
      <h2 className="section-title">📊 Repository Graphs</h2>
      <div className="graphs-grid">
        <PlotCard title="Stars & Forks" figure={graphs.stars_forks} />
        <PlotCard title="Language Breakdown" figure={graphs.language_pie} />
        <PlotCard title="Commit Activity" figure={graphs.commit_activity} />
        <PlotCard title="Top Contributors" figure={graphs.contributors} />
        <PlotCard title="Similar Repos Comparison" figure={graphs.similar_scatter} />
      </div>
    </section>
  );
}
