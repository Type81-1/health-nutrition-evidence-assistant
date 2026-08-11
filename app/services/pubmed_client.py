from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

import httpx


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


QUERY_CONCEPTS = (
    (("限钠", "低钠", "减钠", "少盐", "减盐", "控盐", "食盐", "盐"), '("Sodium, Dietary"[MeSH Terms] OR sodium[Title/Abstract] OR salt[Title/Abstract])'),
    (("高血压", "血压"), '("Hypertension"[MeSH Terms] OR "blood pressure"[Title/Abstract])'),
    (("地中海",), '("Diet, Mediterranean"[MeSH Terms] OR "Mediterranean diet"[Title/Abstract])'),
    (("心血管", "心脏", "中风"), '("Cardiovascular Diseases"[MeSH Terms] OR cardiovascular[Title/Abstract])'),
    (("dash",), '("Dietary Approaches To Stop Hypertension"[Title/Abstract] OR "DASH diet"[Title/Abstract])'),
    (("血脂", "胆固醇", "高脂血症"), '("Dyslipidemias"[MeSH Terms] OR cholesterol[Title/Abstract] OR lipid[Title/Abstract])'),
    (("保健品", "补充剂", "营养补充"), '("Dietary Supplements"[MeSH Terms] OR supplement*[Title/Abstract])'),
    (("维生素d", "维他命d"), '("Vitamin D"[MeSH Terms] OR "vitamin D"[Title/Abstract])'),
    (("睡眠", "失眠"), '("Sleep"[MeSH Terms] OR sleep[Title/Abstract] OR insomnia[Title/Abstract])'),
    (("减肥", "减重", "体重", "肥胖"), '("Weight Loss"[MeSH Terms] OR obesity[Title/Abstract] OR "body weight"[Title/Abstract])'),
    (("间歇性禁食", "间歇性断食", "轻断食"), '("intermittent fasting"[Title/Abstract] OR "time-restricted eating"[Title/Abstract])'),
    (("糖尿病", "血糖"), '("Diabetes Mellitus, Type 2"[MeSH Terms] OR "glycemic control"[Title/Abstract])'),
    (("膳食纤维", "纤维", "便秘"), '("Dietary Fiber"[MeSH Terms] OR constipation[Title/Abstract])'),
    (("益生菌", "肠道", "肠胃"), '("Probiotics"[MeSH Terms] OR probiotic*[Title/Abstract] OR "gut microbiota"[Title/Abstract])'),
    (("鱼油", "欧米伽3", "omega-3"), '("Fatty Acids, Omega-3"[MeSH Terms] OR omega-3[Title/Abstract])'),
    (("咖啡", "咖啡因"), '("Coffee"[MeSH Terms] OR coffee[Title/Abstract] OR caffeine[Title/Abstract])'),
    (("加工食品", "超加工食品"), '("ultra-processed food"[Title/Abstract] OR "processed food"[Title/Abstract])'),
    (("坚果",), '("Nuts"[MeSH Terms] OR nuts[Title/Abstract])'),
)

EVIDENCE_TYPE_TERMS = (
    (("系统综述", "meta分析", "荟萃分析"), '(systematic review[Publication Type] OR meta-analysis[Publication Type])'),
    (("随机对照", "随机试验", "rct"), 'randomized controlled trial[Publication Type]'),
    (("指南",), '(guideline[Publication Type] OR practice guideline[Publication Type])'),
)


class PubMedClient:
    @staticmethod
    def build_query(query: str) -> str:
        normalized = query.lower().replace(" ", "")
        concepts = [
            expression
            for aliases, expression in QUERY_CONCEPTS
            if any(alias in normalized for alias in aliases)
        ]
        evidence_types = [
            expression
            for aliases, expression in EVIDENCE_TYPE_TERMS
            if any(alias in normalized for alias in aliases)
        ]
        clauses = list(dict.fromkeys(concepts + evidence_types))
        return " AND ".join(clauses) if clauses else query.strip()

    async def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        candidate_limit = min(max(limit * 10, 30), 100)
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(candidate_limit),
            "retmode": "json",
            "sort": "relevance",
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
            detail_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
            if os.getenv("NCBI_API_KEY"):
                detail_params["api_key"] = os.environ["NCBI_API_KEY"]
            if os.getenv("NCBI_EMAIL"):
                detail_params["email"] = os.environ["NCBI_EMAIL"]
            details = await client.get(
                f"{EUTILS_BASE}/efetch.fcgi",
                params=detail_params,
            )
            details.raise_for_status()
        articles = self._parse_articles(details.text)
        return self._rank_articles(query, articles)[:limit]

    @staticmethod
    def _rank_articles(
        query: str, articles: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        title_abstract_terms = []
        for quoted, bare in re.findall(
            r'"([^"]+)"\[Title/Abstract\]|([A-Za-z0-9*-]+)\[Title/Abstract\]',
            query,
            flags=re.IGNORECASE,
        ):
            term = (quoted or bare).replace("*", "").lower()
            if term and term not in title_abstract_terms:
                title_abstract_terms.append(term)

        def score(article: dict[str, str]) -> int:
            title = article["title"].lower()
            abstract = article["abstract"].lower()
            publication_types = article["source_type"].lower()
            relevance = sum(
                10 if term in title else 2 if term in abstract else 0
                for term in title_abstract_terms
            )
            if any(
                evidence_type in publication_types
                for evidence_type in (
                    "systematic review",
                    "meta-analysis",
                    "randomized controlled trial",
                    "guideline",
                )
            ):
                relevance += 1
            return relevance

        return sorted(articles, key=score, reverse=True)

    @staticmethod
    def _parse_articles(xml_text: str) -> list[dict[str, str]]:
        root = ET.fromstring(xml_text)
        articles: list[dict[str, str]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID", default="")
            title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else "Untitled"
            abstract_parts = []
            for part in article.findall(".//Abstract/AbstractText"):
                label = part.attrib.get("Label", "").title()
                text = "".join(part.itertext()).strip()
                abstract_parts.append(f"{label}: {text}" if label else text)
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
                    "source_type": ", ".join(
                        item.text or "" for item in article.findall(".//PublicationTypeList/PublicationType")
                    ),
                }
            )
        return articles
