from __future__ import annotations

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# ═══════════════════════════════════════════════════════════════
# MeSH 主题词映射表（英文关键词 → MeSH 标准词）
# 覆盖常见营养、代谢疾病、心血管等领域
# ═══════════════════════════════════════════════════════════════

_MESH_MAP: dict[str, list[str]] = {
    # 饮食模式
    "mediterranean diet": ["Diet, Mediterranean", "Cardiovascular Diseases/prevention & control"],
    "dash diet": ["Dietary Approaches To Stop Hypertension", "Hypertension/diet therapy"],
    "ketogenic diet": ["Diet, Ketogenic", "Diet, Carbohydrate-Restricted"],
    "low carbohydrate": ["Diet, Carbohydrate-Restricted", "Diet, High-Protein Low-Carbohydrate"],
    "plant-based diet": ["Diet, Vegetarian", "Diet, Vegan"],
    "vegetarian": ["Diet, Vegetarian"],
    "intermittent fasting": ["Fasting", "Caloric Restriction"],
    "time-restricted eating": ["Fasting", "Feeding Behavior"],
    "anti-inflammatory diet": ["Inflammation/diet therapy", "Diet", "Anti-Inflammatory Agents"],

    # 代谢疾病
    "diabetes": ["Diabetes Mellitus/diet therapy", "Diabetes Mellitus, Type 2/diet therapy", "Blood Glucose"],
    "glycemic control": ["Glycemic Control", "Blood Glucose/metabolism", "Glycemic Index"],
    "obesity": ["Obesity/diet therapy", "Weight Loss", "Body Mass Index"],
    "weight loss": ["Weight Loss", "Obesity/diet therapy", "Caloric Restriction"],
    "weight management": ["Body Weight Maintenance", "Weight Loss", "Obesity/prevention & control"],
    "dyslipidemia": ["Dyslipidemias/diet therapy", "Cholesterol, LDL/blood", "Triglycerides/blood"],
    "hyperlipidemia": ["Hyperlipidemias/diet therapy", "Cholesterol/blood"],
    "metabolic syndrome": ["Metabolic Syndrome/diet therapy", "Insulin Resistance"],

    # 心血管
    "hypertension": ["Hypertension/diet therapy", "Blood Pressure", "Sodium, Dietary"],
    "blood pressure": ["Blood Pressure", "Hypertension", "Sodium, Dietary"],
    "cardiovascular disease": ["Cardiovascular Diseases/prevention & control", "Heart Disease Risk Factors"],
    "cardiovascular": ["Cardiovascular Diseases/prevention & control", "Heart Disease Risk Factors"],
    "coronary heart disease": ["Coronary Disease/diet therapy", "Coronary Disease/prevention & control"],
    "stroke": ["Stroke/prevention & control", "Cerebrovascular Disorders"],
    "cholesterol": ["Cholesterol/blood", "Cholesterol, Dietary", "Cholesterol, LDL"],
    "ldl": ["Cholesterol, LDL/blood", "Cholesterol, LDL/drug effects"],
    "triglyceride": ["Triglycerides/blood", "Hypertriglyceridemia/diet therapy"],

    # 营养素
    "vitamin d": ["Vitamin D", "Vitamin D Deficiency", "Dietary Supplements"],
    "calcium": ["Calcium, Dietary", "Calcium", "Bone Density"],
    "omega-3": ["Fatty Acids, Omega-3", "Fish Oils", "Eicosapentaenoic Acid"],
    "fish oil": ["Fish Oils", "Fatty Acids, Omega-3", "Dietary Supplements"],
    "fiber": ["Dietary Fiber", "Prebiotics", "Gastrointestinal Microbiome"],
    "dietary fiber": ["Dietary Fiber", "Gastrointestinal Microbiome", "Digestive System"],
    "protein": ["Dietary Proteins", "Diet, High-Protein", "Amino Acids"],
    "vitamin c": ["Ascorbic Acid", "Ascorbic Acid/therapeutic use", "Common Cold/prevention & control"],
    "magnesium": ["Magnesium", "Magnesium/blood", "Dietary Supplements"],
    "potassium": ["Potassium, Dietary", "Potassium/blood", "Hypertension"],
    "iron": ["Iron, Dietary", "Anemia, Iron-Deficiency/diet therapy"],
    "zinc": ["Zinc", "Dietary Supplements", "Zinc/deficiency"],

    # 特殊人群
    "pregnancy": ["Pregnancy", "Maternal Nutritional Physiological Phenomena", "Prenatal Care"],
    "maternal": ["Maternal Nutritional Physiological Phenomena", "Pregnancy", "Dietary Supplements"],
    "child": ["Child Nutritional Physiological Phenomena", "Child", "Pediatric Obesity/prevention & control"],
    "pediatric": ["Child", "Adolescent", "Pediatric Obesity"],
    "elderly": ["Aged", "Aging", "Nutritional Status", "Sarcopenia"],
    "aging": ["Aging", "Aged", "Sarcopenia/prevention & control"],

    # 肠道与免疫
    "probiotic": ["Probiotics", "Gastrointestinal Microbiome", "Prebiotics"],
    "gut microbiota": ["Gastrointestinal Microbiome", "Probiotics", "Prebiotics"],
    "inflammation": ["Inflammation/diet therapy", "C-Reactive Protein", "Anti-Inflammatory Agents"],

    # 其他疾病
    "gout": ["Gout/diet therapy", "Hyperuricemia/diet therapy", "Uric Acid/blood"],
    "uric acid": ["Uric Acid/blood", "Hyperuricemia/diet therapy", "Gout"],
    "osteoporosis": ["Osteoporosis/prevention & control", "Bone Density", "Calcium, Dietary"],
    "bone health": ["Bone Density", "Osteoporosis/prevention & control", "Vitamin D"],
    "kidney disease": ["Renal Insufficiency, Chronic/diet therapy", "Diet, Protein-Restricted"],
    "renal": ["Renal Insufficiency, Chronic/diet therapy", "Kidney/diet therapy"],
    "sarcopenia": ["Sarcopenia/prevention & control", "Dietary Proteins", "Aged"],

    # 常见食物
    "egg": ["Eggs", "Cholesterol, Dietary", "Diet"],
    "coffee": ["Coffee", "Caffeine", "Cardiovascular Diseases"],
    "tea": ["Tea", "Catechins", "Antioxidants"],
    "green tea": ["Tea", "Catechins", "Antioxidants"],
    "red wine": ["Wine", "Alcoholic Beverages", "Cardiovascular Diseases"],
    "alcohol": ["Alcohol Drinking", "Ethanol", "Alcoholic Beverages"],
    "olive oil": ["Olive Oil", "Diet, Mediterranean", "Plant Oils"],
    "nuts": ["Nuts", "Diet", "Cardiovascular Diseases"],
    "soy": ["Soybeans", "Soy Foods", "Isoflavones"],
    "garlic": ["Garlic", "Allium", "Dietary Supplements"],
    "red meat": ["Red Meat", "Meat", "Cardiovascular Diseases"],
}

