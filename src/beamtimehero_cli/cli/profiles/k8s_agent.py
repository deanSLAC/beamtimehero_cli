"""k8s-agent profile — playground (S3DF + Postgres + Slack) surface.

The Streamlit/Slack assistant in the playground deployment shells into
``beamtimehero k8s-agent <leaf>`` for every tool call. Each alias here
points at the canonical ``(tree, ..., name)`` in the master catalog;
the dispatcher routes through ``execute_tool`` exactly as if the agent
had invoked the canonical path directly.

Keep this list short and curated. If a tool isn't here, the agent
shouldn't be using it.
"""
from __future__ import annotations

PROFILE = {
    "name": "k8s-agent",
    "description": "Playground (S3DF + k8s) agent surface.",
    "aliases": {
        # Scan data (Postgres metadata + pickle DataFrames).
        "list-scans":              ("s3df", "list_scans"),
        "get-latest-scan":         ("s3df", "get_latest_scan"),
        "read-scan":               ("s3df", "read_scan"),
        "plot-scan":               ("s3df", "plot_scan"),
        "get-active-counter":      ("s3df", "get_active_counter"),
        "get-scan-deadtime":       ("s3df", "get_scan_deadtime"),

        # Raw read-only SQL (Postgres-direct, sub-branch).
        "execute-readonly-sql":    ("s3df", "psql", "execute_readonly_sql"),

        # Slack messaging.
        "post-slack-message":      ("slack", "post_slack_message"),
        "read-channel-messages":   ("slack", "read_channel_messages"),
        "read-thread-replies":     ("slack", "read_thread_replies"),
        "list-channels":           ("slack", "list_channels"),
    },
}
