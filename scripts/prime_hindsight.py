#!/usr/bin/env python3
"""Launch upstream Hindsight MCP for the current devenv project."""

import os
import sys
from pathlib import Path

from agent_storage import hindsight_config, hindsight_private_config


RUNTIME = Path("/opt/hindsight/.hindsight/coding-agents/dist/mcp-server.js")


def mcp_environment(base, cwd, inherited, harness="prime-agent"):
    config = hindsight_config(base, cwd)
    if config is None:
        raise ValueError("Hindsight is disabled; enable it in pi/config/hindsight.json first")
    private = hindsight_private_config(base, config)
    # Honor only the devenv project policy, not stale overrides inherited from Pi.
    env = {key: value for key, value in inherited.items() if not key.startswith("HINDSIGHT_")}
    env.update(
        HINDSIGHT_CONFIG=str(private),
        HINDSIGHT_MCP_HARNESS=harness,
        HINDSIGHT_MCP_PROJECT_CWD=str(cwd),
    )
    return env


def main():
    harness = sys.argv[1] if len(sys.argv) > 1 else "prime-agent"
    try:
        if not RUNTIME.is_file():
            raise ValueError("Hindsight MCP runtime missing; rebuild the devenv image")
        env = mcp_environment(Path("/run/agents/pi"), Path.cwd(), os.environ, harness)
        os.execvpe("bun", ["bun", str(RUNTIME)], env)
    except (OSError, ValueError) as exc:
        print(f"Hindsight MCP: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
