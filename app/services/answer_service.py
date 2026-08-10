from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas import AnswerResponse, Citation
from app.services.evidence_store import EvidenceChunk, EvidenceStore
from app.services.llm_client import OpenAICompatibleLlm


SAFETY_NOTE = (
    "这是健康科普，不替代个体化诊疗。正在使用降压药、降脂药、利尿剂，或处于孕期、"
    "有肾病/心衰等情况时，请先与医生或注册营养师讨论饮食调整。"
)

# ── 敏感内容拦截 ──────────────────────────────────────────────
# 每个元组为 (正则模式, 拒答原因)
_REJECTION_RULES: list[tuple[re.Pattern[str], str]] = [
    # 极端偏方 / 伪科学疗法
    (re.compile(r"(?:有什么|有哪些|谁知道|求|推荐).{0,6}(?:偏方|土方|秘方|祖传方|民间方)"), "涉及寻求未经科学验证的民间偏方，不予作答。"),
    (re.compile(r"(?:偏方|土方|秘方|祖传方|民间方).{0,6}(?:治好|治愈|根治|能治|管用|亲测)"), "涉及宣传未经科学验证的民间偏方，不予作答。"),
    (re.compile(r"排毒.*(餐|法|食谱|饮食)|酸碱体质|辟谷|灌肠|尿疗|生吃.*治病"), "涉及伪科学或危险食疗主张，不予作答。"),
    (re.compile(r"(断食|禁食|绝食)\s*(疗法|养生|减肥)"), "涉及极端断食/禁食，可能造成健康风险，不予作答。"),
    # 要求替代正规医疗
    (re.compile(r"(不吃药|停药|断药|停西药|不用药).*(能|可以|行|好)"), "涉及替代正规医疗的建议，不予作答。"),
    (re.compile(r"(治好|治愈|根治|痊愈).*(吃|喝|食疗|食物|饮食)"), "不可宣传食物/食疗可治愈疾病，不予作答。"),
    (re.compile(r"(代替|替代).*(药物|药品|降糖药|降压药|降脂药|他汀|胰岛素)"), "饮食不可替代处方药物，此类建议不予作答。"),
    # 要求诊断
    (re.compile(r"我这是(得了|不是|什么)病|帮忙.*诊断|帮我.*看看.*病|这个症状.*什么病"), "不提供疾病诊断，请前往医院就诊。"),
    # 要求用药建议
    (re.compile(r"该?(吃|用|买)(什么|哪种|哪个)(药|药品|药物)"), "不提供用药建议，请咨询医生或药师。"),
    (re.compile(r"(怎么|如何)(治|处理|办).*(病|症状|不舒服)"), "不提供治疗建议，请前往医院就诊。"),
    # 危险偏方识别
    (re.compile(r"(生吃|生吞).*(泥鳅|蛇胆|鱼胆|蜈蚣|蝎子)"), "涉及危险偏方，可能危及生命，不予作答。"),
    (re.compile(r"(何首乌|马兜铃|关木通|广防己).*(吃|喝|泡|煮|炖)"), "涉及已知肝毒性/肾毒性药材，不予作答。"),
]


@dataclass
class SafetyCheck:
    safe: bool
    reason: str = ""


def check_safety(question: str) -> SafetyCheck:
    """检测问题是否涉及敏感/危险内容。安全返回 SafetyCheck(safe=True)。"""
    for pattern, reason in _REJECTION_RULES:
        if pattern.search(question):
            return SafetyCheck(safe=False, reason=reason)
    return SafetyCheck(safe=True)


REJECTION_PREAMBLE = "基于安全与伦理准则，"

# ── 简易会话记忆（进程内，重启丢失；仅用于多轮追问上下文）──
_conversations: dict[str, list[dict[str, str]]] = {}
_MAX_HISTORY_TURNS = 5


def _build_context(conversation_id: str | None, question: str) -> str:
    """如果有历史对话，拼接到当前问题前面作为上下文。"""
    if not conversation_id or conversation_id not in _conversations:
        return question
    history = _conversations[conversation_id][-_MAX_HISTORY_TURNS:]
    lines: list[str] = []
    for h in history:
        # 只取前 200 字作为摘要，避免 prompt 过长
        prev_a = h["answer"][:200].replace("\n", " ")
        lines.append(f"用户：{h['question']}\n助手：{prev_a}...")
    history_text = "\n".join(lines)
    return f"对话历史（用于理解上下文）：\n{history_text}\n\n当前问题：{question}"


