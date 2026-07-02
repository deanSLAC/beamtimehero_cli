"""LLM-based and regex-based error detection for SPEC log output."""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from beamtimehero_cli.llm import get_pool, is_lockout, retry_after_seconds

logger = logging.getLogger(__name__)

# SLAC AI Gateway (OpenAI-compatible). Model id matches the SLAC gateway's
# Bedrock-backed Opus; override with SLAC_MODEL if the gateway's id changes.
API_BASE = "https://ai-api.slac.stanford.edu/v1"
MODEL = os.getenv("SLAC_MODEL", "us.anthropic.claude-opus-4-8-v1")

# Ordered gateway keys: prefer the primary, fall back to the existing key when
# the primary is rate-limited / locked out of usage. Read lazily (not at import)
# so a key set after import is still picked up.
_KEY_ENVS = ("SLAC_API_KEY_PRIMARY", "SLAC_API_KEY")


def _key_pool():
    """Shared KeyPool for this checker's gateway, built from the current env."""
    return get_pool(
        "beamtimehero_error_checker",
        [(name, os.getenv(name, "")) for name in _KEY_ENVS],
    )

SYSTEM_PROMPT = """You are analyzing SPEC beamline control log output for errors, warnings, and unexpected behavior.

You will receive numbered chunks of log output, each consisting of a SPEC command and its output.

For each chunk that contains an error, warning, or unexpected behavior, return a JSON array of objects with:
- "chunk_index": the 0-based index of the chunk
- "error_description": a concise description of what went wrong

Common error patterns to look for:
- "Syntax error" messages
- "Not a command or macro" messages
- "EPICS exception" messages
- "motor_par(): Not configured" messages
- Motor limit violations
- Count/scan aborts or timeouts
- Any error text or unexpected warnings

If no errors are found in any chunk, return an empty array: []

Respond with ONLY the JSON array, no other text."""


@dataclass
class DetectedError:
    command_text: str
    error_description: str
    chunk_index: int


# Known error patterns for regex fallback
ERROR_PATTERNS = [
    (re.compile(r'Syntax error', re.IGNORECASE), 'Syntax error'),
    (re.compile(r'Not a command or macro', re.IGNORECASE), 'Unknown command/macro'),
    (re.compile(r'EPICS exception', re.IGNORECASE), 'EPICS exception'),
    (re.compile(r'motor_par\(\):\s*Not configured', re.IGNORECASE), 'Unconfigured motor'),
    (re.compile(r'taking too long.*waiting for', re.IGNORECASE), 'Timeout waiting for device'),
    (re.compile(r'limit violation', re.IGNORECASE), 'Motor limit violation'),
    (re.compile(r'scan aborted', re.IGNORECASE), 'Scan aborted'),
]


def check_for_errors_regex(chunks: list) -> List[DetectedError]:
    """Fast regex-based error detection."""
    errors = []
    for i, chunk in enumerate(chunks):
        raw = chunk.raw_text if hasattr(chunk, 'raw_text') else chunk.get('raw_text', '')
        cmd = chunk.command_text if hasattr(chunk, 'command_text') else chunk.get('command_text', '')
        for pattern, label in ERROR_PATTERNS:
            if pattern.search(raw):
                errors.append(DetectedError(
                    command_text=cmd,
                    error_description=f"{label}: {_extract_error_line(raw, pattern)}",
                    chunk_index=i,
                ))
    return errors


def _extract_error_line(text: str, pattern: re.Pattern) -> str:
    """Extract the first line matching the pattern from text."""
    for line in text.split('\n'):
        if pattern.search(line):
            return line.strip()
    return ""


