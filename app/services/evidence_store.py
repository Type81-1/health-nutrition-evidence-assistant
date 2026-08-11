from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = PROJECT_ROOT / "data" / "seed_evidence.jsonl"  # 优先 JSONL
_SEED_PATH_JSON = PROJECT_ROOT / "data" / "seed_evidence.json"  # 兼容旧格式
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

# ── BM25 参数 ──
BM25_K1 = 1.5          # 词频饱和参数
BM25_B = 0.75           # 长度归一化参数
# ── RRF 融合参数 ──
RRF_K = 60               # 标准 RRF 常数


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


# ═══════════════════════════════════════════════════════════════
# BM25 关键词检索引擎（中英混合分词，零额外依赖）
# ═══════════════════════════════════════════════════════════════

class BM25Index:
    """轻量 BM25 检索引擎。

    分词策略：
    - 中文：字符 bigram（如 "地中海" → "地中" "中海"）+ unigram（单字回退）
    - 英文：≥2 字母的单词
    - 数字：独立数字串

    索引在 index() 时一次性构建；增量添加通过 add_chunks() 触发重建。
    """

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B):
        self.k1 = k1
        self.b = b
        self._chunks: list[EvidenceChunk] = []
        self._doc_lengths: list[int] = []
        self._term_freqs: list[dict[str, int]] = []
        self._idf: dict[str, float] = {}
        self._avgdl: float = 0.0

    # ── 分词 ─────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text_lower = text.lower()
        tokens: list[str] = []

        # 中文 → bigram + unigram
        cjk_spans = re.findall(
            r'[一-鿿㐀-䶿豈-﫿]+', text_lower
        )
        for span in cjk_spans:
            for i in range(len(span) - 1):
                tokens.append(span[i:i + 2])
            for ch in span:
                tokens.append(ch)

        # 英文单词（≥2 字母）
        tokens.extend(re.findall(r'[a-z]{2,}', text_lower))

        # 数字串
        tokens.extend(re.findall(r'\d+', text_lower))

        return tokens

    # ── 索引构建 ─────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        return len(self._chunks) == 0

    def index(self, chunks: list[EvidenceChunk]) -> None:
        """从零构建 BM25 索引（IDF / 文档长度 / 词频）。"""
        self._chunks = list(chunks)
        self._doc_lengths.clear()
        self._term_freqs.clear()
        self._idf.clear()

        if not chunks:
            self._avgdl = 0.0
            return

        df: dict[str, int] = defaultdict(int)
        N = len(chunks)

        for chunk in chunks:
            text = f"{chunk.title}\n{chunk.content}"
            tokens = self._tokenize(text)
            self._doc_lengths.append(len(tokens))
            tf: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self._term_freqs.append(dict(tf))
            for t in set(tokens):
                df[t] += 1

        self._avgdl = sum(self._doc_lengths) / N

        for term, freq in df.items():
            self._idf[term] = math.log(
                (N - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def add_chunks(self, chunks: list[EvidenceChunk]) -> None:
        """增量添加文献（触发全量重建，因 IDF/avgdl 需重算）。"""
        if chunks:
            self.index(self._chunks + chunks)

    # ── 检索 ─────────────────────────────────────────────

    def _score(self, query_tokens: list[str], doc_idx: int) -> float:
        tf = self._term_freqs[doc_idx]
        dl = self._doc_lengths[doc_idx]
        total = 0.0
        for t in query_tokens:
            idf = self._idf.get(t, 0.0)
            if idf == 0.0:
                continue
            f = tf.get(t, 0)
            if f == 0:
                continue
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (
                1 - self.b + self.b * dl / max(self._avgdl, 1.0)
            )
            total += idf * numerator / denominator
        return total

    def search(
        self, query: str, limit: int = 10
    ) -> list[tuple[EvidenceChunk, float]]:
        """返回 (chunk, BM25_score) 降序列表。无匹配时返回空列表。"""
        if not self._chunks:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return [(self._chunks[0], 0.0)] if self._chunks else []
        scored = [
            (self._score(query_tokens, i), i)
            for i in range(len(self._chunks))
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            (self._chunks[i], s)
            for s, i in scored[:limit]
            if s > 0.0
        ]


# ═══════════════════════════════════════════════════════════════
# Reciprocal Rank Fusion（RRF）
# ═══════════════════════════════════════════════════════════════

def rrf_fusion(
    results_a: list[EvidenceChunk],
    results_b: list[EvidenceChunk],
    k: int = RRF_K,
    limit: int = 10,
) -> list[EvidenceChunk]:
    """将两个有序结果列表按 RRF 分数融合，返回 top-N。

    RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
    其中 k=60（标准常数），rank 从 1 开始。
    """
    scores: dict[str, tuple[float, EvidenceChunk]] = {}

    for rank, chunk in enumerate(results_a, start=1):
        cid = chunk.id
        inc = 1.0 / (k + rank)
        if cid in scores:
            scores[cid] = (scores[cid][0] + inc, chunk)
        else:
            scores[cid] = (inc, chunk)

    for rank, chunk in enumerate(results_b, start=1):
        cid = chunk.id
        inc = 1.0 / (k + rank)
        if cid in scores:
            scores[cid] = (scores[cid][0] + inc, chunk)
        else:
            scores[cid] = (inc, chunk)

    ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in ranked[:limit]]


# ═══════════════════════════════════════════════════════════════
# MMR 互补筛选（避免同类文献冗余）
# ═══════════════════════════════════════════════════════════════

# 证据类型层级（用于 MMR 类型分类）
_EVIDENCE_TYPE_MAP = {
    "系统综述/Meta分析": "meta",
    "临床指南/专家共识": "guideline",
    "随机对照试验": "rct",
    "综述": "review",
    "观察性研究": "observational",
    "其他研究": "other",
    "专业指南/科学声明": "guideline",
    "专业指南": "guideline",
    "国际指南": "guideline",
    "Review": "review",
    "Trial": "rct",
}

MMR_LAMBDA = 0.6  # 相关性 vs 多样性的权重（越高越看重相关性）


def _evidence_type(chunk: EvidenceChunk) -> str:
    """将证据等级映射到标准类型标签。"""
    return _EVIDENCE_TYPE_MAP.get(chunk.evidence_level, "other")


def mmr_diversify(
    candidates: list[EvidenceChunk],
    limit: int = 5,
    lmbda: float = MMR_LAMBDA,
) -> list[EvidenceChunk]:
    """MMR (Maximal Marginal Relevance) 互补筛选。

    从候选列表中选取 top-N，在保持相关性的同时最大化证据类型多样性。
    - 优先保证至少覆盖 meta/rct/guideline 三类不同类型
    - 同类文献超过 1 篇时施加递减惩罚
    """
    if len(candidates) <= limit:
        return candidates

    selected: list[EvidenceChunk] = []
    remaining = list(candidates)

    while remaining and len(selected) < limit:
        best_idx = 0
        best_score = -float("inf")

        for i, chunk in enumerate(remaining):
            # 相关性分数（位置越前越高）
            relevance = 1.0 - (i / max(len(remaining), 1))

            # 多样性惩罚：与已选文献同类型的数量越多，惩罚越大
            current_type = _evidence_type(chunk)
            penalty = 0.0
            for sel in selected:
                if _evidence_type(sel) == current_type:
                    penalty += 0.30  # 每多一篇同类型扣 0.3

            mmr = lmbda * relevance - (1 - lmbda) * penalty
            if mmr > best_score:
                best_score = mmr
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected


# ═══════════════════════════════════════════════════════════════
# EvidenceStore（混合检索入口）
# ═══════════════════════════════════════════════════════════════

class EvidenceStore:
    """Chroma 语义 + BM25 关键词 → RRF 混合检索。

    - Chroma 可用时：并行跑语义 + BM25，RRF 融合取 top-N
    - Chroma 不可用时：纯 BM25 检索
    """

    def __init__(
        self,
        seed_path: Path = SEED_PATH,
        persist_path: Path = CHROMA_PATH,
        enable_chroma: bool = True,
    ):
        self.seed_path = seed_path
        self.persist_path = persist_path
        self._chunks = self._load_seed()

        # BM25 索引（始终可用）
        self._bm25 = BM25Index()
        self._bm25.index(self._chunks)

        self._collection = None
        self.backend = "BM25 keyword retrieval"
        if enable_chroma:
            self._initialise_chroma()

    # ── 数据加载 ─────────────────────────────────────────

    def _load_seed(self) -> list[EvidenceChunk]:
        # 优先 JSONL（PPT 要求标准格式），回退 JSON
        if self.seed_path.exists():
            records = []
            for line in self.seed_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    records.append(json.loads(line))
            return [EvidenceChunk(**record) for record in records]
        if _SEED_PATH_JSON.exists():
            records = json.loads(_SEED_PATH_JSON.read_text(encoding="utf-8"))
            return [EvidenceChunk(**record) for record in records]
        raise FileNotFoundError(
            f"知识库文件未找到: {self.seed_path} 或 {_SEED_PATH_JSON}"
        )

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
            self.backend = "hybrid (Chroma + BM25 → RRF)"
        except Exception:
            self._collection = None

    # ── 增删 ─────────────────────────────────────────────

    def add_chunks(self, chunks: Iterable[EvidenceChunk]) -> int:
        new_chunks = list(chunks)
        if not new_chunks:
            return 0
        self._chunks.extend(new_chunks)

        # 同步 BM25
        self._bm25.add_chunks(new_chunks)

        # 同步 Chroma
        if self._collection is not None:
            self._collection.upsert(
                ids=[chunk.id for chunk in new_chunks],
                documents=[chunk.content for chunk in new_chunks],
                metadatas=[chunk.metadata() for chunk in new_chunks],
            )
        return len(new_chunks)

    # ── 混合检索 ─────────────────────────────────────────

    def search(self, question: str, limit: int = 4) -> list[EvidenceChunk]:
        """执行混合检索：Chroma 语义 + BM25 关键词 → RRF 融合。

        Chroma 不可用时退回纯 BM25。
        """
        # BM25 始终可用
        bm25_results = self._bm25.search(question, limit=limit * 3)
        bm25_chunks = [c for c, _ in bm25_results]

        # Chroma 语义检索
        if self._collection is not None:
            try:
                chroma_limit = limit * 2
                result = self._collection.query(
                    query_texts=[question], n_results=chroma_limit
                )
                chroma_chunks = [
                    EvidenceChunk(
                        id=result["ids"][0][idx],
                        content=result["documents"][0][idx],
                        **result["metadatas"][0][idx],
                    )
                    for idx in range(len(result["ids"][0]))
                ]
                # RRF 融合 → MMR 互补筛选
                fused = rrf_fusion(
                    chroma_chunks, bm25_chunks, k=RRF_K, limit=limit * 2
                )
                return mmr_diversify(fused, limit=limit)
            except Exception:
                pass

        # 纯 BM25 回退
        return bm25_chunks[:limit] if bm25_chunks else []