# Article type filter (PubMed Publication Type qualifiers)
_ARTICLE_TYPE_FILTER = (
    "(review[PT] OR meta-analysis[PT] OR \"systematic review\"[PT] "
    "OR \"randomized controlled trial\"[PT] OR \"controlled clinical trial\"[PT] "
    "OR guideline[PT] OR \"practice guideline\"[PT])"
)

# 撤稿/不完整排除
_RETRACTION_FILTER = "NOT retracted publication[PT] NOT retraction of publication[PT]"
# 必须有摘要
_HAS_ABSTRACT_FILTER = "hasabstract[text]"


def _extract_key_concepts(english_query: str) -> list[str]:
    """从英文查询中提取核心概念词（按长度降序，优先匹配更具体的词）。"""
    query_lower = english_query.lower()
    # 去括号和特殊字符
    query_clean = re.sub(r'[\[\]\"\'\(\)]', ' ', query_lower)
    concepts = []
    # 先按长词匹配（如 "mediterranean diet" 优于 "diet"）
    sorted_keys = sorted(_MESH_MAP.keys(), key=len, reverse=True)
    matched_positions: set[int] = set()
    for key in sorted_keys:
        pos = query_clean.find(key)
        if pos >= 0:
            # 检查是否已被更长的匹配覆盖
            key_range = set(range(pos, pos + len(key)))
            if not key_range & matched_positions:
                concepts.append(key)
                matched_positions |= key_range
    return concepts


def _lookup_mesh_terms(concepts: list[str]) -> list[str]:
    """根据英文概念返回对应的 MeSH 术语列表。"""
    mesh_terms: list[str] = []
    seen: set[str] = set()
    for concept in concepts:
        for mesh in _MESH_MAP.get(concept, []):
            mesh_lower = mesh.lower()
            if mesh_lower not in seen:
                mesh_terms.append(mesh)
                seen.add(mesh_lower)
    return mesh_terms