def _remember(conversation_id: str | None, question: str, answer: str) -> None:
    """记录本轮问答。"""
    if not conversation_id:
        return
    _conversations.setdefault(conversation_id, []).append(
        {"question": question, "answer": answer}
    )
    if len(_conversations[conversation_id]) > _MAX_HISTORY_TURNS * 2:
        _conversations[conversation_id] = _conversations[conversation_id][-_MAX_HISTORY_TURNS:]


class AnswerService:
    def __init__(self, store: EvidenceStore):
        self.store = store
        self.llm = OpenAICompatibleLlm()

    def answer(
        self,
        question: str,
        extra_evidence: list[EvidenceChunk] | None = None,
        pubmed_error: str | None = None,
        skip_local: bool = False,
        conversation_id: str | None = None,
    ) -> AnswerResponse:
        extra_evidence = extra_evidence or []
        # 多轮对话：拼接历史上下文
        context_question = _build_context(conversation_id, question)
        # PubMed 有结果时跳过本地，避免混入不相关证据
        if skip_local:
            local_evidence: list[EvidenceChunk] = []
        else:
            local_evidence = self.store.search(context_question, limit=4)
        combined = list(extra_evidence) + list(local_evidence)
        if not combined:
            note = pubmed_error or "未检索到可用证据。"
            return AnswerResponse(
                answer_markdown="目前证据库和实时检索中都没有足以支撑回答的资料，因此不作具体结论。",
                citations=[],
                safety_note=SAFETY_NOTE,
                retrieval_note=note,
            )

        citations = [self._citation(chunk, index + 1) for index, chunk in enumerate(combined)]
        # LLM 用含历史的问题，fallback 用原始问题
        answer = self.llm.answer(context_question, combined) or self._build_consumer_answer(question, combined)
        _remember(conversation_id, question, answer)
        source_parts: list[str] = []
        if extra_evidence:
            source_parts.append(f"多源实时检索 {len(extra_evidence)} 条（PubMed + Europe PMC）")
        if local_evidence:
            source_parts.append(f"{self.store.backend} 选取 {len(local_evidence)} 条")
        if pubmed_error:
            source_parts.append(pubmed_error)
        return AnswerResponse(
            answer_markdown=answer,
            citations=citations,
            safety_note=SAFETY_NOTE,
            retrieval_note="；".join(source_parts),
        )

    @staticmethod
    def _citation(chunk: EvidenceChunk, position: int) -> Citation:
        return Citation(
            label=f"E{position}",
            title=chunk.title,
            source_type=chunk.source_type,
            year=chunk.year,
            url=chunk.url,
            excerpt=chunk.content,
            evidence_level=chunk.evidence_level,
        )

    @staticmethod
    def _build_consumer_answer(question: str, evidence: list[EvidenceChunk]) -> str:
        labels = [f"[E{index}]" for index in range(1, len(evidence) + 1)]
        # 汇总所有证据的标题和要点，而非只取第一条
        evidence_summaries: list[str] = []
        for i, chunk in enumerate(evidence):
            # 分别尝试中文句号和英文句号切分，取前两句
            for sep in ("。", ". "):
                sentences = chunk.content.split(sep)
                if len(sentences) >= 2:
                    break
            key = sep.join(s.strip() for s in sentences[:2] if s.strip())
            evidence_summaries.append(f"{labels[i]} {chunk.title}：{key}")

        parts = [
            f"关于 {question} ，检索到 {len(evidence)} 条证据，摘要如下：",
            "",
            *[f"  {s}" for s in evidence_summaries],
            "",
            "需要说明的是，当前大模型暂不可用，以上为直接检索到的原始证据摘录，未经归纳总结。以下内容仅供参考，不能替代医生或注册营养师的专业建议。",
            "",
            "如果你愿意，可以告诉我更多具体情况（比如是否有确诊疾病、正在服用什么药物），我可以帮你更有针对性地整理信息。",
        ]
        return "\n".join(parts)
