from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx


EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


@dataclass
class BatchDownloadResult:
    records: int
    xml_files: int
    output_dir: Path


class EuropePmcOpenAccessPlugin:
    """可独立复用的数据源插件：实时检索 + 批量获取 Europe PMC 的开放获取全文 XML。"""

    async def search(self, query: str, limit: int = 5, max_age_years: int = 10) -> list[dict[str, str]]:
        """实时检索 Europe PMC，返回与 PubMed 相同格式的文献列表。"""
        from datetime import datetime

        current_year = datetime.now().year
        query_with_filter = f"({query}) AND (PUB_YEAR:[{current_year - max_age_years} TO {current_year}])"
        params = {
            "query": query_with_filter,
            "format": "json",
            "pageSize": str(min(limit, 25)),
            "resultType": "core",
            "sort": "RELEVANCE",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{EUROPE_PMC_BASE}/search", params=params)
            resp.raise_for_status()
            results = resp.json().get("resultList", {}).get("result", [])[:limit]
        articles: list[dict[str, str]] = []
        for r in results:
            pmid = r.get("pmid", "")
            pmcid = r.get("pmcid", "")
            articles.append({
                "pmid": pmid or pmcid,
                "title": r.get("title", "Untitled"),
                "abstract": r.get("abstractText") or "Europe PMC 未提供摘要。",
                "journal": r.get("journalTitle", ""),
                "year": r.get("pubYear", ""),
                "url": f"https://europepmc.org/article/MED/{pmid}" if pmid else f"https://europepmc.org/article/PMC/{pmcid}",
                "_source": "europe_pmc",
            })
        return articles

    async def download(self, query: str, limit: int, output_dir: Path) -> BatchDownloadResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        params = {
            "query": f"({query}) AND OPEN_ACCESS:Y",
            "format": "json",
            "pageSize": str(min(limit, 100)),
            "resultType": "core",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{EUROPE_PMC_BASE}/search", params=params)
            response.raise_for_status()
            results = response.json().get("resultList", {}).get("result", [])[:limit]
            (output_dir / "metadata.json").write_text(
                __import__("json").dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            xml_files = 0
            for record in results:
                pmcid = record.get("pmcid")
                if not pmcid:
                    continue
                xml = await client.get(f"{EUROPE_PMC_BASE}/{pmcid}/fullTextXML")
                if xml.status_code == 200 and xml.text.strip():
                    (output_dir / f"{pmcid}.xml").write_text(xml.text, encoding="utf-8")
                    xml_files += 1
        return BatchDownloadResult(records=len(results), xml_files=xml_files, output_dir=output_dir)
