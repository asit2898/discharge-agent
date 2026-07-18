"""Thin Claude client for the two LLM stages (assertion extraction + self-verify).

Design rules:
  * Reads ANTHROPIC_API_KEY from the environment or a repo-root .env (never committed).
  * `available()` guards every call site so the deterministic engine runs fully when
    no key is present — the LLM stages simply no-op and the checks still fire.
  * Structured output is obtained via a forced tool call (a JSON-schema tool), which
    is the reliable way to get typed data out of the Messages API.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from . import config

# Model split per docs/engine.md: a strong model for extraction/verify quality.
EXTRACT_MODEL = os.environ.get("DISCHARGE_EXTRACT_MODEL", "claude-opus-4-8")
VERIFY_MODEL = os.environ.get("DISCHARGE_VERIFY_MODEL", "claude-opus-4-8")


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency): populate os.environ from repo-root .env."""
    env_path = config.REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()


@lru_cache(maxsize=1)
def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=key)


def available() -> bool:
    return _client() is not None


def call_structured(
    *,
    model: str,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    schema: dict[str, Any],
    max_tokens: int = 4096,
) -> Optional[dict[str, Any]]:
    """Force the model to emit one structured object via a tool call. Returns the
    tool input dict, or None if the LLM is unavailable or produced no tool use."""
    client = _client()
    if client is None:
        return None
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)
    return None


def status() -> dict[str, Any]:
    """Surfaced at /api/health so the UI can show whether the LLM stages are live."""
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    have_sdk = True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        have_sdk = False
    return {
        "llm_available": available(),
        "have_api_key": have_key,
        "have_sdk": have_sdk,
        "extract_model": EXTRACT_MODEL,
        "verify_model": VERIFY_MODEL,
    }
