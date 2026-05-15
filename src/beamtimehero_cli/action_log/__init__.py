"""action_log — the durable SPEC-action audit trail.

Writer invariant: every `spec_cmd` action is INSERT'd as an ActionLog
row *before* the command is injected to SPEC. Read-only calls go to
QueryLog. Both tables live in their own sqlite file, independent of
the orchestration DB.
"""

from beamtimehero_cli.action_log.cli_log import record_cli_invocation
from beamtimehero_cli.action_log.db import (
    finish_action,
    invalidate_for_experiment,
    log_query,
    mark_action_started,
    recent_actions,
    recent_queries,
    start_action,
)
from beamtimehero_cli.action_log.models import ActionLog, CliInvocationLog, QueryLog
from beamtimehero_cli.action_log.session import get_session, init_db

__all__ = [
    "ActionLog",
    "CliInvocationLog",
    "QueryLog",
    "finish_action",
    "get_session",
    "init_db",
    "invalidate_for_experiment",
    "log_query",
    "mark_action_started",
    "recent_actions",
    "recent_queries",
    "record_cli_invocation",
    "start_action",
]
