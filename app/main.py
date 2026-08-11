from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import AnswerResponse, PubMedSearchRequest, QuestionRequest
from app.services.answer_service import REJECTION_PREAMBLE, SAFETY_NOTE, DOMAIN_REJECTION_MESSAGE, AnswerService, _build_context, check_safety, check_domain
from app.services.evidence_store import EvidenceChunk, EvidenceStore
from app.services.llm_client import OpenAICompatibleLlm
from app.services.pubmed_client import PubMedClient
from app.services.query_logger import QueryTrace
from app.services.source_plugins import EuropePmcOpenAccessPlugin


def _pubmed_to_chunks(articles: list[dict[str, str]]) -> list[EvidenceChunk]:
    """将检索结果转为证据片段列表。"""
    chunks: list[EvidenceChunk] = []
    for article in articles:
        pmid = article.get("pmid", "")
        source_label = "Europe PMC" if article.get("_source") == "europe_pmc" else "PubMed 文献"
        chunks.append(EvidenceChunk(
            id=f"pubmed-{pmid}",
            title=article.get("title", ""),
            source_type=f"{source_label} · {article.get('journal', '')}",
            year=article.get("year", "未标注"),
            url=article.get("url", ""),
            evidence_level="实时检索",
            content=f"{article.get('title', '')}\n{article.get('abstract', '')}",
        ))
    return chunks


def _rerank_chunks(chunks: list[EvidenceChunk], top_n: int = 8) -> list[EvidenceChunk]:
    """按权威性和时效性重排证据，优选出 top_n 条。"""

    def _authority_score(title: str) -> float:
        t = title.lower()
        if any(kw in t for kw in ("systematic review", "meta-analysis", "meta analysis")):
            return 1.0
        if any(kw in t for kw in ("guideline", "statement", "consensus", "recommendation")):
            return 0.9
        if any(kw in t for kw in ("randomized controlled trial", "randomised controlled trial", "rct", "randomized trial")):
            return 0.8
        if "review" in t:
            return 0.7
        if any(kw in t for kw in ("cohort", "prospective", "observational", "cross-sectional")):
            return 0.5
        if any(kw in t for kw in ("case report", "case series")):
            return 0.3
        return 0.4

    def _recency_score(year_str: str) -> float:
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            return 0.3
        from datetime import datetime
        age = datetime.now().year - year
        if age <= 0:
            return 1.0
        if age == 1:
            return 0.9
        if age <= 3:
            return 0.7
        if age <= 5:
            return 0.5
        if age <= 10:
            return 0.3
        return 0.1

    def _authority_label(title: str) -> str:
        score = _authority_score(title)
        if score >= 1.0:
            return "系统综述/Meta分析"
        if score >= 0.9:
            return "临床指南/专家共识"
        if score >= 0.8:
            return "随机对照试验"
        if score >= 0.7:
            return "综述"
        if score >= 0.5:
            return "观察性研究"
        return "其他研究"

    scored = []
    for chunk in chunks:
        auth = _authority_score(chunk.title)
        recency = _recency_score(chunk.year)
        total = auth * 0.6 + recency * 0.4
        # 更新证据等级标签
        chunk.evidence_level = _authority_label(chunk.title)
        scored.append((total, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_n]]


STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="健康营养证据助手", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store = EvidenceStore()
answers = AnswerService(store)
pubmed = PubMedClient()
europe_pmc = EuropePmcOpenAccessPlugin()
llm = OpenAICompatibleLlm()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "retrieval_backend": store.backend}


@app.post("/api/answer", response_model=AnswerResponse)
async def answer_question(payload: QuestionRequest) -> AnswerResponse:
    trace = QueryTrace(payload.question.strip(), payload.conversation_id)
    # 域外检测
    domain = check_domain(payload.question.strip())
    if not domain.safe:
        trace.mark_blocked(domain.reason)
        return AnswerResponse(
            answer_markdown=f"{DOMAIN_REJECTION_MESSAGE}",
            citations=[],
            safety_note=SAFETY_NOTE,
            retrieval_note=f"请求已拒绝：{domain.reason}",
        )
    safety = check_safety(payload.question.strip())
    if not safety.safe:
        trace.mark_blocked(safety.reason)
        return AnswerResponse(
            answer_markdown=f"{REJECTION_PREAMBLE}{safety.reason}",
            citations=[],
            safety_note=SAFETY_NOTE,
            retrieval_note="请求已被安全拦截。",
        )
    pubmed_error: str | None = None
    extra_evidence: list[EvidenceChunk] = []
    if payload.include_pubmed:
        query = llm.translate_to_pubmed_query(payload.question.strip()) or payload.question.strip()
        # 并行检索 PubMed + Europe PMC
        async def _search_pubmed() -> tuple[str, list[dict[str, str]]]:
            try:
                articles = await pubmed.search(query, limit=6)
                trace.add_search("pubmed", query, len(articles))
                return ("pubmed", articles)
            except Exception as exc:
                trace.add_error(f"PubMed: {type(exc).__name__}")
                return ("pubmed_error", [{"error": f"PubMed: {type(exc).__name__}"}])

        async def _search_europe_pmc() -> tuple[str, list[dict[str, str]]]:
            try:
                articles = await europe_pmc.search(query, limit=4)
                trace.add_search("europe_pmc", query, len(articles))
                return ("europe_pmc", articles)
            except Exception as exc:
                trace.add_error(f"Europe PMC: {type(exc).__name__}")
                return ("europe_pmc_error", [{"error": f"Europe PMC: {type(exc).__name__}"}])

        results = await asyncio.gather(_search_pubmed(), _search_europe_pmc())
        # 合并去重（按 PMID）
        seen_pmids: set[str] = set()
        all_articles: list[dict[str, str]] = []
        errors: list[str] = []
        for source, articles in results:
            if source.endswith("_error"):
                errors.append(articles[0]["error"] if articles else source)
                continue
            for a in articles:
                pmid = a.get("pmid", "")
                if pmid and pmid not in seen_pmids:
                    seen_pmids.add(pmid)
                    all_articles.append(a)
        extra_evidence = _rerank_chunks(_pubmed_to_chunks(all_articles))
        if errors:
            pubmed_error = f"部分数据源暂不可用（{'；'.join(errors)}）"
    resp = answers.answer(
        payload.question.strip(),
        extra_evidence=extra_evidence if extra_evidence else None,
        pubmed_error=pubmed_error,
        skip_local=bool(extra_evidence),  # 实时检索有结果就跳过本地
        conversation_id=payload.conversation_id,
    )
    trace.finish(llm_used=(resp.answer_markdown != "" and "[E" in resp.answer_markdown), citation_count=len(resp.citations))
    return resp


