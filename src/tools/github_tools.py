"""LangChain tools for fetching GitHub repository data."""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any

from github import Github, GithubException
from langchain_core.tools import tool

from src.utils.helpers import parse_github_url

logger = logging.getLogger(__name__)


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    client = Github(token) if token else Github()
    
    # Check rate limit early
    try:
        rate_limit = client.get_user().get_repos().totalCount
        logger.debug(f"GitHub client initialized (token: {bool(token)})")
    except GithubException as e:
        if "rate limit" in str(e).lower() or e.status == 403:
            logger.warning(f"GitHub rate limit exceeded: {e}")
        else:
            logger.debug(f"GitHub client check: {e}")
    
    return client


def _get_repo(owner: str, repo_name: str):
    """Fetch a repo with token auth, retrying anonymously if token is invalid."""
    token = os.getenv("GITHUB_TOKEN")
    repo_full_name = f"{owner}/{repo_name}"

    # Try token first for higher rate limits; transparently fallback on bad token.
    if token and token != "ghp_...":  # Check if token is actually set
        try:
            return Github(token).get_repo(repo_full_name)
        except GithubException as exc:
            if "rate limit" in str(exc).lower():
                logger.warning(f"Rate limit hit with token, falling back to unauthenticated")
            elif getattr(exc, "status", None) != 401:
                logger.warning(f"Exception with token (status {getattr(exc, 'status', '?')}): {exc}")
                raise

    return Github().get_repo(repo_full_name)


# ---------------------------------------------------------------------------
# Tool 1: Basic repo info
# ---------------------------------------------------------------------------

@tool
def get_repo_info(github_url: str) -> dict[str, Any]:
    """
    Fetch basic metadata for a GitHub repository.

    Returns owner, name, description, stars, forks, open issues,
    primary language, license, topics, created_at, updated_at, and
    the repository homepage URL.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
    except GithubException as exc:
        return {"error": str(exc)}

    license_name = repo.license.name if repo.license else "None"
    return {
        "owner": owner,
        "name": repo.name,
        "full_name": repo.full_name,
        "description": repo.description or "",
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
        "open_issues": repo.open_issues_count,
        "watchers": repo.watchers_count,
        "language": repo.language or "Unknown",
        "license": license_name,
        "topics": repo.get_topics(),
        "created_at": repo.created_at.isoformat(),
        "updated_at": repo.updated_at.isoformat(),
        "homepage": repo.homepage or "",
        "html_url": repo.html_url,
        "default_branch": repo.default_branch,
    }


# ---------------------------------------------------------------------------
# Tool 2: Languages breakdown
# ---------------------------------------------------------------------------

@tool
def get_language_breakdown(github_url: str) -> dict[str, int]:
    """
    Return a dictionary of programming languages and their byte counts
    for the given GitHub repository URL.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        return dict(repo.get_languages())
    except GithubException as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool 3: Top contributors
# ---------------------------------------------------------------------------

@tool
def get_contributors(github_url: str) -> list[dict[str, Any]]:
    """
    Return the top-10 contributors for a GitHub repository with their
    login, avatar URL, and total contribution count.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        contributors = []
        for c in repo.get_contributors()[:10]:
            contributors.append(
                {
                    "login": c.login,
                    "avatar_url": c.avatar_url,
                    "contributions": c.contributions,
                    "profile_url": c.html_url,
                }
            )
        return contributors
    except GithubException as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Tool 4: Commit activity (last 52 weeks)
# ---------------------------------------------------------------------------

@tool
def get_commit_activity(github_url: str) -> list[dict[str, Any]]:
    """
    Return weekly commit counts for the past 52 weeks for the given
    GitHub repository URL. Each item has 'week' (ISO date) and 'commits'.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        stats = repo.get_stats_commit_activity()
        if not stats:
            return []
        result = []
        for week in stats:
            dt = datetime.fromtimestamp(week.week, tz=timezone.utc)
            result.append({"week": dt.strftime("%Y-%m-%d"), "commits": week.total})
        return result
    except GithubException as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Tool 5: Directory / file tree (top-level)
# ---------------------------------------------------------------------------

@tool
def get_directory_tree(github_url: str) -> list[dict[str, str]]:
    """
    Return the top-level file and directory structure of a GitHub repository.
    Each item has 'type' (file|dir), 'name', and 'path'.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        contents = repo.get_contents("")
        tree = []
        for item in contents:
            tree.append(
                {"type": item.type, "name": item.name, "path": item.path}
            )
        return sorted(tree, key=lambda x: (x["type"] != "dir", x["name"]))
    except GithubException as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Tool 6: README content
# ---------------------------------------------------------------------------

@tool
def get_readme(github_url: str) -> str:
    """
    Fetch the README content of a GitHub repository as plain text.
    Returns the raw markdown string, truncated to 4000 chars if too large.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        readme = repo.get_readme()
        content = readme.decoded_content.decode("utf-8", errors="replace")
        return content[:4000] + ("\n\n[…truncated]" if len(content) > 4000 else "")
    except GithubException as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 7: Recent releases
# ---------------------------------------------------------------------------

