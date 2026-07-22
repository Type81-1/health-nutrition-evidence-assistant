# 健康营养证据助手 MVP

面向普通消费者的健康营养科普助手。它把问题映射到本地证据库与 PubMed 实时检索结果，并只基于已检索到的资料给出可追溯的回答。

## 已实现的技术点

- **PubMed E-utilities**：在页面中按需实时检索 PubMed 题录与摘要。
- **`pymupdf4llm` 文档解析**：命令行把 PDF 转为 Markdown，再按段落写入知识库。
- **Chroma 向量检索**：优先使用 Chroma 的语义检索；不可用时自动回退至本地词项检索，保证课堂演示可运行。
- **证据约束回答**：每条关键结论都有 `[E1]` 式可点击来源；没有足够证据时会明确说明，而不会补造引用。
- **基础评估**：固定问题集可检查是否有引用、是否出现安全提示、引用是否来自检索结果。

## 快速开始

```zsh
cd /Users/astrid/Documents/health-nutrition-evidence-assistant

# 建议使用项目本地虚拟环境，避免污染 Anaconda base。
/Users/astrid/anaconda3/envs/py311/bin/python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 10

# 可选：配置 PubMed 和大模型 key。
cp .env.example .env

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000`。默认使用稳定的本地关键词检索；如需启用 Chroma 语义检索，可在 `.env` 中设置 `ENABLE_CHROMA=true`。

不配置 API key 也可以运行本地证据问答。`NCBI_API_KEY` 只用于提升 PubMed 高频访问稳定性；`LLM_API_KEY` 只用于可选的大模型增强回答。

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

## 赛道二优化点

- 本地证据库已扩展到 17 条，覆盖地中海饮食、DASH、限钠、血脂、膳食纤维、鱼油、糖摄入和超加工食品。
- 关键词检索加入中文短语、领域同义词、标题命中和证据等级加权。
- PubMed 检索支持常见中文健康问题到英文检索词的转换，并在 `efetch` 超时时回退到 `esummary`。
- 评测集扩展到 10 个问题，并检查预期来源 ID 是否命中。

## 使用边界

本系统用于健康教育与文献线索整理，不能替代医生诊断、治疗方案或紧急医疗服务。孕期、儿童、慢病用药、严重症状或正在调整药物时，应咨询合格医疗专业人士。
