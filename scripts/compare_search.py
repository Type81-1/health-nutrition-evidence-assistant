"""对比纯 Chroma 语义检索 vs BM25 关键词检索 vs RRF 混合检索。
使用方法: python scripts/compare_search.py "你的中文查询"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.evidence_store import EvidenceStore, BM25Index, rrf_fusion


SEP = "-" * 72
store = EvidenceStore()


def show_list(label: str, chunks: list, color: str = ""):
    print(f"\n  [{label}]  ({len(chunks)} 条)")
    if not chunks:
        print("    (无结果)")
        return
    for i, c in enumerate(chunks, 1):
        print(f"    {i}. {c.title[:68]}")
        print(f"       {c.source_type[:50]} | {c.year} | {c.evidence_level}")


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "地中海饮食对心血管有什么好处"

    print("=" * 72)
    print(f"  混合检索对比 · 查询: \"{query}\"")
    print(f"  知识库: {len(store._chunks)} 篇 | 后端: {store.backend}")
    print("=" * 72)

    # 1. 纯 Chroma 语义检索
    chroma_chunks: list = []
    if store._collection is not None:
        result = store._collection.query(query_texts=[query], n_results=6)
        from app.services.evidence_store import EvidenceChunk

        chroma_chunks = [
            EvidenceChunk(
                id=result["ids"][0][i],
                content=result["documents"][0][i],
                **result["metadatas"][0][i],
            )
            for i in range(len(result["ids"][0]))
        ]

    # 2. 纯 BM25 关键词检索
    bm25_scored = store._bm25.search(query, limit=6)
    bm25_chunks = [c for c, _ in bm25_scored]

    # 3. RRF 混合检索
    hybrid = store.search(query, limit=6)

    # ── 展示 ──
    show_list("Chroma 语义 (纯向量)", chroma_chunks)
    show_list("BM25 关键词 (纯词频)", bm25_chunks)
    show_list("RRF 混合融合 (最终输出)", hybrid)

    # ── 对比分析 ──
    print(f"\n{SEP}")
    print("  结果交集分析")
    print(SEP)

    chroma_ids = {c.id for c in chroma_chunks}
    bm25_ids = {c.id for c in bm25_chunks}
    hybrid_ids = {c.id for c in hybrid}

    both = chroma_ids & bm25_ids
    chroma_only = chroma_ids - bm25_ids
    bm25_only = bm25_ids - chroma_ids

    print(f"  Chroma 独有: {len(chroma_only)} 篇  (语义理解捕获，关键词匹配不到的)")
    for cid in chroma_only:
        c = next((x for x in chroma_chunks if x.id == cid), None)
        if c:
            print(f"    · {c.title[:60]}")

    print(f"  BM25 独有:   {len(bm25_only)} 篇  (关键词精准命中，语义相似度排不上)")
    for cid in bm25_only:
        c = next((x for x in bm25_chunks if x.id == cid), None)
        if c:
            print(f"    · {c.title[:60]}")

    print(f"  两者共有:    {len(both)} 篇  (双路共识，RRF 得分最高)")
    for cid in both:
        c = next((x for x in hybrid if x.id == cid), None)
        if c:
            print(f"    · {c.title[:60]}")

    print(f"\n  最终输出: {len(hybrid)} 篇 → RRF 融合后兼顾语义相关性 + 关键词精准度")


if __name__ == "__main__":
    main()
