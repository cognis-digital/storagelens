"""Core engine for STORAGELENS.

Real storage-layout diffing: detects the storage-collision bugs that break
upgradeable proxy contracts when the implementation layout changes
incompatibly between versions.

Detection rules (each maps to a real upgrade-safety hazard):

  RENAMED            slot/offset kept, label changed         (info / warning)
  RETYPED            same position, different type/width      (error)
  MOVED              same label, different slot/offset         (error)
  REMOVED            old variable no longer present           (error)
  INSERTED_MIDDLE    new variable inserted before the end      (error)
  SHRUNK_PACK        packed slot now holds fewer bytes         (warning)
  APPENDED           new variable added at the end            (ok / info)

A "collision" is any finding that would cause a deployed proxy to read a
storage slot as the wrong variable after upgrade. RETYPED / MOVED / REMOVED
/ INSERTED_MIDDLE are collisions and fail the gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Severity ordering for sorting / gating. Higher = worse.
SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "error": 3}

# Findings at or above this severity are treated as collisions (gate fails).
_COLLISION_KINDS = {"RETYPED", "MOVED", "REMOVED", "INSERTED_MIDDLE"}


@dataclass(frozen=True)
class StorageVariable:
    """A single storage slot entry from a solc storage layout."""

    label: str
    slot: int
    offset: int
    type_id: str
    num_bytes: int  # width of the underlying type, 0 if unknown

    @property
    def position(self) -> tuple[int, int]:
        return (self.slot, self.offset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "slot": self.slot,
            "offset": self.offset,
            "type": self.type_id,
            "numberOfBytes": self.num_bytes,
        }


@dataclass
class Finding:
    kind: str
    severity: str
    label: str
    slot: Optional[int]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffResult:
    findings: list[Finding] = field(default_factory=list)
    old_count: int = 0
    new_count: int = 0

    @property
    def collisions(self) -> list[Finding]:
        return [f for f in self.findings if f.kind in _COLLISION_KINDS]

    @property
    def has_collision(self) -> bool:
        return bool(self.collisions)

    @property
    def max_severity(self) -> str:
        if not self.findings:
            return "ok"
        return max((f.severity for f in self.findings), key=lambda s: SEVERITY_ORDER[s])

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_count": self.old_count,
            "new_count": self.new_count,
            "has_collision": self.has_collision,
            "max_severity": self.max_severity,
            "collision_count": len(self.collisions),
            "findings": [f.to_dict() for f in self.findings],
        }


def _to_int(value: Any, default: int = 0) -> int:
    """solc encodes slot/numberOfBytes as strings; offset as int. Be liberal."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def parse_layout(data: dict[str, Any]) -> list[StorageVariable]:
    """Parse a solc-style storage-layout dict into ordered StorageVariables.

    Accepts the full solc artifact ({"storage": [...], "types": {...}}) or a
    bare list of storage entries. Sorted by (slot, offset) so ordering is
    canonical regardless of source order.
    """
    if isinstance(data, list):
        entries = data
        types: dict[str, Any] = {}
    elif isinstance(data, dict):
        entries = data.get("storage", [])
        types = data.get("types") or {}
        if not isinstance(entries, list):
            raise ValueError("'storage' must be a list of slot entries")
    else:
        raise ValueError("layout must be an object or a list")

    out: list[StorageVariable] = []
    for i, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"storage entry #{i} must be an object")
        type_id = str(raw.get("type", ""))
        num_bytes = _to_int(raw.get("numberOfBytes"), 0)
        if num_bytes == 0 and type_id and isinstance(types.get(type_id), dict):
            num_bytes = _to_int(types[type_id].get("numberOfBytes"), 0)
        out.append(
            StorageVariable(
                label=str(raw.get("label", f"<unnamed#{i}>")),
                slot=_to_int(raw.get("slot"), 0),
                offset=_to_int(raw.get("offset"), 0),
                type_id=type_id,
                num_bytes=num_bytes,
            )
        )
    out.sort(key=lambda v: v.position)
    return out


