"""beamtimehero_cli.spec_control — SPEC dispatcher and transports.

Layering:
  spec_cmd        — high-level command dispatcher
  transport       — DispatchResult, _MockScreen, busy-state (transport-agnostic)
  sandbox_client  — spec-eval Docker API transport
  screen_client   — pure GNU-screen transport
  tcp_client      — pure TCP server-mode transport
"""

from beamtimehero_cli.spec_control import (
    phase_allowlist,
    sandbox_client,
    screen_client,
    spec_cmd,
    tcp_client,
    transport,
)

__all__ = [
    "phase_allowlist",
    "sandbox_client",
    "screen_client",
    "spec_cmd",
    "tcp_client",
    "transport",
]
