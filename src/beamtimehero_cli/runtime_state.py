"""Process-local cache of the current experiment phase + active experiment id.

`beamtimehero_cli` is a library; the host application that drives it
(the autonomous orchestrator, an interactive CLI session, a test
harness) is responsible for calling `set_phase` whenever it wants the
audit-log stamp to reflect a new phase or a new active experiment.

`set_phase` validates the slug against `phases.VALID_PHASES`
and updates the in-memory dict. There is no DB write-through here —
this package has no `ExperimentPlan` table; persistent state, if any,
is the host's concern. Hosts that want to repopulate state on a fresh
subprocess (e.g. the autonomous beamtimehero CLI) should call
`set_phase` from their own bootstrap path.
"""

from __future__ import annotations

from typing import Any, Optional

from beamtimehero_cli.spec_control import phases


_STATE: dict[str, Any] = {
    "phase": phases.PHASE_SETUP,
    "experiment_id": None,
}


def get_phase() -> str:
    return _STATE["phase"]


def get_experiment_id() -> Optional[str]:
    return _STATE.get("experiment_id")


def set_phase(phase: str, experiment_id: str | None = None) -> None:
    if phase not in phases.VALID_PHASES:
        raise ValueError(f"unknown phase: {phase}")
    _STATE["phase"] = phase
    if experiment_id:
        _STATE["experiment_id"] = experiment_id


def set_experiment_id(experiment_id: str | None) -> None:
    """Update the active experiment without changing phase."""
    _STATE["experiment_id"] = experiment_id
