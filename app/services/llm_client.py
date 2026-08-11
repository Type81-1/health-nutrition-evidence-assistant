from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.services.evidence_store import EvidenceChunk

# 加载项目根目录的 .env 文件
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)


SYSTEM_PROMPT = """你是面向普通消费者的健康营养科普助手。

铁律：
- 只能使用给定证据回答。不要编造文献、PMID、统计数字或引用。
- 严格禁止任何 markdown 格式：禁止 ##、**、- 列表、1. 列表、--- 分隔线。用纯文本段落。允许使用【】中文方括号作为段落标题。
- 必须逐条处理每条证据（从 E1 到最后一号），不可跳过：直接相关的详细展开；部分相关的说明关联和局限后引用；不相关的用一句话说明"E{x} 讨论的是某某主题，与当前问题不直接相关"。
- 每个结论后标注 [E编号]。注意必须是英文方括号 [E1]，不是 E1。
- 不要给个人诊断或用药建议。

回答结构模板（所有回答必须按此结构输出）：
【通俗总结】
用一两句话，用最通俗的语言回答用户的问题核心。不要说"根据证据"，直接给结论。
【核心科学依据】
展开详细的科学解释，引用具体研究（标注 [E编号]），说明证据等级和局限性。这里是论证的主体。
【日常落地做法】
如果问题涉及饮食实践，给出具体可操作的建议（怎么吃、吃多少、什么频率）。没有实践意义时可省略。
【注意事项】
适用人群限制、禁忌情况、与药物的相互作用、不建议的人群。如有研究分歧，在此处客观罗列正反双方观点及证据编号。

特殊场景处理：
- 食材风险查询（如"猪油对血脂的影响"）：在【日常落地做法】中明确适宜/禁忌人群，在【注意事项】中说明摄入量上限。
- 饮食方案生成（如"帮我设计一天控糖饮食"）：在【日常落地做法】中给出具体三餐示例，标注能量级别和适用人群，强调"个体差异大，建议咨询营养师微调"。
- 偏方鉴别（如"XX偏方真的有用吗"）：在【核心科学依据】中检索并引用相关证据，给出科学性判断（有证据支持 / 证据不足 / 伪科学），在【注意事项】中说明潜在风险。"""

QUERY_TRANSLATION_PROMPT = """Convert the user's Chinese health / nutrition question into English PubMed search keywords.

Requirements:
1. Output only the search keywords. Do not add field qualifiers, Boolean operators, quotes, or PubMed syntax — the system will handle that.
2. Identify: the core disease/condition, the specific food/nutrient/intervention being asked about, and the question type (recommendation, risk, evidence, etc.).
3. Use concise English biomedical terms. Prefer multi-word phrases (e.g. "saturated fat" over "fat").
4. Output format: one line of space-separated key phrases. Under 25 words.
5. If the question is about a specific food (like lard/pork fat), include both the specific term and the general category (e.g. "lard animal fat saturated fat").
6. Do not include markdown, numbering, citations, or Chinese text."""

