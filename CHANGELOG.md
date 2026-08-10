# 健康营养证据助手 - 改动记录

> 记录所有功能增强、Bug 修复和架构调整，按时间倒序排列。

---

## 2026-08-10 · 第十二轮：Taste-skill 去 AI 味

### 改动文件
- `app/static/styles.css`
- `app/static/index.html`

### 变更内容
- **Em-dash 清零**：CSS 注释中所有 `—` 替换为 `-`；HTML `<title>` 和 `og:title` 中 `—` 替换为 `·`（全站零 em-dash，通过 taste-skill 禁令）。
- **Design Read**: 消费者健康问答 App / Operate 模式 / 柔和结构主义，`VARIANCE:5 / MOTION:4 / DENSITY:2`。
- 审查结论：无 AI 紫渐变、无 eyebrow（已删）、无三列等宽卡片、无 Inter 字体、无 scroll cue、无版本号、无章节编号、无装饰点。配色一致（单绿 accent），形状体系一致（pill 交互 / soft 容器）。

---

## 2026-08-10 · 第十一轮：Impeccable Polish 最终质量

### 改动文件
- `app/static/styles.css`
- `app/static/index.html`
- `app/static/app.js`

### 变更内容
- **Eyebrow 删除**：craft-floor 明确禁止 kicker/eyebrow，移除 `.eyebrow` HTML 元素及所有 CSS。
- **Unicode 图标替换为 SVG**：
  - 空状态 `+` → 搜索放大镜 SVG（Phosphor 风格，`stroke-width:1.5`）
  - 新对话按钮 `+` → 加号线 SVG（`stroke-width:2`）
  - 消息前缀 `Q` 伪元素 → 问号圆圈 SVG（`stroke-width:2`）
- **h1 `transition: font-size` 移除**：避免 layout thrash。
- **Shimmer 骨架屏动画**：`ease-in-out-expo` → `linear`。
- **textarea 加 `maxlength="500"`**：与服务端校验一致。
- **死代码清理**：`.eyebrow` CSS、`.empty-icon` 无用 `font-size`/`font-weight`。
- **Detector 结果: 0 发现**。

---

## 2026-08-10 · 第十轮：Soft-skill 柔和 UI 重写

### 改动文件
- `app/static/styles.css`（重写）
- `app/static/index.html`

### 变更内容
- **Vibe**: Soft Structuralism（银灰白底 + 大胆 Grotesk + 超软漫射阴影 + 大量留白）。
- **导航栏**：从贴顶全宽横条 → 悬浮玻璃胶囊（`top:16px` 不贴边，`backdrop-blur` + 半透明白底）。
- **标题**：50px / weight 750 / `letter-spacing: -0.015em` / `text-wrap: balance`。
- **阴影系统**：三层漫射阴影（ambient / float / modal），全部用 `var(--ink)` 调色。
- **卡片**：去硬边框 `border: 1px solid rgba(0,0,0,.03)` + 漫射阴影 + hover 上浮。
- **输入框**：超软边框 + focus 时绿色光环 `box-shadow: 0 0 0 4px`。
- **按钮**：全圆药丸 `border-radius: 999px`，hover 上浮 + 辉光，active `scale(.97)`。
- **过渡曲线**：全部替换为自定义 `cubic-bezier`（ease-spring / ease-out-expo）。
- **容器**：820px 聚焦阅读宽度。
- **字体平滑**：`-webkit-font-smoothing: antialiased`。
- **徽章**：全部圆药丸 `border-radius: 999px`。
- **关键词高亮**：从实色块 → 渐变下划线式。
- **空状态**：虚线边框卡片 + 温暖背景。
- **骨架屏**：shimmer 动画骨架条。
- **布局间距**：intro 64px，消息间距 36px，大量留白。
- **修复 `side-tab`**：安全声明从左侧竖条 → 顶部细线。
- **修复 `layout-transition`**：移除 intro padding 过渡动画。

### Design Hook 通过项
- `side-tab` 修复（`.message-safety` `border-left` → `border-top`）
- `layout-transition` 修复（移除 `.intro` padding 过渡）

---

## 2026-08-10 · 第九轮：结构化模板 + 关键词高亮 + 食材风险 + 饮食方案 + 偏方鉴别 + 来源可视化

### 改动文件
- `app/services/llm_client.py`
- `app/services/answer_service.py`
- `app/static/app.js`
- `app/static/styles.css`

### #5 结构化答案模板
- SYSTEM_PROMPT 重写，要求所有回答按固定结构输出：
  - `【通俗总结】` — 一两句话直接回答核心问题
  - `【核心科学依据】` — 详细展开，逐条引用证据
  - `【日常落地做法】` — 可操作建议（怎么吃、吃多少）
  - `【注意事项】` — 禁忌人群、药物相互作用、研究分歧
