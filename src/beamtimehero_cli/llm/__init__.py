"""LLM-gateway helpers shared across the projects that depend on this package.

Currently exposes :mod:`beamtimehero_cli.llm.key_pool` — an ordered API-key
selector with per-key lockout memory, used to prefer a primary gateway key and
fall back to a secondary key when the primary is rate-limited / locked out.
"""

from .key_pool import KeyPool, get_pool, is_lockout, retry_after_seconds

__all__ = ["KeyPool", "get_pool", "is_lockout", "retry_after_seconds"]
