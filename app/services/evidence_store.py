from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = PROJECT_ROOT / "data" / "seed_evidence.json"
PUBMED_EVIDENCE_PATH = PROJECT_ROOT / "data" / "pubmed_evidence.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"


GENERIC_TERMS = {
    "什么",
    "是否",
    "真的",
    "有用",
    "帮助",
    "怎么",
    "如何",
    "看待",
    "应该",
    "可以",
    "证据",
    "研究",
    "饮食",
    "健康",
    "的人",
    "一下",
}

# Only intervention aliases are expanded. Outcome terms such as "血压" remain
# literal so that an unsupported subject (for example, a specific food) cannot
# retrieve every blood-pressure paper in the store.
CONCEPT_ALIASES = (
    ("地中海饮食", "地中海式饮食", "地中海", "mediterranean"),
    ("限钠", "低钠", "减钠", "减少钠", "钠摄入", "减盐", "少盐", "控盐", "食盐", "盐", "sodium", "salt"),
    ("dash", "dash饮食"),
    ("保健品", "补充剂", "营养补充剂", "supplement"),
    ("维生素d", "维生素 d", "维d", "维 d", "vitamin d"),
    ("睡眠", "失眠", "睡不好", "sleep"),
    ("膳食纤维", "纤维", "车前子", "psyllium", "fiber", "fibre"),
    ("便秘", "排便", "constipation"),
    ("间歇性禁食", "轻断食", "限时进食", "隔日禁食", "intermittent fasting"),
    ("减重", "减肥", "体重", "weight loss"),
    ("益生菌", "probiotic"),
    ("抗生素相关腹泻", "抗生素腹泻", "antibiotic-associated diarrhoea", "antibiotic-associated diarrhea"),
    ("omega-3", "omega 3", "欧米伽3", "鱼油", "二十碳五烯酸乙酯", "icosapent ethyl"),
    ("咖啡", "咖啡因", "coffee", "caffeine"),
    ("2型糖尿病", "二型糖尿病", "糖尿病", "血糖", "糖化血红蛋白", "type 2 diabetes", "hba1c"),
    ("低碳饮食", "低碳水", "生酮饮食", "生酮", "low carbohydrate", "ketogenic"),
    ("胆固醇", "血脂", "低密度脂蛋白", "ldl"),
    ("超加工食品", "高度加工食品", "ultra-processed"),
    ("坚果", "nuts"),
    ("蛋白质", "蛋白粉", "protein"),
    ("增肌", "肌肉", "力量训练", "抗阻训练", "muscle", "resistance training"),
)


def _contains_alias(text: str, alias: str) -> bool:
    if alias.isascii():
        return re.search(rf"\b{re.escape(alias)}\b", text) is not None
    return alias in text


@dataclass
class EvidenceChunk:
    id: str
    title: str
    source_type: str
    year: str
    url: str
    evidence_level: str
    content: str
    search_terms: str = ""

    def metadata(self) -> dict[str, str]:
        return {
            "title": self.title,
            "source_type": self.source_type,
            "year": self.year,
            "url": self.url,
            "evidence_level": self.evidence_level,
        }

    def searchable_text(self) -> str:
        return f"{self.title} {self.search_terms} {self.content}"


