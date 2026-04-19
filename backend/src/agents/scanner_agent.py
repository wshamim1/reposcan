"""LangChain ReAct agent that orchestrates all repo-scanning tools."""

from __future__ import annotations

import os
import logging
import sys
import threading
import re
from typing import Any

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from backend.src.tools.github_tools import (
  ALL_GITHUB_TOOLS,
  get_commit_activity,
  get_contributors,
  get_directory_tree,
  get_language_breakdown,
    get_readme,
  get_releases,
  get_repo_info,
  get_dependencies,
  get_cicd_info,
)
from backend.src.tools.similarity_tools import ALL_SIMILARITY_TOOLS, find_similar_repos

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr),
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt / ReAct template
# ---------------------------------------------------------------------------

_REACT_TEMPLATE = """You are RepoScan, an expert GitHub repository analyst.

Your job is to thoroughly analyze a GitHub repository and produce a structured JSON summary.

You have access to the following tools:
{tools}

Use EXACTLY this format for EVERY step:

Thought: [your reasoning]
Action: [tool name from: {tool_names}]
Action Input: [the input to pass to the tool]
Observation: [the tool result — filled in automatically]
... (repeat Thought/Action/Observation as needed)
Thought: I now have all the information needed.
Final Answer: [your complete JSON summary]

---

Analysis steps to follow IN ORDER:
1. Call get_repo_info to get metadata.
2. Call get_readme to understand what the project does.
3. Call get_language_breakdown to see language composition.
4. Call get_contributors to find key contributors.
5. Call get_commit_activity to examine activity trends.
6. Call get_directory_tree to understand project structure.
7. Call get_releases to check recent releases.
8. Call find_similar_repos to discover related projects.
9. Synthesise EVERYTHING into a Final Answer JSON with this exact schema:

{{
  "repo": {{
    "full_name": "...",
    "description": "...",
    "stars": 0,
    "forks": 0,
    "open_issues": 0,
    "watchers": 0,
    "language": "...",
    "license": "...",
    "topics": [],
    "created_at": "...",
    "updated_at": "...",
    "html_url": "..."
  }},
  "summary": "2-3 sentence plain English summary of what this repo is and what it does.",
  "purpose": "One sentence — the core purpose of the project.",
    "getting_started": ["step-by-step setup commands from README"],
  "tech_stack": ["list", "of", "technologies"],
  "key_features": ["bullet", "point", "features", "extracted", "from", "readme"],
  "activity": {{
    "commit_trend": "growing | stable | declining | new",
    "total_commits_last_year": 0
  }},
  "top_contributors": [
    {{"login": "...", "contributions": 0, "profile_url": "..."}}
  ],
  "language_breakdown": {{}},
  "directory_tree": [],
  "recent_releases": [],
  "similar_repos": [
    {{
      "full_name": "...",
      "description": "...",
      "stars": 0,
      "language": "...",
      "html_url": "..."
    }}
  ]
}}

Begin!

Repository to analyze: {input}
{agent_scratchpad}"""

_PROMPT = PromptTemplate.from_template(_REACT_TEMPLATE)

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

ALL_TOOLS = ALL_GITHUB_TOOLS + ALL_SIMILARITY_TOOLS

_NOISY_TECH_TOKENS = {
    "url",
    "urls",
    "http",
    "https",
    "text",
    "plain text",
    "markdown",
    "md",
    "unknown",
    "none",
    "n/a",
}


def _clean_text_fragment(text: str) -> str:
    """Normalize README/description snippets into readable plain text."""
    if not text:
        return ""

    cleaned = text
    # Remove HTML tags.
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Replace markdown links/images with their human text.
    cleaned = re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", cleaned)
    # Remove inline code markers/backticks.
    cleaned = cleaned.replace("`", "")
    # Remove markdown emphasis markers.
    cleaned = re.sub(r"[*_]{1,3}", "", cleaned)
    # Collapse whitespace.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    # Remove common sentence-fragment tails.
    cleaned = cleaned.rstrip(":;,- ")
    return cleaned


def _normalize_tech_stack(raw_stack: list[str]) -> list[str]:
    """Drop noisy pseudo-technologies and keep unique readable labels."""
    cleaned: list[str] = []
    seen: set[str] = set()

    for item in raw_stack or []:
        value = _clean_text_fragment(str(item))
        if not value:
            continue
        lowered = value.lower()
        if lowered in _NOISY_TECH_TOKENS:
            continue
        if lowered.startswith("http"):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value)

    return cleaned[:8]


