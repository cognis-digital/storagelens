"""STORAGELENS MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from storagelens.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-storagelens[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-storagelens[mcp]'")
        return 1
    app = FastMCP("storagelens")

    @app.tool()
    def storagelens_scan(target: str) -> str:
        """Diffs and decodes contract storage layouts across proxy upgrades to catch storage-collision and uninitialized-slot bugs.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