@app.post("/api/answer/stream")
async def answer_stream(payload: QuestionRequest):
    # 域外检测
    domain = check_domain(payload.question.strip())
    if not domain.safe:
        async def _domain_blocked():
            yield f"data: {json.dumps({'type': 'blocked', 'reason': DOMAIN_REJECTION_MESSAGE})}\n\n"
        return StreamingResponse(_domain_blocked(), media_type="text/event-stream")

    safety = check_safety(payload.question.strip())
    if not safety.safe:
        async def _blocked():
            yield f"data: {json.dumps({'type': 'blocked', 'reason': safety.reason})}\n\n"
        return StreamingResponse(_blocked(), media_type="text/event-stream")

    # 预处理（与 /api/answer 相同）
    pubmed_error: str | None = None
    extra_evidence: list[EvidenceChunk] = []
    if payload.include_pubmed:
        query = llm.translate_to_pubmed_query(payload.question.strip()) or payload.question.strip()
        async def _search_both():
            nonlocal pubmed_error, extra_evidence
            async def _s_pubmed():
                try:
                    articles = await pubmed.search(query, limit=6)
                    return ("pubmed", articles)
                except Exception as exc:
                    return ("pubmed_error", [{"error": f"PubMed: {type(exc).__name__}"}])
            async def _s_europe():
                try:
                    articles = await europe_pmc.search(query, limit=4)
                    return ("europe_pmc", articles)
                except Exception as exc:
                    return ("europe_pmc_error", [{"error": f"Europe PMC: {type(exc).__name__}"}])
            results = await asyncio.gather(_s_pubmed(), _s_europe())
            seen: set[str] = set()
            all_articles: list[dict[str, str]] = []
            errors: list[str] = []
            for source, articles in results:
                if source.endswith("_error"):
                    errors.append(articles[0]["error"] if articles else source)
                    continue
                for a in articles:
                    pmid = a.get("pmid", "")
                    if pmid and pmid not in seen:
                        seen.add(pmid)
                        all_articles.append(a)
            extra_evidence = _rerank_chunks(_pubmed_to_chunks(all_articles))
            if errors:
                pubmed_error = f"部分数据源暂不可用（{'；'.join(errors)}）"
        await _search_both()

    context_question = _build_context(payload.conversation_id, payload.question.strip())
    # 实时检索有结果就用，没有则回退本地知识库（需翻译中文查询）
    combined = list(extra_evidence)
    if not combined:
        search_query = llm.translate_to_pubmed_query(payload.question.strip()) or payload.question.strip()
        combined = store.search(search_query, limit=4)
    if not combined:
        async def _empty():
            yield f"data: {json.dumps({'type': 'error', 'message': '未检索到可用证据。'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    citations = [
        {
            "label": f"E{i+1}",
            "title": c.title,
            "source_type": c.source_type,
            "year": c.year,
            "url": c.url,
            "excerpt": c.content,
            "evidence_level": c.evidence_level,
        }
        for i, c in enumerate(combined)
    ]
    if extra_evidence:
        source_note = f"多源实时检索 {len(extra_evidence)} 条（PubMed + Europe PMC）"
    else:
        source_note = f"{store.backend} 选取 {len(combined)} 条"
    if pubmed_error:
        source_note += "；" + pubmed_error

    async def _stream():
        # 先发检索元数据
        yield f"data: {json.dumps({'type': 'meta', 'retrieval_note': source_note, 'citations': citations, 'safety_note': SAFETY_NOTE})}\n\n"
        full_text = ""
        async for chunk in llm.stream_answer(payload.question.strip(), combined):
            if chunk is None:
                # LLM 不可用，走 fallback
                fallback = answers._build_consumer_answer(payload.question.strip(), combined)
                yield f"data: {json.dumps({'type': 'chunk', 'text': fallback})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            full_text += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        if full_text and not re.search(r"\[E\d+\]", full_text):
            # 无引用，回退
            fallback = answers._build_consumer_answer(payload.question.strip(), combined)
            yield f"data: {json.dumps({'type': 'chunk', 'text': fallback})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/api/pubmed/search")
async def pubmed_search(payload: PubMedSearchRequest) -> dict[str, list[dict[str, str]]]:
    try:
        query = llm.translate_to_pubmed_query(payload.query.strip()) or payload.query.strip()
        return {"articles": await pubmed.search(query, payload.limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="PubMed 当前无法访问，请稍后重试。") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