def _first_sentence(text: str) -> str:
    cleaned = _clean_text_fragment(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return parts[0].strip()


def _normalize_intro_text(text: str) -> str:
    """Remove awkward trailing fragments such as 'It includes.' from README intros."""
    cleaned = _clean_text_fragment(text)
    if not cleaned:
        return ""

    cleaned = re.sub(
        r"\b(?:it\s+)?(?:includes|contains|features|provides|offers)\.?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" .,:;-")
    return cleaned


def _strip_repo_self_reference(text: str) -> str:
    """Convert 'This repository is ...' into a neutral phrase for better sentence flow."""
    if not text:
        return ""
    cleaned = text.strip()
    return re.sub(r"^this repository\s+(is|focuses on)\s+", "", cleaned, flags=re.IGNORECASE)


def _extract_readme_intro(readme: str) -> str:
    if not readme or readme.startswith("Error:"):
        return ""
    lines = [ln.strip() for ln in readme.splitlines()]
    paragraphs: list[str] = []
    current: list[str] = []
    for ln in lines:
        if not ln:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if ln.startswith("#"):
            continue
        if ln.startswith("![") or ln.startswith("<img"):
            continue
        if ln.startswith("[!"):
            continue
        if "shields.io" in ln.lower() or "img.shields.io" in ln.lower():
            continue

        cleaned = _clean_text_fragment(ln)
        if not cleaned:
            continue

        current.append(cleaned)
        if len(" ".join(current)) > 280:
            paragraphs.append(" ".join(current).strip())
            break
    if current and not paragraphs:
        paragraphs.append(" ".join(current).strip())
    intro = paragraphs[0][:320] if paragraphs else ""
    return _normalize_intro_text(intro)


def _extract_getting_started(readme: str) -> list[str]:
    if not readme or readme.startswith("Error:"):
        return []

    lines = readme.splitlines()
    heading_re = re.compile(r"^#{1,3}\s*(getting started|quick start|installation|setup|usage)\b", re.IGNORECASE)
    next_heading_re = re.compile(r"^#{1,3}\s+")
    cmd_re = re.compile(
        r"^\s*(git\s+clone|cd\s+|python\s+|python3\s+|pip\s+|pip3\s+|npm\s+(install|i|run)\s+|yarn\s+|pnpm\s+|poetry\s+|uv\s+|uvicorn\s+|docker\s+|make\s+|source\s+)",
        re.IGNORECASE,
    )

    start = -1
    for idx, ln in enumerate(lines):
        if heading_re.match(ln.strip()):
            start = idx + 1
            break

    if start == -1:
        # No explicit section: pull first few command-like lines from whole README.
        steps = []
        for ln in lines:
            clean = ln.strip().lstrip("-*")
            if cmd_re.match(clean):
                steps.append(clean)
            if len(steps) >= 5:
                break
        return steps

    steps: list[str] = []
    in_code_block = False
    for ln in lines[start:]:
        stripped = ln.strip()
        if next_heading_re.match(stripped):
            break
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not stripped:
            continue

        candidate = stripped.lstrip("-*").strip()
        if in_code_block and cmd_re.match(candidate):
            steps.append(candidate)
        elif re.match(r"^\d+[\.)]\s+", candidate):
            step_text = re.sub(r"^\d+[\.)]\s+", "", candidate)
            if cmd_re.match(step_text):
                steps.append(step_text)
        elif cmd_re.match(candidate):
            steps.append(candidate)

        if len(steps) >= 6:
            break

    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for s in steps:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped[:6]


def _generate_getting_started_fallback(
    repo: dict[str, Any],
    tech_stack: list[str],
    dependencies: dict[str, Any] | None,
    cicd: dict[str, Any] | None,
) -> list[str]:
    """Generate practical setup commands when README lacks explicit install/run steps."""
    repo_url = (repo.get("html_url") or "<repository-url>").strip()
    repo_name = (repo.get("name") or repo.get("full_name") or "repo").split("/")[-1]

    dep_files = set((dependencies or {}).get("files", {}).keys())
    stack_lower = [str(x).lower() for x in (tech_stack or [])]
    cicd_tools = set((cicd or {}).get("tools", []))

    has_python = bool(
        {"requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.cfg", "Pipfile"} & dep_files
        or "python" in stack_lower
    )
    has_node = bool(
        {"package.json", "yarn.lock", "pnpm-lock.yaml"} & dep_files
        or any(x in stack_lower for x in ["javascript", "typescript"])
    )
    has_go = bool("go.mod" in dep_files or "go" in stack_lower)
    has_rust = bool("Cargo.toml" in dep_files or "rust" in stack_lower)
    has_docker = bool("Docker" in cicd_tools or "Docker Compose" in cicd_tools)

    steps: list[str] = [
        f"git clone {repo_url}",
        f"cd {repo_name}",
    ]

    if has_python:
        steps.extend(
            [
                "python3 -m venv .venv",
                "source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate",
            ]
        )
        if "requirements.txt" in dep_files:
            steps.append("pip install -r requirements.txt")
        elif "requirements-dev.txt" in dep_files:
            steps.append("pip install -r requirements-dev.txt")
        elif "pyproject.toml" in dep_files:
            steps.append("pip install -e .")
        elif "Pipfile" in dep_files:
            steps.append("pipenv install")
        else:
            steps.append("pip install -r requirements.txt  # if available")

    if has_node:
        if "pnpm-lock.yaml" in dep_files:
            steps.append("pnpm install")
            steps.append("pnpm run dev")
        elif "yarn.lock" in dep_files:
            steps.append("yarn install")
            steps.append("yarn dev")
        else:
            steps.append("npm install")
            steps.append("npm run dev")

    if has_go:
        steps.extend(["go mod download", "go run ./..."])

    if has_rust:
        steps.extend(["cargo build", "cargo run"])

    if has_docker:
        steps.append("docker compose up --build  # if docker-compose.yml is present")

    if len(steps) <= 2:
        steps.extend(
            [
                "# Install dependencies based on project files (requirements.txt, package.json, etc.)",
                "# Run the project entrypoint described in README",
            ]
        )

    # Deduplicate while preserving order and keep it concise.
    deduped: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if step not in seen:
            seen.add(step)
            deduped.append(step)
    return deduped[:10]


def _compose_fallback_summary(
    repo: dict[str, Any],
    readme_intro: str,
    tech_stack: list[str],
    getting_started: list[str],
) -> str:
    name = repo.get("full_name") or repo.get("name") or "This repository"
    description = _clean_text_fragment((repo.get("description") or "").strip())
    readme_intro = _normalize_intro_text(readme_intro)
    tech_stack = _normalize_tech_stack(tech_stack)

    parts: list[str] = []
    used_intro_as_lead = False

    if description:
        parts.append(f"{name} is {description.rstrip('.')}.")
    elif readme_intro:
        intro_body = _strip_repo_self_reference(readme_intro).rstrip(".")
        if intro_body:
            parts.append(f"{name} is {intro_body}.")
            used_intro_as_lead = True
        else:
            parts.append(f"{name} provides project assets and implementation code for its domain use case.")
    else:
        parts.append(f"{name} provides project assets and implementation code for its domain use case.")

    if tech_stack:
        top_stack = ", ".join(tech_stack[:4])
        parts.append(f"The primary technologies appear to be {top_stack}.")

    desc_l = description.lower()
    intro_l = readme_intro.lower()
    is_duplicate = bool(desc_l and intro_l and (intro_l in desc_l or desc_l in intro_l))
    if readme_intro and not used_intro_as_lead and not is_duplicate:
        parts.append(f"At a high level, {readme_intro.rstrip('.')}." )

    if getting_started:
        parts.append(
            f"To get started, follow the repository setup steps (about {len(getting_started)} key commands/steps extracted from README)."
        )
    else:
        parts.append("To get started, review the README for installation and usage instructions.")

    # Keep summary concise but meaningful (2-4 sentences).
    return " ".join(parts[:4])


def _compute_health_score_and_risks(
    repo: dict[str, Any],
    commit_activity: list[dict[str, Any]],
    recent_releases: list[dict[str, Any]],
    top_contributors: list[dict[str, Any]],
    readme_text: str,
) -> tuple[dict[str, Any], list[str]]:
    score = 50
    risks: list[str] = []

    stars = int(repo.get("stars", 0) or 0)
    forks = int(repo.get("forks", 0) or 0)
    watchers = int(repo.get("watchers", 0) or 0)
    open_issues = int(repo.get("open_issues", 0) or 0)
    license_name = str(repo.get("license", "") or "").strip().lower()

    commits_total = sum(
        item.get("commits", 0)
        for item in commit_activity
        if isinstance(item, dict)
    )

    # Community/adoption indicators.
    if stars >= 500:
        score += 10
    elif stars >= 50:
        score += 6
    elif stars == 0:
        score -= 4

    if forks >= 20:
        score += 5
    if watchers >= 10:
        score += 2

    # Activity indicators.
    if commits_total >= 200:
        score += 10
    elif commits_total >= 50:
        score += 6
    elif commits_total == 0:
        score -= 12
        risks.append("No commit activity detected in the last year.")
    else:
        score -= 4

    # Release hygiene.
    if recent_releases:
        score += 8
    else:
        score -= 6
        risks.append("No releases found; versioning and upgrade stability are unclear.")

    # Contributor distribution.
    if len(top_contributors) >= 5:
        score += 6
    elif len(top_contributors) >= 2:
        score += 3
    else:
        score -= 5
        risks.append("Low contributor diversity (potential bus-factor risk).")

    # Documentation and setup signals.
    has_readme = bool(readme_text and not readme_text.startswith("Error:"))
    if has_readme:
        score += 5
    else:
        score -= 10
        risks.append("README content missing or unavailable.")

    # License clarity.
    if license_name and license_name != "none":
        score += 4
    else:
        score -= 8
        risks.append("No license detected; legal usage terms may be unclear.")

    # Issue load (rough heuristic for small/medium projects).
    if open_issues >= 100:
        score -= 8
        risks.append("High open issue count may indicate maintenance backlog.")
    elif open_issues >= 25:
        score -= 3

    score = max(0, min(100, score))
    if score >= 80:
        grade = "A"
        status = "Healthy"
    elif score >= 65:
        grade = "B"
        status = "Good"
    elif score >= 50:
        grade = "C"
        status = "Moderate"
    elif score >= 35:
        grade = "D"
        status = "Risky"
    else:
        grade = "F"
        status = "High Risk"

    health = {
        "score": score,
        "grade": grade,
        "status": status,
        "signals": {
            "stars": stars,
            "forks": forks,
            "commits_last_year": commits_total,
            "open_issues": open_issues,
            "has_releases": bool(recent_releases),
            "contributor_count": len(top_contributors),
            "has_license": bool(license_name and license_name != "none"),
            "has_readme": has_readme,
        },
    }
    return health, risks


def _compute_use_case_match(
    use_case: str | None,
    repo: dict[str, Any],
    summary: str,
    readme_text: str,
    tech_stack: list[str],
) -> dict[str, Any] | None:
    intent_catalog: dict[str, dict[str, Any]] = {
        "RAG": {
            "weight": 1.0,
            "keywords": ["rag", "retrieval", "embedding", "vector", "milvus", "faiss", "qdrant", "pinecone", "langchain"],
        },
        "MLOps": {
            "weight": 0.95,
            "keywords": ["mlops", "model", "pipeline", "training", "experiment", "airflow", "kubeflow", "mlflow", "monitoring"],
        },
        "API Backend": {
            "weight": 0.9,
            "keywords": ["api", "rest", "fastapi", "flask", "django", "express", "backend", "endpoint", "service"],
        },
        "Data Engineering": {
            "weight": 0.85,
            "keywords": ["etl", "data", "warehouse", "spark", "stream", "batch", "ingestion", "analytics"],
        },
        "DevOps": {
            "weight": 0.8,
            "keywords": ["docker", "kubernetes", "helm", "ci", "cd", "terraform", "ansible", "deploy", "infra"],
        },
        "Frontend": {
            "weight": 0.75,
            "keywords": ["frontend", "react", "vue", "next", "ui", "vite", "component", "tailwind"],
        },
    }

    if not use_case or not use_case.strip():
        return None

    keywords = [t for t in re.findall(r"[a-zA-Z0-9]+", use_case.lower()) if len(t) >= 3]
    if not keywords:
        return {
            "query": use_case,
            "score": 0,
            "fit": "Low",
            "matched_keywords": [],
            "explanation": "Use-case text is too short to evaluate meaningful keyword overlap.",
        }

    haystack_parts = [
        (repo.get("name") or ""),
        (repo.get("full_name") or ""),
        (repo.get("description") or ""),
        summary or "",
        " ".join(repo.get("topics", []) or []),
        " ".join(tech_stack or []),
        (readme_text or "")[:5000],
    ]
    haystack = "\n".join(haystack_parts).lower()

    matched = [kw for kw in keywords if kw in haystack]
    coverage = len(matched) / max(1, len(keywords))

    # Intent-aware matching: detect requested intent categories and score repo evidence.
    requested_intents: list[str] = []
    for intent, spec in intent_catalog.items():
        intent_kw = spec["keywords"]
        if any(kw in use_case.lower() for kw in intent_kw):
            requested_intents.append(intent)

    repo_intent_scores: dict[str, int] = {}
    for intent, spec in intent_catalog.items():
        intent_kw = spec["keywords"]
        hit_count = sum(1 for kw in intent_kw if kw in haystack)
        ratio = hit_count / max(1, len(intent_kw))
        weighted_score = int(round(ratio * 100 * float(spec["weight"])))
        repo_intent_scores[intent] = max(0, min(100, weighted_score))

    if requested_intents:
        intent_score = int(
            round(
                sum(repo_intent_scores[i] for i in requested_intents)
                / max(1, len(requested_intents))
            )
        )
    else:
        top_two = sorted(repo_intent_scores.values(), reverse=True)[:2]
        intent_score = int(round(sum(top_two) / max(1, len(top_two)))) if top_two else 0

    # Blend keyword overlap and weighted intent confidence.
    score = int(round((coverage * 100 * 0.45) + (intent_score * 0.55)))
    if score >= 75:
        fit = "High"
    elif score >= 45:
        fit = "Medium"
    else:
        fit = "Low"

    top_intents = sorted(repo_intent_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_intents_payload = [{"intent": name, "score": val} for name, val in top_intents if val > 0]

    if matched:
        explanation = (
            f"Matched {len(matched)} of {len(keywords)} use-case keywords in repository metadata/README: "
            + ", ".join(matched[:8])
        )
    else:
        explanation = "No strong keyword overlap found between the requested use case and repository metadata/README."

    if requested_intents:
        explanation += (
            f" Requested intent categories: {', '.join(requested_intents)}."
            f" Intent confidence score: {intent_score}/100."
        )
    elif top_intents_payload:
        explanation += (
            " Top inferred intent categories: "
            + ", ".join(f"{i['intent']} ({i['score']})" for i in top_intents_payload)
            + "."
        )

    return {
        "query": use_case,
        "score": score,
        "fit": fit,
        "matched_keywords": matched,
        "requested_intents": requested_intents,
        "top_intents": top_intents_payload,
        "intent_score": intent_score,
        "explanation": explanation,
    }


def _build_similar_repo_clusters(similar_repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not similar_repos:
        return []

    theme_keywords: dict[str, list[str]] = {
        "Vector DB": ["milvus", "qdrant", "faiss", "vector", "embedding", "pinecone"],
        "LLM / AI": ["llm", "ai", "langchain", "transformer", "prompt", "rag"],
        "API / Backend": ["api", "backend", "fastapi", "flask", "express", "service"],
        "Data Engineering": ["etl", "pipeline", "warehouse", "spark", "stream", "analytics"],
        "DevOps / Infra": ["docker", "kubernetes", "helm", "terraform", "deployment"],
    }

    buckets: dict[str, list[dict[str, Any]]] = {}

    def pick_theme(repo_item: dict[str, Any]) -> str:
        text = " ".join([
            (repo_item.get("full_name") or "").lower(),
            (repo_item.get("description") or "").lower(),
            " ".join((repo_item.get("topics") or [])).lower(),
        ])
        best_theme = "General"
        best_hits = 0
        for theme, kws in theme_keywords.items():
            hits = sum(1 for kw in kws if kw in text)
            if hits > best_hits:
                best_hits = hits
                best_theme = theme
        return best_theme

    for item in similar_repos:
        language = item.get("language") or "Unknown"
        theme = pick_theme(item)
        cluster_name = f"{theme} · {language}"
        buckets.setdefault(cluster_name, []).append(item)

    clusters: list[dict[str, Any]] = []
    for name, repos in buckets.items():
        sorted_repos = sorted(repos, key=lambda x: x.get("stars", 0), reverse=True)
        clusters.append(
            {
                "name": name,
                "count": len(sorted_repos),
                "repos": sorted_repos[:6],
            }
        )

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


def build_agent_executor(verbose: bool = False) -> AgentExecutor:
    """Build and return a configured LangChain ReAct AgentExecutor."""
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    logger.info(f"build_agent_executor: Building executor with model={model}")
    
    try:
        llm = ChatOpenAI(model=model, temperature=0, timeout=120, request_timeout=120)
        logger.debug(f"build_agent_executor: ChatOpenAI initialized")

        agent = create_react_agent(llm=llm, tools=ALL_TOOLS, prompt=_PROMPT)
        logger.debug(f"build_agent_executor: React agent created with {len(ALL_TOOLS)} tools")

        executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=verbose,
            max_iterations=10,  # Reduced from 15 to avoid long hangs
            handle_parsing_errors=True,
            return_intermediate_steps=False,
        )
        logger.info(f"build_agent_executor: AgentExecutor created successfully")
        return executor
    except Exception as e:
        logger.error(f"build_agent_executor: Failed to build agent executor: {e}", exc_info=True)
        raise


def _fallback_scan_from_tools(
    github_url: str,
    raw_output: str = "",
    use_case: str | None = None,
) -> dict[str, Any]:
    """Build a reliable scan result directly from GitHub tools (no LLM parsing)."""
    logger.info(f"_fallback_scan_from_tools: Building fallback scan for {github_url}")
    
    import threading
    
    def safely_invoke_tool(tool_fn, url, tool_name, timeout=15):
        """Invoke a tool with timeout and error handling."""
        result_container = {"result": None, "error": None}
        
        def run_tool():
            try:
                logger.debug(f"_fallback_scan_from_tools: Calling {tool_name}...")
                result_container["result"] = tool_fn.invoke(url)
            except Exception as e:
                logger.warning(f"_fallback_scan_from_tools: {tool_name} failed: {e}")
                result_container["error"] = e
        
        thread = threading.Thread(target=run_tool, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            logger.warning(f"_fallback_scan_from_tools: {tool_name} timed out after {timeout}s")
            return None
        
        if result_container["error"]:
            return None
        
        return result_container["result"]
    
    try:
        logger.debug(f"_fallback_scan_from_tools: Fetching repo info...")
        repo = safely_invoke_tool(get_repo_info, github_url, "get_repo_info", timeout=10)
        if not isinstance(repo, dict):
            repo = {}

        logger.debug(f"_fallback_scan_from_tools: Fetching language breakdown...")
        language_breakdown = safely_invoke_tool(get_language_breakdown, github_url, "get_language_breakdown", timeout=10)
        if not isinstance(language_breakdown, dict):
            language_breakdown = {}

        logger.debug(f"_fallback_scan_from_tools: Fetching contributors...")
        contributors = safely_invoke_tool(get_contributors, github_url, "get_contributors", timeout=10)
        if not isinstance(contributors, list):
            contributors = []

        logger.debug(f"_fallback_scan_from_tools: Fetching commit activity...")
        commit_activity = safely_invoke_tool(get_commit_activity, github_url, "get_commit_activity", timeout=10)
        if not isinstance(commit_activity, list):
            commit_activity = []

        logger.debug(f"_fallback_scan_from_tools: Fetching directory tree...")
        directory_tree = safely_invoke_tool(get_directory_tree, github_url, "get_directory_tree", timeout=10)
        if not isinstance(directory_tree, list):
            directory_tree = []

        logger.debug(f"_fallback_scan_from_tools: Fetching releases...")
        recent_releases = safely_invoke_tool(get_releases, github_url, "get_releases", timeout=10)
        if not isinstance(recent_releases, list):
            recent_releases = []

        logger.debug(f"_fallback_scan_from_tools: Fetching readme...")
        readme_text = safely_invoke_tool(get_readme, github_url, "get_readme", timeout=10)
        if not isinstance(readme_text, str):
            readme_text = ""

        logger.debug(f"_fallback_scan_from_tools: Finding similar repos...")
        similar_repos = safely_invoke_tool(find_similar_repos, github_url, "find_similar_repos", timeout=10)
        if not isinstance(similar_repos, list):
            similar_repos = []

        logger.debug(f"_fallback_scan_from_tools: Fetching dependencies...")
        dependencies_raw = safely_invoke_tool(get_dependencies, github_url, "get_dependencies", timeout=12)
        dependencies = dependencies_raw if isinstance(dependencies_raw, dict) and "files" in dependencies_raw else {"files": {}}

        logger.debug(f"_fallback_scan_from_tools: Fetching CI/CD info...")
        cicd_raw = safely_invoke_tool(get_cicd_info, github_url, "get_cicd_info", timeout=12)
        cicd = cicd_raw if isinstance(cicd_raw, dict) and "tools" in cicd_raw else {"tools": [], "workflows": [], "has_ci": False}

        commits_total = sum(item.get("commits", 0) for item in commit_activity if isinstance(item, dict))
        activity = {
            "commit_trend": "unknown",
            "total_commits_last_year": commits_total,
        }

        description = repo.get("description", "") if isinstance(repo, dict) else ""
        readme_intro = _extract_readme_intro(readme_text)
        getting_started = _extract_getting_started(readme_text)
        getting_started_source = "readme"
        if not getting_started:
            getting_started = _generate_getting_started_fallback(
                repo=repo if isinstance(repo, dict) else {},
                tech_stack=list(language_breakdown.keys())[:8] if isinstance(language_breakdown, dict) else [],
                dependencies=dependencies,
                cicd=cicd,
            )
            if getting_started:
                getting_started_source = "generated"
        normalized_stack = _normalize_tech_stack(
            list(language_breakdown.keys()) if isinstance(language_breakdown, dict) else []
        )

        fallback_summary = _compose_fallback_summary(
            repo=repo if isinstance(repo, dict) else {},
            readme_intro=readme_intro,
            tech_stack=normalized_stack,
            getting_started=getting_started,
        )

        purpose_text = _first_sentence(description or readme_intro)

        result = {
            "repo": repo if isinstance(repo, dict) else {},
            "summary": fallback_summary,
            "purpose": (purpose_text or "N/A"),
            "getting_started": getting_started,
            "getting_started_source": getting_started_source,
            "tech_stack": normalized_stack,
            "key_features": [],
            "activity": activity,
            "readme": readme_text,
            "dependencies": dependencies,
            "cicd": cicd,
            "top_contributors": [
                c
                for c in contributors
                if isinstance(c, dict) and "error" not in c
            ],
            "language_breakdown": language_breakdown if isinstance(language_breakdown, dict) and "error" not in language_breakdown else {},
            "directory_tree": [
                t
                for t in directory_tree
                if isinstance(t, dict) and "error" not in t
            ],
            "recent_releases": [
                r
                for r in recent_releases
                if isinstance(r, dict) and "error" not in r
            ],
            "similar_repos": [
                r
                for r in similar_repos
                if isinstance(r, dict) and "error" not in r
            ],
            # Keep raw activity so chart builder can render commit graph consistently.
            "commit_activity": commit_activity,
        }

        health, risks = _compute_health_score_and_risks(
            repo=result["repo"],
            commit_activity=commit_activity,
            recent_releases=result["recent_releases"],
            top_contributors=result["top_contributors"],
            readme_text=readme_text,
        )
        result["health"] = health
        result["risk_flags"] = risks
        result["use_case_match"] = _compute_use_case_match(
            use_case=use_case,
            repo=result["repo"],
            summary=result["summary"],
            readme_text=readme_text,
            tech_stack=result.get("tech_stack", []),
        )
        result["similar_repo_clusters"] = _build_similar_repo_clusters(result.get("similar_repos", []))

        if raw_output:
            result["raw_output"] = raw_output
            result["warning"] = "LLM summary parsing failed; used direct GitHub data fallback."
        
        logger.info(f"_fallback_scan_from_tools: Fallback scan completed successfully")
        return result
    except Exception as e:
        logger.error(f"_fallback_scan_from_tools: Error building fallback: {e}", exc_info=True)
        # Return even more minimal fallback
        return {
            "repo": {"full_name": github_url, "error": str(e)},
            "summary": "Failed to fetch full data",
            "purpose": "N/A",
            "tech_stack": [],
            "key_features": [],
            "activity": {"commit_trend": "unknown", "total_commits_last_year": 0},
            "top_contributors": [],
            "language_breakdown": {},
            "directory_tree": [],
            "recent_releases": [],
            "similar_repos": [],
            "getting_started": [],
            "health": {"score": 0, "grade": "F", "status": "High Risk", "signals": {}},
            "risk_flags": ["Scan failed before health assessment could complete."],
            "use_case_match": None,
            "similar_repo_clusters": [],
        }


def scan_repository(github_url: str, verbose: bool = False, use_case: str | None = None) -> dict[str, Any]:
    """
    Run the full repo scan for the given GitHub URL.
    
    Strategy:
    1. Try fast direct GitHub API calls first (usually works well)
    2. Only use LLM agent if specifically needed
    
    Returns the parsed JSON summary dict.
    """
    import json
    import threading

    logger.info(f"scan_repository: Starting scan for {github_url}")
    
    # Start with fast direct GitHub tools (usually 5-10 seconds)
    logger.info(f"scan_repository: Fetching data directly from GitHub API (fast path)...")
    try:
        fallback_result = _fallback_scan_from_tools(github_url, use_case=use_case)
        logger.info(f"scan_repository: Direct GitHub fetch completed successfully")
        return fallback_result
    except Exception as e:
        logger.warning(f"scan_repository: Direct fetch failed: {e}, attempting LLM agent...")
    
    # Only use agent as fallback if direct API fails
    try:
        token = os.getenv("GITHUB_TOKEN", "")
        if token in ("", "ghp_...", "ghp_"):
            logger.warning(f"scan_repository: No valid GitHub token found")
        
        logger.info(f"scan_repository: Building agent executor...")
        executor = build_agent_executor(verbose=verbose)
        
        # Wrap agent.invoke in a timeout thread
        logger.info(f"scan_repository: Invoking agent with 90-second timeout...")
        result_container = {"result": None, "error": None}
        
        def agent_thread():
            try:
                result_container["result"] = executor.invoke({"input": github_url})
            except Exception as e:
                result_container["error"] = e
        
        thread = threading.Thread(target=agent_thread, daemon=True)
        thread.start()
        thread.join(timeout=90)  # 90-second timeout
        
        if thread.is_alive():
            logger.error(f"scan_repository: Agent timed out after 90 seconds, using fallback")
            return _fallback_scan_from_tools(github_url, use_case=use_case)
        
        if result_container["error"]:
            logger.error(f"scan_repository: Agent error: {result_container['error']}", exc_info=True)
            return _fallback_scan_from_tools(github_url, use_case=use_case)
        
        result = result_container["result"]
        if not result:
            logger.warning(f"scan_repository: Agent returned None, using fallback")
            return _fallback_scan_from_tools(github_url, use_case=use_case)
        
        logger.info(f"scan_repository: Agent returned, response type: {type(result)}")
        raw = result.get("output", "") if isinstance(result, dict) else str(result)
        
        logger.info(f"scan_repository: Raw output length: {len(raw)} chars")
        
        # Check if agent hit rate limits or errors
        if "rate limit" in raw.lower() or "403" in raw or "error" in raw.lower()[:100]:
            logger.warning(f"scan_repository: Agent output contains error/rate limit, using fallback")
            return _fallback_scan_from_tools(github_url, use_case=use_case)
        
        logger.debug(f"scan_repository: Raw output (first 500 chars): {raw[:500]}")

        # The agent should return valid JSON; extract it safely
        try:
            # Strip any markdown code fences the LLM might have added
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.splitlines()
                clean = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            
            logger.debug(f"scan_repository: Attempting JSON parse (cleaned length: {len(clean)})...")
            parsed = json.loads(clean)

            # Guard against partial/malformed agent JSON that omits core repo stats.
            repo = parsed.get("repo", {}) if isinstance(parsed, dict) else {}
            if not isinstance(repo, dict) or repo.get("stars") is None:
                logger.warning(f"scan_repository: Agent returned incomplete repo data, using fallback")
                fallback = _fallback_scan_from_tools(github_url, use_case=use_case)
                if isinstance(parsed, dict):
                    merged = {**fallback, **parsed}
                    merged["repo"] = {**fallback.get("repo", {}), **repo}
                    if use_case and merged.get("use_case_match") is None:
                        merged["use_case_match"] = _compute_use_case_match(
                            use_case=use_case,
                            repo=merged.get("repo", {}),
                            summary=merged.get("summary", ""),
                            readme_text="",
                            tech_stack=merged.get("tech_stack", []),
                        )
                    merged["similar_repo_clusters"] = _build_similar_repo_clusters(
                        merged.get("similar_repos", [])
                    )
                    return merged
                return fallback

            logger.info(f"scan_repository: Successfully parsed agent response with repo: {repo.get('full_name', 'unknown')}")
            if isinstance(parsed, dict):
                parsed["similar_repo_clusters"] = _build_similar_repo_clusters(parsed.get("similar_repos", []))
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"scan_repository: JSON parse failed: {e}, using fallback scan from tools")
            return _fallback_scan_from_tools(github_url, use_case=use_case)
    except Exception as e:
        logger.error(f"scan_repository: Unexpected error: {e}", exc_info=True)
        try:
            logger.info(f"scan_repository: Using direct GitHub API fallback...")
            return _fallback_scan_from_tools(github_url, use_case=use_case)
        except Exception as fallback_err:
            logger.error(f"scan_repository: Even fallback failed: {fallback_err}", exc_info=True)
            # Return a minimal error response
            return {
                "repo": {"full_name": github_url, "error": str(e)},
                "summary": f"Scan failed: {e}",
                "purpose": "N/A",
                "tech_stack": [],
                "key_features": [],
                "activity": {"commit_trend": "unknown", "total_commits_last_year": 0},
                "top_contributors": [],
                "language_breakdown": {},
                "directory_tree": [],
                "recent_releases": [],
                "similar_repos": [],
                "getting_started": [],
                "health": {"score": 0, "grade": "F", "status": "High Risk", "signals": {}},
                "risk_flags": ["Scan failed before health assessment could complete."],
                "use_case_match": None,
                "similar_repo_clusters": [],
                "error": str(e),
            }