@tool
def get_releases(github_url: str) -> list[dict[str, Any]]:
    """
    Return the 5 most recent releases of a GitHub repository with tag,
    name, published date, and release notes excerpt.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
        releases = []
        for r in repo.get_releases()[:5]:
            body = (r.body or "")[:300]
            releases.append(
                {
                    "tag": r.tag_name,
                    "name": r.title,
                    "published_at": r.published_at.isoformat() if r.published_at else "",
                    "notes": body,
                }
            )
        return releases
    except GithubException as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Tool 8: Dependency scanner
# ---------------------------------------------------------------------------

_DEP_FILES = [
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.cfg",
    "Pipfile",
    "package.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "Gemfile",
    "Cargo.toml",
    "build.gradle",
    "pom.xml",
]

def _parse_requirements_txt(content: str) -> list[str]:
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifier
        name = re.split(r"[><=!;\[]", line)[0].strip()
        if name:
            deps.append(name)
    return deps[:30]

def _parse_package_json(content: str) -> list[str]:
    try:
        import json
        data = json.loads(content)
        deps = list((data.get("dependencies") or {}).keys())
        dev_deps = list((data.get("devDependencies") or {}).keys())
        return (deps + dev_deps)[:30]
    except Exception:
        return []

def _parse_pyproject_toml(content: str) -> list[str]:
    deps = []
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in ("[tool.poetry.dependencies]", "[project]", "[tool.poetry.dev-dependencies]"):
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
        if in_deps and "=" in stripped and not stripped.startswith("#"):
            name = stripped.split("=")[0].strip().strip('"')
            if name and name != "python":
                deps.append(name)
    return deps[:30]

def _parse_go_mod(content: str) -> list[str]:
    deps = []
    in_require = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "require (":
            in_require = True
            continue
        if stripped == ")" and in_require:
            in_require = False
            continue
        if stripped.startswith("require "):
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append(parts[1].split("/")[-1])
            continue
        if in_require and stripped and not stripped.startswith("//"):
            parts = stripped.split()
            if parts:
                deps.append(parts[0].split("/")[-1])
    return deps[:30]

import re as _re

@tool
def get_dependencies(github_url: str) -> dict[str, Any]:
    """
    Detect and parse dependency files in a GitHub repository.
    Returns a dict with file names found and parsed dependency lists.
    """
    import re
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
    except GithubException as exc:
        return {"error": str(exc), "files": {}}

    found: dict[str, list[str]] = {}
    for dep_file in _DEP_FILES:
        try:
            file_content = repo.get_contents(dep_file)
            text = file_content.decoded_content.decode("utf-8", errors="replace")
            if dep_file in ("requirements.txt", "requirements-dev.txt"):
                found[dep_file] = _parse_requirements_txt(text)
            elif dep_file == "package.json":
                found[dep_file] = _parse_package_json(text)
            elif dep_file == "pyproject.toml":
                found[dep_file] = _parse_pyproject_toml(text)
            elif dep_file == "go.mod":
                found[dep_file] = _parse_go_mod(text)
            elif dep_file == "Pipfile":
                found[dep_file] = _parse_requirements_txt(text)
            else:
                # Generic: just list first 20 non-blank non-comment lines
                lines = [
                    l.strip() for l in text.splitlines()
                    if l.strip() and not l.strip().startswith("#")
                ]
                found[dep_file] = lines[:20]
        except GithubException:
            continue
        except Exception:
            continue

    return {"files": found}


# ---------------------------------------------------------------------------
# Tool 9: CI/CD status detector
# ---------------------------------------------------------------------------

_CICD_SIGNALS = [
    (".github/workflows", "GitHub Actions"),
    (".travis.yml", "Travis CI"),
    ("circle.yml", "CircleCI"),
    (".circleci/config.yml", "CircleCI"),
    ("Jenkinsfile", "Jenkins"),
    (".gitlab-ci.yml", "GitLab CI"),
    ("azure-pipelines.yml", "Azure Pipelines"),
    ("Dockerfile", "Docker"),
    ("docker-compose.yml", "Docker Compose"),
    (".dockerignore", "Docker"),
    ("Makefile", "Make"),
    ("tox.ini", "Tox"),
    (".pre-commit-config.yaml", "Pre-commit"),
    ("sonar-project.properties", "SonarQube"),
    ("codecov.yml", "Codecov"),
    (".github/dependabot.yml", "Dependabot"),
]

@tool
def get_cicd_info(github_url: str) -> dict[str, Any]:
    """
    Detect CI/CD tooling and DevOps artifacts in a GitHub repository.
    Returns detected tools and any GitHub Actions workflow names.
    """
    owner, repo_name = parse_github_url(github_url)
    try:
        repo = _get_repo(owner, repo_name)
    except GithubException as exc:
        return {"error": str(exc), "tools": [], "workflows": []}

    detected_tools: list[str] = []
    workflows: list[str] = []

    for path, tool_name in _CICD_SIGNALS:
        try:
            repo.get_contents(path)
            if tool_name not in detected_tools:
                detected_tools.append(tool_name)
            # If it's the workflows directory, list individual workflow files
            if path == ".github/workflows":
                try:
                    wf_contents = repo.get_contents(".github/workflows")
                    for wf in (wf_contents if isinstance(wf_contents, list) else [wf_contents]):
                        if wf.name.endswith((".yml", ".yaml")):
                            workflows.append(wf.name.replace(".yml", "").replace(".yaml", "").replace("-", " ").replace("_", " ").title())
                except Exception:
                    pass
        except GithubException:
            continue
        except Exception:
            continue

    return {
        "tools": detected_tools,
        "workflows": workflows[:10],
        "has_ci": len(detected_tools) > 0,
    }


# All tools exported as a list for easy agent registration
ALL_GITHUB_TOOLS = [
    get_repo_info,
    get_language_breakdown,
    get_contributors,
    get_commit_activity,
    get_directory_tree,
    get_readme,
    get_releases,
    get_dependencies,
    get_cicd_info,
]
