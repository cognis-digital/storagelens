# STORAGELENS — Architecture

> Diffs and decodes contract storage layouts across proxy upgrades to catch storage-collision and uninitialized-slot bugs.

```
input ──▶ collect ──▶ rules/analyzers ──▶ score ──▶ findings ──▶ table · json
                              │                          │
                         (this repo)                 MCP tool (agents)
```

- **collect** normalizes the target (file/dir/API) into records.
- **rules/analyzers** apply the heuristics shipped in `storagelens/core.py`.
- **score** ranks by severity.
- **MCP server** (`storagelens mcp`) exposes `scan` for Cognis.Studio agents.

Extend by adding a rule + a test + a `demos/NN-*/SCENARIO.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
