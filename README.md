# 食证 · 健康营养证据助手

> 🏆 2026 小挑战杯 / 创业计划竞赛 · 科技创新和未来产业赛道

面向普通消费者的健康营养循证科普助手。检索 PubMed + Europe PMC 公开文献，用通俗语言给出有据可查的回答。**每条结论都可追溯到原始研究。**

---

## 一、快速开始

### 环境要求

- Python 3.11+
- 网络连接（用于 PubMed / LLM API 调用）

### 安装与启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key（或其他 OpenAI-compatible 服务）

# 3. 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开 `http://127.0.0.1:8000`。首次启动自动将 `data/seed_evidence.jsonl`（524 篇文献）写入本地 Chroma 向量数据库。

---

## 二、核心能力

| 能力 | 说明 |
|------|------|
| 🔍 多源检索 | Chroma 语义检索 + BM25 关键词检索 → RRF 融合重排 |
| 📚 实时查询 | PubMed E-utilities + Europe PMC REST API + ClinicalTrials.gov |
| 🛡️ 安全闸门 | 域外拒答 + 伪科学拦截 + 危险药材检测 + 伪造 PMID 检测 |
| 📝 引用溯源 | 每句结论标注 `[Ex]` 可点击引用锚点，链接到原文 |
| 🎯 证据分级 | Meta分析 > 临床指南 > RCT > 综述 > 观察性研究，可视化徽章 |
| 💬 多轮对话 | 上下文感知，支持连续追问 |
| 🔄 多 Agent 协作 | Researcher → Writer → Critic 三角色管线 |
| 📊 流式输出 | SSE 实时渲染，Typewriter 逐字展示 |

---

## 三、系统架构

```
用户浏览器 (Vanilla JS + CSS)
        │  HTTP + SSE
        ▼
FastAPI 接入层
        │
   ┌────┼────┬──────────┬──────────┐
   ▼    ▼    ▼          ▼          ▼
安全过滤  查询翻译  对话管理  证据检索
(check_   (LLM    (会话    (Chroma
domain/  中→英   记忆)    + BM25
safety)  翻译)            + PubMed)
   │    │    │          │
   └────┼────┴──────────┘
        ▼
   LLM 生成层
   (DeepSeek Chat)
        │
   ┌────┼────┬──────────┐
   ▼    ▼    ▼          ▼
引用校验  幻觉检测  技能系统  工作流管线
(PMID   (伪造   (动态    (可配置
白名单) PMID)  Prompt)  步骤链)
```

详细架构见 [`docs/architecture.md`](docs/architecture.md)。

---

## 四、D2 进阶模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 🔧 Tool 工具层 | `app/services/tools.py` | 4 个标准化 JSON Schema 工具 |
| 🧠 Skill 技能层 | `app/services/skills.py` | 5 个按需加载 Prompt 模块 |
| 🔌 MCP 封装 | `app/services/mcp_handler.py` | JSON-RPC 2.0, STDIO/HTTP 双传输 |
| ⚙️ Workflow 管线 | `app/services/workflow.py` | 9 步可配置流水线引擎 |
| 🤖 多 Agent | `app/services/agent_pipeline.py` | Researcher → Writer → Critic |

---

## 五、项目文件结构

```
├── app/
│   ├── main.py                    # FastAPI 服务入口（全部端点）
│   ├── schemas.py                 # Pydantic 数据模型
│   ├── static/
│   │   ├── index.html             # 单页前端
│   │   ├── app.js                 # 前端逻辑（SSE + Agent 进度 + Markdown 渲染）
│   │   └── styles.css             # Soft Structuralism 视觉系统
│   └── services/
│       ├── evidence_store.py      # Chroma + BM25 + RRF 检索
│       ├── pubmed_client.py       # PubMed E-utilities
│       ├── llm_client.py          # LLM 调用 + 查询翻译
│       ├── answer_service.py      # 完整问答管线（安全 + 检索 + 生成 + 校验）
│       ├── tools.py               # Tool 工具层（D2）
│       ├── skills.py              # Skill 技能层（D2）
│       ├── mcp_handler.py         # MCP 协议（D2）
│       ├── workflow.py            # Pipeline 工作流（D2）
│       ├── agent_pipeline.py      # 多 Agent 协作（D2）
│       ├── source_plugins.py      # Europe PMC 数据源插件
│       ├── query_logger.py        # 查询日志
│       └── wiki_store.py          # Wiki 证据库管理
├── data/
│   ├── seed_evidence.jsonl        # 524 篇预索引文献
│   ├── demo_questions.json        # 10 题演示题库
│   ├── test_survey.json           # 128 题综合评估问卷
│   ├── evaluation_questions.json  # 基础评测问题集
│   ├── wiki_topics.jsonl          # Wiki 话题种子数据
│   └── chroma/                    # ChromaDB 持久化目录
├── scripts/
│   ├── evaluate.py                # 🆕 一键验收脚本
│   ├── run_evaluation.py          # RAG vs 裸LLM 对比评测
│   ├── run_survey_eval.py         # 128 题 5 部分评分
│   ├── expand_knowledge_base.py   # 知识库扩展
│   ├── ingest_markdown.py         # PDF/Markdown 导入
│   └── run_mcp_stdio.py           # MCP STDIO 入口
├── docs/
│   ├── architecture.md            # 系统架构
│   ├── ethics.md                  # 伦理准则与免责声明
│   └── mcp_setup.md              # MCP 配置指南
├── RULES.md                       # 🆕 项目规则文件
├── .env.example                   # 🆕 环境变量模板
├── requirements.txt               # Python 依赖
└── CHANGELOG.md                   # 变更日志
```

