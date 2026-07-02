"""Ordered API-key selection with per-key lockout memory.

A :class:`KeyPool` holds an ordered list of candidate gateway API keys — the
first is the *primary*, the rest are fallbacks. When a key comes back
rate-limited / locked out of usage, :meth:`KeyPool.mark_locked_out` puts it in a
cooldown window so callers prefer the next key until the primary recovers.

This is deliberately stdlib-only (no config, pydantic, or LLM-SDK dependency) so
every project that depends on ``beamtimehero_cli`` — autonomous, playground, and
this library's own log error-checker — can share one implementation. Lockout
state is per-process: a process shares one pool per gateway via :func:`get_pool`,
so multiple call sites in the same process cooperate, while separate processes
each discover a lockout independently (at most one extra 429 per process per
cooldown window).
"""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional, Tuple

# Substrings that mark a "locked out of usage" response body (quota / usage
# limit exhausted) even when the HTTP status itself is not 429.
_LOCKOUT_BODY_MARKERS = (
    "rate limit",
    "rate_limit",
    "quota",
    "too many requests",
    "usage limit",
    "overloaded",
)

_DEFAULT_COOLDOWN_S = 900.0


def _default_cooldown() -> float:
    """Cooldown window (seconds), overridable via ``LLM_KEY_COOLDOWN_S``."""
    raw = os.getenv("LLM_KEY_COOLDOWN_S")
    if not raw:
        return _DEFAULT_COOLDOWN_S
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_COOLDOWN_S
    return val if val > 0 else _DEFAULT_COOLDOWN_S


def is_lockout(status_code: Optional[int], body: str = "") -> bool:
    """True if a response indicates the key is locked out of usage.

    Triggers on HTTP 429 (rate limited) or a quota / usage-limit marker in the
    response body. Auth failures (401/403) are intentionally *excluded* — those
    usually mean a bad or revoked key, not exhausted usage, and falling back
    would just burn the second key too.
    """
    if status_code == 429:
        return True
    if body:
        low = body.lower()
        return any(marker in low for marker in _LOCKOUT_BODY_MARKERS)
    return False


def retry_after_seconds(headers) -> Optional[float]:
    """Parse a ``Retry-After`` header (delta-seconds form) into seconds.

    Returns ``None`` when the header is absent or in the HTTP-date form (which
    we do not honor — callers fall back to the default cooldown instead).
    """
    if not headers:
        return None
    val = None
    # requests' CaseInsensitiveDict handles either case; be defensive for plain dicts.
    try:
        val = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        return None
    if not val:
        return None
    try:
        secs = float(val)
    except (TypeError, ValueError):
        return None
    return secs if secs > 0 else None


class KeyPool:
    """An ordered set of candidate API keys with per-key cooldown.

    ``keys`` is an ordered list of ``(env_name, value)`` pairs; the first is the
    primary. Pairs with an empty value are dropped, so a pool configured with an
    unset primary simply behaves like a single-key pool (fully backward
    compatible with the pre-failover single-key behavior).
    """

    def __init__(self, keys, cooldown_s: Optional[float] = None):
        self._keys: List[Tuple[str, str]] = [(n, v) for (n, v) in keys if v]
        self._cooldown_s = cooldown_s if cooldown_s is not None else _default_cooldown()
        self._locked_until: dict = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> float:
        # Monotonic clock: cooldowns are durations, immune to wall-clock jumps.
        return time.monotonic()

    def _usable(self, name: str, now: float) -> bool:
        until = self._locked_until.get(name)
        return until is None or until <= now

    def order(self) -> List[Tuple[str, str]]:
        """All keys with usable ones first (original order preserved), then any
        cooling-down keys sorted by soonest expiry.

        Direct-HTTP callers iterate this to retry across every key in one call;
        even fully locked-out keys are returned last so a caller never ends up
        with zero keys to try.
        """
        now = self._now()
        with self._lock:
            usable = [(n, v) for (n, v) in self._keys if self._usable(n, now)]
            locked = [(n, v) for (n, v) in self._keys if not self._usable(n, now)]
            locked.sort(key=lambda kv: self._locked_until.get(kv[0], 0.0))
        return usable + locked

    def active(self) -> Optional[Tuple[str, str]]:
        """The single key to use right now: first usable, else least-locked.

        Used by one-shot pickers (e.g. building the env for a ``claude -p``
        spawn) that cannot retry across keys within a single attempt.
        """
        ordered = self.order()
        return ordered[0] if ordered else None

    def mark_locked_out(self, env_name: str, retry_after: Optional[float] = None) -> None:
        """Put ``env_name`` in a cooldown window (default, or ``retry_after``)."""
        window = retry_after if (retry_after and retry_after > 0) else self._cooldown_s
        with self._lock:
            self._locked_until[env_name] = self._now() + window

    def clear(self, env_name: Optional[str] = None) -> None:
        """Clear cooldown for one key, or all keys when ``env_name`` is None."""
        with self._lock:
            if env_name is None:
                self._locked_until.clear()
            else:
                self._locked_until.pop(env_name, None)

    def all_locked(self) -> bool:
        """True if there is at least one key and every key is cooling down."""
        now = self._now()
        with self._lock:
            return bool(self._keys) and all(
                not self._usable(n, now) for n, _ in self._keys
            )

    @property
    def names(self) -> List[str]:
        return [n for n, _ in self._keys]

    def __bool__(self) -> bool:
        return bool(self._keys)


_registry: dict = {}
_registry_lock = threading.Lock()


def get_pool(gateway_id: str, keys, cooldown_s: Optional[float] = None) -> KeyPool:
    """Return a process-wide shared :class:`KeyPool` for ``gateway_id``.

    Created on first use so cooldown state is shared across every call site in
    the process. If the configured key *names* change (rare — e.g. env re-read
    with a newly-set primary), the pool is rebuilt so the new key takes effect.
    """
    names = [n for (n, v) in keys if v]
    with _registry_lock:
        pool = _registry.get(gateway_id)
        if pool is None or pool.names != names:
            pool = KeyPool(keys, cooldown_s=cooldown_s)
            _registry[gateway_id] = pool
        return pool