- 允许使用 `【】` 中文方括号作为段落标题（不是 markdown）

### #6 关键词高亮
- `app.js` 新增 40+ 术语高亮词表（按长度降序排列）
- `renderAnswer()` 在 `escapeHtml` 之后、引用链接之前插入 `<mark class="kw">` 标签
- CSS：`.kw` 浅绿背景 + 深绿文字，不干扰阅读

### #7 食材风险查询
- SYSTEM_PROMPT 内置食材风险场景指引
- 自动输出适宜/禁忌人群、摄入量上限、与药物的相互作用

### #8 饮食方案简易生成
- SYSTEM_PROMPT 内置饮食方案生成场景指引
- 输出具体三餐示例 + 能量级别 + "个体差异大，建议咨询营养师微调"

### #9 偏方鉴别
- SYSTEM_PROMPT 内置偏方鉴别场景指引
- 检索证据后给出科学性判断（有证据支持 / 证据不足 / 伪科学）
- 同时修复安全拦截：`偏方` 关键词从无条件拦截改为"求偏方"/"推偏方"语境拦截，允许"这个说法科学吗"类探究性问题通过

### #11 检索来源可视化
- `app.js` 重写 `renderCitations()`：每条引用带彩色证据等级徽章
  - Meta 分析 → 金色 `Meta`
  - 临床指南 → 蓝色 `指南`
  - RCT → 绿色 `RCT`
  - 综述 → 青色 `综述`
  - 观察性研究 → 灰色 `观察`
- 引用面板默认展开（`<details open>`）
- 显示"文中引用 N 条"计数
- 修复引用链接锚点 bug（`messages.length` → `msgIndex`）
- CSS 新增 `.ev-badge` 5 种颜色变体

---

## 2026-08-10 · 第八轮：观点冲突整理

### 改动文件
- `app/services/llm_client.py`

### 变更内容
- **SYSTEM_PROMPT 新增冲突处理规则**：当多条证据结论矛盾时，LLM 必须输出"研究分歧"段落，客观罗列正反双方证据编号。
- 规则要点：
  - 按证据等级说明倾向（如系统综述 vs 观察性研究），不强行站队。
  - 证据方向一致时无需输出分歧段落。
  - 示例格式已写入 prompt。

### 同时修复
- `app/static/styles.css`：
  - `.intro` 移除 `transition: padding`（避免 layout thrash，保留 font-size 过渡）。
  - `.message-safety` 左边框 3px → 1px（更微妙的设计规范）。

---

## 2026-08-10 · 第七轮：结果重排

### 改动文件
- `app/main.py`

### 变更内容
- 新增 `_rerank_chunks()` 函数，在 PubMed + Europe PMC 检索合并后对证据进行重排。
- **评分算法**：
  - 权威性（60%）：从标题识别研究类型
    | 研究类型 | 得分 |
    |---|---|
    | 系统综述 / Meta 分析 | 1.0 |
    | 临床指南 / 专家共识 | 0.9 |
    | 随机对照试验 | 0.8 |
    | 综述 | 0.7 |
    | 观察性研究 | 0.5 |
    | 病例报告 | 0.3 |
    | 其他 | 0.4 |
  - 时效性（40%）：按出版年份计分，越新越高。
- `evidence_level` 字段同步更新为具体研究类型标签（不再显示笼统的"实时检索"）。
- 取 top 8 条传入 LLM。

---

## 2026-08-10 · 第六轮：日志系统

### 改动文件
- `app/services/query_logger.py`（新建）
- `app/main.py`
- `.gitignore`

### 变更内容
- 新建 `QueryTrace` 类，记录每次问答的完整链路。
- 日志格式：JSONL（每行一条 JSON），写入 `logs/queries.jsonl`。
- 记录字段：
  - `type` — 事件类型（`answer` / `safety_block`）
  - `question` — 用户问题（截断至 300 字）
  - `conversation_id` — 会话 ID（多轮对话追溯）
  - `searches` — 各数据源检索查询词及命中数
  - `llm_used` — 是否成功调用 LLM
  - `citations` — 引用数量
  - `blocked` / `block_reason` — 安全拦截标记
  - `errors` — 异常信息
  - `duration_ms` — 总耗时（毫秒）
  - `ts` — UTC 时间戳
- 自动轮转：单文件超过 10MB 自动归档为 `queries_YYYYMMDD_HHMMSS.jsonl`。
- `logs/` 已加入 `.gitignore`。

---

## 2026-08-10 · 第五轮：多轮对话