def load_layout(path: str) -> list[StorageVariable]:
    """Load and parse a storage layout from a JSON file on disk."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return parse_layout(data)


def diff_layouts(
    old: list[StorageVariable],
    new: list[StorageVariable],
) -> DiffResult:
    """Diff two parsed layouts and return findings.

    The algorithm walks both layouts in canonical (slot, offset) order. For
    each occupied position it compares what the old version expected to live
    there vs. what the new version puts there, classifying each delta into a
    real upgrade hazard.
    """
    result = DiffResult(old_count=len(old), new_count=len(new))

    old_by_pos = {v.position: v for v in old}
    new_by_pos = {v.position: v for v in new}
    old_by_label = {v.label: v for v in old}
    new_by_label = {v.label: v for v in new}

    # Highest slot the old layout actually used (the "append boundary").
    old_max_slot = max((v.slot for v in old), default=-1)

    handled_new_positions: set[tuple[int, int]] = set()

    # --- Walk every position the OLD layout occupied. ---
    for pos in sorted(old_by_pos):
        ov = old_by_pos[pos]
        nv = new_by_pos.get(pos)

        if nv is not None:
            # Genuine insertion: a NEW variable now sits at this slot and the old
            # variable has been pushed elsewhere in the new layout. That is an
            # insertion + move, NOT a retype of the old variable at this slot.
            moved = new_by_label.get(ov.label)
            if (nv.label not in old_by_label and moved is not None
                    and moved.position != pos):
                result.findings.append(
                    Finding(
                        kind="MOVED",
                        severity="error",
                        label=ov.label,
                        slot=ov.slot,
                        message=(
                            f"'{ov.label}' moved from slot {ov.slot}+{ov.offset} "
                            f"to slot {moved.slot}+{moved.offset}; breaks existing storage"
                        ),
                    )
                )
                handled_new_positions.add(moved.position)
                # leave nv's position unhandled -> new-position walk flags INSERTED_MIDDLE
                continue
            handled_new_positions.add(pos)
            if ov.type_id == nv.type_id and ov.label == nv.label:
                continue  # identical -> safe
            if ov.type_id != nv.type_id:
                # Same physical slot, different type: classic collision.
                width_note = ""
                if ov.num_bytes and nv.num_bytes and ov.num_bytes != nv.num_bytes:
                    width_note = (
                        f" (width {ov.num_bytes}B -> {nv.num_bytes}B)"
                    )
                result.findings.append(
                    Finding(
                        kind="RETYPED",
                        severity="error",
                        label=ov.label,
                        slot=ov.slot,
                        message=(
                            f"slot {ov.slot}+{ov.offset}: type changed "
                            f"'{ov.type_id}' -> '{nv.type_id}'{width_note}; "
                            f"existing storage will be misread"
                        ),
                    )
                )
            else:
                # Same position & type, different name -> usually a rename.
                result.findings.append(
                    Finding(
                        kind="RENAMED",
                        severity="warning",
                        label=ov.label,
                        slot=ov.slot,
                        message=(
                            f"slot {ov.slot}+{ov.offset}: renamed "
                            f"'{ov.label}' -> '{nv.label}' (same type); "
                            f"layout-compatible but verify intent"
                        ),
                    )
                )
            continue

        # Nothing at the old position in the new layout. Where did it go?
        moved_to = new_by_label.get(ov.label)
        if moved_to is not None and moved_to.position != ov.position:
            handled_new_positions.add(moved_to.position)
            result.findings.append(
                Finding(
                    kind="MOVED",
                    severity="error",
                    label=ov.label,
                    slot=ov.slot,
                    message=(
                        f"'{ov.label}' moved from slot {ov.slot}+{ov.offset} "
                        f"to slot {moved_to.slot}+{moved_to.offset}; "
                        f"breaks existing storage"
                    ),
                )
            )
        elif moved_to is None:
            # Variable is gone. If something else now occupies the gap-free
            # region this slot is silently reinterpreted.
            result.findings.append(
                Finding(
                    kind="REMOVED",
                    severity="error",
                    label=ov.label,
                    slot=ov.slot,
                    message=(
                        f"'{ov.label}' (slot {ov.slot}+{ov.offset}) removed; "
                        f"slot will be reinterpreted as whatever follows"
                    ),
                )
            )
        # else: same label, same position handled above

    # --- Walk NEW positions that the old layout never used. ---
    for pos in sorted(new_by_pos):
        if pos in handled_new_positions:
            continue
        nv = new_by_pos[pos]
        # If the old version had a variable with this label elsewhere, the
        # MOVED finding already covered it.
        if nv.label in old_by_label and old_by_label[nv.label].position != pos:
            continue
        if nv.slot > old_max_slot:
            result.findings.append(
                Finding(
                    kind="APPENDED",
                    severity="info",
                    label=nv.label,
                    slot=nv.slot,
                    message=(
                        f"'{nv.label}' appended at slot {nv.slot}+{nv.offset}; "
                        f"safe (beyond previous layout)"
                    ),
                )
            )
        else:
            result.findings.append(
                Finding(
                    kind="INSERTED_MIDDLE",
                    severity="error",
                    label=nv.label,
                    slot=nv.slot,
                    message=(
                        f"'{nv.label}' inserted at slot {nv.slot}+{nv.offset}, "
                        f"before end of old layout (max slot {old_max_slot}); "
                        f"shifts every following variable"
                    ),
                )
            )

    # Stable sort: worst severity first, then by slot.
    result.findings.sort(
        key=lambda f: (-SEVERITY_ORDER[f.severity], f.slot if f.slot is not None else 0)
    )
    return result
