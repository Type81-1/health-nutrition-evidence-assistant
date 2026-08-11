"""结构化查询日志：每次问答记录为一行 JSON，方便排查和统计。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / "queries.jsonl"
MAX_LOG_SIZE_MB = 10


def _rotate_if_needed() -> None:
    """日志文件超过上限时重命名归档。"""
    if not LOG_FILE.exists():
        return
    if LOG_FILE.stat().st_size < MAX_LOG_SIZE_MB * 1024 * 1024:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOG_FILE.rename(LOG_DIR / f"queries_{stamp}.jsonl")


def log(entry: dict) -> None:
    """写入一条日志。自动附加时间戳。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed()
    entry.setdefault("ts", datetime.now(timezone.utc).isoformat())
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


class QueryTrace:
    """一次问答的完整链路追踪。"""

    def __init__(self, question: str, conversation_id: str | None = None) -> None:
        self.question = question
        self.conversation_id = conversation_id
        self._start = time.perf_counter()
        self.search_sources: list[dict] = []
        self.errors: list[str] = []
        self.llm_used = False
        self.citation_count = 0
        self.blocked = False
        self.block_reason = ""

    def add_search(self, source: str, query: str, result_count: int) -> None:
        self.search_sources.append({"source": source, "query": query[:200], "results": result_count})

    def add_error(self, error: str) -> None:
        self.errors.append(error)

    def finish(self, llm_used: bool, citation_count: int) -> None:
        self.llm_used = llm_used
        self.citation_count = citation_count
        duration_ms = round((time.perf_counter() - self._start) * 1000)
        log({
            "type": "answer",
            "question": self.question[:300],
            "conversation_id": self.conversation_id,
            "searches": self.search_sources,
            "llm_used": self.llm_used,
            "citations": self.citation_count,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "errors": self.errors,
            "duration_ms": duration_ms,
        })

    def mark_blocked(self, reason: str) -> None:
        self.blocked = True
        self.block_reason = reason
        duration_ms = round((time.perf_counter() - self._start) * 1000)
        log({
            "type": "safety_block",
            "question": self.question[:300],
            "reason": reason,
            "duration_ms": duration_ms,
        })
