from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = PROJECT_ROOT / "data" / "seed_evidence.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"


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
            existing = self._collection.count()
            if existing == 0:
                self._collection.add(
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
        terms = set(re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}", question.lower()))

        def score(chunk: EvidenceChunk) -> int:
            searchable = f"{chunk.title} {chunk.content}".lower()
            return sum(term in searchable for term in terms)

        ranked = sorted(self._chunks, key=score, reverse=True)
        return [chunk for chunk in ranked if score(chunk) > 0][:limit] or ranked[:limit]
