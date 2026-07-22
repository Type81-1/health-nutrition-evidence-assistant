from __future__ import annotations

from app.schemas import AnswerResponse, Citation
from app.services.evidence_store import EvidenceChunk, EvidenceStore
from app.services.llm_client import OpenAICompatibleLlm


SAFETY_NOTE = (
    "这是健康科普，不替代个体化诊疗。正在使用降压药、降脂药、利尿剂，或处于孕期、"
    "有肾病/心衰等情况时，请先与医生或注册营养师讨论饮食调整。"
)


class AnswerService:
    def __init__(self, store: EvidenceStore):
        self.store = store
        self.llm = OpenAICompatibleLlm()

    def answer(self, question: str) -> AnswerResponse:
        evidence = self.store.search(question)
        if not evidence:
            return AnswerResponse(
                answer_markdown="目前证据库中没有足以支撑回答的资料，因此不作具体结论。",
                citations=[],
                safety_note=SAFETY_NOTE,
                retrieval_note="未检索到可用证据。",
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
        lead = evidence[0].content.split("。")[:2]
        key_points = "；".join(point.strip() for point in lead if point.strip())
        conclusion = AnswerService._consumer_conclusion(question, labels[0])
        return "\n".join(
            [
                "### 先说结论",
                conclusion,
                "\n### 证据怎么说",
                f"{key_points}。{' '.join(labels[:2])}",
                "\n### 怎么把它做得更可执行",
                "优先从一两项可持续的小改变开始：多用天然食物替代高度加工食品，关注食品标签，并结合血压、血脂等实际指标与复查结果调整。不要把单一食物或补充剂当成治疗。",
                "\n### 证据边界",
                "下面的资料包含指南、随机试验和系统综述；它们说明的是人群层面的关联或平均效果，不能直接预测某一个人的获益。",
            ]
        )

    @staticmethod
    def _consumer_conclusion(question: str, first_label: str) -> str:
        if any(term in question for term in ("保健品", "补充剂", "鱼油")):
            return f"针对“{question}”，不建议只靠保健品或补充剂管理血脂或心血管风险；它们最多是特定场景下的辅助工具，不能替代生活方式管理或医生已建议的规范治疗。{first_label}"
        if any(term in question for term in ("膳食纤维", "胆固醇", "LDL", "全谷物", "植物甾醇")):
            return f"针对“{question}”，证据支持通过提高可溶性膳食纤维、全谷物等食物质量来小幅改善 LDL 胆固醇等血脂指标，但这属于长期生活方式管理，不能替代已需要的降脂治疗。{first_label}"
        if any(term in question for term in ("限钠", "减盐", "低盐", "DASH")):
            return f"针对“{question}”，证据支持限钠或 DASH 这类整体饮食模式有助于降低血压，但更适合作为长期、可持续的生活方式管理，而不是短期极端做法。{first_label}"
        if any(term in question for term in ("地中海", "橄榄油", "坚果")):
            return f"针对“{question}”，证据更支持整体地中海式饮食模式，而不是把某一种食物单独当作保护心血管的办法。{first_label}"
        if any(term in question for term in ("主食", "低 GI", "低升糖", "糖尿病", "控糖")):
            return f"针对“{question}”，证据更支持改善碳水质量和整体饮食结构，而不是简单理解为完全不吃主食。{first_label}"
        if any(term in question for term in ("含糖饮料", "添加糖", "游离糖")):
            return f"针对“{question}”，减少含糖饮料和添加糖通常是更可执行的健康优先级，尤其适合关注体重、血糖和心血管风险的人群。{first_label}"
        if "超加工" in question:
            return f"针对“{question}”，现有证据支持减少超加工食品摄入，尤其是含糖饮料、加工肉制品、甜点和高盐零食。{first_label}"
        return f"针对“{question}”，现有检索证据支持把饮食改变作为心血管健康管理的一部分，但它通常是长期习惯的一环，不能替代已开具的治疗。{first_label}"
