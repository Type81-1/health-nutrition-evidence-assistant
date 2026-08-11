"""从 PubMed + Europe PMC 批量拉取文献，扩增本地知识库。

使用方法:
    python scripts/expand_knowledge_base.py              # 全部拉取
    python scripts/expand_knowledge_base.py --dry        # 预览查询计划
    python scripts/expand_knowledge_base.py --quick      # 快速 5 维测试
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ENV_PATH = ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)

from app.services.evidence_store import EvidenceStore

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# ═══════════════════════════════════════════════════════
# 15 个核心健康维度（精简至实用覆盖）
# ═══════════════════════════════════════════════════════

DIMENSIONS = [
    # 饮食模式
    ("地中海饮食", "Mediterranean diet cardiovascular disease prevention"),
    ("DASH饮食与血压", "DASH diet dietary approaches stop hypertension blood pressure"),
    ("植物性饮食", "plant-based vegetarian vegan diet health outcomes chronic disease"),
    ("低碳水生酮饮食", "low carbohydrate ketogenic diet metabolic health weight loss"),
    # 代谢疾病
    ("糖尿病医学营养治疗", "diabetes mellitus medical nutrition therapy glycemic control"),
    ("肥胖减重饮食干预", "obesity weight management dietary intervention lifestyle"),
    ("血脂异常膳食管理", "dyslipidemia dietary fat saturated fat cholesterol cardiovascular"),
    # 营养素
    ("维生素D与钙", "vitamin D calcium supplementation bone health deficiency"),
    ("膳食纤维与肠道", "dietary fiber prebiotics gut microbiota gastrointestinal health"),
    ("Omega-3脂肪酸", "omega-3 fatty acids fish oil supplementation cardiovascular"),
    # 特殊人群
    ("孕期营养", "pregnancy maternal nutrition micronutrient supplementation outcomes"),
    ("儿童青少年营养", "childhood pediatric nutrition obesity prevention dietary guideline"),
    ("老年营养与肌少症", "elderly aging nutrition sarcopenia protein intake cognitive"),
    # 热门话题
    ("抗炎饮食", "anti-inflammatory dietary pattern chronic inflammation disease"),
    ("间歇性禁食", "intermittent fasting time-restricted eating cardiometabolic health"),
]

# 只取综述和临床试验两类（最多元互补）
TYPE_FILTERS = {
    "Review": 'AND (review[PT] OR meta-analysis[PT] OR "systematic review"[PT])',
    "Trial": 'AND ("randomized controlled trial"[PT] OR "controlled clinical trial"[PT] OR "clinical trial"[PT])',
}

# 两个年份区间
YEAR_RANGES = [
    (2021, 2026),   # 近期
    (2015, 2020),   # 中期
]

ARTICLES_PER_QUERY = 10
TARGET = 500


# ═══════════════════════════════════════════════════════
# API 客户端（含重试 + 限流控制）
# ═══════════════════════════════════════════════════════

async def fetch_pubmed(query: str, limit: int, y_min: int, y_max: int) -> list[dict]:
    """PubMed 检索（单次调用，失败返回空列表不抛异常）。"""
    full = f"({query}) AND ({y_min}[pdat]:{y_max}[pdat]) AND hasabstract[text]"
    params = {
        "db": "pubmed", "term": full, "retmax": str(limit),
        "retmode": "json", "sort": "relevance",
    }
    if os.getenv("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    if os.getenv("NCBI_EMAIL"):
        params["email"] = os.environ["NCBI_EMAIL"]

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=25) as cli:
                sr = await cli.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
                sr.raise_for_status()
                ids = sr.json()["esearchresult"].get("idlist", [])
                if not ids:
                    return []
                dr = await cli.get(
                    f"{EUTILS_BASE}/efetch.fcgi",
                    params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                )
                dr.raise_for_status()
            articles = []
            root_el = ET.fromstring(dr.text)
            for a in root_el.findall(".//PubmedArticle"):
                pmid = a.findtext(".//PMID", default="")
                t_el = a.find(".//ArticleTitle")
                title = "".join(t_el.itertext()) if t_el is not None else "Untitled"
                abs_parts = ["".join(p.itertext()) for p in a.findall(".//Abstract/AbstractText")]
                abstract = " ".join(abs_parts)
                if not abstract or len(abstract) < 80:
                    continue
                journal = a.findtext(".//Journal/Title", default="")
                year = a.findtext(".//PubDate/Year", default="") or a.findtext(".//ArticleDate/Year", default="")
                articles.append({
                    "pmid": pmid, "title": title, "abstract": abstract[:2000],
                    "journal": journal, "year": year or "未标注",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "_source": "pubmed",
                })
            return articles
        except Exception:
            if attempt < 2:
                await asyncio.sleep(2)
    return []


async def fetch_europe_pmc(query: str, limit: int, y_min: int, y_max: int) -> list[dict]:
    """Europe PMC 检索。"""
    full = f"({query}) AND HAS_ABSTRACT:Y AND (PUB_YEAR:[{y_min} TO {y_max}])"
    params = {
        "query": full, "format": "json",
        "pageSize": str(min(limit, 25)), "resultType": "core",
        "sort": "RELEVANCE",
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.get(f"{EPMC_BASE}/search", params=params)
                r.raise_for_status()
                results = r.json().get("resultList", {}).get("result", [])[:limit]
            articles = []
            for item in results:
                pmid = item.get("pmid", "") or item.get("pmcid", "")
                abstract = item.get("abstractText") or ""
                if not abstract or len(abstract) < 80:
                    continue
                articles.append({
                    "pmid": pmid,
                    "title": item.get("title", "Untitled"),
                    "abstract": abstract[:2000],
                    "journal": item.get("journalTitle", ""),
                    "year": item.get("pubYear", ""),
                    "url": (f"https://europepmc.org/article/MED/{item['pmid']}"
                            if item.get("pmid") else
                            f"https://europepmc.org/article/PMC/{item.get('pmcid', '')}"),
                    "_source": "europe_pmc",
                })
            return articles
        except Exception:
            if attempt < 2:
                await asyncio.sleep(2)
    return []


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--quick", action="store_true", help="只跑前 5 个维度")
    args = parser.parse_args()

    dims = DIMENSIONS[:5] if args.quick else DIMENSIONS

    # 生成计划
    plan = []
    for topic, query in dims:
        for type_key, type_filter in TYPE_FILTERS.items():
            for y_min, y_max in YEAR_RANGES:
                plan.append({"topic": topic, "base_query": query, "type": type_key,
                             "type_filter": type_filter, "y_min": y_min, "y_max": y_max})

    total_slots = len(plan) * ARTICLES_PER_QUERY * 2
    print("=" * 60)
    print(f"知识库扩增 · {len(dims)} 维 × {len(TYPE_FILTERS)} 类 × {len(YEAR_RANGES)} 年 = {len(plan)} 查询")
    print(f"每查询 {ARTICLES_PER_QUERY} 篇 × PubMed+EPMC = 预计 ~{total_slots} 篇 raw → ~{TARGET} 篇（去重后）")
    print("=" * 60)

    if args.dry:
        for i, p in enumerate(plan):
            print(f"  [{i+1:02d}] {p['topic']} · {p['type']} · {p['y_min']}-{p['y_max']}")
        return

    seen: set[str] = set()
    all_articles: list[dict] = []
    stats = {"pubmed": 0, "epmc": 0, "err": 0}
    sem = asyncio.Semaphore(1)  # 串行请求，避免限流

    async def one(p: dict, idx: int):
        nonlocal all_articles, stats
        async with sem:
            pubmed_q = p["base_query"] + " " + p["type_filter"].replace("AND ", "")
            t0 = time.perf_counter()
            pubmed_r = await fetch_pubmed(pubmed_q, ARTICLES_PER_QUERY, p["y_min"], p["y_max"])
            stats["pubmed"] += len(pubmed_r)

            epmc_r = await fetch_europe_pmc(p["base_query"], ARTICLES_PER_QUERY, p["y_min"], p["y_max"])
            stats["epmc"] += len(epmc_r)

            new = 0
            for a in pubmed_r + epmc_r:
                pid = a.get("pmid", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    a["_topic"] = p["topic"]
                    a["_type"] = p["type"]
                    a["_year_range"] = f"{p['y_min']}-{p['y_max']}"
                    all_articles.append(a)
                    new += 1

            elapsed = (time.perf_counter() - t0) * 1000
            print(f"  [{idx+1:02d}/{len(plan)}] {p['topic']:<12} {p['type']:<6} "
                  f"{p['y_min']}-{p['y_max']}  "
                  f"PM:{len(pubmed_r):>2}  EPMC:{len(epmc_r):>2}  +{new:>2}  "
                  f"累计:{len(all_articles):>3}  {elapsed:.0f}ms")

            await asyncio.sleep(1.5)  # API 限流保护

    print(f"\n开始检索...\n")
    start = time.perf_counter()
    for i, p in enumerate(plan):
        await one(p, i)

    elapsed = time.perf_counter() - start

    # 统计
    print(f"\n{'='*60}")
    print(f"检索完成 · PM:{stats['pubmed']}  EPMC:{stats['epmc']}  去重:{len(all_articles)}  耗时:{elapsed:.0f}s")
    print(f"{'='*60}")

    year_dist: dict[str, int] = {}
    for a in all_articles:
        y = a.get("year", "?")
        year_dist[y] = year_dist.get(y, 0) + 1
    print("年份分布:")
    for y in sorted(year_dist.keys()):
        bar = "█" * min(year_dist[y], 40)
        print(f"  {y}: {year_dist[y]:>3}  {bar}")

    # 保存
    seed_path = ROOT / "data" / "seed_evidence.json"
    existing = json.loads(seed_path.read_text("utf-8")) if seed_path.exists() else []
    new_chunks = []
    for a in all_articles:
        src = "Europe PMC" if a.get("_source") == "europe_pmc" else "PubMed"
        new_chunks.append({
            "id": f"kb-{a.get('pmid', '')}",
            "title": a["title"],
            "source_type": f"{src} · {a.get('journal', '')}",
            "year": a.get("year", "未标注"),
            "url": a.get("url", ""),
            "evidence_level": a.get("_type", "实时检索"),
            "content": f"{a['title']}\n{a.get('abstract', '')}",
        })

    all_seed = existing + new_chunks
    print(f"\n合并: {len(existing)} (旧) + {len(new_chunks)} (新) = {len(all_seed)} 篇")

    if seed_path.exists():
        import shutil as _shutil
        _shutil.move(str(seed_path), str(seed_path.with_suffix(".json.bak")))
    seed_path.write_text(json.dumps(all_seed, ensure_ascii=False, indent=2), "utf-8")
    print(f"已写入: {seed_path}")

    # 重建 Chroma
    chroma_path = ROOT / "data" / "chroma"
    try:
        if chroma_path.exists():
            import shutil
            shutil.rmtree(chroma_path)
        store = EvidenceStore(seed_path=seed_path, persist_path=chroma_path, enable_chroma=True)
        print(f"Chroma: {len(store._chunks)} 条 · {store.backend}")
    except PermissionError:
        print(f"[!] Chroma 被占用，请停服后手动: 删 data/chroma 再重启")

    print(f"\n完成。")


if __name__ == "__main__":
    asyncio.run(main())
