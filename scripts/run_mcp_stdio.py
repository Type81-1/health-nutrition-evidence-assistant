#!/usr/bin/env python
"""MCP STDIO 启动入口。

用法（Claude Desktop 配置）:
{
  "mcpServers": {
    "health-nutrition-evidence": {
      "command": "python",
      "args": ["scripts/run_mcp_stdio.py"],
      "cwd": "/path/to/health-nutrition-evidence-assistant"
    }
  }
}

也可直接命令行测试:
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python scripts/run_mcp_stdio.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.mcp_handler import run_stdio

if __name__ == "__main__":
    asyncio.run(run_stdio())