---

## 六、评测与验收

### 一键验收

```bash
python scripts/evaluate.py              # 完整评测（~25 min）
python scripts/evaluate.py --quick      # 快测抽查（< 2 min）
python scripts/evaluate.py --json       # JSON 输出（CI 用）
```

### 评测结果

| 评测 | 得分 | 满分 | 比例 |
|------|------|------|------|
| P1 域内知识问答 (96题) | 177 | 192 | 92% |
| P2 多轮追问 (12题) | 23.5 | 24 | 98% |
| P3 医疗边界 (10题) | 17 | 20 | 85% |
| P4 域外拒答 (5题) | 10 | 10 | 100% |
| P5 幻觉诱导对抗 (5题) | 7 | 10 | 70% |
| **总计 (128题)** | **234.5** | **256** | **92%** |

### 三层校验流程

| 层 | 方法 | 覆盖 | 频率 |
|----|------|------|------|
| L1 程序硬规则 | `check_safety()` + `verify_citations()` + `check_domain()` | 100% | 每次请求 |
| L2 LLM 语义打分 | `evaluate.py` 自动评分 | 全量题库 | 每次改动 |
| L3 人工复核 | P3/P5 高风险题型人工审查 | 边界题型 | 答辩前 |

---

## 七、常用命令

```bash
# 导入 PDF 文献
python scripts/ingest_markdown.py --pdf "文献.pdf" --title "标题" --source-url "https://..."

# 导入 Markdown 文献
python scripts/ingest_markdown.py --markdown "文献.md" --title "标题"

# 扩展知识库（Europe PMC 批量获取）
python scripts/expand_knowledge_base.py

# 启动 MCP STDIO 模式（Claude Desktop 集成）
python scripts/run_mcp_stdio.py

# 运行测试
pytest
```

---

## 八、使用边界与伦理声明

> ⚠️ **重要**：本系统用于**健康教育和文献线索整理**。不能替代医生诊断、治疗方案或紧急医疗服务。

- **不提供**：疾病诊断、用药建议、个体化食疗方案
- **不替代**：医生、注册营养师的面对面咨询
- **安全红线**：越界问题明确说明并引导线下就医
- **证据闭环**：所有结论标注来源，无证据时如实说明
- **AI 标注**：回答标注"AI 生成，建议人工复核"

完整伦理准则见 [`docs/ethics.md`](docs/ethics.md)。

---

## 九、答辩演示

### 固定演示流程（8 分钟）

1. **正常案例 1**：有充分证据的循证科普（如"地中海饮食与心血管风险"）
2. **正常案例 2**：多轮追问展示上下文理解
3. **拒答/边界案例**：域外问题或伪科学鉴别

### 备用方案

- 录屏备用（API / 网络崩溃时离线播放）
- 冻结模型版本和 Prompt，不现场调试

### 团队分工

- **主讲**：梳理主线故事线
- **操作**：执行演示，指向界面引用
- **备答**：应对评委追问

---

## 十、开发规范

见 [`RULES.md`](RULES.md) — 输出格式规范、安全拒答红线、证据分级标准、Git 提交规范、测试验收流程。

关键原则：
- 小步迭代，细粒度 Git 提交
- 每次改动后跑 `evaluate.py --quick`
- 不临期更换模型或乱改 Prompt
- `.env` 严禁提交到代码仓库

---

**让每一条健康建议都能找到依据。**