async def _lookup_mesh_api(keyword: str) -> list[str]:
    """通过 NCBI MeSH API 查找未知关键词的 MeSH 术语（备用）。"""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{EUTILS_BASE}/esearch.fcgi",
                params={
                    "db": "mesh",
                    "term": keyword,
                    "retmax": "3",
                    "retmode": "json",
                },
            )
            r.raise_for_status()
            ids = r.json()["esearchresult"].get("idlist", [])
            if not ids:
                return []
            # Fetch MeSH term names
            r2 = await client.get(
                f"{EUTILS_BASE}/efetch.fcgi",
                params={
                    "db": "mesh",
                    "id": ",".join(ids[:3]),
                    "retmode": "xml",
                },
            )
            r2.raise_for_status()
            root = ET.fromstring(r2.text)
            terms: list[str] = []
            for descriptor in root.findall(".//DescriptorName"):
                name = descriptor.findtext("String", default="")
                if name:
                    terms.append(name)
            return terms
    except Exception:
        return []


def build_pubmed_query(
    english_query: str,
    max_age_years: int = 10,
    include_mesh: bool = True,
    include_article_types: bool = True,
) -> str:
    """构建包含四重过滤的 PubMed 检索式。

    1. MeSH 主题词
    2. 干预/自由文本关键词
    3. 年限（近 N 年）
    4. 文献类型（综述/Meta/RCT/指南）
    """
    current_year = datetime.now().year
    parts: list[str] = []

    # 自由文本关键词
    cleaned = re.sub(r'[\[\]\"\'\(\)]', ' ', english_query)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    parts.append(f"({cleaned})")

    # MeSH 主题词
    if include_mesh:
        concepts = _extract_key_concepts(english_query)
        mesh_terms = _lookup_mesh_terms(concepts)
        if mesh_terms:
            mesh_str = " OR ".join(f'"{m}"[MeSH Terms]' for m in mesh_terms[:6])
            parts.append(f"({mesh_str})")

    # 文献类型
    if include_article_types:
        parts.append(_ARTICLE_TYPE_FILTER)

    # 日期范围
    mindate = str(current_year - max_age_years)
    maxdate = str(current_year)
    parts.append(f"({mindate}[pdat]:{maxdate}[pdat])")

    # 摘要 + 撤稿过滤
    parts.append(_HAS_ABSTRACT_FILTER)
    parts.append(_RETRACTION_FILTER)

    # OR 组合（MeSH 和自由文本是互补的）
    if len(parts) > 3:
        # 有 MeSH: (keywords) OR (MeSH) AND type AND date AND abstract AND retraction
        keyword_part = parts[0]
        mesh_part = parts[1]
        rest = " AND ".join(parts[2:])
        return f"({keyword_part} OR {mesh_part}) AND {rest}"
    else:
        return " AND ".join(parts)


class PubMedClient:
    """PubMed E-utilities 客户端（含 MeSH + 文献类型 + 年限四重过滤）。"""

    async def search(
        self, query: str, limit: int = 5, max_age_years: int = 10
    ) -> list[dict[str, str]]:
        query_with_filter = build_pubmed_query(
            english_query=query,
            max_age_years=max_age_years,
            include_mesh=True,
            include_article_types=True,
        )
        params = {
            "db": "pubmed",
            "term": query_with_filter,
            "retmax": str(limit),
            "retmode": "json",
            "sort": "relevance",
        }
        if os.getenv("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        if os.getenv("NCBI_EMAIL"):
            params["email"] = os.environ["NCBI_EMAIL"]

        async with httpx.AsyncClient(timeout=15) as client:
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

    def search_sync(
        self, query: str, limit: int = 5, max_age_years: int = 10
    ) -> list[dict[str, str]]:
        """同步包装，供非 async 环境使用。"""
        return asyncio.run(self.search(query, limit, max_age_years))

    @staticmethod
    def _parse_articles(xml_text: str) -> list[dict[str, str]]:
        root = ET.fromstring(xml_text)
        articles: list[dict[str, str]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID", default="")
            title_el = article.find(".//ArticleTitle")
            title = (
                "".join(title_el.itertext())
                if title_el is not None
                else "Untitled"
            )
            abstract_parts = [
                "".join(part.itertext())
                for part in article.findall(".//Abstract/AbstractText")
            ]
            abstract_text = " ".join(abstract_parts)
            # 跳过空摘要
            if not abstract_text or len(abstract_text) < 80:
                continue
            journal = article.findtext(".//Journal/Title", default="")
            year = (
                article.findtext(".//PubDate/Year", default="")
                or article.findtext(".//ArticleDate/Year", default="")
            )
            # 提取文献类型标签
            pub_types = [
                pt.text
                for pt in article.findall(".//PublicationType")
                if pt.text
            ]
            articles.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract_text[:2000],
                    "journal": journal,
                    "year": year or "未标注",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "pub_types": "|".join(pub_types),
                    "_source": "pubmed",
                }
            )
        return articles
