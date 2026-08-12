# MCP 服务配置指南

## 方式一：HTTP 传输（当前可用）

```
POST http://127.0.0.1:8001/mcp
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

## 方式二：STDIO 传输（Claude Desktop 集成）

编辑 Claude Desktop 配置文件：

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

添加：

```json
{
  "mcpServers": {
    "health-nutrition-evidence": {
      "command": "python",
      "args": ["scripts/run_mcp_stdio.py"],
      "cwd": "D:\\health-nutrition-evidence-assistant"
    }
  }
}
```

## 可用工具

| 工具 | 描述 |
|------|------|
| `search_pubmed` | 检索 PubMed，支持 MeSH + 年份 + 文献类型过滤 |
| `verify_citation` | 核验 [Ex] 引用真实性 + 伪造 PMID 检测 |
| `get_trial_record` | 查询 ClinicalTrials.gov NCT 编号 |
| `format_evidence_card` | 标准化证据卡片（等级徽章 + 来源 + PMID） |

## 可用资源

| 资源 | 描述 |
|------|------|
| `kb://local/evidence` | 524 篇本地循证文献 |
| `wiki://topics` | 8 个高频营养主题结构化知识 |
| `pubmed://live` | PubMed 实时检索 API |
| `clinicaltrials://live` | ClinicalTrials.gov 查询 |

## 测试命令

```bash
# 列出工具
curl -s -X POST http://127.0.0.1:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# 调用 verify_citation
curl -s -X POST http://127.0.0.1:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"verify_citation","arguments":{"answer_text":"[E1] valid [E5] fake","evidence_count":3}}}'
```
