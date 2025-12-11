"""Command-line interface for STORAGELENS.

Examples:
  # Diff two solc storage-layout JSON files (CI gate):
  storagelens diff old_layout.json new_layout.json

  # Machine-readable output for piping into CI logic:
  storagelens diff old.json new.json --format json

  # Show version:
  storagelens --version

Exit codes:
  0  layouts are upgrade-compatible (no collisions)
  1  a storage collision was detected (gate should fail)
  2  usage / input error
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import DiffResult, load_layout, diff_layouts

_SEV_LABEL = {
    "ok": "OK",
    "info": "INFO",
    "warning": "WARN",
    "error": "ERROR",
}


def _render_table(result: DiffResult, old_path: str, new_path: str) -> str:
    lines: list[str] = []
    lines.append(f"STORAGELENS  {old_path}  ->  {new_path}")
    lines.append(
        f"  old slots: {result.old_count}   new slots: {result.new_count}"
    )
    lines.append("")
    if not result.findings:
        lines.append("  No layout changes detected. Upgrade-compatible.")
        return "\n".join(lines)

    sev_w = max(len(_SEV_LABEL[f.severity]) for f in result.findings)
    kind_w = max(len(f.kind) for f in result.findings)
    for f in result.findings:
        sev = _SEV_LABEL[f.severity].ljust(sev_w)
        kind = f.kind.ljust(kind_w)
        lines.append(f"  [{sev}] {kind}  {f.message}")

    lines.append("")
    if result.has_collision:
        lines.append(
            f"  FAIL: {len(result.collisions)} storage collision(s) detected."
        )
    elif result.max_severity == "warning":
        lines.append("  PASS (with warnings): no collisions, review renames.")
    else:
        lines.append("  PASS: layouts are upgrade-compatible.")
    return "\n".join(lines)


def _cmd_diff(args: argparse.Namespace) -> int:
    try:
        old = load_layout(args.old)
        new = load_layout(args.new)
    except FileNotFoundError as exc:
        print(f"{TOOL_NAME}: file not found: {exc.filename}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"{TOOL_NAME}: invalid layout: {exc}", file=sys.stderr)
        return 2

    result = diff_layouts(old, new)

    if args.format == "json":
        payload = result.to_dict()
        payload["old"] = args.old
        payload["new"] = args.new
        print(json.dumps(payload, indent=2))
    else:
        print(_render_table(result, args.old, args.new))

    return 1 if result.has_collision else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=(
            "Diff contract storage layouts across versions to catch "
            "storage-collision bugs in upgradeable contracts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  storagelens diff old_layout.json new_layout.json\n"
            "  storagelens diff old.json new.json --format json\n"
            "\n"
            "Layout files are standard solc --storage-layout JSON "
            "(also emitted by Hardhat/Foundry).\n"
            "Exit 1 on collision so it can be used directly as a CI gate."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{TOOL_NAME} {TOOL_VERSION}",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="output format (default: table)",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p_diff = sub.add_parser(
        "diff",
        help="diff an old layout against a new layout",
        description="Compare two storage layouts and report upgrade hazards.",
    )
    p_diff.add_argument("old", help="path to the OLD storage-layout JSON")
    p_diff.add_argument("new", help="path to the NEW storage-layout JSON")
    p_diff.set_defaults(func=_cmd_diff)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
