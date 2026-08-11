from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from app.services.evidence_store import EvidenceChunk, EvidenceStore


def markdown_chunks(markdown: str, title: str, source_url: str, source_type: str = "导入资料") -> list[EvidenceChunk]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", markdown) if len(item.strip()) >= 80]
    return [
        EvidenceChunk(
            id=f"import-{uuid4().hex}",
            title=title,
            source_type=source_type,
            year="未标注",
            url=source_url,
            evidence_level="待人工核验",
            content=paragraph[:1800],
        )
        for paragraph in paragraphs
    ]


def ingest_file(store: EvidenceStore, source: Path, title: str, source_url: str) -> int:
    if source.suffix.lower() == ".pdf":
        import pymupdf4llm

        markdown = pymupdf4llm.to_markdown(str(source))
    else:
        markdown = source.read_text(encoding="utf-8")
    return store.add_chunks(markdown_chunks(markdown, title, source_url))
