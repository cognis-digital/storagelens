"""Hardening tests: error paths, edge cases, and input validation."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storagelens.core import (
    parse_layout,
    load_layout,
    diff_layouts,
    scan,
    to_json,
    DiffResult,
    TOOL_NAME,
    TOOL_VERSION,
)
from storagelens.cli import main


# ---------------------------------------------------------------------------
# parse_layout – invalid inputs
# ---------------------------------------------------------------------------

def test_parse_layout_rejects_non_object():
    """A plain string is not a valid layout."""
    with pytest.raises(ValueError, match="object or a list"):
        parse_layout("not a dict")  # type: ignore[arg-type]


def test_parse_layout_rejects_bad_storage_type():
    """'storage' key must be a list, not a string."""
    with pytest.raises(ValueError, match="'storage' must be a list"):
        parse_layout({"storage": "bad"})


def test_parse_layout_rejects_non_dict_entry():
    """Each entry in the storage list must be a dict."""
    with pytest.raises(ValueError, match="entry #0 must be an object"):
        parse_layout({"storage": ["not_a_dict"]})


def test_parse_layout_empty_storage_returns_empty_list():
    """An empty storage array is valid and should return []."""
    result = parse_layout({"storage": [], "types": {}})
    assert result == []


def test_parse_layout_bare_list():
    """A bare list (no wrapper dict) is acceptable."""
    result = parse_layout(
        [{"label": "x", "slot": "0", "offset": 0, "type": "t_uint256"}]
    )
    assert len(result) == 1
    assert result[0].label == "x"


# ---------------------------------------------------------------------------
# load_layout – file I/O errors
# ---------------------------------------------------------------------------

def test_load_layout_missing_file_raises():
    """Missing file raises FileNotFoundError (not a generic OSError)."""
    with pytest.raises(FileNotFoundError):
        load_layout("/nonexistent/path/layout.json")


def test_load_layout_malformed_json_raises():
    """Truncated JSON raises json.JSONDecodeError."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as fh:
        fh.write("{bad json")
        path = fh.name
    try:
        with pytest.raises(json.JSONDecodeError):
            load_layout(path)
    finally:
        os.unlink(path)


def test_load_layout_valid_json_but_invalid_structure():
    """Valid JSON that is not a layout dict/list raises ValueError."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as fh:
        json.dump(42, fh)  # a bare integer is not a valid layout
        path = fh.name
    try:
        with pytest.raises(ValueError):
            load_layout(path)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# diff_layouts – type guards
# ---------------------------------------------------------------------------

def test_diff_layouts_rejects_non_list_old():
    with pytest.raises(TypeError, match="old layout must be a list"):
        diff_layouts("not_a_list", [])  # type: ignore[arg-type]


def test_diff_layouts_rejects_non_list_new():
    with pytest.raises(TypeError, match="new layout must be a list"):
        diff_layouts([], None)  # type: ignore[arg-type]


def test_diff_layouts_both_empty_is_clean():
    """Two empty layouts produce a clean DiffResult with no findings."""
    result = diff_layouts([], [])
    assert result.findings == []
    assert not result.has_collision
    assert result.old_count == 0
    assert result.new_count == 0


# ---------------------------------------------------------------------------
# scan() and to_json() helpers
# ---------------------------------------------------------------------------

def test_scan_valid_file_returns_diff_result():
    demos = os.path.join(os.path.dirname(__file__), "..", "demos", "01-basic")
    old_path = os.path.join(demos, "old_layout.json")
    result = scan(old_path)
    assert isinstance(result, DiffResult)
    # Scanning a layout against itself is always clean.
    assert not result.has_collision


def test_scan_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        scan("/no/such/file.json")


def test_to_json_produces_valid_json():
    result = diff_layouts([], [])
    out = to_json(result)
    parsed = json.loads(out)
    assert "has_collision" in parsed
    assert parsed["has_collision"] is False


# ---------------------------------------------------------------------------
# CLI – error exit codes
# ---------------------------------------------------------------------------

def test_cli_missing_file_exits_2(capsys):
    """A missing file argument must exit with code 2, not a traceback."""
    rc = main(["diff", "/no/such/old.json", "/no/such/new.json"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "file not found" in err.lower() or "not found" in err.lower()


def test_cli_malformed_json_exits_2(capsys):
    """A file containing invalid JSON must exit with code 2."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as fh:
        fh.write("{not valid json")
        bad = fh.name
    try:
        rc = main(["diff", bad, bad])
        assert rc == 2
        err = capsys.readouterr().err
        assert "invalid layout" in err.lower() or err  # some error message printed
    finally:
        os.unlink(bad)


def test_cli_no_subcommand_returns_2():
    rc = main([])
    assert rc == 2


# ---------------------------------------------------------------------------
# TOOL_NAME / TOOL_VERSION are accessible from core
# ---------------------------------------------------------------------------

def test_core_exports_tool_identity():
    assert TOOL_NAME == "storagelens"
    assert isinstance(TOOL_VERSION, str)
    assert TOOL_VERSION.count(".") >= 1
