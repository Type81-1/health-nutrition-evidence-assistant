"""LLM Wiki 知识库 — 高频稳定营养主题的结构化页面。

定位：提前整理高频稳定科普主题，区别于每次实时检索的 RAG。
- Ingest: 新文献入库时自动/手动更新主题页
- Query: 提问优先读取结构化主题页，再补充原始文献
- Lint: 定期清理失效链接、过时结论、冲突观点

标准主题页结构:
  一句话结论 → 适用人群 → 核心证据 → 研究局限 → 禁止回答范围 → 更新时间
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIKI_PATH = PROJECT_ROOT / "data" / "wiki_topics.jsonl"


@dataclass
class WikiTopic:
    """结构化的 Wiki 主题页面。"""
    id: str                              # 唯一 slug，如 "mediterranean-diet"
    title: str                           # 主题名称
    one_liner: str                       # 一句话结论
    target_population: str               # 适用人群
    core_evidence: list[dict] = field(default_factory=list)  # [{text, source_ids}]
    limitations: str = ""                # 研究局限性
    scope_boundary: str = ""             # 无法回答的问题范围
    related_queries: list[str] = field(default_factory=list)  # 相关常见问题
    source_article_ids: list[str] = field(default_factory=list)  # 知识库中的文献 ID
    updated_at: str = ""                 # ISO 时间戳

    def to_text(self) -> str:
        """转为 LLM 可用的文本上下文。"""
        lines = [
            f"【Wiki 主题】{self.title}",
            f"【一句话结论】{self.one_liner}",
            f"【适用人群】{self.target_population}",
            "",
            "【核心证据】",
        ]
        for i, ev in enumerate(self.core_evidence, 1):
            srcs = ", ".join(ev.get("source_ids", []))
            lines.append(f"  {i}. {ev['text']}（来源: {srcs}）")
        if self.limitations:
            lines.append(f"\n【研究局限】{self.limitations}")
        if self.scope_boundary:
            lines.append(f"\n【回答边界】{self.scope_boundary}")
        lines.append(f"\n【更新时间】{self.updated_at}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "one_liner": self.one_liner,
            "target_population": self.target_population,
            "core_evidence": self.core_evidence,
            "limitations": self.limitations,
            "scope_boundary": self.scope_boundary,
            "related_queries": self.related_queries,
            "source_article_ids": self.source_article_ids,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WikiTopic:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class WikiStore:
    """LLM Wiki 主题知识库。"""

    def __init__(self, wiki_path: Path = WIKI_PATH):
        self.wiki_path = wiki_path
        self._topics: dict[str, WikiTopic] = {}
        self._load()

    def _load(self) -> None:
        if not self.wiki_path.exists():
            return
        for line in self.wiki_path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                topic = WikiTopic.from_dict(json.loads(line))
                self._topics[topic.id] = topic
            except (json.JSONDecodeError, TypeError):
                continue

    def _save(self) -> None:
        self.wiki_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.wiki_path, "w", encoding="utf-8") as f:
            for topic in self._topics.values():
                f.write(json.dumps(topic.to_dict(), ensure_ascii=False) + "\n")

    @property
    def topic_count(self) -> int:
        return len(self._topics)

    def list_topics(self) -> list[dict]:
        """返回所有主题的简要列表。"""
        return [
            {
                "id": t.id, "title": t.title,
                "one_liner": t.one_liner,
                "updated_at": t.updated_at,
            }
            for t in self._topics.values()
        ]

    def get_topic(self, topic_id: str) -> WikiTopic | None:
        return self._topics.get(topic_id)

    def search(self, query: str, top_n: int = 3) -> list[WikiTopic]:
        """关键词搜索 Wiki 主题（中英混合匹配）。"""
        q_lower = query.lower()
        # 中文按 bigram 拆分；英文按空格拆分
        cjk = re.findall(r'[一-鿿]+', q_lower)
        cjk_bigrams: set[str] = set()
        for span in cjk:
            for i in range(len(span) - 1):
                cjk_bigrams.add(span[i:i + 2])
        english_words = set(w.lower() for w in re.findall(r'[a-z]{2,}', q_lower))
        query_tokens = cjk_bigrams | english_words

        scored = []
        for topic in self._topics.values():
            searchable = (
                f"{topic.title} {topic.one_liner} "
                f"{topic.target_population} "
                f"{' '.join(topic.related_queries)}"
            ).lower()
            score = sum(1 for t in query_tokens if t in searchable)
            # 标题精确匹配加分
            title_tokens = set()
            for span in re.findall(r'[一-鿿]+', topic.title.lower()):
                for i in range(len(span) - 1):
                    title_tokens.add(span[i:i + 2])
            title_overlap = len(cjk_bigrams & title_tokens)
            score += title_overlap * 5
            scored.append((score, topic))
        scored.sort(key=lambda x: x[0], reverse=True)
        # 最低阈值：避免无健康关键词的查询误匹配 Wiki 主题
        # 例如 "PMID 99999999" 不应匹配到益生菌主题
        best_score = scored[0][0] if scored else 0
        if best_score < 3:  # 至少 3 个 bigram 命中或 1 个标题命中
            return []
        return [t for s, t in scored[:top_n] if s > 0]

    def upsert_topic(self, topic: WikiTopic) -> None:
        """添加或更新主题。"""
        self._topics[topic.id] = topic
        self._save()

    def remove_topic(self, topic_id: str) -> bool:
        if topic_id in self._topics:
            del self._topics[topic_id]
            self._save()
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# Wiki 主题生成 Prompt（LLM 从证据列表提炼结构化主题页）
# ═══════════════════════════════════════════════════════════════

WIKI_GENERATE_PROMPT = """你是一个健康营养 Wiki 编辑。请基于以下研究证据，生成一个结构化的主题知识页面。

