"""
FastAPI backend for RepoScan.

Endpoints:
  POST /api/scan          — Full AI-powered repo scan (LangChain agent)
  GET  /api/scan/{job_id} — Poll scan job status  (async job pattern)
  GET  /api/graphs        — Raw GitHub data + Plotly charts (no LLM)
  GET  /api/similar       — Similar repos only
  GET  /api/health        — Health check
"""

from __future__ import annotations

import os
import uuid
import logging
import sys
import json
import subprocess
import shlex
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from github import Github, GithubException

load_dotenv()

# Configure logging to see debug output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr),
    ]
)
logger = logging.getLogger(__name__)

# In-memory job store (swap for Redis in production)
_JOBS: dict[str, dict[str, Any]] = {}

_CACHE_DIR = Path(os.getenv("OUTPUT_DIR", "./output")) / "cache"
_CACHE_FILE = _CACHE_DIR / "scan_cache.json"
_CACHE_VERSION = 3


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: nothing special needed
    yield
    # shutdown: clear job store
    _JOBS.clear()


app = FastAPI(
    title="RepoScan API",
    description="AI-powered GitHub repository scanner backed by LangChain agents.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the Vite dev server (port 5173) and any production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    github_url: str
    verbose: bool = False
    use_case: str | None = None
    force_refresh: bool = False


class ScriptExecRequest(BaseModel):
    script: str
    timeout_seconds: int = 90
    working_dir: str | None = None


class JobStatus(BaseModel):
    job_id: str
    status: str          # pending | running | done | error
    result: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_scan(
    job_id: str,
    github_url: str,
    verbose: bool,
    use_case: str | None = None,
    force_refresh: bool = False,
) -> None:
    """Run the LangChain agent scan in a background thread."""
    logger.info(f"[{job_id}] Starting scan for {github_url}")
    _JOBS[job_id]["status"] = "running"
    try:
        cache_key = github_url.strip().lower()
        current_updated_at, repo_meta = _get_repo_updated_at(github_url)
        cache = _load_scan_cache()
        cached_entry = cache.get(cache_key)
        cache_reason = "Fresh scan completed."

        if (
            not force_refresh
            and cached_entry
            and current_updated_at
            and cached_entry.get("cache_version") == _CACHE_VERSION
            and cached_entry.get("repo_updated_at") == current_updated_at
            and isinstance(cached_entry.get("result"), dict)
        ):
            cached_result = deepcopy(cached_entry["result"])
            cached_result["cache"] = {
                "hit": True,
                "repo_updated_at": current_updated_at,
                "scanned_at": cached_entry.get("scanned_at"),
                "message": "Reused cached report because repository has no recent updates.",
            }
            logger.info(f"[{job_id}] Cache hit. Reusing previous scan for unchanged repository")
            _JOBS[job_id].update({"status": "done", "result": cached_result})
            return

        if force_refresh:
            logger.info(f"[{job_id}] Force refresh requested; bypassing cache")
            cache_reason = "Fresh scan completed because force refresh was requested."

        if cached_entry and cached_entry.get("cache_version") != _CACHE_VERSION:
            logger.info(
                f"[{job_id}] Cache entry version mismatch "
                f"({cached_entry.get('cache_version')} != {_CACHE_VERSION}); running fresh scan"
            )
            cache_reason = "Fresh scan completed because cached schema was outdated."

        if cached_entry and current_updated_at and cached_entry.get("repo_updated_at") != current_updated_at:
            cache_reason = "Fresh scan completed because repository was updated since last scan."

        if cached_entry and not current_updated_at:
            cache_reason = "Fresh scan completed because repository update timestamp could not be verified."

        logger.info(f"[{job_id}] Importing scanner agent...")
        from backend.src.agents.scanner_agent import scan_repository
        from backend.src.graphs.repo_visualizer import build_all_graphs

        logger.info(f"[{job_id}] Running scan_repository...")
        result = scan_repository(github_url, verbose=verbose, use_case=use_case)
        
        logger.info(f"[{job_id}] Scan completed, building graphs...")
        graphs = build_all_graphs(result)
        final_result = {**result, "graphs": graphs}

        final_result["cache"] = {
            "hit": False,
            "repo_updated_at": current_updated_at,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "message": cache_reason,
        }

        # Ensure repo metadata is present even if scanner returned partial fields.
        if isinstance(repo_meta, dict) and isinstance(final_result.get("repo"), dict):
            final_result["repo"] = {**repo_meta, **final_result["repo"]}

        cache[cache_key] = {
            "cache_version": _CACHE_VERSION,
            "repo_updated_at": current_updated_at,
            "scanned_at": final_result["cache"]["scanned_at"],
            "result": final_result,
        }
        _save_scan_cache(cache)
        
        logger.info(f"[{job_id}] Scan finished successfully")
        _JOBS[job_id].update(
            {
                "status": "done",
                "result": final_result,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[{job_id}] Scan failed with error: {exc}", exc_info=True)
        _JOBS[job_id].update({"status": "error", "error": str(exc)})


def _load_scan_cache() -> dict[str, Any]:
    try:
        if not _CACHE_FILE.exists():
            return {}
        return json.loads(_CACHE_FILE.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to load cache file: {exc}")
        return {}


def _save_scan_cache(cache_data: dict[str, Any]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache_data))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to save cache file: {exc}")


def _get_repo_updated_at(github_url: str) -> tuple[str | None, dict[str, Any] | None]:
    try:
        from backend.src.tools.github_tools import get_repo_info

        repo_info = get_repo_info.invoke(github_url)
        if isinstance(repo_info, dict):
            return repo_info.get("updated_at"), repo_info
        return None, None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to fetch repo updated_at for cache check: {exc}")
        return None, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/scan", response_model=JobStatus, status_code=202)
async def start_scan(payload: ScanRequest, background_tasks: BackgroundTasks) -> JobStatus:
    """
    Kick off an async repo scan. Returns a job_id immediately.
    Poll GET /api/scan/{job_id} to check progress.
    """
    if not payload.github_url.strip():
        raise HTTPException(status_code=400, detail="github_url must not be empty")

    job_id = str(uuid.uuid4())
    logger.info(f"[{job_id}] New scan request for {payload.github_url}")
    _JOBS[job_id] = {"status": "pending", "result": None, "error": None}

    background_tasks.add_task(
        _run_scan,
        job_id,
        payload.github_url.strip(),
        payload.verbose,
        payload.use_case.strip() if payload.use_case else None,
        payload.force_refresh,
    )
    logger.info(f"[{job_id}] Scan queued, returning job_id")
    return JobStatus(job_id=job_id, status="pending")


@app.get("/api/scan/{job_id}", response_model=JobStatus)
async def get_scan_status(job_id: str) -> JobStatus:
    """Poll the status of a previously submitted scan job."""
    job = _JOBS.get(job_id)
    if job is None:
        logger.warning(f"[{job_id}] Job not found")
        raise HTTPException(status_code=404, detail="Job not found")
    status = job.get("status", "unknown")
    logger.debug(f"[{job_id}] Status poll: {status}")
    return JobStatus(job_id=job_id, **job)


@app.get("/api/graphs")
async def get_graphs(github_url: str) -> dict:
    """
    Fetch raw GitHub data and generate Plotly graphs WITHOUT the LLM agent.
    Fast — uses only GitHub API calls, no OpenAI cost.
    """
    from backend.src.tools.github_tools import (
        get_repo_info,
        get_language_breakdown,
        get_contributors,
        get_commit_activity,
    )
    from backend.src.graphs.repo_visualizer import build_all_graphs

    if not github_url.strip():
        raise HTTPException(status_code=400, detail="github_url is required")

    try:
        repo_info = get_repo_info.invoke(github_url)
        lang = get_language_breakdown.invoke(github_url)
        contributors = get_contributors.invoke(github_url)
        activity = get_commit_activity.invoke(github_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    scan_data = {
        "repo": repo_info,
        "language_breakdown": lang,
        "top_contributors": contributors,
        "commit_activity": activity,
        "similar_repos": [],
    }
    graphs = build_all_graphs(scan_data)
    return {"data": scan_data, "graphs": graphs}


@app.get("/api/similar")
async def get_similar(github_url: str) -> dict:
    """Find similar repositories for the given GitHub URL."""
    from backend.src.tools.similarity_tools import find_similar_repos

    if not github_url.strip():
        raise HTTPException(status_code=400, detail="github_url is required")

    try:
        similar = find_similar_repos.invoke(github_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"similar_repos": similar}


@app.get("/api/search-repos")
async def search_repos(keywords: str, limit: int = 8) -> dict:
    """Search public GitHub repositories by keywords."""
    query = (keywords or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="keywords is required")

    safe_limit = max(1, min(limit, 20))
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token) if token else Github()

    try:
        repos = gh.search_repositories(
            query=f"{query} in:name,description,readme",
            sort="stars",
            order="desc",
        )
        results = []
        for repo in repos[:safe_limit]:
            results.append(
                {
                    "full_name": repo.full_name,
                    "description": repo.description or "",
                    "stars": repo.stargazers_count,
                    "language": repo.language or "Unknown",
                    "html_url": repo.html_url,
                }
            )
    except GithubException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"query": query, "results": results}


@app.get("/api/history")
async def get_history() -> dict:
    """Return summary list of all previously scanned repositories from cache."""
    cache = _load_scan_cache()
    history = []
    for url, entry in cache.items():
        result = entry.get("result", {})
        repo = result.get("repo", {})
        history.append({
            "github_url": url,
            "full_name": repo.get("full_name", url),
            "description": repo.get("description", ""),
            "language": repo.get("language", ""),
            "stars": repo.get("stars", 0),
            "scanned_at": entry.get("scanned_at", ""),
            "health_grade": result.get("health", {}).get("grade", "?"),
            "health_score": result.get("health", {}).get("score", 0),
        })
    # Most recently scanned first
    history.sort(key=lambda x: x.get("scanned_at", ""), reverse=True)
    return {"history": history}


@app.delete("/api/history")
async def delete_history(github_url: str | None = None) -> dict:
    """Delete one cached history entry by URL, or clear all history when URL is omitted."""
    cache = _load_scan_cache()

    if github_url is None:
        _save_scan_cache({})
        return {"deleted": "all", "remaining": 0}

    key = github_url.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="github_url must not be empty")

    if key not in cache:
        raise HTTPException(status_code=404, detail="History entry not found")

    del cache[key]
    _save_scan_cache(cache)
    return {"deleted": key, "remaining": len(cache)}


@app.post("/api/execute-script")
async def execute_script(payload: ScriptExecRequest) -> dict:
    """Execute a setup script from UI with a conservative command allowlist."""
    script = (payload.script or "").strip()
    if not script:
        raise HTTPException(status_code=400, detail="script must not be empty")

    allowed_commands = {
        "git",
        "cd",
        "python",
        "python3",
        "pip",
        "pip3",
        "npm",
        "yarn",
        "pnpm",
        "poetry",
        "uv",
        "uvicorn",
        "make",
        "source",
        "echo",
        "export",
        "mkdir",
        "ls",
    }

    unsafe_tokens = {
        "rm -rf",
        "sudo",
        "shutdown",
        "reboot",
        ":(){",
        "mkfs",
        "dd if=",
        "chmod -R 777",
    }

    lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
    for line in lines:
        if line.startswith("#") or line in {"set -e", "set -eux", "set -o errexit"}:
            continue
        lowered = line.lower()
        if any(tok in lowered for tok in unsafe_tokens):
            raise HTTPException(status_code=400, detail=f"Blocked unsafe command: {line}")

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid shell syntax: {line}") from exc

        if not parts:
            continue
        cmd = parts[0]
        if cmd not in allowed_commands:
            raise HTTPException(
                status_code=400,
                detail=f"Command '{cmd}' is not allowed from UI execution",
            )

    timeout_seconds = max(5, min(payload.timeout_seconds, 240))
    cwd = payload.working_dir or os.getcwd()

    try:
        completed = subprocess.run(
            ["bash", "-lc", script],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "working_dir": cwd,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": (exc.stdout or "")[-12000:],
            "stderr": ((exc.stderr or "") + "\nTimed out while executing script")[-12000:],
            "working_dir": cwd,
        }
