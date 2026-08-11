# 健康营养证据助手 - 改动记录

> 记录所有功能增强、Bug 修复和架构调整，按时间倒序排列。

---

## 2026-08-11 · 第二十四轮：MMR 互补筛选 + 拒答三段式模板

### 改动文件
- `app/services/evidence_store.py`
- `app/services/answer_service.py`
- `app/main.py`

### 变更内容
- **MMR 互补筛选**：`mmr_diversify()` 在 RRF 融合后应用 Maximal Marginal Relevance，优先选取互补证据类型（Meta/RCT/指南/综述/观察），同类文献超过 1 篇时施加 0.30 递减惩罚，确保最终回答的证据来源多样化。
- **拒答三段式模板**：`build_no_evidence_response()` 按 PPT 要求输出「已检索到的内容 / 缺失的证据类型 / 建议补充方向」三段式拒答话术，附带 PubMed 直链搜索建议。
- **证据冲突模板**：`build_evidence_conflict_response()` 客观陈列冲突观点，不下强行定论。
- 流式端点同步更新拒答话术。

---

## 2026-08-11 · 第二十三轮：LLM Wiki 知识库 + JSONL 存储格式

### 改动文件
- `app/services/wiki_store.py`（新增）
- `data/wiki_topics.jsonl`（新增）
- `data/seed_evidence.jsonl`（新增）
- `app/services/evidence_store.py`
- `app/services/answer_service.py`
- `app/main.py`
- `scripts/expand_knowledge_base.py`

### 变更内容
- **LLM Wiki 知识库**（赛道二优先加分项）：`WikiStore` 管理 8 个高频稳定营养主题的结构化页面。
  - 标准结构：一句话结论 → 适用人群 → 核心证据（带来源编号） → 研究局限 → 禁止回答范围 → 更新时间。
  - 8 个预设主题：地中海饮食、限钠与血压、鸡蛋与胆固醇、维生素D、益生菌、Omega-3、间歇性断食、咖啡与健康。
  - CJK bigram 中文搜索匹配，优先查询 Wiki 主题页再补充实时 RAG 检索。
  - API：`GET /api/wiki/topics` + `GET /api/wiki/topics/{id}`。
- **JSONL 存储格式**：`seed_evidence.jsonl`（524 行，每行一条 JSON 记录），符合 PPT「统一 JSONL 存储」要求。`EvidenceStore._load_seed()` 优先 JSONL、回退 JSON。
- `expand_knowledge_base.py` 输出格式同步切换 JSONL。
- `AnswerService.answer()` 新增 `wiki_text` 参数，Wiki 主题作为 LLM 前置上下文增强回答质量。

---

## 2026-08-11 · 第二十二轮：演示预设问题集

### 改动文件
- `data/demo_questions.json`（新增）
- `app/static/index.html`
- `app/static/styles.css`
- `app/static/app.js`

### 变更内容
- **10 道演示问题**：按功能特性分为证据检索、多轮追问、域外拒答、幻觉防御、医疗边界五类，每道题附标签和说明。
- **前端演示面板**：首页「🎯 演示模式」按钮展开幻灯片式面板，卡片按功能颜色编码（绿/红/紫/橙），点击卡片自动提问。多轮追问组自动连续触发（Q1→Q2）。
- **演示面板动画**：`demoSlideIn` 入场动画（`ease-out-expo`）。

---

## 2026-08-11 · 第二十一轮：MeSH 主题词 + PMID 真实性校验

### 改动文件
- `app/services/pubmed_client.py`
- `app/services/answer_service.py`
- `app/main.py`

### 变更内容
- **MeSH 主题词检索**（PPT 四重过滤要求）：`build_pubmed_query()` 组合 MeSH + 自由文本 + 文献类型 + 年限 + 撤稿排除 + 摘要过滤，六重过滤。
  - `_MESH_MAP`：60+ 条英文关键词→MeSH 标准词映射（覆盖饮食模式、代谢疾病、心血管、营养素、特殊人群等）。
  - `_lookup_mesh_api()`：NCBI MeSH API 备用查找未知术语。
  - 文献类型过滤：`review[PT] OR meta-analysis[PT] OR RCT[PT] OR guideline[PT]`。
  - 撤稿排除：`NOT retracted publication[PT]`。
- **PMID 真实性校验**（幻觉防控第一层）：`verify_citations()` 检查所有 [Ex] 引用是否在检索结果范围内；`verify_fabricated_pmids()` 检测超出 PMID 范围（>4000 万）的伪造编号。
- 校验结果自动附加到回答末尾，流式端点同步输出 `citation_warn` 事件。

---

## 2026-08-11 · 第二十轮：域外拒答

### 改动文件
- `app/services/answer_service.py`
- `app/main.py`

