"""The harness adapter contract.

Core modules depend on this protocol, never on a concrete harness. Adding a
second harness must not require editing anything outside ``octk/adapters/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers
    from ..capabilities import CapabilityRecord


@dataclass(frozen=True)
class DiscoveryResult:
    """Discovery output plus a reason when nothing (or not everything) worked.

    Iterable over records, so callers that only want the records can ignore the
    reason channel without a second call.
    """

    records: tuple[CapabilityRecord, ...] = ()
    reason: str | None = None

    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    @property
    def ok(self) -> bool:
        return self.reason is None


@runtime_checkable
class HarnessAdapter(Protocol):
    """Minimum surface every harness adapter must provide."""

    id: str

    def detect(self) -> dict[str, Any] | None:
        """Return a summary of the harness, or None when it is absent."""

    def discover_capabilities(self) -> DiscoveryResult:
        """Return validated records. Read-only and idempotent.

        A failure returns an empty result plus ``reason``; it never raises.
        """

    def install_hints(self) -> list[str]:
        """Return human-facing setup suggestions. Never applied automatically."""