def _build_user_message(chunks: list) -> str:
    """Format chunks into a numbered list for the LLM prompt."""
    parts = []
    for i, chunk in enumerate(chunks):
        raw = chunk.raw_text if hasattr(chunk, 'raw_text') else chunk.get('raw_text', '')
        cmd = chunk.command_text if hasattr(chunk, 'command_text') else chunk.get('command_text', '')
        parts.append(f"--- Chunk {i} ---\nCommand: {cmd}\n{raw}")
    return '\n\n'.join(parts)


def _call_llm(system: str, user: str) -> Optional[str]:
    """Call the SLAC AI Gateway chat completions endpoint.

    Tries the primary key first and falls back to the secondary key on a
    rate-limit / lockout response (HTTP 429 or a quota marker), remembering the
    lockout so subsequent calls skip the exhausted key until it cools down. Any
    other failure returns ``None`` so the caller degrades to regex detection,
    exactly as before.
    """
    pool = _key_pool()
    keys = pool.order()
    if not keys:
        logger.warning(
            "No LLM gateway API key set (API_KEY_PRIMARY / API_KEY); "
            "skipping LLM error detection."
        )
        return None

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # No temperature: gateway-side model configs (e.g. Bedrock with
        # extended thinking) reject non-default values.
        "max_tokens": 4096,
    }

    for env_name, key in keys:
        try:
            resp = requests.post(
                f"{API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
        except Exception as e:
            # Network-level failure is not a key lockout — don't burn the other
            # key over it; degrade to regex as before.
            logger.warning("LLM call failed: %s", e)
            return None

        # A valid completion always carries "choices"; anything else is an error
        # body (some gateways return rate-limit errors even with HTTP 200).
        try:
            data = resp.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and "choices" in data:
            return data["choices"][0]["message"]["content"]

        if is_lockout(resp.status_code, resp.text):
            pool.mark_locked_out(env_name, retry_after_seconds(resp.headers))
            logger.warning(
                "LLM gateway key %s locked out (HTTP %s); trying fallback key.",
                env_name, resp.status_code,
            )
            continue

        # Non-lockout failure (bad request, auth error, 5xx, malformed body):
        # give up and let the caller fall back to regex, as before.
        try:
            resp.raise_for_status()
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
        else:
            logger.warning(
                "LLM response missing 'choices': %s", (resp.text or "")[:200]
            )
        return None

    logger.warning(
        "All LLM gateway keys locked out; skipping LLM error detection."
    )
    return None


def _parse_llm_response(response_text: str, chunks: list) -> List[DetectedError]:
    """Parse the JSON array from the LLM response into DetectedError objects."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
        return []

    errors = []
    for item in items:
        idx = item.get("chunk_index", 0)
        if 0 <= idx < len(chunks):
            chunk = chunks[idx]
            cmd = chunk.command_text if hasattr(chunk, 'command_text') else chunk.get('command_text', '')
            errors.append(DetectedError(
                command_text=cmd,
                error_description=item.get("error_description", "Unknown error"),
                chunk_index=idx,
            ))
    return errors


def check_for_errors_llm(chunks: list) -> List[DetectedError]:
    """Send command chunks to the LLM for error detection."""
    if not chunks:
        return []
    user_msg = _build_user_message(chunks)
    response = _call_llm(SYSTEM_PROMPT, user_msg)
    if response is None:
        logger.info("Falling back to regex error detection.")
        return check_for_errors_regex(chunks)
    return _parse_llm_response(response, chunks)


def check_for_errors(chunks: list, use_llm: bool = True, batch_size: int = 20) -> List[DetectedError]:
    """Process all chunks for errors, optionally using LLM in batches.

    Args:
        chunks: List of CommandChunk objects.
        use_llm: If True, use LLM detection. If False, use regex only.
        batch_size: Number of chunks per LLM call.
    """
    if not use_llm:
        return check_for_errors_regex(chunks)

    all_errors = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_errors = check_for_errors_llm(batch)
        # Adjust chunk_index to be relative to the full list
        for err in batch_errors:
            err.chunk_index += i
        all_errors.extend(batch_errors)
    return all_errors
