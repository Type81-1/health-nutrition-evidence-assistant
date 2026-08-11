from __future__ import annotations

from app.services.evidence_store import EvidenceStore
from app.services.llm_client import OpenAICompatibleLlm


TERM_GLOSSARY = {
    "随机对照试验": "把参与者随机分组后进行比较的研究",
    "随机试验": "把参与者随机分组后进行比较的研究",
    "系统综述": "汇总并分析多项研究的资料",
    "科学声明": "专业机构根据现有研究提出的总结",
    "心血管事件": "心脏病发作、中风等严重心血管问题",
    "心血管风险": "发生心脏病或中风等问题的可能性",
    "钠摄入": "吃进去的钠（主要来自盐、调味品和加工食品）",
    "依从性": "能否长期按要求执行",
    "干预强度": "饮食改变执行得有多严格",
    "对照饮食": "用来比较的另一种饮食方式",
    "主要结局": "研究最重点观察的结果",
    "相关": "同时出现，但不一定能证明因果",
    "人群层面": "一组人的平均情况",
    "高心血管风险人群": "本来就更容易发生心脏病或中风的一组人",
}


class EvidenceSimplifier:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store
        self.llm = OpenAICompatibleLlm()

    def simplify(self, source_id: str) -> tuple[str, str] | None:
        evidence = self.store.get_by_id(source_id)
        if evidence is None:
            return None
        model_text = self.llm.simplify(evidence.content)
        if model_text:
            return model_text, "model"
        text = evidence.content
        for technical, plain in TERM_GLOSSARY.items():
            text = text.replace(technical, plain)
        return f"简单说：{text}", "glossary"