要求：
1. **一句话结论**：用通俗语言回答这个主题的核心问题（不超过 80 字）
2. **适用人群**：明确这个结论适用于哪些人、不适用于哪些人（不超过 100 字）
3. **核心证据**：列出 3-5 条关键证据，每条包含具体研究发现和对应的文献编号（如 [E1]）
4. **研究局限**：客观说明现有证据的局限性（样本量、人群、随访时间等，不超过 100 字）
5. **禁止回答范围**：列出这个主题下不能回答的问题类型（如个体化用药、替代医疗等，不超过 80 字）
6. **相关常见问题**：列出 3-5 个用户可能追问的问题

主题：{topic_title}

可用证据：
{evidence_text}

请输出纯 JSON（不要 markdown 代码块包裹）：
{{"one_liner": "...", "target_population": "...", "core_evidence": [{{"text": "...", "source_ids": ["E1"]}}], "limitations": "...", "scope_boundary": "...", "related_queries": ["..."]}}"""


# ═══════════════════════════════════════════════════════════════
# 预设高频 Wiki 主题种子数据（确保即使 LLM 不可用也有基础覆盖）
# ═══════════════════════════════════════════════════════════════

_SEED_WIKI_TOPICS = [
    WikiTopic(
        id="mediterranean-diet",
        title="地中海饮食与心血管健康",
        one_liner="地中海饮食（富含蔬果、全谷物、橄榄油、鱼类，限制红肉和加工食品）可降低主要心血管事件风险约30%，证据来自多国大规模RCT和队列研究。",
        target_population="适用于心血管高风险人群及一般成年人的长期健康维护。正在服用降压药/降脂药/抗凝药者应咨询医生后再大幅调整饮食结构。",
        core_evidence=[
            {"text": "PREDIMED 随机对照试验（7447人，随访约5年）：特级初榨橄榄油或坚果补充的地中海饮食组主要心血管事件风险较对照组降低约30%。", "source_ids": ["E1"]},
            {"text": "多项前瞻性队列研究的Meta分析：高度依从地中海饮食模式与全因死亡风险降低约25%、心血管死亡降低约30%相关。", "source_ids": ["E2"]},
            {"text": "地中海饮食的抗炎作用机制：降低CRP、IL-6等炎症标志物水平，改善血管内皮功能。", "source_ids": ["E3"]},
            {"text": "2021年美国心脏协会科学声明及ESC指南均将地中海饮食推荐为心血管疾病预防的一线饮食模式。", "source_ids": ["E4"]},
        ],
        limitations="多数证据来自地中海沿岸国家人群，中国人群长期依从性的直接研究偏少；饮食成分的地域可获得性和烹饪习惯差异可能影响效果；观察性研究存在残余混杂。",
        scope_boundary="不能回答地中海饮食是否可替代降压/降脂药物；不能给出个体化每日食谱（需营养师评估）。",
        related_queries=["地中海饮食适合中国人吗？", "地中海饮食每天具体怎么吃？", "橄榄油比猪油健康多少？", "DASH饮食和地中海饮食哪个更好？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="sodium-hypertension",
        title="限钠饮食与血压控制",
        one_liner="减少钠摄入可显著降低血压（收缩压平均降低约4-5mmHg），对高血压患者效果更明显。WHO建议成人每日钠摄入<2g（盐<5g）。",
        target_population="高血压患者受益最大；正常血压人群同样受益但幅度较小。肾功能不全、正在服用利尿剂者需在医生指导下调整钠摄入。",
        core_evidence=[
            {"text": "Cochrane系统综述（多国RCT）：减钠使高血压患者收缩压降低约5.4mmHg、舒张压降低约2.8mmHg，正常血压者也轻度降低。", "source_ids": ["E1"]},
            {"text": "DASH-钠试验：减钠+DASH饮食组合降压力度最大，单纯减钠亦有明确效果，效应呈剂量-反应关系。", "source_ids": ["E2"]},
            {"text": "高钠摄入是全球疾病负担的主要膳食风险因素之一，与每年数百万心血管死亡相关。", "source_ids": ["E3"]},
        ],
        limitations="个体对钠敏感性存在差异；极低钠摄入（<1.5g/天）的安全性尚存争议；中国人均钠摄入远超推荐量（约10g盐/天），但直接研究偏少。",
        scope_boundary="不能回答是否需要停用降压药、如何调整药物剂量；不能替代高血压个体化治疗方案。",
        related_queries=["每天吃多少盐安全？", "低钠盐值得换吗？", "酱油蚝油里的钠怎么控制？", "不吃盐血压就能正常吗？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="dietary-cholesterol-eggs",
        title="膳食胆固醇与鸡蛋摄入",
        one_liner="对于大多数健康人，每天吃1个鸡蛋不会显著增加心血管风险，膳食胆固醇对血胆固醇的影响远小于饱和脂肪和反式脂肪。糖尿病患者需适度限制。",
        target_population="一般健康成年人每日1个鸡蛋是安全的。糖尿病患者、家族性高胆固醇血症患者应个体化评估。",
        core_evidence=[
            {"text": "多项大规模前瞻性队列研究Meta分析（数百万人-年随访）：每日1个鸡蛋与心血管风险无显著关联，但糖尿病患者中观察到轻微风险增加。", "source_ids": ["E1"]},
            {"text": "膳食胆固醇对血LDL-C的影响存在显著的个体差异（高反应vs低反应者），且饱和脂肪对血胆固醇的升高作用远大于膳食胆固醇本身。", "source_ids": ["E2"]},
            {"text": "鸡蛋富含优质蛋白、卵磷脂、叶黄素和多种维生素，其营养价值需要在风险评估中综合考量。", "source_ids": ["E3"]},
        ],
        limitations="多数研究为观察性，无法完全排除混杂因素（吃蛋多的人可能整体饮食模式也不健康）；缺乏10年以上长期RCT数据；中国人群每日蛋摄入量和烹饪方式的影响研究较少。",
        scope_boundary="不能回答高胆固醇血症是否可仅靠不吃蛋来控制；不能替代他汀类药物治疗决策。",
        related_queries=["每天吃几个鸡蛋安全？", "蛋白和蛋黄哪个更健康？", "高胆固醇的人能吃鸡蛋吗？", "鸡蛋和心脏病到底有没有关系？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="vitamin-d-bone",
        title="维生素D与骨骼健康",
        one_liner="维生素D联合钙补充对骨质疏松高风险人群（绝经后女性、老年人、长期室内工作者）降低骨折风险有益；对普通成人单补维生素D的骨骼获益证据不足。",
        target_population="绝经后女性、老年人、日照不足者、深肤色人群受益最明确；一般成年人不建议常规大剂量补充。",
        core_evidence=[
            {"text": "大规模Meta分析：单纯维生素D补充对普通人群骨折风险无显著降低；维生素D+钙联合补充使髋部骨折风险降低约16-30%，主要在老年及机构居住人群中。", "source_ids": ["E1"]},
            {"text": "维生素D的主要作用是促进肠道钙吸收和维持血钙水平，间接影响骨骼矿化；其骨骼外作用（免疫、心血管）仍在研究中。", "source_ids": ["E2"]},
            {"text": "各国指南推荐骨质疏松高风险人群每日补充维生素D 800-2000 IU，维持血清25(OH)D ≥50 nmol/L。", "source_ids": ["E3"]},
        ],
        limitations="不同研究对'充足'维D水平的定义不同；日照和食物强化地区的居民维D水平可能已然足够；大剂量间歇补充的骨折风险信号值得关注。",
        scope_boundary="不能回答具体补充剂量（需检测血清25(OH)D水平后由医生决定）；不能替代骨质疏松药物治疗方案。",
        related_queries=["维生素D每天该补多少？", "晒太阳够还需要补D吗？", "小孩需要补维生素D吗？", "维生素D能预防感冒吗？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="probiotics-gut",
        title="益生菌与肠道健康",
        one_liner="特定菌株的益生菌对抗生素相关性腹泻、肠易激综合征部分症状有中等证据支持；对普通健康人的肠道菌群改善效果尚不确切，产品间效果不可通用。",
        target_population="适用：抗生素使用者（预防腹泻）、IBS患者（部分菌株）、乳糖不耐受者。不适用：重症免疫功能低下者（有感染风险）。",
        core_evidence=[
            {"text": "Cochrane综述：益生菌使抗生素相关性腹泻风险降低约60%，以乳酸杆菌和布拉氏酵母菌证据最强（中等质量证据）。", "source_ids": ["E1"]},
            {"text": "部分菌株（如Bifidobacterium infantis 35624）对IBS腹胀和腹痛有中等改善效果，但不同菌株差异极大，效果不可外推。", "source_ids": ["E2"]},
            {"text": "健康人常规使用益生菌对肠道菌群多样性的改善证据不足；益生菌在肠道内的定植通常短暂（数天至数周）。", "source_ids": ["E3"]},
        ],
        limitations="益生菌市场产品菌株种类繁多，绝大多数缺乏独立RCT验证；菌株特异性意味着一种益生菌有效的结论不能类推到另一种；肠道菌群领域研究仍在快速发展，部分结论可能过时。",
        scope_boundary="不能推荐具体益生菌品牌或产品；不能说益生菌可治疗严重肠道疾病（IBD、艰难梭菌感染需医生处理）。",
        related_queries=["益生菌和益生元有什么区别？", "酸奶能替代益生菌补充剂吗？", "什么情况下该吃益生菌？", "益生菌有副作用吗？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="omega3-cardiovascular",
        title="Omega-3脂肪酸与心血管保护",
        one_liner="每周吃2-3次深海鱼（提供约250-500mg/天EPA+DHA）对心血管有保护作用；鱼油补充剂在当代他汀治疗背景下的增量获益证据有限且存争议。",
        target_population="推荐所有成年人每周摄入富含Omega-3的鱼类。已有心血管疾病者可能从高纯度EPA制剂获益，需医生评估。鱼过敏者可考虑藻油DHA替代。",
        core_evidence=[
            {"text": "多项队列研究一致显示鱼类摄入与心血管风险降低相关（每周2-3次鱼比不吃鱼降低约15-20%冠心病风险）。", "source_ids": ["E1"]},
            {"text": "REDUCE-IT试验：高纯度EPA（4g/天）在高心血管风险人群中降低主要心血管事件约25%，但低剂量鱼油在VITAL等试验中未显示心血管获益。", "source_ids": ["E2"]},
            {"text": "2021年AHA科学声明：Omega-3补充剂对普通人群心脏保护证据不足；优先推荐食补（鱼类）而非补充剂。", "source_ids": ["E3"]},
        ],
        limitations="鱼油补充剂剂量、纯度、EPA/DHA比例差异大，研究结果难以统一比较；REDUCE-IT的高剂量方案伴随轻微房颤风险增加；膳食鱼类中的Omega-3与其他营养成分协同作用难以分离。",
        scope_boundary="不能推荐具体鱼油品牌或剂量；不能用鱼油替代他汀等心血管药物。",
        related_queries=["深海鱼油保健品值得吃吗？", "三文鱼和金枪鱼哪个Omega-3多？", "素食者怎么补Omega-3？", "吃鱼油有副作用吗？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="intermittent-fasting",
        title="间歇性断食与代谢健康",
        one_liner="间歇性断食（16:8或5:2模式）在短期内可帮助减重（主要通过减少总热量摄入），对胰岛素敏感性有改善作用。长期效果和安全性数据有限，不适合孕妇、青少年、有进食障碍史者。",
        target_population="适用：超重/肥胖成年人短期体重管理（3-6个月）。不适用：孕妇、哺乳期、青少年、体重过低者、1型糖尿病、进食障碍史、正在使用降糖药/胰岛素者。",
        core_evidence=[
            {"text": "多项RCT的Meta分析：间歇性断食6-12个月减重效果与持续热量限制相当（约4-8%体重），无明确代谢优势，核心机制仍是总热量减少。", "source_ids": ["E1"]},
            {"text": "限时进食（TRE）试验：每日8-10小时进食窗口可改善胰岛素敏感性和β细胞功能，独立于体重变化（短期RCT证据）。", "source_ids": ["E2"]},
            {"text": "长期（>1年）依从性和安全性数据有限；部分研究中报告了轻度头晕、便秘、注意力不集中等不良反应。", "source_ids": ["E3"]},
        ],
        limitations="多数试验持续时间<12个月，长期心血管终点数据缺失；不同断食方案（16:8, 5:2, ADF）之间缺乏头对头比较；中国人群的断食研究极少。",
        scope_boundary="不能推荐糖尿病患者或用药人群自行尝试断食（有低血糖风险）；不能将断食作为疾病治疗方法推荐。",
        related_queries=["16:8和5:2哪种更好？", "断食期间能喝水吗？", "断食会影响肌肉吗？", "断食适合长期做吗？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
    WikiTopic(
        id="coffee-health",
        title="咖啡与健康影响",
        one_liner="适度饮用咖啡（每天2-4杯）与全因死亡率降低和多种慢性病风险下降相关；主要获益来自咖啡中的多酚类抗氧化物而非咖啡因。孕期应限制摄入。",
        target_population="一般成年人适度饮用有益。孕妇建议<200mg咖啡因/天（约1-2杯）；焦虑症、严重失眠、心律不齐者应减少或避免。",
        core_evidence=[
            {"text": "多项大型前瞻性队列Meta分析：每日3-4杯咖啡与全因死亡率降低约15%、心血管死亡率降低约20%相关。", "source_ids": ["E1"]},
            {"text": "咖啡摄入与2型糖尿病风险降低呈剂量-反应关系（每杯约降低7%），与肝癌风险降低约40%相关。", "source_ids": ["E2"]},
            {"text": "咖啡的短期升压效应在长期饮用者中减弱（耐受现象）；未观察到长期咖啡摄入增加高血压风险。", "source_ids": ["E3"]},
        ],
        limitations="多数证据来自观察性研究，咖啡饮用者的其他健康生活方式可能混淆结果；个体对咖啡因的代谢速率差异大（CYP1A2基因型）；加糖、加奶油的咖啡饮料可能抵消健康效益。",
        scope_boundary="不能回答咖啡是否可以替代药物；不能推荐咖啡作为疾病治疗方法。",
        related_queries=["每天喝多少咖啡安全？", "咖啡会让血压升高吗？", "孕妇能喝咖啡吗？", "速溶咖啡和现磨哪个健康？"],
        source_article_ids=[],
        updated_at="2026-08-11",
    ),
]


def seed_wiki_store(store: WikiStore) -> int:
    """向 WikiStore 写入预设主题（如尚不存在）。"""
    count = 0
    for topic in _SEED_WIKI_TOPICS:
        if topic.id not in store._topics:
            store.upsert_topic(topic)
            count += 1
    return count
