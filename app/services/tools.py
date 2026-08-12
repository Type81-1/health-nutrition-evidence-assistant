"""标准化工具层（Tool Layer）—— D2 文档必做模块。

每个工具遵循统一规范：
- 单一职责，只做一件事
- 输入输出标准化 JSON
- 异常结构化返回（不抛裸异常）
- 附带 JSON Schema 定义（未来可用于 MCP 封装）

工具清单：
  search_pubmed       — 按年份、文献类型检索 PubMed
  verify_citation      — 核验引用 ID 真实性 + 伪造 PMID 检测
  get_trial_record     — 查询 ClinicalTrials.gov 临床试验 NCT 编号
  format_evidence_card — 标准化证据卡片输出
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app.services.pubmed_client import PubMedClient
from app.services.answer_service import verify_citations, verify_fabricated_pmids
from app.services.evidence_store import EvidenceChunk


# ═══════════════════════════════════════════════════════════════
# Tool 标准化接口
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolSpec:
    """单个工具的完整定义。"""
    name: str
    description: str
    input_schema: dict  # JSON Schema
    handler: Callable[[dict], Awaitable[dict]]  # async (input) -> output
    category: str = "general"  # retrieval / verification / formatting


@dataclass
class ToolResult:
    """标准化工具返回。"""
    success: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════
# Tool 1: search_pubmed
# ═══════════════════════════════════════════════════════════════

SEARCH_PUBMED_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "英文 PubMed 检索关键词"},
        "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        "max_age_years": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30},
    },
    "required": ["query"],
}

_pubmed_client = PubMedClient()


async def search_pubmed_handler(input: dict) -> dict:
    """检索 PubMed 文献。"""
    query = input.get("query", "")
    limit = input.get("limit", 5)
    max_age = input.get("max_age_years", 10)

    if not query.strip():
        return ToolResult(success=False, error="查询关键词不能为空").to_dict()

    try:
        articles = await _pubmed_client.search(
            query=query, limit=limit, max_age_years=max_age
        )
        return ToolResult(
            success=True,
            data={
                "count": len(articles),
                "articles": [
                    {
                        "pmid": a.get("pmid", ""),
                        "title": a.get("title", "")[:120],
                        "journal": a.get("journal", ""),
                        "year": a.get("year", ""),
                        "pub_types": a.get("pub_types", ""),
                        "url": a.get("url", ""),
                    }
                    for a in articles
                ],
            },
        ).to_dict()
    except Exception as e:
        return ToolResult(success=False, error=f"PubMed 检索失败: {type(e).__name__}").to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool 2: verify_citation
# ═══════════════════════════════════════════════════════════════

VERIFY_CITATION_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_text": {"type": "string", "description": "待校验的回答文本"},
        "evidence_count": {"type": "integer", "description": "检索到的证据总数"},
    },
    "required": ["answer_text", "evidence_count"],
}


async def verify_citation_handler(input: dict) -> dict:
    """核验回答中的引用是否真实存在。"""
    answer_text = input.get("answer_text", "")
    evidence_count = input.get("evidence_count", 0)

    if not answer_text:
        return ToolResult(success=False, error="回答文本不能为空").to_dict()

    # 第一层：引用范围校验
    cit_result = verify_citations(answer_text, evidence_count)
    # 第二层：伪造 PMID 检测
    fake_pmids = verify_fabricated_pmids(answer_text)

    return ToolResult(
        success=True,
        data={
            "citation_check": {
                "valid": cit_result.valid,
                "total_refs": cit_result.total_refs,
                "valid_refs": cit_result.valid_refs,
                "fabricated_refs": cit_result.fabricated_refs,
                "reason": cit_result.reason,
            },
            "pmid_check": {
                "suspicious_pmids": fake_pmids,
                "has_fabricated": len(fake_pmids) > 0,
            },
        },
    ).to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool 3: get_trial_record
# ═══════════════════════════════════════════════════════════════

GET_TRIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "nct_id": {"type": "string", "description": "临床试验 NCT 编号，如 NCT01234567"},
    },
    "required": ["nct_id"],
}

_CLINICAL_TRIALS_API = "https://clinicaltrials.gov/api/v2/studies"


async def get_trial_record_handler(input: dict) -> dict:
    """查询 ClinicalTrials.gov 临床试验详情。"""
    nct_id = input.get("nct_id", "").strip()
    if not re.match(r"^NCT\d{8}$", nct_id, re.IGNORECASE):
        return ToolResult(
            success=False,
            error=f"无效的 NCT 编号格式: {nct_id}（应为 NCT 后跟 8 位数字）",
        ).to_dict()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_CLINICAL_TRIALS_API}/{nct_id}",
                params={"format": "json"},
            )
            r.raise_for_status()
            data = r.json()
            protocol = data.get("protocolSection", {})

            # 安全提取嵌套字段
            def _safe_get(d: dict, *keys: str, default=""):
                for k in keys:
                    if isinstance(d, dict):
                        d = d.get(k, {})
                    else:
                        return default
                return d if d else default

            ident = protocol.get("identificationModule", {})
            status_mod = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            desc = protocol.get("descriptionModule", {})

            enrollment = design.get("enrollmentInfo", {})
            if isinstance(enrollment, dict):
                enrollment_count = str(enrollment.get("count", ""))
            else:
                enrollment_count = str(enrollment) if enrollment else ""

            conditions_list = desc.get("conditions", [])
            if isinstance(conditions_list, list):
                conditions = [
                    (c.get("condition", "") if isinstance(c, dict) else str(c))
                    for c in conditions_list
                ]
            else:
                conditions = [str(conditions_list)] if conditions_list else []

            return ToolResult(
                success=True,
                data={
                    "nct_id": nct_id,
                    "title": ident.get("briefTitle", ""),
                    "official_title": ident.get("officialTitle", ""),
                    "status": status_mod.get("overallStatus", ""),
                    "study_type": design.get("studyType", ""),
                    "phases": design.get("phases", []) or [],
                    "enrollment": enrollment_count,
                    "brief_summary": desc.get("briefSummary", ""),
                    "conditions": conditions,
                    "url": f"https://clinicaltrials.gov/study/{nct_id}",
                },
            ).to_dict()
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"ClinicalTrials.gov 查询失败: {type(e).__name__}"
        ).to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool 4: format_evidence_card
# ═══════════════════════════════════════════════════════════════

FORMAT_EVIDENCE_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pmid": {"type": "string"},
        "journal": {"type": "string"},
        "year": {"type": "string"},
        "evidence_level": {"type": "string"},
        "excerpt": {"type": "string", "description": "证据摘要（不超过 300 字）"},
        "url": {"type": "string"},
    },
    "required": ["title", "evidence_level"],
}

# 证据等级 → 徽章映射
_LEVEL_BADGE = {
    "系统综述/Meta分析": ("Meta", "🥇"),
    "临床指南/专家共识": ("指南", "📋"),
    "随机对照试验": ("RCT", "🧪"),
    "综述": ("综述", "📚"),
    "观察性研究": ("观察", "📊"),
    "其他研究": ("其他", "📄"),
    "Review": ("综述", "📚"),
    "Trial": ("RCT", "🧪"),
    "专业指南/科学声明": ("指南", "📋"),
    "专业指南": ("指南", "📋"),
    "国际指南": ("指南", "📋"),
}


async def format_evidence_card_handler(input: dict) -> dict:
    """将证据数据格式化为标准化展示卡片。"""
    title = input.get("title", "Untitled")
    pmid = input.get("pmid", "")
    journal = input.get("journal", "")
    year = input.get("year", "")
    level = input.get("evidence_level", "其他研究")
    excerpt = input.get("excerpt", "")[:300]
    url = input.get("url", "")

    badge = _LEVEL_BADGE.get(level, ("其他", "📄"))

    card = {
        "header": {
            "badge_icon": badge[1],
            "badge_label": badge[0],
            "evidence_level": level,
        },
        "body": {
            "title": title[:150],
            "source": f"{journal} · {year}" if journal else year,
            "excerpt": excerpt,
        },
        "footer": {
            "pmid": pmid,
            "url": url or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "citation_label": "",  # 待调用方填写 [Ex]
        },
    }
    return ToolResult(success=True, data=card).to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool Registry（工具注册中心）
# ═══════════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_pubmed": ToolSpec(
        name="search_pubmed",
        description="检索 PubMed 生物医学文献数据库。支持按关键词、年份范围、文献类型（综述/RCT/指南）过滤。返回 PMID、标题、期刊、年份、摘要。",
        input_schema=SEARCH_PUBMED_SCHEMA,
        handler=search_pubmed_handler,
        category="retrieval",
    ),
    "verify_citation": ToolSpec(
        name="verify_citation",
        description="核验回答中的引用 [Ex] 和 PMID 是否真实存在。第一层检查引用编号是否在证据范围内；第二层检测超出合理范围的伪造 PMID。",
        input_schema=VERIFY_CITATION_SCHEMA,
        handler=verify_citation_handler,
        category="verification",
    ),
    "get_trial_record": ToolSpec(
        name="get_trial_record",
        description="查询 ClinicalTrials.gov 上指定 NCT 编号的临床试验详情。返回试验标题、状态、阶段、招募人数、摘要等。",
        input_schema=GET_TRIAL_SCHEMA,
        handler=get_trial_record_handler,
        category="retrieval",
    ),
    "format_evidence_card": ToolSpec(
        name="format_evidence_card",
        description="将单条证据数据格式化为标准化展示卡片。包含证据等级徽章（Meta/指南/RCT/综述/观察）、标题、来源、摘要、PMID 链接。",
        input_schema=FORMAT_EVIDENCE_CARD_SCHEMA,
        handler=format_evidence_card_handler,
        category="formatting",
    ),
}


def list_tools(category: str = "") -> list[dict]:
    """列出所有可用工具（含 JSON Schema）。"""
    tools = TOOL_REGISTRY.values()
    if category:
        tools = [t for t in tools if t.category == category]
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


async def call_tool(name: str, input: dict) -> dict:
    """按名称调用工具。"""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return ToolResult(
            success=False,
            error=f"未知工具: {name}。可用工具: {', '.join(TOOL_REGISTRY.keys())}",
        ).to_dict()
    try:
        return await tool.handler(input)
    except Exception as e:
        return ToolResult(success=False, error=f"工具执行异常: {type(e).__name__}: {e}").to_dict()