### 改动文件
- `app/schemas.py`
- `app/services/answer_service.py`
- `app/main.py`
- `app/static/index.html`（重写）
- `app/static/styles.css`（重写）
- `app/static/app.js`（重写）

### 后端变更
- `QuestionRequest` 新增 `conversation_id` 可选字段。
- 新增 `_build_context()`：将最近 5 轮问答历史拼接进 LLM prompt，使追问能理解上下文。
- 新增 `_remember()`：每轮回答后记录问答对，供后续追问使用。
- 会话存储：进程内 `dict`，重启丢失（演示用途）。

### 前端变更
- **聊天式界面**：消息列表 + 底部固定输入框，替代原来单次问答展示。
- 每条消息包含：用户问题气泡 + 回答 + 引用来源（可折叠）+ 安全声明。
- 新消息自动滚动到底部，带淡入动画。
- **多轮追问**：首问自动生成 `conversation_id`，后续请求自动携带，LLM 结合上下文回答。
- **"+ 新对话"按钮**：重置会话，清空历史。
- Intro 区域在有消息后自动收折，释放屏幕空间。
- 引用链接按消息编号锚定（`#citation-{msgIndex}-E{num}`），避免多轮间引用 ID 冲突。
- Ctrl+Enter 快捷发送。

---

## 2026-08-10 · 第四轮：评测题库 + 对比评测

### 改动文件
- `data/evaluation_questions.json`（重写）
- `scripts/run_evaluation.py`（重写）

### 变更内容
- **题库扩容**：从 3 题扩展到 30 题，覆盖 9 个分类：
  - 饮食模式、三高管理、食材功效、营养素、特殊人群、运动营养、体重管理、疾病管理、食品安全
- **评测脚本**：自动对比 RAG 助手 vs 裸大模型
- **4 维自动评分**（满分 10）：
  - 引用率（3 分）：是否有 `[E1]` 等证据标注
  - 幻觉风险（3 分）：是否编造 PMID、精确百分比、虚假期刊
  - 可读性（2 分）：中文长度 ≥80 字、无 markdown 格式
  - 安全边界（2 分）：是否包含免责声明关键词
- 输出控制台对比表格 + `evaluation_report.md` Markdown 报告。

---

## 2026-08-10 · 第三轮：检索过滤（年份 + 文献类型）

### 改动文件
- `app/services/pubmed_client.py`
- `app/services/source_plugins.py`

### 变更内容
- **PubMed 日期过滤**：查询自动追加 `AND (mindate[pdat]:maxdate[pdat])`，默认限定近 10 年。
- **Europe PMC 日期过滤**：查询自动追加 `AND (PUB_YEAR:[X TO Y])`，默认限定近 10 年。
- 两边的 `max_age_years` 参数默认 10，可按需调整。
- PubMed 查询增加 `sort=relevance` 明确按相关度排序。

---

## 2026-08-10 · 第二轮：Europe PMC 接入

### 改动文件
- `app/services/source_plugins.py`
- `app/services/pubmed_client.py`
- `app/main.py`
- `app/services/answer_service.py`

### 变更内容
- `EuropePmcOpenAccessPlugin` 新增 `search()` 方法，实时检索 Europe PMC REST API。
- PubMed 和 Europe PMC 文章均标记 `_source` 字段，用于区分来源。
- `main.py` 使用 `asyncio.gather` 并行检索 PubMed（6 条）+ Europe PMC（4 条）。
- 按 PMID 去重合并，避免重复文献。
- 某个数据源挂了不影响另一个。
- 前端检索来源标签改为"多源实时检索（PubMed + Europe PMC）"。

---

## 2026-08-10 · 第一轮：敏感内容拦截

### 改动文件
- `app/services/answer_service.py`
- `app/main.py`

### 变更内容
- 新增 11 条正则拦截规则，覆盖：
  - 偏方 / 伪科学（偏方、排毒、酸碱体质、辟谷、灌肠、尿疗）
  - 替代医疗（不吃药、停药能好吗）
  - 食疗治病（吃 XX 能治愈、根治）
  - 代替药物（饮食替代降压药 / 降糖药）
  - 要求诊断（我这是什么病）
  - 用药建议（该吃什么药）
  - 危险偏方（生吃泥鳅 / 蛇胆、何首乌 / 马兜铃等肝肾毒性药材）
- 拦截发生在 PubMed 检索和 LLM 调用**之前**，零开销。
- 被拦截返回："基于安全与伦理准则，[具体原因]"。

---

## 历史改动（上一轮会话）

### LLM 配置修复
- `app/services/llm_client.py`：添加 `load_dotenv()`，修复 `.env` 未加载导致 LLM 永远未配置的问题。

