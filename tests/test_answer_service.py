from app.services.answer_service import AnswerService
from app.services.evidence_store import EvidenceStore


def test_answer_has_retrieved_citations() -> None:
    store = EvidenceStore(enable_chroma=False)
    response = AnswerService(store).answer("限钠饮食对高血压是否有帮助？")
    assert response.citations
    assert "[E1]" in response.answer_markdown
    assert all(citation.url for citation in response.citations)


def test_consumer_answer_includes_safety_boundary() -> None:
    store = EvidenceStore(enable_chroma=False)
    response = AnswerService(store).answer("地中海饮食对心血管风险有什么证据？")
    assert "不替代个体化诊疗" in response.safety_note
