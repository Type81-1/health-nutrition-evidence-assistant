from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    AnswerResponse,
    PubMedSearchRequest,
    QuestionRequest,
    SimplifyEvidenceRequest,
    SimplifyEvidenceResponse,
)
from app.services.answer_service import AnswerService
from app.services.evidence_store import EvidenceStore
from app.services.evidence_simplifier import EvidenceSimplifier
from app.services.pubmed_client import PubMedClient


STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="健康营养证据助手", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store = EvidenceStore()
answers = AnswerService(store)
pubmed = PubMedClient()
simplifier = EvidenceSimplifier(store)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "retrieval_backend": store.backend}


@app.post("/api/answer", response_model=AnswerResponse)
def answer_question(payload: QuestionRequest) -> AnswerResponse:
    return answers.answer(payload.question.strip())


@app.post("/api/pubmed/search")
async def pubmed_search(payload: PubMedSearchRequest) -> dict[str, object]:
    try:
        query_used = pubmed.build_query(payload.query.strip())
        return {
            "query_used": query_used,
            "articles": await pubmed.search(query_used, payload.limit),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail="PubMed 当前无法访问，请稍后重试。") from exc


@app.post("/api/evidence/simplify", response_model=SimplifyEvidenceResponse)
def simplify_evidence(payload: SimplifyEvidenceRequest) -> SimplifyEvidenceResponse:
    result = simplifier.simplify(payload.source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到对应证据。")
    plain_language, method = result
    return SimplifyEvidenceResponse(
        source_id=payload.source_id,
        plain_language=plain_language,
        method=method,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
