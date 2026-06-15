"""storagelens — part of the Cognis Neural Suite."""
from storagelens.core import (  # noqa: F401
    TOOL_NAME,
    TOOL_VERSION,
    StorageVariable,
    Finding,
    DiffResult,
    parse_layout,
    load_layout,
    diff_layouts,
    scan,
    to_json,
)

__version__ = TOOL_VERSION