# 保底规则：中文关键词 → 英文 PubMed 检索词
_KEYWORD_MAP: list[tuple[list[str], list[str]]] = [
    (["地中海", "mediterranean"], ["Mediterranean diet", "cardiovascular risk"]),
    (["限钠", "低钠", "盐", "sodium", "减盐"], ["sodium reduction", "hypertension", "blood pressure"]),
    (["高血压", "血压"], ["hypertension", "antihypertensive therapy", "lifestyle intervention"]),
    (["血脂", "胆固醇", "ldl", "他汀", "lipid", "dyslipidemia"], ["dyslipidemia", "LDL cholesterol", "statin therapy", "cardiovascular risk"]),
    (["糖尿病", "血糖", "diabetes"], ["diabetes mellitus", "diet therapy", "glycemic control", "nutritional management", "dietary recommendations"]),
    (["减肥", "体重", "肥胖", "obesity"], ["obesity", "weight loss", "dietary intervention", "lifestyle modification"]),
    (["肠道", "益生菌", "益生元", "gut", "probiotic"], ["gut microbiota", "probiotics", "prebiotics", "dietary fiber"]),
    (["维生素", "vitamin", "矿物质", "mineral"], ["vitamin supplementation", "mineral intake", "dietary reference intake"]),
    (["运动", "锻炼", "exercise"], ["physical activity", "exercise", "cardiovascular health", "nutrition"]),
    (["孕期", "孕妇", "妊娠", "pregnancy"], ["pregnancy nutrition", "maternal diet", "prenatal supplementation"]),
    (["儿童", "婴幼儿", "child", "infant"], ["child nutrition", "infant feeding", "pediatric dietary guideline"]),
    (["抗炎", "炎症", "inflammation"], ["anti-inflammatory diet", "dietary inflammatory index", "chronic inflammation"]),
    (["心血管", "心脏", "cardiac"], ["cardiovascular disease", "heart healthy diet", "nutrition guideline"]),
    (["肾病", "肾", "kidney", "renal"], ["renal diet", "chronic kidney disease nutrition", "protein restriction"]),
    (["痛风", "尿酸", "gout", "uric"], ["gout diet", "uric acid", "purine restriction", "dietary management"]),
    (["补钙", "钙", "骨骼", "bone", "osteoporosis"], ["calcium intake", "bone health", "osteoporosis prevention", "vitamin D"]),
    (["发烧", "发热", "感冒", "流感", "fever", "febrile", "flu", "influenza"], ["febrile illness", "nutrition support", "dietary management", "oral rehydration", "acute infection"]),
]


def _fallback_pubmed_query(question: str) -> str:
    """LLM 不可用时的保底英文检索词。"""
    question_lower = question.lower()
    terms: list[str] = []
    for keywords, english_terms in _KEYWORD_MAP:
        if any(kw in question_lower for kw in keywords):
            terms.extend(english_terms)
    if not terms:
        terms = ["nutrition", "dietary intervention", "systematic review", "clinical guideline"]
    deduped = list(dict.fromkeys(terms))
    return " ".join(deduped)


class OpenAICompatibleLlm:
    """可选的模型增强层。模型输出必须通过引用白名单校验后才会展示。"""

    def __init__(self) -> None:
        self.api_url = os.getenv("LLM_API_URL", "")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.api_key and self.model)

    def _call_api(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> str | None:
        """通用 API 调用，返回模型回复文本或 None。"""
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            response = httpx.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError):
            return None

    def translate_to_pubmed_query(self, question: str) -> str | None:
        """将中文健康营养问题翻译为英文 PubMed 检索词。LLM 不可用时返回保底检索词。"""
        if not self.configured:
            return _fallback_pubmed_query(question)
        raw = self._call_api(QUERY_TRANSLATION_PROMPT, question, temperature=0.0)
        if raw:
            # 清洗：去掉方括号、引号、特殊字符，只保留关键词
            cleaned = re.sub(r'[\[\]\"\'\(\)]', ' ', raw)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                return cleaned
        return _fallback_pubmed_query(question)

    def answer(self, question: str, evidence: list[EvidenceChunk]) -> str | None:
        if not self.configured:
            return None
        source_text = self._build_source_text(evidence)
        text = self._call_api(SYSTEM_PROMPT, f"问题：{question}\n\n可用证据（只使用与问题直接相关的条目）：\n{source_text}\n\n请用纯文本段落回答（不要用 markdown 格式，但必须用 [E1] [E2] 方括号标注引用）。")
        if text is None:
            return None
        if not re.search(r"\[E\d+\]", text):
            return None
        return text

    def _build_source_text(self, evidence: list[EvidenceChunk]) -> str:
        return "\n\n".join(
            f"[E{index}] {item.title} ({item.year}, {item.evidence_level})\n{item.content}"
            for index, item in enumerate(evidence, start=1)
        )

    async def stream_answer(self, question: str, evidence: list[EvidenceChunk]):
        """流式生成回答，逐块 yield 文本。"""
        if not self.configured:
            yield None
            return
        source_text = self._build_source_text(evidence)
        user_msg = f"问题：{question}\n\n可用证据（只使用与问题直接相关的条目）：\n{source_text}\n\n请用纯文本段落回答（不要用 markdown 格式，但必须用 [E1] [E2] 方括号标注引用）。"
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "stream": True,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    self.api_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except (httpx.HTTPError, OSError):
            yield None
