"""External providers: Graphify and Ponytail.

Detection only. OCTK never installs, updates, bundles, or executes these
tools. It records whether they are present and what state they are in, so the
agent can decide whether to use them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderStatus:
    """What OCTK knows about one external provider."""

    id: str
    available: bool
    version: str | None
    detail: str
    state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