### PubMed 实时检索接入
- `app/main.py`：`/api/answer` 改为 `async def`，自动调用 PubMed 搜索。
- 新增 `_pubmed_to_chunks()` 将 PubMed API 结果转为 `EvidenceChunk`。

### 中文查询翻译
- `llm_client.py`：新增 `translate_to_pubmed_query()`，LLM 将中文问题翻译为英文 PubMed 关键词。
- 新增 16 组中文→英文关键词保底映射表（`_KEYWORD_MAP`），覆盖地中海饮食、高血压、糖尿病、减肥、肠道、维生素、运动、孕期、儿童、抗炎、心血管、肾病、痛风、补钙、发烧等。
- 清洗 LLM 输出中的方括号、引号等特殊字符。

### PubMed 优先于本地种子
- `answer_service.py`：新增 `skip_local` 参数，PubMed 有结果时跳过 Chroma 本地检索。
- `extra_evidence` 和 `pubmed_error` 参数贯穿 answer 流程。

### 引用格式修复
- `SYSTEM_PROMPT` 明确要求英文方括号 `[E1]`。
- 引用校验从严格白名单放宽为最低检查 `re.search(r"\[E\d+\]", text)`。

### Markdown 格式禁止
- `SYSTEM_PROMPT` 明确禁止 `##`、`**`、`-` 列表、`1.` 列表、`---` 分隔线。
- 前端 `renderMarkdown` 重命名为 `renderAnswer`，去除 `###` 标题匹配。

### 前端改进
- `app.js`：请求体包含 `include_pubmed: true`。
- 按钮加载阶段提示（正在分析问题 → 正在检索 PubMed → 正在检索本地证据 → 正在生成回答）。
- `retrieval_note` 显示在回答上方。
- LLM 超时 25s → 60s。

### 静默失败修复
- PubMed 异常不再静默吞掉，通过 `pubmed_error` 反馈到前端 `retrieval_note`。

---

## 架构总览

```
用户提问 (index.html + app.js)
    │
    ▼
安全拦截 (check_safety)
    │ 通过
    ▼
查询翻译 (translate_to_pubmed_query)
    │
    ├─ 并行检索 ─────────────────────┐
    │  PubMed (pubmed_client)         │
    │  Europe PMC (source_plugins)    │
    │       │                         │
    │       ▼                         │
    │  去重合并 (_pubmed_to_chunks)    │
    │       │                         │
    │       ▼                         │
    │  结果重排 (_rerank_chunks)       │
    │       │                         │
    │       ▼                         │
    │  本地 Chroma 检索 (skip_local)   │
    │       │                         │
    │       ▼                         │
    │  证据合并 (combined)            │
    │       │                         │
    │       ▼                         │
    │  LLM 回答 (llm_client.answer)   │
    │  含：历史上下文 + 观点冲突识别   │
    │       │                         │
    │       ▼                         │
    │  记录日志 (query_logger)        │
    │       │                         │
    │       ▼                         │
    │  返回前端 (AnswerResponse)      │
    │       │                         │
    │       ▼                         │
    └── 渲染聊天消息                  │
        会话记忆 (_remember)          │
```

---

## 测试

```bash
# 启动服务器
cd D:\health-nutrition-evidence-assistant
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 安全拦截测试
curl -X POST http://127.0.0.1:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"偏方能治高血压吗？","include_pubmed":false}'

# 正常检索测试
curl -X POST http://127.0.0.1:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"地中海饮食有什么好处？","include_pubmed":true,"conversation_id":"test-001"}'

# 多轮追问测试
curl -X POST http://127.0.0.1:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"日常三餐怎么落地？","include_pubmed":false,"conversation_id":"test-001"}'

# 评测
python scripts/run_evaluation.py

# 查看日志
cat logs/queries.jsonl
```

---

## 待办

- [ ] 暗色模式（taste-skill 建议 consumer-facing 页面应双模式）。
- [ ] PubMed 检索超时重试机制。
- [ ] 前端关键词高亮对英文术语的支持（当前仅支持中文术语）。
- [x] ~~侧边栏"实时检索 PubMed"按钮~~ 用户决定保留，不删除。
- [x] 结构化答案模板
- [x] 偏方鉴别
- [x] 评测题库对比评测
- [x] 多轮对话
- [x] 结果重排
- [x] 观点冲突整理
- [x] 关键词高亮
- [x] 食材风险查询
- [x] 饮食方案生成
- [x] 检索来源可视化
- [x] 聊天对话窗口 UI
- [x] 混合检索
- [x] 敏感内容拦截
- [x] Europe PMC 接入
- [x] PubMed 日期过滤
- [x] 日志系统
- [x] 前端设计重写（Soft Structuralism + Polish + Taste-skill）
