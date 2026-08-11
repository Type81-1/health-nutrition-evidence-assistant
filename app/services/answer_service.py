from __future__ import annotations

from app.schemas import AnswerResponse, Citation
from app.services.evidence_store import EvidenceChunk, EvidenceStore
from app.services.llm_client import OpenAICompatibleLlm


SAFETY_NOTE = (
    "这是健康科普，不替代个体化诊疗。正在使用降压药、降脂药、利尿剂，或处于孕期、"
    "有肾病/心衰等情况时，请先与医生或注册营养师讨论饮食调整。"
)

PERSONALIZED_CARE_TERMS = (
    "怎么治疗",
    "怎么治",
    "吃什么药",
    "用什么药",
    "应该吃哪种药",
    "停药",
    "换药",
    "调整剂量",
    "诊断我",
    "开处方",
)

EMERGENCY_TERMS = ("胸痛", "呼吸困难", "昏厥", "意识不清", "严重过敏", "大出血")


class AnswerService:
    def __init__(self, store: EvidenceStore):
        self.store = store
        self.llm = OpenAICompatibleLlm()

    def answer(self, question: str) -> AnswerResponse:
        boundary_response = self._safety_boundary(question)
        if boundary_response is not None:
            return boundary_response

        evidence = self.store.search(question)
        if not evidence:
            return AnswerResponse(
                answer_markdown="\n".join(
                    [
                        "### 当前没有足够证据",
                        "本地证据库没有找到与这个问题直接相关的资料，因此不作具体结论，也不会用其他主题的研究代替回答。",
                        "\n### 下一步",
                        "你可以换一种更具体的问法，或使用右侧的 PubMed 实时检索继续查找公开文献。",
                    ]
                ),
                citations=[],
                safety_note=SAFETY_NOTE,
                retrieval_note="相关性检查未通过，未返回证据。",
            )

        citations = [self._citation(chunk, index + 1) for index, chunk in enumerate(evidence)]
        answer = self.llm.answer(question, evidence) or self._build_consumer_answer(question, evidence)
        return AnswerResponse(
            answer_markdown=answer,
            citations=citations,
            safety_note=SAFETY_NOTE,
            retrieval_note=f"已从 {self.store.backend} 选取 {len(evidence)} 条证据。",
        )

    @staticmethod
    def _citation(chunk: EvidenceChunk, position: int) -> Citation:
        return Citation(
            label=f"E{position}",
            source_id=chunk.id,
            title=chunk.title,
            source_type=chunk.source_type,
            year=chunk.year,
            url=chunk.url,
            excerpt=chunk.content,
            evidence_level=chunk.evidence_level,
            evidence_role=AnswerService._evidence_role(chunk),
        )

    @staticmethod
    def _build_consumer_answer(question: str, evidence: list[EvidenceChunk]) -> str:
        if len(evidence) < 3:
            labels = " ".join(f"[E{index}]" for index in range(1, len(evidence) + 1))
            sections = [
                "### 证据数量有限",
                f"这次只找到 {len(evidence)} 条直接相关资料，以下内容只能概括已检索到的发现，不能据此下确定结论。{labels}",
                "\n### 已检索到的发现",
            ]
        else:
            sections = ["### 先说结论"]
        for index, chunk in enumerate(evidence[:2], start=1):
            conclusion = AnswerService._sentences(chunk.content)[0]
            sections.append(f"{conclusion} [E{index}]")

        sections.append("\n### 证据怎么说")
        for index, chunk in enumerate(evidence[:3], start=1):
            sections.append(
                f"{chunk.source_type}（{chunk.year}）：{chunk.content} [E{index}]"
            )

        sections.append("\n### 可以怎样行动")
        action = AnswerService._find_action(evidence)
        if action is None:
            sections.append(
                "当前检索资料主要说明可能的效果，没有提供足够具体的个人执行方案；需要结合个人指标时，请咨询医生或注册营养师。"
            )
        else:
            sentence, label = action
            sections.append(f"证据中可以直接采用的做法是：{sentence} [{label}]")

        labels = " ".join(f"[E{index}]" for index in range(1, min(len(evidence), 3) + 1))
        source_types = "、".join(dict.fromkeys(chunk.source_type for chunk in evidence[:3]))
        sections.extend(
            [
                "\n### 证据边界",
                f"这次回答依据的是{source_types}。结论只适用于这些资料所覆盖的人群、干预和结局，不能直接预测某一个人的效果。{labels}",
            ]
        )
        return "\n".join(sections)

    @staticmethod
    def _evidence_role(chunk: EvidenceChunk) -> str:
        source = f"{chunk.source_type} {chunk.evidence_level}"
        if any(term in source for term in ("综述", "Meta", "指南", "声明")):
            return "证据总览"
        if "随机" in source:
            return "因果证据"
        return "边界证据"

    @staticmethod
    def _safety_boundary(question: str) -> AnswerResponse | None:
        if any(term in question for term in EMERGENCY_TERMS):
            return AnswerResponse(
                answer_markdown="\n".join(
                    [
                        "### 请立即寻求医疗帮助",
                        "这个问题可能涉及紧急情况，本系统不能进行诊断或远程处置。请立即联系当地急救服务或尽快前往急诊，不要等待在线回答。",
                    ]
                ),
                citations=[],
                safety_note=SAFETY_NOTE,
                retrieval_note="问题超出健康科普边界，已停止检索。",
            )
        if any(term in question for term in PERSONALIZED_CARE_TERMS):
            return AnswerResponse(
                answer_markdown="\n".join(
                    [
                        "### 这个问题需要专业人员判断",
                        "本系统不能提供诊断、处方、停药、换药或剂量调整建议。能提供的是一般营养证据和公开文献线索；涉及个人治疗时，请联系了解你病史和用药情况的医生或注册营养师。",
                    ]
                ),
                citations=[],
                safety_note=SAFETY_NOTE,
                retrieval_note="问题超出非个体化科普范围，已安全拒答。",
            )
        return None

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [sentence.strip() for sentence in text.split("。") if sentence.strip()]

    @staticmethod
    def _find_action(evidence: list[EvidenceChunk]) -> tuple[str, str] | None:
        action_markers = ("建议", "重点", "采用", "限制", "优先", "支持把", "长期", "做饭")
        for index, chunk in enumerate(evidence, start=1):
            for sentence in AnswerService._sentences(chunk.content):
                if any(marker in sentence for marker in action_markers):
                    return f"{sentence}。", f"E{index}"
        return None