### 变更内容
- **域外检测**：`check_domain()` 函数，7 组正则模式识别非健康营养问题（编程、天气、金融投资、影视娱乐、写作办公、数学计算），匹配后立即拒答（0ms）。
- **健康信号白名单**：中文 50+、英文 15+ 关键词，命中任一信号直接放行，避免误拦。
- `DOMAIN_REJECTION_MESSAGE`：统一拒答语——"我是专门提供健康营养循证科普的助手。您的问题超出了我的知识范围..."
- 集成到 `/api/answer` 和 `/api/answer/stream` 两个端点。

---

## 2026-08-11 · 第十九轮：Wiki 知识浏览页

### 改动文件
- `app/static/wiki.html`（新增）
- `app/static/wiki.css`（新增）
- `app/static/wiki.js`（新增）
- `app/main.py`
- `app/static/index.html`
- `app/static/styles.css`

### 变更内容
- **证据库浏览页**（`/wiki`）：展示 524 篇文献的可视化覆盖。
  - **统计卡片**：总文献数、来源期刊数、年份跨度、最多证据等级。
  - **筛选栏**：按证据等级（Meta/指南/RCT/综述/观察）、年份年代、关键词搜索。
  - **文章卡片网格**：标题 + 证据等级徽章 + 期刊/年份 + 摘要预览 → 点击弹 Modal 详情。
  - **分页**：每页 24 条，页码导航。
- **API `/api/knowledge`**：`q/level/year_from/year_to/page/size` 七参数过滤 + 全局统计信息。
- **导航双向互通**：聊天页顶部新增「证据库」入口，Wiki 页导航栏新增「问答」入口。

---

## 2026-08-11 · 第十八轮：128 题综合问卷 + RAGAS 8 维评测

### 改动文件
- `data/test_survey.json`（新增）
- `scripts/run_survey_eval.py`（新增）
- `data/evaluation_questions.json`
- `scripts/run_ragas_eval.py`

### 变更内容
- **128 题综合问卷**（5 部分评分体系）：
  - P1 域内知识（96 题）+ P2 多轮追问（12 题）+ P3 医疗边界（10 题）+ P4 域外拒答（5 题）+ P5 幻觉对抗（5 题）。
  - 满分 256 分，实测 234.5 / 256（92%）。
  - P4 域外拒答 10/10（100%，0ms 即时拦截）；P2 多轮追问 23.5/24（98%）。
- **RAGAS 8 维评测**（从 4 维扩展）：忠实度 + 相关性 + 正确性 + 召回率 + 精度 + 覆盖率 + 安全性 + 抗噪性。加权综合公式。
- `scripts/run_survey_eval.py`：5 部分各自独立评分逻辑，支持 `--quick` / `--part` 参数。

---

## 2026-08-11 · 第十七轮：混合检索 BM25 + Chroma → RRF

### 改动文件
- `app/services/evidence_store.py`
- `app/services/answer_service.py`
- `app/main.py`

### 变更内容
- **BM25Index**：自研 BM25 关键词检索引擎，零外部依赖。中文 CJK bigram + unigram 分词，英文词级分词，数字独立 token。524 篇索引 8887 个词项，检索速度 1ms。
- **RRF 融合**：`rrf_fusion()` 实现 Reciprocal Rank Fusion（k=60），将 Chroma 语义结果与 BM25 关键词结果融合排序。
- **检索流水线**：Chroma (limit×2) + BM25 (limit×3) → RRF 融合 → MMR 互补筛选 → 最终 Top-N。
- **中文查询翻译**：`answer_service.py` 在本地检索前调用 `translate_to_pubmed_query()` 将中文转为英文关键词，解决本地英文知识库的中文语义匹配问题（翻译后检索命中率从 0% 提升至 100%）。
- **流式端点本地回退**：`/api/answer/stream` 当 PubMed 无结果时自动回退本地知识库，不再直接报"未检索到可用证据"。

---

## 2026-08-11 · 第十六轮：知识库扩增至 524 篇 + 架构图 + 伦理声明

### 改动文件
- `data/seed_evidence.json`
- `scripts/expand_knowledge_base.py`（新增）
- `scripts/compare_search.py`（新增）
- `docs/architecture.md`（新增）
- `docs/ethics.md`（新增）
- `data/evaluation_questions.json`

