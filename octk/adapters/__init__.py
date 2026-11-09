"""Harness and provider adapters.

Adapters are the only place harness-specific knowledge is allowed to live.
They are read-only: discovery never invokes, installs, or mutates anything.

Core modules import the neutral names below. Nothing outside this package
should import ``opencode``/``opencode_scaffold`` directly.
"""

from __future__ import annotations

from .base import HarnessAdapter
from .opencode import OpenCodeAdapter
from .opencode import discover as discover_capabilities
from .opencode_scaffold import AGENTS_DIR as agents_dir
from .opencode_scaffold import AGENT_NAMES as agent_names
from .opencode_scaffold import managed_files as scaffold_managed_files
from .opencode_scaffold import opencode_json as mcp_config
from .opencode_scaffold import permissions_gate
from .opencode_scaffold import render_agent_md as render_agent

__all__ = [
    "HarnessAdapter",
    "OpenCodeAdapter",
    "agent_names",
    "agents_dir",
    "discover_capabilities",
    "mcp_config",
    "permissions_gate",
    "render_agent",
    "scaffold_managed_files",
]
