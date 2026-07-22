from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import httpx


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

PUBMED_QUERY_EXPANSIONS = {
    "DASH": "DASH diet hypertension randomized trial blood pressure",
    "限钠": "dietary sodium reduction hypertension blood pressure",
    "减盐": "dietary sodium reduction hypertension blood pressure",
    "低盐": "dietary sodium reduction hypertension blood pressure",
    "高血压": "dietary sodium reduction hypertension blood pressure",
    "地中海": "Mediterranean diet cardiovascular disease prevention",
    "心血管": "diet cardiovascular disease prevention",
    "血脂": "dyslipidemia cholesterol dietary supplements cardiovascular risk",
    "胆固醇": "dyslipidemia cholesterol dietary supplements cardiovascular risk",
    "膳食纤维": "soluble fiber LDL cholesterol randomized trial meta-analysis",
    "全谷物": "whole grain LDL cholesterol randomized trial meta-analysis",
    "保健品": "dietary supplements dyslipidemia cardiovascular risk",
    "补充剂": "dietary supplements dyslipidemia cardiovascular risk",
    "鱼油": "omega-3 fatty acids fish oil dyslipidemia cardiovascular risk",
    "糖尿病": "glycemic index diet diabetes nutrition therapy systematic review",
    "控糖": "glycemic index diet diabetes nutrition therapy systematic review",
    "主食": "glycemic index dietary carbohydrate diabetes nutrition therapy",
    "含糖饮料": "sugar sweetened beverages diabetes cardiovascular risk meta-analysis",
    "添加糖": "free sugars sugar sweetened beverages diabetes guideline",
    "超加工": "ultra-processed food cardiovascular disease meta-analysis",
}


class PubMedClient:
    async def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        query = self._normalise_query(query)
        params = {"db": "pubmed", "term": query, "retmax": str(limit), "retmode": "json"}
        if os.getenv("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        if os.getenv("NCBI_EMAIL"):
            params["email"] = os.environ["NCBI_EMAIL"]
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            search = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
            search.raise_for_status()
            ids = search.json()["esearchresult"].get("idlist", [])
            if not ids:
                return []
            try:
                details = await client.get(
                    f"{EUTILS_BASE}/efetch.fcgi",
                    params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                )
                details.raise_for_status()
            except httpx.HTTPError:
                return await self._summarise_articles(client, ids)
        return self._parse_articles(details.text)

    @staticmethod
    def _normalise_query(query: str) -> str:
        matched = [
            expansion
            for trigger, expansion in PUBMED_QUERY_EXPANSIONS.items()
            if trigger in query
        ]
        if matched:
            return " OR ".join(dict.fromkeys(matched))
        return query

    @staticmethod
    def _parse_articles(xml_text: str) -> list[dict[str, str]]:
        root = ET.fromstring(xml_text)
        articles: list[dict[str, str]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID", default="")
            title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else "Untitled"
            abstract_parts = ["".join(part.itertext()) for part in article.findall(".//Abstract/AbstractText")]
            journal = article.findtext(".//Journal/Title", default="")
            year = article.findtext(".//PubDate/Year", default="") or article.findtext(".//ArticleDate/Year", default="")
            articles.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "abstract": " ".join(abstract_parts) or "PubMed 未提供摘要。",
                    "journal": journal,
                    "year": year,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
        return articles

    @staticmethod
    async def _summarise_articles(client: httpx.AsyncClient, ids: list[str]) -> list[dict[str, str]]:
        summary = await client.get(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        )
        summary.raise_for_status()
        return PubMedClient._parse_summaries(summary.json())

    @staticmethod
    def _parse_summaries(payload: dict) -> list[dict[str, str]]:
        result = payload.get("result", {})
        articles: list[dict[str, str]] = []
        for pmid in result.get("uids", []):
            item = result.get(pmid, {})
            articles.append(
                {
                    "pmid": pmid,
                    "title": item.get("title") or "Untitled",
                    "abstract": "PubMed summary endpoint did not return an abstract.",
                    "journal": item.get("fulljournalname") or item.get("source") or "",
                    "year": str(item.get("pubdate", ""))[:4],
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
        return articles
