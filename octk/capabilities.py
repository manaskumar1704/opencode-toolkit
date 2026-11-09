"""Capability Registry: a read-only inventory of the user's existing tools.

Discovery is not execution. Nothing in this module invokes, installs, updates,
or rewrites a capability. The registry stores metadata and references only -
never third-party instruction bodies.

Scope precedence is low to high: ``user`` -> ``project`` -> ``local``.
A record's file location is authoritative for its scope; the ``scope`` field
inside the record is normalised to match.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .config import (
    ToolkitPaths,
    atomic_write_json,
    read_json,
    user_capabilities_index,
)

CAPABILITY_TYPES = frozenset(
    {
        "skill",
        "command",
        "plugin",
        "mcp_server",
        "mcp_tool",
        "native_tool",
        "cli",
        "octk_native",
    }
)
ACTIVATION_STATES = frozenset({"enabled", "disabled", "unknown"})
PROVENANCES = frozenset({"discovered", "manual", "octk_provided"})

# Low to high precedence.
SCOPE_PRECEDENCE = ("user", "project", "local")
_SCOPE_ALIASES = {"global": "user"}

MAX_DESCRIPTION = 140
MAX_L0_LINE = 140
# Descriptions are capped shorter at L0: 140 chars per record was measured at
# 60% of the whole payload. 60 keeps the payload informative but compact.
L0_QUERY_DESC = 60
MAX_L1_BATCH = 50
INDEX_VERSION = 1

ID_RE = re.compile(r"^[a-z_]+:[^/\s]+/[^/\s]+$")


class RegistryError(ValueError):
    """Raised when a capability record is malformed."""


@dataclass(frozen=True)
class CapabilityRecord:
    """One capability, at the granularity OCTK is allowed to know about."""

    id: str
    type: str
    name: str
    description: str
    provider: str = "unknown"
    version: str | None = None
    scope: str = "project"
    harness: tuple[str, ...] = ()
    activation: str = "unknown"
    invocation: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] | None = None
    provenance: str = "discovered"
    verified_at: str | None = None
    source_path: str | None = None

    @property
    def available(self) -> bool:
        """Derived availability: anything not explicitly disabled."""
        return self.activation != "disabled"

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to the on-disk shape."""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "version": self.version,
            "scope": self.scope,
            "harness": list(self.harness),
            "activation": self.activation,
            "invocation": dict(self.invocation),
            "permissions": dict(self.permissions),
            "cost": dict(self.cost) if self.cost is not None else None,
            "provenance": self.provenance,
            "verified_at": self.verified_at,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class Registry:
    """Merged view of every scope, plus which scope won each id."""

    records: tuple[CapabilityRecord, ...]
    winners: dict[str, str]

    def get(self, capability_id: str) -> CapabilityRecord | None:
        for record in self.records:
            if record.id == capability_id:
                return record
        return None

    def filter(self, query: str) -> list[CapabilityRecord]:
        needle = query.casefold().strip()
        if not needle:
            return list(self.records)
        return [
            record
            for record in self.records
            if needle in record.id.casefold()
            or needle in record.name.casefold()
            or needle in record.description.casefold()
        ]

    def resolve(
        self, key: str
    ) -> tuple[CapabilityRecord | None, list[CapabilityRecord]]:
        """Resolve an exact id, else a unique name or id suffix.

        Lets L0 expose bare names without the agent having to know ids.
        """
        exact = self.get(key)
        if exact is not None:
            return exact, []
        matches = [
            record
            for record in self.records
            if record.name == key or record.id.endswith("/" + key)
        ]
        if len(matches) == 1:
            return matches[0], []
        return None, matches


