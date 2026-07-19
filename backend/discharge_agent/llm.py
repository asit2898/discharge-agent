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
# The orchestrator agent's model — it drives the tool-use loop (plan → check →
# investigate → confirm/dismiss → act). Same strong model by default.
ORCHESTRATOR_MODEL = os.environ.get("DISCHARGE_ORCHESTRATOR_MODEL", "claude-opus-4-8")


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


def run_tool_loop(
    *,
    model: str,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    dispatch,
    max_iters: int = 24,
    max_tokens: int = 2048,
) -> Optional[list[dict[str, Any]]]:
    """Drive a real multi-turn tool-use loop — the model decides which tool to call
    each turn until it stops (or the iteration cap trips). This is the agent primitive.

    `dispatch(name, input_dict) -> dict` executes one tool call and returns a dict that
    may carry control keys:
        "content" — JSON-serializable payload sent back to the model (defaults to the
                    whole dict minus control keys)
        "summary" — short human string recorded in the trace (defaults to content)
        "stop"    — True to end the loop after this call (e.g. a `finish` tool)

    Returns an ordered trace of events ({"kind": "thought"|"action", ...}) for display,
    or None if the LLM is unavailable. The caller owns any accumulated state via the
    dispatch closure; this function is deliberately state-free.
    """
    client = _client()
    if client is None:
        return None

    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    trace: list[dict[str, Any]] = []

    for _ in range(max_iters):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )

        # Rebuild the assistant turn as plain dicts so it can be replayed in `messages`.
        assistant_content: list[dict[str, Any]] = []
        tool_uses = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text = (block.text or "").strip()
                if text:
                    trace.append({"kind": "thought", "text": text})
                assistant_content.append({"type": "text", "text": block.text or ""})
            elif btype == "tool_use":
                tool_uses.append(block)
                assistant_content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
                )
        messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            break

        tool_results = []
        stop = False
        for tu in tool_uses:
            args = dict(tu.input)
            try:
                out = dispatch(tu.name, args) or {}
            except Exception as exc:  # a bad tool call must not kill the loop
                out = {"content": {"error": str(exc)}, "summary": f"error: {exc}"}
            content = out.get("content", {k: v for k, v in out.items() if k not in ("content", "summary", "stop")})
            summary = out.get("summary")
            if summary is None:
                summary = content if isinstance(content, str) else json.dumps(content, default=str)[:400]
            trace.append({"kind": "action", "tool": tu.name, "input": args, "result": str(summary)[:600]})
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id,
                 "content": content if isinstance(content, str) else json.dumps(content, default=str)}
            )
            if out.get("stop"):
                stop = True
        messages.append({"role": "user", "content": tool_results})
        if stop:
            break

    return trace


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
