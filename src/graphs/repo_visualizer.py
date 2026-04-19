"""
Plotly-based visualizations for repo scan results.

All public functions return a Plotly figure serialized as a JSON string
so it can be embedded directly in the React frontend via react-plotly.js.
"""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def _fig_to_json(fig: go.Figure) -> dict:
    """Serialize a Plotly figure to a plain dict (for JSON API response)."""
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# 1. Language Breakdown — Pie Chart
# ---------------------------------------------------------------------------

def language_pie(language_breakdown: dict[str, int]) -> dict:
    """
    Pie chart of programming language byte counts.
    """
    if not language_breakdown or "error" in language_breakdown:
        return {}

    labels = list(language_breakdown.keys())
    values = list(language_breakdown.values())

    fig = px.pie(
        names=labels,
        values=values,
        title="Language Breakdown",
        hole=0.35,
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
        margin=dict(t=50, b=80, l=20, r=20),
        height=380,
    )
    return _fig_to_json(fig)


# ---------------------------------------------------------------------------
# 2. Commit Activity — Bar Chart (last 52 weeks)
# ---------------------------------------------------------------------------

def commit_activity_bar(commit_activity: list[dict[str, Any]]) -> dict:
    """
    Bar chart showing weekly commit counts over the past year.
    """
    if not commit_activity or (len(commit_activity) == 1 and "error" in commit_activity[0]):
        return {}

    weeks = [item["week"] for item in commit_activity]
    counts = [item["commits"] for item in commit_activity]

    fig = go.Figure(
        go.Bar(
            x=weeks,
            y=counts,
            marker_color="#6366f1",
            hovertemplate="Week: %{x}<br>Commits: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Weekly Commit Activity (Last 52 Weeks)",
        xaxis_title="Week",
        yaxis_title="Commits",
        margin=dict(t=50, b=60, l=50, r=20),
        height=320,
        plot_bgcolor="#f9fafb",
        paper_bgcolor="white",
    )
    return _fig_to_json(fig)


# ---------------------------------------------------------------------------
# 3. Top Contributors — Horizontal Bar
# ---------------------------------------------------------------------------

def contributors_bar(contributors: list[dict[str, Any]]) -> dict:
    """
    Horizontal bar chart of top contributor commit counts.
    """
    if not contributors or (len(contributors) == 1 and "error" in contributors[0]):
        return {}

    logins = [c["login"] for c in contributors]
    contribs = [c["contributions"] for c in contributors]

    fig = go.Figure(
        go.Bar(
            x=contribs,
            y=logins,
            orientation="h",
            marker_color="#10b981",
            hovertemplate="%{y}: %{x} contributions<extra></extra>",
        )
    )
    fig.update_layout(
        title="Top Contributors",
        xaxis_title="Contributions",
        yaxis=dict(autorange="reversed"),
        margin=dict(t=50, b=40, l=120, r=20),
        height=max(280, len(logins) * 35 + 80),
        plot_bgcolor="#f9fafb",
        paper_bgcolor="white",
    )
    return _fig_to_json(fig)


# ---------------------------------------------------------------------------
# 4. Stars vs Forks — Gauge-style metric cards (single figure, 2 indicators)
# ---------------------------------------------------------------------------

def stars_forks_gauge(stars: int, forks: int) -> dict:
    """
    Two side-by-side indicator gauges for Stars and Forks.
    """
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "indicator"}, {"type": "indicator"}]],
    )
    fig.add_trace(
        go.Indicator(
            mode="number+delta",
            value=stars,
            title={"text": "⭐ Stars"},
            number={"font": {"color": "#f59e0b", "size": 48}},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=forks,
            title={"text": "🍴 Forks"},
            number={"font": {"color": "#3b82f6", "size": 48}},
        ),
        row=1,
        col=2,
    )
    fig.update_layout(
        height=200,
        margin=dict(t=40, b=20, l=20, r=20),
        paper_bgcolor="white",
    )
    return _fig_to_json(fig)


# ---------------------------------------------------------------------------
# 5. Similar Repos — Scatter (stars vs forks, labelled)
# ---------------------------------------------------------------------------

def similar_repos_scatter(similar_repos: list[dict[str, Any]]) -> dict:
    """
    Scatter plot of similar repos with stars on X and forks on Y,
    sized by stars, labelled by repo name.
    """
    if not similar_repos:
        return {}

    names = [r.get("full_name", r.get("name", "")) for r in similar_repos]
    stars = [r.get("stars", 0) for r in similar_repos]
    forks = [r.get("forks", 0) for r in similar_repos]
    langs = [r.get("language", "Unknown") for r in similar_repos]

    fig = px.scatter(
        x=stars,
        y=forks,
        text=names,
        color=langs,
        size=[max(s, 1) for s in stars],
        size_max=40,
        labels={"x": "Stars", "y": "Forks", "color": "Language"},
        title="Similar Repositories (Stars vs Forks)",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(
        height=420,
        margin=dict(t=60, b=50, l=60, r=20),
        plot_bgcolor="#f9fafb",
        paper_bgcolor="white",
    )
    return _fig_to_json(fig)


# ---------------------------------------------------------------------------
# Master builder — returns all graphs in one call
# ---------------------------------------------------------------------------

def build_all_graphs(scan_result: dict[str, Any]) -> dict[str, dict]:
    """
    Given a full scan_result dict (from the agent), build and return
    all Plotly figures as a dict of {chart_name: plotly_json}.
    """
    repo = scan_result.get("repo", {})
    return {
        "language_pie": language_pie(scan_result.get("language_breakdown", {})),
        "commit_activity": commit_activity_bar(
            scan_result.get("activity_raw", scan_result.get("commit_activity", []))
        ),
        "contributors": contributors_bar(scan_result.get("top_contributors", [])),
        "stars_forks": stars_forks_gauge(
            repo.get("stars", 0), repo.get("forks", 0)
        ),
        "similar_scatter": similar_repos_scatter(scan_result.get("similar_repos", [])),
    }
