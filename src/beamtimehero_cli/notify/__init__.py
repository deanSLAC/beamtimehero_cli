"""Notification integrations (Slack, etc.).

Each submodule lazy-imports its third-party SDK so the bare ``beamtimehero_cli``
install runs without those dependencies unless the deployment actually
needs them. Install with ``pip install 'beamtimehero_cli[slack]'`` for
Slack support.
"""
