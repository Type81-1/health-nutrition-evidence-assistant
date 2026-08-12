"""MCP (Model Context Protocol) 封装层 —— D2 文档进阶模块。

协议：JSON-RPC 2.0
传输：STDIO（Claude Desktop 等）/ HTTP（REST API 兼容）
工具来源：app/services/tools.py 的 TOOL_REGISTRY

MCP 方法：
  initialize          — 握手，返回服务器能力
  tools/list          — 列出所有可用工具（含 JSON Schema）
  tools/call          — 调用指定工具
  resources/list      — 列出可用资源（知识库统计）
  prompts/list        — 列出可用 Prompt 模板（Skill 列表）
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.services.tools import TOOL_REGISTRY, call_tool
from app.services.skills import SKILL_REGISTRY

MCP_VERSION = "0.1.0"
SERVER_NAME = "health-nutrition-evidence-mcp"
SERVER_DESCRIPTION = "健康营养证据助手 MCP 服务 — 提供 PubMed 检索、引用校验、临床试验查询等工具"


# ═══════════════════════════════════════════════════════════════
# JSON-RPC 2.0 消息处理
# ═══════════════════════════════════════════════════════════════

def _jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# ═══════════════════════════════════════════════════════════════
# MCP 核心方法
# ═══════════════════════════════════════════════════════════════

async def _handle_initialize(id: Any, params: dict) -> dict:
    """MCP 握手：返回服务器能力和版本。"""
    return _jsonrpc_response(id, {
        "protocolVersion": MCP_VERSION,
        "serverInfo": {
            "name": SERVER_NAME,
            "version": MCP_VERSION,
            "description": SERVER_DESCRIPTION,
        },
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False},
            "prompts": {"listChanged": False},
        },
    })


async def _handle_tools_list(id: Any, params: dict) -> dict:
    """列出所有可用工具 + JSON Schema。"""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        tools.append({
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.input_schema,
        })
    return _jsonrpc_response(id, {"tools": tools})


async def _handle_tools_call(id: Any, params: dict) -> dict:
    """调用指定工具。params.name + params.arguments"""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in TOOL_REGISTRY:
        return _jsonrpc_error(id, -32602, f"Unknown tool: {tool_name}")

    result = await call_tool(tool_name, arguments)

    # MCP 要求 content 为 text/plain 或 text/markdown 数组
    return _jsonrpc_response(id, {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2),
            }
        ],
        "isError": not result.get("success", False),
    })


async def _handle_resources_list(id: Any, params: dict) -> dict:
    """列出可用知识资源。"""
    resources = [
        {
            "uri": "kb://local/evidence",
            "name": "本地循证知识库",
            "description": "524 篇 PubMed 预索引营养文献",
            "mimeType": "application/jsonl",
        },
        {
            "uri": "wiki://topics",
            "name": "LLM Wiki 主题页",
            "description": "8 个高频营养主题的结构化知识",
            "mimeType": "application/jsonl",
        },
        {
            "uri": "pubmed://live",
            "name": "PubMed 实时检索",
            "description": "E-utilities API，支持 MeSH + 类型 + 年份过滤",
        },
        {
            "uri": "clinicaltrials://live",
            "name": "ClinicalTrials.gov",
            "description": "临床试验 NCT 编号查询",
        },
    ]
    return _jsonrpc_response(id, {"resources": resources})


async def _handle_prompts_list(id: Any, params: dict) -> dict:
    """列出可用 Skill（Prompt 模板）。"""
    prompts = []
    for name, skill in SKILL_REGISTRY.items():
        prompts.append({
            "name": f"skill:{name}",
            "description": skill.description,
            "arguments": [
                {"name": "always_load", "description": "Always active" if skill.always_load else f"Triggers: {skill.triggers[:3]}"},
            ],
        })
    return _jsonrpc_response(id, {"prompts": prompts})


# ═══════════════════════════════════════════════════════════════
# 方法路由
# ═══════════════════════════════════════════════════════════════

_METHOD_MAP = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
    "resources/list": _handle_resources_list,
    "prompts/list": _handle_prompts_list,
}


async def process_request(raw: dict) -> dict:
    """处理单个 JSON-RPC 请求。"""
    req_id = raw.get("id")
    method = raw.get("method", "")
    params = raw.get("params", {})

    if method not in _METHOD_MAP:
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    try:
        return await _METHOD_MAP[method](req_id, params)
    except Exception as e:
        return _jsonrpc_error(req_id, -32603, f"Internal error: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════
# STDIO Transport（Claude Desktop 等原生集成）
# ═══════════════════════════════════════════════════════════════

async def run_stdio() -> None:
    """启动 MCP STDIO 服务器。

    从 stdin 逐行读取 JSON-RPC 请求，处理后写入 stdout。
    用法: python scripts/run_mcp_stdio.py
    """
    print(f"[MCP] {SERVER_NAME} v{MCP_VERSION} starting on STDIO", file=sys.stderr)

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            line = line.decode("utf-8").strip()
            if not line:
                continue

            request = json.loads(line)
            response = await process_request(request)

            writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            await writer.drain()
        except json.JSONDecodeError:
            err = _jsonrpc_error(None, -32700, "Parse error")
            writer.write((json.dumps(err, ensure_ascii=False) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as e:
            print(f"[MCP] Error: {e}", file=sys.stderr)
            break

    writer.close()
    print("[MCP] Server stopped", file=sys.stderr)
