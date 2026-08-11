from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient:
    async def search(self, query: str, limit: int = 5, max_age_years: int = 10) -> list[dict[str, str]]:
        # 日期过滤：只检索近 N 年的文献
        current_year = datetime.now().year
        mindate = str(current_year - max_age_years)
        maxdate = str(current_year)
        # 优化检索精度：优先综述、Meta 分析、临床试验
        query_with_filter = f"({query}) AND ({mindate}[pdat]:{maxdate}[pdat])"
        params = {
            "db": "pubmed",
            "term": query_with_filter,
            "retmax": str(limit),
            "retmode": "json",
            "sort": "relevance",  # 按相关度排序（默认就是 relevance）
        }
        if os.getenv("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        if os.getenv("NCBI_EMAIL"):
            params["email"] = os.environ["NCBI_EMAIL"]
        async with httpx.AsyncClient(timeout=12) as client:
            search = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
            search.raise_for_status()
            ids = search.json()["esearchresult"].get("idlist", [])
            if not ids:
                return []
            details = await client.get(
                f"{EUTILS_BASE}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
            details.raise_for_status()
        return self._parse_articles(details.text)

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
                    "_source": "pubmed",
                }
            )
        return articles
