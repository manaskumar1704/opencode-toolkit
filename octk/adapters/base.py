"""The harness adapter contract.

Core modules depend on this protocol, never on a concrete harness. Adding a
second harness must not require editing anything outside ``octk/adapters/``.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable


@runtime_checkable
class HarnessAdapter(Protocol):
    """Minimum surface every harness adapter must provide."""

    id: str

    def detect(self) -> dict[str, Any] | None:
        """Return a summary of the harness, or None when it is absent."""

    def discover_capabilities(self) -> Iterable[dict[str, Any]]:
        """Return raw capability records. Read-only and idempotent."""

    def install_hints(self) -> list[str]:
        """Return human-facing setup suggestions. Never applied automatically."""
