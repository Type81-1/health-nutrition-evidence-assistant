"""可配置工作流引擎 —— D2 文档进阶模块。

将硬编码的 answer() 流程抽象为可配置的 Pipeline：
- 步骤可独立开关（enabled/disabled）
- 顺序可调整
- 新步骤可插入，不影响现有步骤
- 每个步骤有独立的 handler 和配置
- Pipeline 定义存储在 JSON 配置文件中

适用场景：
- A/B 测试：不同配置对比效果
- 渐进调试：逐个关闭步骤定位问题
- 功能迭代：加新步骤不需要改核心代码
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = PROJECT_ROOT / "data" / "pipeline_config.json"


@dataclass
class PipelineStep:
    """工作流中的单个步骤。"""
    name: str
    description: str
    handler: Callable  # async (context: PipelineContext) -> PipelineContext
    enabled: bool = True
    config: dict = field(default_factory=dict)
    category: str = "core"


@dataclass
class PipelineContext:
    """流经 Pipeline 的上下文对象。步骤间通过此对象传递数据。"""
    question: str = ""
    conversation_id: str | None = None

    # 中间状态
    translated_query: str = ""
    wiki_text: str | None = None
    wiki_topic_id: str | None = None
    local_evidence: list = field(default_factory=list)
    pubmed_evidence: list = field(default_factory=list)
    combined_evidence: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    answer_text: str = ""

    # 控制标志
    domain_blocked: bool = False
    domain_reason: str = ""
    safety_blocked: bool = False
    safety_reason: str = ""
    no_evidence: bool = False
    citation_invalid: bool = False

    # 元数据
    errors: list[str] = field(default_factory=list)
    retrieval_note: str = ""
    step_traces: list[dict] = field(default_factory=list)  # 每个步骤的执行记录

    def trace(self, step_name: str, outcome: str, detail: str = "") -> None:
        self.step_traces.append({
            "step": step_name,
            "outcome": outcome,
            "detail": detail,
        })


class Pipeline:
    """可配置的工作流管线。"""

    def __init__(self, steps: list[PipelineStep] | None = None):
        self.steps: list[PipelineStep] = steps or []
        self._name: str = "unnamed"

    @property
    def enabled_steps(self) -> list[PipelineStep]:
        return [s for s in self.steps if s.enabled]

    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]

    def active_step_names(self) -> list[str]:
        return [s.name for s in self.enabled_steps]

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        """按顺序执行所有启用的步骤。"""
        for step in self.enabled_steps:
            try:
                ctx = await step.handler(ctx)
                ctx.trace(step.name, "ok")
            except Exception as e:
                ctx.trace(step.name, "error", str(e))
                ctx.errors.append(f"[{step.name}] {type(e).__name__}: {e}")
                # 关键步骤失败则终止
                if step.category in ("safety", "core"):
                    break
        return ctx

    def to_dict(self) -> dict:
        return {
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "enabled": s.enabled,
                    "category": s.category,
                    "config": s.config,
                }
                for s in self.steps
            ]
        }

    def save(self, path: Path | None = None) -> None:
        path = path or PIPELINE_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> dict:
        """加载配置文件（不重建 Pipeline，仅返回配置字典）。"""
        path = path or PIPELINE_CONFIG_PATH
        if not path.exists():
            return {"steps": []}
        return json.loads(path.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════
# 步骤 Handler（从 answer_service / main.py 提取）
# ═══════════════════════════════════════════════════════════════

_SAFETY_NOTE = (
    "这是健康科普，不替代个体化诊疗。正在使用降压药、降脂药、利尿剂，或处于孕期、"
    "有肾病/心衰等情况时，请先与医生或注册营养师讨论饮食调整。"
)


async def _step_domain_check(ctx: PipelineContext) -> PipelineContext:
    """步骤 1: 域外检测"""
    from app.services.answer_service import check_domain
    domain = check_domain(ctx.question)
    if not domain.safe:
        ctx.domain_blocked = True
        ctx.domain_reason = domain.reason
        ctx.answer_text = "我是专门提供健康营养循证科普的助手。您的问题超出了我的知识范围，请提出与饮食、营养、慢性病预防等相关的问题。"
    return ctx


async def _step_safety_check(ctx: PipelineContext) -> PipelineContext:
    """步骤 2: 安全检测"""
    from app.services.answer_service import check_safety
    safety = check_safety(ctx.question)
    if not safety.safe:
        ctx.safety_blocked = True
        ctx.safety_reason = safety.reason
        ctx.answer_text = f"基于安全与伦理准则，{safety.reason}"
    return ctx


async def _step_query_translation(ctx: PipelineContext) -> PipelineContext:
    """步骤 3: 中文查询翻译"""
    from app.services.llm_client import OpenAICompatibleLlm
    llm = OpenAICompatibleLlm()
    ctx.translated_query = llm.translate_to_pubmed_query(ctx.question) or ctx.question
    return ctx


async def _step_wiki_lookup(ctx: PipelineContext) -> PipelineContext:
    """步骤 4: Wiki 主题匹配"""
    from app.services.wiki_store import WikiStore
    wiki = WikiStore()
    hits = wiki.search(ctx.question, top_n=1)
    if hits:
        ctx.wiki_text = hits[0].to_text()
        ctx.wiki_topic_id = hits[0].id
    return ctx


async def _step_local_search(ctx: PipelineContext) -> PipelineContext:
    """步骤 5: 本地知识库检索"""
    from app.services.evidence_store import EvidenceStore
    store = EvidenceStore()
    search_q = ctx.translated_query or ctx.question
    ctx.local_evidence = store.search(search_q, limit=4)
    return ctx


async def _step_combine_evidence(ctx: PipelineContext) -> PipelineContext:
    """步骤 6: 合并证据"""
    all_ev = list(ctx.pubmed_evidence) + list(ctx.local_evidence)
    seen = set()
    unique = []
    for c in all_ev:
        cid = getattr(c, 'id', str(c))
        if cid not in seen:
            seen.add(cid)
            unique.append(c)
    ctx.combined_evidence = unique
    if not ctx.combined_evidence:
        ctx.no_evidence = True
    return ctx


async def _step_llm_generate(ctx: PipelineContext) -> PipelineContext:
    """步骤 7: LLM 生成回答"""
    from app.services.llm_client import OpenAICompatibleLlm
    llm = OpenAICompatibleLlm()
    from app.services.answer_service import _build_context
    context_q = _build_context(ctx.conversation_id, ctx.question)

    # Wiki 增强
    llm_q = context_q
    if ctx.wiki_text:
        llm_q = f"以下为系统预整理的高频主题知识：\n\n{ctx.wiki_text}\n\n---\n{context_q}"

    answer = llm.answer(llm_q, ctx.combined_evidence)
    if answer is None:
        from app.services.answer_service import _build_consumer_answer
        answer = _build_consumer_answer(ctx.question, ctx.combined_evidence)
    ctx.answer_text = answer
    return ctx


async def _step_citation_verify(ctx: PipelineContext) -> PipelineContext:
    """步骤 8: 引用真实性校验"""
    from app.services.answer_service import verify_citations, verify_fabricated_pmids
    cit_ok = verify_citations(ctx.answer_text, len(ctx.combined_evidence))
    fake_pmids = verify_fabricated_pmids(ctx.answer_text)
    if not cit_ok.valid or fake_pmids:
        ctx.citation_invalid = True
    return ctx


async def _step_build_retrieval_note(ctx: PipelineContext) -> PipelineContext:
    """步骤 9: 构建检索来源说明"""
    parts = []
    if ctx.wiki_topic_id:
        from app.services.wiki_store import WikiStore
        wiki = WikiStore()
        topic = wiki.get_topic(ctx.wiki_topic_id)
        if topic:
            parts.append(f"Wiki「{topic.title}」+ ")
    if ctx.local_evidence:
        from app.services.evidence_store import EvidenceStore
        store = EvidenceStore()
        parts.append(f"{store.backend} 选取 {len(ctx.local_evidence)} 条")
    elif ctx.pubmed_evidence:
        parts.append(f"PubMed 实时检索 {len(ctx.pubmed_evidence)} 条")
    ctx.retrieval_note = "".join(parts) if parts else "未检索到可用证据"
    return ctx


# ═══════════════════════════════════════════════════════════════
# 默认 Pipeline 定义（当前系统全部功能）
# ═══════════════════════════════════════════════════════════════

def build_default_pipeline() -> Pipeline:
    """构建默认的完整 Pipeline。"""
    return Pipeline(steps=[
        PipelineStep("domain_check", "域外检测（非健康问题拒答）", _step_domain_check, enabled=True, category="safety"),
        PipelineStep("safety_check", "安全红线检测（偏方/伪科学/用药等）", _step_safety_check, enabled=True, category="safety"),
        PipelineStep("query_translation", "中文→英文查询翻译", _step_query_translation, enabled=True),
        PipelineStep("wiki_lookup", "Wiki 高频主题匹配", _step_wiki_lookup, enabled=True),
        PipelineStep("local_search", "本地知识库混合检索（BM25+Chroma→RRF→MMR）", _step_local_search, enabled=True),
        PipelineStep("combine_evidence", "证据合并去重", _step_combine_evidence, enabled=True),
        PipelineStep("llm_generate", "LLM 生成回答（含 Skill 动态 Prompt）", _step_llm_generate, enabled=True, category="core"),
        PipelineStep("citation_verify", "引用真实性校验 + 伪造 PMID 检测", _step_citation_verify, enabled=True),
        PipelineStep("build_retrieval_note", "构建检索来源说明", _step_build_retrieval_note, enabled=True),
    ])


def build_light_pipeline() -> Pipeline:
    """构建轻量 Pipeline（关闭 Wiki + PubMed，仅本地 KB）。"""
    p = build_default_pipeline()
    for s in p.steps:
        if s.name == "wiki_lookup":
            s.enabled = False
    return p


def build_full_pipeline() -> Pipeline:
    """构建全功能 Pipeline（所有步骤开启）。"""
    return build_default_pipeline()
