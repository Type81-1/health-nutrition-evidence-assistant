# 健康营养证据助手 MVP

面向普通消费者的健康营养科普助手。它把问题映射到本地证据库与 PubMed 实时检索结果，并只基于已检索到的资料给出可追溯的回答。

## 已实现的技术点

- **PubMed E-utilities**：在页面中按需实时检索 PubMed 题录与摘要。
- **`pymupdf4llm` 文档解析**：命令行把 PDF 转为 Markdown，再按段落写入知识库。
- **Chroma 向量检索**：优先使用 Chroma 的语义检索；不可用时自动回退至本地词项检索，保证课堂演示可运行。
- **证据约束回答**：每条关键结论都有 `[E1]` 式可点击来源；没有足够证据时会明确说明，而不会补造引用。
- **基础评估**：固定问题集可检查是否有引用、是否出现安全提示、引用是否来自检索结果。

## 快速开始

```powershell
cd outputs/health-nutrition-evidence-assistant
# 将 E:\python312\python.exe 换成你的 Python 3.11+ 可执行文件。
E:\python312\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File scripts/start_local_server.ps1
```

打开 `http://127.0.0.1:8000`。初次启动会把 `data/seed_evidence.json` 中的示例指南与研究写入本地 Chroma 数据库。

## 常用命令

```powershell
# 导入一份 PDF：先转 Markdown，再切分、向量化、入库
python scripts/ingest_markdown.py --pdf "你的资料.pdf" --title "资料标题" --source-url "https://example.org"

# 导入已有 Markdown
python scripts/ingest_markdown.py --markdown "你的资料.md" --title "资料标题" --source-url "https://example.org"

# 从 Europe PMC 批量下载开放获取记录的元数据与全文 XML
python scripts/download_europe_pmc_open_access.py --query "mediterranean diet cardiovascular" --limit 20

# 跑固定评测集
python scripts/run_evaluation.py

# 运行测试
pytest
```

## 文件说明

| 文件/目录 | 作用 |
| --- | --- |
| `app/main.py` | FastAPI 服务与接口入口 |
| `app/services/evidence_store.py` | Chroma 建库、切分、检索与降级检索 |
| `app/services/pubmed_client.py` | PubMed E-utilities 实时检索 |
| `app/services/llm_client.py` | 可选 OpenAI 兼容大模型调用，带引用白名单校验 |
| `app/services/source_plugins.py` | 可复用的 Europe PMC 批量获取插件 |
| `app/services/answer_service.py` | 受证据约束的科普回答与引用组装 |
| `app/services/document_ingestion.py` | PDF/Markdown 解析和入库流程 |
| `app/static/` | 浏览器界面 |
| `data/seed_evidence.json` | 可离线演示的公开指南、综述与试验摘要 |
| `data/evaluation_questions.json` | 可复跑的基础评测问题 |
| `scripts/ingest_markdown.py` | 文档导入命令 |
| `scripts/download_europe_pmc_open_access.py` | Europe PMC 开放获取批量下载命令 |
| `scripts/run_evaluation.py` | 评测命令 |
| `scripts/start_local_server.ps1` | 本地启动命令 |
| `tests/` | 不依赖网络的行为测试 |

## 使用边界

本系统用于健康教育与文献线索整理，不能替代医生诊断、治疗方案或紧急医疗服务。孕期、儿童、慢病用药、严重症状或正在调整药物时，应咨询合格医疗专业人士。