class EvidenceStore:
    """Evidence retrieval with a lexical relevance gate and optional reranking."""

    def __init__(
        self,
        seed_path: Path = SEED_PATH,
        persist_path: Path = CHROMA_PATH,
        enable_chroma: bool = True,
        additional_paths: tuple[Path, ...] | None = None,
    ):
        self.seed_path = seed_path
        self.persist_path = persist_path
        if additional_paths is None:
            additional_paths = (PUBMED_EVIDENCE_PATH,) if seed_path == SEED_PATH else ()
        self.evidence_paths = (seed_path, *additional_paths)
        self._chunks = self._load_evidence()
        self._collection = None
        self.backend = "相关性词项检索"
        if enable_chroma:
            self._initialise_chroma()

    def _load_evidence(self) -> list[EvidenceChunk]:
        chunks: list[EvidenceChunk] = []
        seen_ids: set[str] = set()
        for path in self.evidence_paths:
            if not path.exists():
                continue
            records = json.loads(path.read_text(encoding="utf-8"))
            for record in records:
                chunk = EvidenceChunk(**record)
                if chunk.id in seen_ids:
                    raise ValueError(f"重复的证据 ID：{chunk.id}")
                seen_ids.add(chunk.id)
                chunks.append(chunk)
        return chunks

    def _initialise_chroma(self) -> None:
        try:
            import chromadb

            self.persist_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_path))
            self._collection = client.get_or_create_collection(
                name="nutrition_evidence",
                metadata={"description": "健康营养公开证据库"},
            )
            current_ids = {chunk.id for chunk in self._chunks}
            stored_ids = set(self._collection.get().get("ids", []))
            stale_ids = sorted(stored_ids - current_ids)
            if stale_ids:
                self._collection.delete(ids=stale_ids)
            self._collection.upsert(
                ids=[chunk.id for chunk in self._chunks],
                documents=[chunk.searchable_text() for chunk in self._chunks],
                metadatas=[chunk.metadata() for chunk in self._chunks],
            )
            self.backend = "人工标签相关性检索 + Chroma 证据索引"
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
                documents=[chunk.searchable_text() for chunk in new_chunks],
                metadatas=[chunk.metadata() for chunk in new_chunks],
            )
        return len(new_chunks)

    def get_by_id(self, source_id: str) -> EvidenceChunk | None:
        return next((chunk for chunk in self._chunks if chunk.id == source_id), None)

    def search(self, question: str, limit: int = 4) -> list[EvidenceChunk]:
        # Semantic stores always return nearest neighbours, including unrelated
        # ones. Lexical gating prevents those neighbours from becoming evidence.
        # Use the persisted vector collection as an index, but keep the final
        # ordering deterministic and auditable. Semantic nearest-neighbour
        # ordering can otherwise promote a broad but wrong nutrition topic.
        return self._keyword_search(question, limit)

    def _keyword_search(self, question: str, limit: int) -> list[EvidenceChunk]:
        terms = self._query_terms(question)
        if not terms:
            return []

        normalized = question.lower()
        requested_concepts = [
            aliases
            for aliases in CONCEPT_ALIASES
            if any(_contains_alias(normalized, alias) for alias in aliases)
        ]
        required_subject = None if requested_concepts else self._required_subject(normalized)

        def covers_subject(chunk: EvidenceChunk) -> bool:
            # Concepts must occur in a title or a curator-reviewed search tag.
            # A passing mention in the summary is useful for ranking, but is
            # not enough to make a paper evidence for another topic.
            searchable = f"{chunk.title} {chunk.search_terms}".lower()
            if requested_concepts and not all(
                any(_contains_alias(searchable, alias) for alias in aliases)
                for aliases in requested_concepts
            ):
                return False
            if required_subject and required_subject not in searchable:
                return False
            return True

        def score(chunk: EvidenceChunk) -> int:
            title = chunk.title.lower()
            content = f"{chunk.search_terms} {chunk.content}".lower()
            return sum(
                weight * (3 if term in title else 1 if term in content else 0)
                for term, weight in terms.items()
            )

        ranked = sorted(
            ((score(chunk), chunk) for chunk in self._chunks if covers_subject(chunk)),
            key=lambda item: (item[0], item[1].year),
            reverse=True,
        )
        return [chunk for relevance, chunk in ranked if relevance >= 3][:limit]

    @staticmethod
    def _required_subject(question: str) -> str | None:
        match = re.match(r"^(.{1,16}?)(?:能不能|能否|能|会不会|会|是否|对)", question)
        if not match:
            return None
        subject = match.group(1)
        for prefix in ("请问", "想知道", "多吃", "少吃", "吃", "喝", "服用", "补充"):
            if subject.startswith(prefix):
                subject = subject[len(prefix) :]
        subject = subject.strip()
        if any(outcome in subject for outcome in ("血压", "高血压", "血脂", "胆固醇", "心血管")):
            return None
        return subject if 1 < len(subject) <= 8 and subject not in GENERIC_TERMS else None

    @staticmethod
    def _query_terms(question: str) -> dict[str, int]:
        normalized = question.lower()
        terms: dict[str, int] = {}

        for word in re.findall(r"[a-zA-Z]{3,}", normalized):
            if word not in GENERIC_TERMS:
                terms[word] = max(terms.get(word, 0), 2)

        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            for size in (4, 3, 2):
                for start in range(len(sequence) - size + 1):
                    term = sequence[start : start + size]
                    if term not in GENERIC_TERMS and not any(
                        term in generic for generic in GENERIC_TERMS
                    ):
                        terms[term] = max(terms.get(term, 0), 1)

        for aliases in CONCEPT_ALIASES:
            if any(_contains_alias(normalized, alias) for alias in aliases):
                for alias in aliases:
                    terms[alias] = max(terms.get(alias, 0), 3)

        return terms