def _normalise_scope(value: Any, *, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    scope = _SCOPE_ALIASES.get(value.strip().casefold(), value.strip().casefold())
    if scope not in SCOPE_PRECEDENCE:
        raise RegistryError(
            f"invalid scope {value!r}: expected one of {', '.join(SCOPE_PRECEDENCE)}"
        )
    return scope


def _normalise_verified_at(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RegistryError("verified_at must be an ISO date string or null")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError(f"verified_at {value!r} is not an ISO date") from exc
    return value


def _normalise_cost(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RegistryError("cost must be an object or null")
    if value.get("measurement") != "measured":
        raise RegistryError("cost is only allowed with measurement: 'measured'")
    tokens = value.get("context_tokens")
    if not isinstance(tokens, int) or tokens < 0:
        raise RegistryError("cost.context_tokens must be a non-negative integer")
    return dict(value)


def record_from_dict(data: Any, *, scope: str) -> CapabilityRecord:
    """Validate one raw record and pin its scope to the file it came from."""
    if not isinstance(data, dict):
        raise RegistryError("capability record must be an object")

    record_id = data.get("id")
    if not isinstance(record_id, str) or not ID_RE.match(record_id):
        raise RegistryError(
            f"invalid id {record_id!r}: expected '<type>:<provider>/<name>'"
        )

    cap_type = data.get("type")
    if cap_type not in CAPABILITY_TYPES:
        raise RegistryError(
            f"{record_id}: invalid type {cap_type!r}: "
            f"expected one of {', '.join(sorted(CAPABILITY_TYPES))}"
        )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RegistryError(f"{record_id}: name is required")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise RegistryError(f"{record_id}: description is required")
    if len(description) > MAX_DESCRIPTION:
        raise RegistryError(
            f"{record_id}: description exceeds {MAX_DESCRIPTION} chars"
        )

    activation = data.get("activation", "unknown")
    if activation not in ACTIVATION_STATES:
        raise RegistryError(
            f"{record_id}: invalid activation {activation!r}: "
            f"expected one of {', '.join(sorted(ACTIVATION_STATES))}"
        )

    provenance = data.get("provenance", "discovered")
    if provenance not in PROVENANCES:
        raise RegistryError(
            f"{record_id}: invalid provenance {provenance!r}: "
            f"expected one of {', '.join(sorted(PROVENANCES))}"
        )

    harness = data.get("harness") or []
    if not isinstance(harness, (list, tuple)) or not all(
        isinstance(item, str) for item in harness
    ):
        raise RegistryError(f"{record_id}: harness must be a list of strings")

    invocation = data.get("invocation") or {}
    permissions = data.get("permissions") or {}
    if not isinstance(invocation, dict):
        raise RegistryError(f"{record_id}: invocation must be an object")
    if not isinstance(permissions, dict):
        raise RegistryError(f"{record_id}: permissions must be an object")

    version = data.get("version")
    if version is not None and not isinstance(version, str):
        raise RegistryError(f"{record_id}: version must be a string or null")

    provider = data.get("provider") or "unknown"
    if not isinstance(provider, str):
        raise RegistryError(f"{record_id}: provider must be a string")

    source_path = data.get("source_path")
    if source_path is not None and not isinstance(source_path, str):
        raise RegistryError(f"{record_id}: source_path must be a string or null")

    return CapabilityRecord(
        id=record_id,
        type=cap_type,
        name=name.strip(),
        description=description.strip(),
        provider=provider,
        version=version,
        scope=_normalise_scope(data.get("scope"), fallback=scope),
        harness=tuple(harness),
        activation=activation,
        invocation=dict(invocation),
        permissions=dict(permissions),
        cost=_normalise_cost(data.get("cost")),
        provenance=provenance,
        verified_at=_normalise_verified_at(data.get("verified_at")),
        source_path=source_path,
    )


def _read_index(path: Path, scope: str) -> list[CapabilityRecord]:
    """Read one index file. Missing or invalid files yield an empty list."""
    data = read_json(path, default=None)
    if data is None:
        return []
    if isinstance(data, dict):
        raw = data.get("capabilities", [])
    elif isinstance(data, list):
        raw = data
    else:
        return []
    if not isinstance(raw, list):
        return []

    records: list[CapabilityRecord] = []
    for entry in raw:
        try:
            record = record_from_dict(entry, scope=scope)
        except RegistryError:
            # A malformed record must not take the whole registry down.
            continue
        # File location wins over any self-declared scope.
        records.append(replace(record, scope=scope))
    return records


def merge_scopes(
    scoped: Iterable[tuple[str, Iterable[CapabilityRecord]]],
) -> Registry:
    """Merge scopes in precedence order; later scopes win."""
    merged: dict[str, CapabilityRecord] = {}
    winners: dict[str, str] = {}
    for scope, records in scoped:
        for record in records:
            merged[record.id] = replace(record, scope=scope)
            winners[record.id] = scope
    ordered = tuple(merged[key] for key in sorted(merged))
    return Registry(records=ordered, winners=winners)


def load_registry(
    root: Path,
    *,
    user_index: Path | None = None,
    project_index: Path | None = None,
    local_index: Path | None = None,
) -> Registry:
    """Load and merge every scope. Never executes a capability."""
    paths = ToolkitPaths(root)
    user_path = user_index if user_index is not None else user_capabilities_index()
    project_path = (
        project_index if project_index is not None else paths.capabilities_index
    )
    local_path = local_index if local_index is not None else paths.capabilities_local

    return merge_scopes(
        [
            ("user", _read_index(user_path, "user")),
            ("project", _read_index(project_path, "project")),
            ("local", _read_index(local_path, "local")),
        ]
    )


def _wrap_names(prefix: str, names: list[str], width: int = MAX_L0_LINE) -> list[str]:
    """Wrap a comma-separated name list so no line exceeds ``width``."""
    lines: list[str] = []
    current = prefix
    for name in names:
        addition = name if current == prefix else ", " + name
        if current != prefix and len(current) + len(addition) > width:
            lines.append(current)
            current = "    " + name
        else:
            current += addition
    lines.append(current)
    return lines


def render_l0(records: Iterable[CapabilityRecord], *, query: str = "") -> str:
    """Compact inventory.

    Without a query this is names grouped by type - the smallest useful
    inventory. With a query it adds the short description, because the agent
    has already narrowed the field and needs enough to choose.
    """
    items = sorted(records, key=lambda record: (record.type, record.name.casefold()))
    if not items:
        return (
            "No capabilities registered. Run `octk capabilities discover --write` "
            "or register one with `octk capabilities register`."
        )

    if query:
        lines = [f"Capabilities ({len(items)}) matching {query!r}:"]
        for record in items:
            description = record.description[:L0_QUERY_DESC]
            line = f"{record.name} [{record.type}] {description}"
            if len(line) > MAX_L0_LINE:
                line = line[: MAX_L0_LINE - 1] + "\u2026"
            lines.append(line)
        lines.append(
            'Use capability_registry(level="L1", query="<term>") for invocation detail.'
        )
        return "\n".join(lines)

    grouped: dict[str, list[str]] = {}
    for record in items:
        grouped.setdefault(record.type, []).append(record.name)

    lines = [f"Capabilities ({len(items)}):"]
    for cap_type in sorted(grouped):
        names = grouped[cap_type]
        lines.extend(_wrap_names(f"  {cap_type} ({len(names)}): ", names))
    lines.append(
        'Use capability_registry(level="L0", query="<term>") for descriptions, '
        'or level="L1" for invocation detail.'
    )
    return "\n".join(lines)


def render_l1(record: CapabilityRecord) -> str:
    """Invocation metadata for one capability."""
    payload = {
        "id": record.id,
        "type": record.type,
        "name": record.name,
        "description": record.description,
        "provider": record.provider,
        "version": record.version,
        "scope": record.scope,
        "harness": list(record.harness),
        "activation": record.activation,
        "available": record.available,
        "invocation": record.invocation,
        "permissions": record.permissions,
        "cost": record.cost,
        "provenance": record.provenance,
        "verified_at": record.verified_at,
        "source_path": record.source_path,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_l2(record: CapabilityRecord) -> str:
    """Reference to the original document. Bodies are never stored or served."""
    if not record.source_path:
        return (
            f"{record.id}\n"
            "reference: (none - manually registered without a source_path)\n"
            "OCTK does not store or serve third-party instruction bodies."
        )
    return (
        f"{record.id}\n"
        f"reference: {record.source_path}\n"
        "Load it with the native tool for this harness "
        "(equip_skill/equip_spec for octk-native capabilities).\n"
        "OCTK does not store or serve third-party instruction bodies."
    )


def render(
    registry: Registry,
    *,
    level: str = "L0",
    query: str = "",
    capability_id: str = "",
) -> str:
    """Render the registry at the requested disclosure level."""
    normalised = level.strip().upper() if isinstance(level, str) else "L0"
    if normalised not in {"L0", "L1", "L2"}:
        return f"octk error: unknown level {level!r}; expected L0, L1, or L2"

    if capability_id:
        record, candidates = registry.resolve(capability_id)
        if record is None:
            if candidates:
                names = ", ".join(item.name for item in candidates)
                return (
                    f"octk error: ambiguous capability {capability_id!r}; "
                    f"matches: {names}"
                )
            return (
                f"octk error: unknown capability {capability_id!r}. "
                'Call capability_registry(level="L0") to list names.'
            )
        if normalised == "L0":
            return render_l0([record])
        if normalised == "L1":
            return render_l1(record)
        return render_l2(record)

    matches = registry.filter(query)

    if normalised == "L0":
        return render_l0(matches, query=query)

    if not matches:
        suffix = f" matching {query!r}" if query else ""
        return f"No capabilities found{suffix}."

    if normalised == "L1":
        batch = matches[:MAX_L1_BATCH]
        body = "\n\n".join(render_l1(record) for record in batch)
        if len(matches) > len(batch):
            body += (
                f"\n\n({len(matches) - len(batch)} more; "
                "narrow with query= or pass capability_id=)"
            )
        return body

    # L2 without an id: return references only, never bodies.
    batch = matches[:MAX_L1_BATCH]
    body = "\n\n".join(render_l2(record) for record in batch)
    if len(matches) > len(batch):
        body += f"\n\n({len(matches) - len(batch)} more; narrow with query=)"
    return body


def write_project_index(root: Path, records: Iterable[CapabilityRecord]) -> Path:
    """Replace the project index. Writes only under .toolkit/capabilities/."""
    paths = ToolkitPaths(root)
    ordered = sorted(records, key=lambda record: record.id)
    payload = {
        "version": INDEX_VERSION,
        "capabilities": [record.to_dict() for record in ordered],
    }
    atomic_write_json(paths.capabilities_index, payload)
    return paths.capabilities_index


def register(root: Path, data: dict[str, Any]) -> CapabilityRecord:
    """Add or replace one manual record in the project index."""
    record = record_from_dict({**data, "provenance": "manual"}, scope="project")
    existing = _read_index(ToolkitPaths(root).capabilities_index, "project")
    merged = {item.id: item for item in existing}
    merged[record.id] = record
    write_project_index(root, merged.values())
    return record


def sync_discovered(
    root: Path, discovered: Iterable[CapabilityRecord]
) -> list[CapabilityRecord]:
    """Merge discovery results into the project index.

    Manual records are preserved: discovery refreshes only records it owns.
    Returns the full merged project list.
    """
    existing = _read_index(ToolkitPaths(root).capabilities_index, "project")
    merged = {
        item.id: item for item in existing if item.provenance != "discovered"
    }
    for record in discovered:
        merged[record.id] = replace(record, provenance="discovered", scope="project")
    ordered = sorted(merged.values(), key=lambda item: item.id)
    write_project_index(root, ordered)
    return ordered

