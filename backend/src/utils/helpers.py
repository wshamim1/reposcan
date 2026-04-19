"""Shared helper utilities for reposcan."""

import re
from urllib.parse import urlparse


def parse_github_url(url: str) -> tuple[str, str]:
    """
    Parse a GitHub URL and return (owner, repo_name).

    Accepts formats:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      github.com/owner/repo
      owner/repo  (shorthand)
    """
    # shorthand  owner/repo
    if re.match(r"^[\w\-\.]+/[\w\-\.]+$", url):
        owner, repo = url.split("/", 1)
        return owner, repo.removesuffix(".git")

    # full URL
    parsed = urlparse(url if "://" in url else f"https://{url}")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse GitHub URL '{url}'. "
            "Expected format: https://github.com/owner/repo"
        )
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo


def format_number(n: int) -> str:
    """Format large numbers with k/M suffixes."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def truncate(text: str, max_len: int = 300) -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"
