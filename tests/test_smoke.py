"""Smoke tests for STORAGELENS. No network. Runs against the real demo."""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storagelens import (
    TOOL_NAME,
    TOOL_VERSION,
    load_layout,
    parse_layout,
    diff_layouts,
)
from storagelens.cli import main

DEMO = os.path.join(os.path.dirname(__file__), "..", "demos", "01-basic")
OLD = os.path.join(DEMO, "old_layout.json")
NEW = os.path.join(DEMO, "new_layout.json")


def test_metadata():
    assert TOOL_NAME == "storagelens"
    assert TOOL_VERSION.count(".") == 2


def test_parse_canonical_order():
    layout = parse_layout(
        {
            "storage": [
                {"label": "b", "slot": "2", "offset": 0, "type": "t_bool"},
                {"label": "a", "slot": "0", "offset": 0, "type": "t_address"},
            ],
            "types": {
                "t_bool": {"numberOfBytes": "1"},
                "t_address": {"numberOfBytes": "20"},
            },
        }
    )
    assert [v.label for v in layout] == ["a", "b"]
    # numberOfBytes resolved from the types table
    assert layout[0].num_bytes == 20


def test_identical_layout_is_clean():
    old = load_layout(OLD)
    result = diff_layouts(old, old)
    assert not result.has_collision
    assert result.findings == []
    assert result.max_severity == "ok"


def test_demo_detects_collisions():
    old = load_layout(OLD)
    new = load_layout(NEW)
    result = diff_layouts(old, new)

    kinds = {f.kind for f in result.findings}
    assert "RETYPED" in kinds       # totalSupply uint256 -> uint128
    assert "INSERTED_MIDDLE" in kinds  # feeRecipient shoved in
    assert "APPENDED" in kinds       # version added at end (safe)

    assert result.has_collision
    assert result.max_severity == "error"
    assert len(result.collisions) >= 2

    # The appended var must NOT be counted as a collision.
    appended = [f for f in result.findings if f.kind == "APPENDED"]
    assert appended and appended[0].label == "version"
    assert appended[0].severity == "info"


def test_rename_is_warning_not_collision():
    old = parse_layout(
        {"storage": [{"label": "x", "slot": "0", "offset": 0, "type": "t_uint256"}],
         "types": {"t_uint256": {"numberOfBytes": "32"}}}
    )
    new = parse_layout(
        {"storage": [{"label": "y", "slot": "0", "offset": 0, "type": "t_uint256"}],
         "types": {"t_uint256": {"numberOfBytes": "32"}}}
    )
    result = diff_layouts(old, new)
    assert [f.kind for f in result.findings] == ["RENAMED"]
    assert not result.has_collision
    assert result.max_severity == "warning"


def test_removed_variable_is_collision():
    old = parse_layout(
        {"storage": [
            {"label": "a", "slot": "0", "offset": 0, "type": "t_address"},
            {"label": "b", "slot": "1", "offset": 0, "type": "t_address"},
        ], "types": {"t_address": {"numberOfBytes": "20"}}}
    )
    new = parse_layout(
        {"storage": [
            {"label": "a", "slot": "0", "offset": 0, "type": "t_address"},
        ], "types": {"t_address": {"numberOfBytes": "20"}}}
    )
    result = diff_layouts(old, new)
    assert any(f.kind == "REMOVED" and f.label == "b" for f in result.findings)
    assert result.has_collision


def test_cli_exit_code_and_json(capsys):
    rc = main(["diff", OLD, NEW, "--format", "json"])
    assert rc == 1  # collisions -> non-zero for CI gate
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["has_collision"] is True
    assert payload["collision_count"] >= 2
    assert payload["old"].endswith("old_layout.json")


def test_cli_clean_diff_exits_zero(capsys):
    rc = main(["diff", OLD, OLD])
    assert rc == 0
    out = capsys.readouterr().out
    assert "upgrade-compatible" in out.lower()


def test_cli_no_command_prints_help():
    rc = main([])
    assert rc == 2
