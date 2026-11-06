"""MCP server for Arjun (stdio). Register in Claude Code:
    claude mcp add arjun -- D:\\Arjun\\.venv\\Scripts\\python D:\\Arjun\\tools\\arjun_mcp\\server.py
See README.md for Claude desktop / OpenCode."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("arjun")

for fn in (
    core.health, core.logs, core.try_turn, core.run_tests,
    core.today, core.feed, core.medicines, core.reminders_today, core.add_reminder,
):
    mcp.tool(name=f"arjun_{fn.__name__}", description=(fn.__doc__ or fn.__name__).strip())(fn)

if __name__ == "__main__":
    mcp.run()
