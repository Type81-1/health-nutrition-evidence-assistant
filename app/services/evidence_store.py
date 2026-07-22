from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = PROJECT_ROOT / "data" / "seed_evidence.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

DOMAIN_QUERY_EXPANSIONS = {
    "DASH": ["高血压", "血压", "降压", "限钠", "低脂乳制品"],
    "限钠": ["减盐", "低盐", "食盐", "钠", "钠摄入", "降低钠"],
    "高血压": ["血压", "降压"],
    "血压": ["高血压", "降压"],
    "血脂": ["胆固醇", "LDL", "甘油三酯", "降脂", "心血管"],
    "胆固醇": ["血脂", "LDL", "膳食纤维", "全谷物", "植物甾醇"],
    "膳食纤维": ["可溶性纤维", "全谷物", "LDL", "胆固醇"],
    "全谷物": ["燕麦", "膳食纤维", "LDL", "胆固醇"],
    "保健品": ["补充剂", "鱼油", "omega", "单一食物", "治疗"],
    "鱼油": ["omega", "甘油三酯", "保健品", "补充剂"],
    "地中海": ["PREDIMED", "橄榄油", "坚果", "心血管"],
    "糖尿病": ["血糖", "低升糖", "低 GI", "主食", "营养治疗"],
    "主食": ["低升糖", "低 GI", "碳水", "血糖", "糖尿病"],
    "含糖饮料": ["游离糖", "添加糖", "糖尿病", "血糖"],
    "糖": ["游离糖", "添加糖", "含糖饮料", "糖尿病"],
    "超加工": ["加工食品", "含糖饮料", "加工肉", "高盐零食", "心血管"],
}

EVIDENCE_LEVEL_WEIGHTS = {
    "国际指南": 8,
    "专业指南": 7,
    "专业指南/科学声明": 7,
    "专业指南/共识": 7,
    "系统综述": 6,
    "随机对照试验": 5,
}


@dataclass
class EvidenceChunk:
    id: str
    title: str
    source_type: str
    year: str
    url: str
    evidence_level: str
    content: str

    def metadata(self) -> dict[str, str]:
        return {
            "title": self.title,
            "source_type": self.source_type,
            "year": self.year,
            "url": self.url,
            "evidence_level": self.evidence_level,
        }


class EvidenceStore:
    """Chroma 优先的证据库；无模型下载条件时可无缝退回词项检索。"""

    def __init__(
        self,
        seed_path: Path = SEED_PATH,
        persist_path: Path = CHROMA_PATH,
        enable_chroma: bool = True,
    ):
        self.seed_path = seed_path
        self.persist_path = persist_path
        self._chunks = self._load_seed()
        self._collection = None
        self.backend = "local keyword retrieval"
        if enable_chroma:
            self._initialise_chroma()

    def _load_seed(self) -> list[EvidenceChunk]:
        records = json.loads(self.seed_path.read_text(encoding="utf-8"))
        return [EvidenceChunk(**record) for record in records]

    def _initialise_chroma(self) -> None:
        try:
            import chromadb

            self.persist_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_path))
            self._collection = client.get_or_create_collection(
                name="nutrition_evidence",
                metadata={"description": "健康营养公开证据库"},
            )
            self._collection.upsert(
                ids=[chunk.id for chunk in self._chunks],
                documents=[chunk.content for chunk in self._chunks],
                metadatas=[chunk.metadata() for chunk in self._chunks],
            )
            self.backend = "Chroma semantic retrieval"
        except Exception:
            # Chroma 的嵌入模型首次下载失败时，课堂演示仍可使用本地样例与关键词检索。
            self._collection = None

    def add_chunks(self, chunks: Iterable[EvidenceChunk]) -> int:
        new_chunks = list(chunks)
        if not new_chunks:
            return 0
        self._chunks.extend(new_chunks)
        if self._collection is not None:
            self._collection.upsert(
                ids=[chunk.id for chunk in new_chunks],
                documents=[chunk.content for chunk in new_chunks],
                metadatas=[chunk.metadata() for chunk in new_chunks],
            )
        return len(new_chunks)

    def search(self, question: str, limit: int = 4) -> list[EvidenceChunk]:
        if self._collection is not None:
            try:
                result = self._collection.query(query_texts=[question], n_results=limit)
                return [
                    EvidenceChunk(
                        id=result["ids"][0][index],
                        content=result["documents"][0][index],
                        **result["metadatas"][0][index],
                    )
                    for index in range(len(result["ids"][0]))
                ]
            except Exception:
                pass
        return self._keyword_search(question, limit)

    def _keyword_search(self, question: str, limit: int) -> list[EvidenceChunk]:
        terms = self._query_terms(question)

        def score(chunk: EvidenceChunk) -> int:
            title = chunk.title.lower()
            content = chunk.content.lower()
            text_score = sum(
                (title.count(term) * weight * 3) + (content.count(term) * weight)
                for term, weight in terms.items()
            )
            if text_score == 0:
                return 0
            evidence_weight = max(
                (
                    weight
                    for label, weight in EVIDENCE_LEVEL_WEIGHTS.items()
                    if label in chunk.evidence_level or label in chunk.source_type
                ),
                default=0,
            )
            return text_score + evidence_weight

        ranked = sorted(self._chunks, key=score, reverse=True)
        return [chunk for chunk in ranked if score(chunk) > 0][:limit] or ranked[:limit]

    @staticmethod
    def _query_terms(question: str) -> dict[str, int]:
        normalized = question.lower()
        terms: dict[str, int] = {}

        def add(term: str, weight: int) -> None:
            if term:
                terms[term.lower()] = max(terms.get(term.lower(), 0), weight)

        for word in re.findall(r"[a-zA-Z]{3,}", normalized):
            add(word, 3)

        for phrase in re.findall(r"[\u4e00-\u9fff]+", normalized):
            for size in (2, 3, 4):
                for index in range(0, max(len(phrase) - size + 1, 0)):
                    add(phrase[index : index + size], size)

        for trigger, expansions in DOMAIN_QUERY_EXPANSIONS.items():
            if trigger.lower() in normalized:
                add(trigger, 5)
                for expansion in expansions:
                    add(expansion, 4)

        return terms
