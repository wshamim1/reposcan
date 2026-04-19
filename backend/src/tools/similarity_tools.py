"""LangChain tool for finding similar GitHub repositories."""

from __future__ import annotations

import os
import re
from typing import Any

from github import Github, GithubException
from langchain_core.tools import tool

from backend.src.utils.helpers import parse_github_url


_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "this", "that", "your", "their",
    "about", "project", "repository", "repo", "tool", "tools", "library", "framework",
    "python", "javascript", "typescript", "java", "golang", "rust", "code", "lab",
    "demo", "example", "examples", "test", "tests", "using", "based",
}


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    return Github(token) if token else Github()


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _extract_keywords(repo_name: str, description: str, topics: list[str]) -> list[str]:
    # Prefer repo-name and topic terms; then enrich with description terms.
    ranked: list[str] = []

    for token in _tokenize(repo_name.replace("-", " ").replace("_", " ")):
        if token not in ranked:
            ranked.append(token)

    for topic in topics:
        for token in _tokenize(topic):
            if token not in ranked:
                ranked.append(token)

    for token in _tokenize(description):
        if token not in ranked:
            ranked.append(token)

    return ranked[:8]


def _similarity_score(
    repo_dict: dict[str, Any],
    keywords: list[str],
    target_topics: set[str],
    target_language: str,
) -> int:
    name = (repo_dict.get("full_name") or "").lower()
    desc = (repo_dict.get("description") or "").lower()
    topics = {t.lower() for t in repo_dict.get("topics", [])}
    language = (repo_dict.get("language") or "").lower()

    score = 0

    for kw in keywords:
        if kw in name:
            score += 8
        if kw in desc:
            score += 4
        if kw in topics:
            score += 6

    overlap = len(target_topics.intersection(topics))
    score += overlap * 4

    if target_language and language == target_language.lower():
        score += 2

    return score


@tool
def find_similar_repos(github_url: str) -> list[dict[str, Any]]:
    """
    Find up to 10 GitHub repositories that are similar to the given repo.

        Strategy:
            1. Extract domain keywords from target repo name/topics/description.
            2. Search GitHub using those keywords (name/description first).
            3. Score candidates by keyword/topic overlap and return top matches.

    Returns a list of dicts with name, description, stars, language,
    topics, and html_url for each similar repo (excluding the target itself).
    """
    owner, repo_name = parse_github_url(github_url)
    g = _get_client()

    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
    except GithubException as exc:
        return [{"error": str(exc)}]

    topics = repo.get_topics()
    language = repo.language or ""
    target_full = repo.full_name.lower()
    keywords = _extract_keywords(repo.name or repo_name, repo.description or "", topics)
    target_topics = {t.lower() for t in topics}

    by_full_name: dict[str, dict[str, Any]] = {}

    def _add_candidate(r: Any) -> None:
        if r.full_name.lower() == target_full:
            return
        item = _repo_dict(r)
        by_full_name[item["full_name"].lower()] = item

    # Keyword-first queries anchored to domain terms (e.g., milvus).
    for kw in keywords[:4]:
        query = f"{kw} in:name,description"
        if language:
            query += f" language:{language}"
        try:
            for r in g.search_repositories(query=query, sort="stars")[:25]:
                _add_candidate(r)
        except GithubException:
            continue

    # Topic query as secondary signal.
    if topics:
        topic_q = " ".join(f"topic:{t}" for t in topics[:3])
        if language:
            topic_q += f" language:{language}"
        try:
            for r in g.search_repositories(query=topic_q, sort="stars")[:25]:
                _add_candidate(r)
        except GithubException:
            pass

    candidates = list(by_full_name.values())
    scored = []
    primary_kw = keywords[0] if keywords else ""
    for item in candidates:
        score = _similarity_score(item, keywords, target_topics, language)
        # Keep moderate matches; strong ones sort to the top anyway.
        if score < 4:
            continue

        # Guardrail: when we have a domain keyword (e.g. milvus), prefer repos
        # that mention it in name/description/topics.
        if primary_kw:
            haystack = " ".join(
                [
                    (item.get("full_name") or "").lower(),
                    (item.get("description") or "").lower(),
                    " ".join((item.get("topics") or [])),
                ]
            )
            if primary_kw not in haystack.lower() and score < 10:
                continue

        scored.append((score, item.get("stars", 0), item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = [item for _, _, item in scored[:10]]

    # Guaranteed fallback: if strict filtering emptied the list, run one focused
    # query on the primary keyword and return the best candidates.
    if not results and primary_kw:
        fallback_query = f"{primary_kw} in:name,description"
        if language:
            fallback_query += f" language:{language}"
        try:
            for r in g.search_repositories(query=fallback_query, sort="stars")[:20]:
                if r.full_name.lower() == target_full:
                    continue
                results.append(_repo_dict(r))
                if len(results) >= 10:
                    break
        except GithubException:
            pass

    return results


def _repo_dict(r: Any) -> dict[str, Any]:
    return {
        "full_name": r.full_name,
        "name": r.name,
        "owner": r.owner.login,
        "description": r.description or "",
        "stars": r.stargazers_count,
        "forks": r.forks_count,
        "language": r.language or "Unknown",
        "topics": r.get_topics(),
        "html_url": r.html_url,
    }


ALL_SIMILARITY_TOOLS = [find_similar_repos]
