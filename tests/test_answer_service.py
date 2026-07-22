from app.services.answer_service import AnswerService
from app.services.evidence_store import EvidenceStore
from app.services.pubmed_client import PubMedClient


def test_answer_has_retrieved_citations() -> None:
    store = EvidenceStore(enable_chroma=False)
    response = AnswerService(store).answer("限钠饮食对高血压是否有帮助？")
    assert response.citations
    assert "[E1]" in response.answer_markdown
    assert all(citation.url for citation in response.citations)


def test_keyword_retrieval_prioritises_sodium_evidence() -> None:
    store = EvidenceStore(enable_chroma=False)
    results = store.search("限钠饮食对高血压是否真的有帮助？")
    result_ids = [result.id for result in results]
    assert result_ids[0] in {"dashes-sodium-2001", "who-sodium-guideline-2012", "cochrane-salt-2021"}
    assert "mediterranean-predimed-2018" not in result_ids[:2]


def test_keyword_retrieval_prioritises_lipid_evidence() -> None:
    store = EvidenceStore(enable_chroma=False)
    results = store.search("膳食纤维对 LDL 胆固醇有帮助吗？")
    result_ids = [result.id for result in results]
    assert result_ids[0] == "soluble-fiber-lipids-2023"
    assert "soluble-fiber-lipids-2023" in result_ids[:2]


def test_consumer_answer_includes_safety_boundary() -> None:
    store = EvidenceStore(enable_chroma=False)
    response = AnswerService(store).answer("地中海饮食对心血管风险有什么证据？")
    assert "不替代个体化诊疗" in response.safety_note


def test_pubmed_query_normalises_common_chinese_topics() -> None:
    query = PubMedClient._normalise_query("限钠饮食对高血压是否真的有帮助？")
    assert "sodium" in query
    assert "hypertension" in query
    assert "ultra-processed" in PubMedClient._normalise_query("超加工食品对心血管健康有什么影响？")


def test_pubmed_summary_payload_is_renderable() -> None:
    articles = PubMedClient._parse_summaries(
        {
            "result": {
                "uids": ["123"],
                "123": {
                    "title": "Dietary sodium and blood pressure",
                    "fulljournalname": "Example Journal",
                    "pubdate": "2021 Jan",
                },
            }
        }
    )
    assert articles[0]["pmid"] == "123"
    assert articles[0]["title"] == "Dietary sodium and blood pressure"
    assert articles[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/123/"
