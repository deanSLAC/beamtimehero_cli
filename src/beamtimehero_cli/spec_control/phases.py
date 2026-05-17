"""Phase identifiers and ordering for the BL15-2 workflow.

Permission gating is intentionally not in this library —
`beamtimehero_cli` is the generic CLI surface, and any agent-role
filtering belongs in the consuming application. See the `autonomous`
repo's `scripts/beamtimehero` for an example of how a consumer adds
per-role argparse branches on top of this library.

What lives here:
  * Phase constants used by consumers to label workflow state.
  * `ALL_PHASES` / `VALID_PHASES` / `PHASE_ORDER` ordering tables.
  * `direction()` / `backward_steps()` helpers for consumers that
    implement their own phase transitions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

PHASE_SETUP = "setup"
PHASE_BL_ALIGN = "beamline_alignment"
PHASE_XES_ALIGN = "xes_alignment"
PHASE_SAMPLE_ALIGN = "sample_alignment"
PHASE_COLLECTION = "collection"
PHASE_COMPLETE = "complete"

ALL_PHASES = [
    PHASE_SETUP,
    PHASE_BL_ALIGN,
    PHASE_XES_ALIGN,
    PHASE_SAMPLE_ALIGN,
    PHASE_COLLECTION,
    PHASE_COMPLETE,
]

# All phase identifiers accepted by `set_phase`.
VALID_PHASES = set(ALL_PHASES)

# Forward sequence used to judge forward vs. backward transitions.
PHASE_ORDER = {name: i for i, name in enumerate(ALL_PHASES)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def direction(prev: str, nxt: str) -> str:
    """Classify a phase transition as 'forward' | 'backward' | 'same'."""
    if prev == nxt:
        return "same"
    a = PHASE_ORDER.get(prev, -1)
    b = PHASE_ORDER.get(nxt, -1)
    if b > a:
        return "forward"
    return "backward"


def backward_steps(prev: str, nxt: str) -> int:
    return max(0, PHASE_ORDER.get(prev, 0) - PHASE_ORDER.get(nxt, 0))