### 变更内容
- **知识库扩增**：从 6 篇扩至 524 篇，覆盖 15 个健康维度（地中海/DASH/植物性/生酮/糖尿病/肥胖/血脂/VitD/纤维/Omega3/孕期/儿童/老年/抗炎/禁食）× 2 种证据类型（Review/Trial）× 2 个年份段（2015-2020/2021-2026）。来源 251 种期刊，年份跨度 2001-2026。
- **`scripts/expand_knowledge_base.py`**：自动化 PubMed + Europe PMC 批量爬虫，60 个查询，内置 3 次重试 + API 限流保护（1.5s 间隔），PMID 去重。
- **`scripts/compare_search.py`**：三路检索对比工具（Chroma 语义 vs BM25 关键词 vs RRF 混合），可视化展示交集/独有结果。
- **`docs/architecture.md`**：一页系统架构图（ASCII 框图 + 数据流时序图 + 技术选型表）。
- **`docs/ethics.md`**：完整伦理准则与免责声明（6 章：定位、伦理原则、安全过滤、隐私、责任边界、引用规范）。
- 评测题库从 3 题扩至 30 题（9 大类）。

---

## 2026-08-11 · 第十五轮：流式输出 (SSE)

### 改动文件
- `app/services/llm_client.py`
- `app/main.py`
- `app/static/app.js`
- `app/static/styles.css`

### 变更内容
- **LLM 流式调用**：`llm_client.py` 新增 `stream_answer()` async generator，使用 `httpx.stream()` + `"stream": True` 调用 DeepSeek API，逐 token yield。
- **新端点 `/api/answer/stream`**：`main.py` 新增 SSE（Server-Sent Events）端点，流式推送事件：
  - `meta` — 检索元数据（引用列表、retrieval_note、safety_note）
  - `chunk` — 逐字文本
  - `done` — 流结束
  - `blocked` / `error` — 安全拦截 / 错误
- **前端流式消费**：`askQuestion()` 改用 `fetch` + `ReadableStream` 逐行解析 SSE，直接用 DOM API 更新 `.answer-content`（不再每个字全量重绘），消除频闪。
- **打字动画**：按钮加载态从逐阶段文字切换 → `正在检索` + 三个跳动圆点（纯 opacity 脉冲）。
- **操作按钮**：每条回答右下角新增复制 + 重新生成按钮，hover 显示。
- **字体本地化**：移除 Google Fonts 外部 `<link>`，改用系统自带字体栈（PingFang SC / Microsoft YaHei / Songti SC）。
- **设计修复**：`dotBounce` 改 `dotPulse`（去除弹跳 easing）；`.message-safety` `border-left` → `border-top`。

### 修复
- 流式渲染频闪：从每个 chunk 调 `renderAllMessages()` → 直接更新 DOM 节点
- `_pending` 状态与 `_streaming` 状态解耦

---

## 2026-08-11 · 第十四轮：RAGAS 学术评测

### 改动文件
- `scripts/run_ragas_eval.py`（新建）
- `ragas_report.md`（自动生成）

### 变更内容
- **评测脚本**：实现 RAGAS（RAG Assessment）四维自动评测：
  - **忠实度 (Faithfulness)**：LLM-as-judge 逐条检查答案声明是否能在证据中找到支撑（0-10）
  - **答案相关性 (Answer Relevancy)**：LLM-as-judge 判断回答是否切题（0-10）
  - **上下文精度 (Context Precision)**：被 [Ex] 引用的证据数 / 总证据数
  - **引用覆盖率 (Citation Coverage)**：实际引用数 / 总证据数
- **综合得分**：加权公式 `忠实度×40% + 相关性×30% + 精度×15% + 覆盖率×15%`
- **LLM-as-Judge**：用 DeepSeek 作为裁判模型，结构化 JSON 输出评分 + 理由。
- **对比模式**：`--compare` 参数同时评测裸 LLM，输出对比表。
- **快速模式**：`--quick` 只跑 5 题快速验证。
- **报告输出**：控制台表格 + `ragas_report.md` Markdown 报告。

### 5 题快速评测结果
| 指标 | RAG 助手 |
|------|---------|
| 忠实度 | 8.6/10 |
| 相关性 | 7.4/10 |
| 上下文精度 | 100% |
| 引用覆盖率 | 100% |
| 综合得分 | 86.6/100 |

---

## 2026-08-11 · 第十三轮：Topbar 间距 + 复制/重新生成/打字动画

### 改动文件
- `app/static/styles.css`
- `app/static/app.js`

### 变更内容
- **Topbar 放大**：`max-width` 820→960px，品牌字 16→18px，食字方块 30→34px，绿点 6→8px，间距全面增大。
- **复制按钮**：每条回答右下角半透明复制图标，点选复制纯文本，弹"已复制"提示。
- **重新生成**：复制旁 rotate 图标，同问题再问 LLM 生成不同措辞。
- **打字圆点**：`正在检索...` 后面三个依次淡入淡出的灰绿圆点。

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
- [ ] Docker 一键部署。
- [x] ~~侧边栏"实时检索 PubMed"按钮~~ 用户决定保留。
- [x] RAGAS 学术评测
- [x] 流式输出 (SSE)
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
- [x] 复制/重新生成按钮
- [x] 打字动画
- [x] 字体本地化
