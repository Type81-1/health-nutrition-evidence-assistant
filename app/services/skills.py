"""标准化技能层（Skill Layer）—— D2 文档必做模块。

Skill = 固化重复专业判断标准，按需加载的轻量化逻辑。
与 Tool 的区别：Tool 负责外部动作执行，Skill 负责领域判断与标准化规则。

设计原则：
- 常驻 Prompt 仅保留安全红线（最小化 token 消耗）
- 其余规则按触发条件动态加载
- 每个 Skill 独立定义、独立测试、可组合
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Skill:
    """单个技能的完整定义。"""
    name: str
    description: str
    prompt_content: str           # 加载到 Prompt 的内容
    triggers: list[str] = field(default_factory=list)   # 触发关键词
    always_load: bool = False     # 是否常驻
    category: str = "general"     # safety / format / language / reasoning


# ═══════════════════════════════════════════════════════════════
# Lean 常驻 Prompt（仅安全红线，其余全拆为 Skill）
# ═══════════════════════════════════════════════════════════════

CORE_PROMPT = """你是面向普通消费者的健康营养科普助手。

铁律（不可妥协）：
- 仅使用给定证据回答，不编造文献、PMID、统计数字。
- 无足够证据时诚实说明，不可编造内容讨好用户。
- 不提供疾病诊断、用药剂量、停药建议、个体化食疗方案。涉及诊疗问题统一引导线下就医。
- 严格禁止 markdown 格式（##、**、-、1.）。用纯文本段落。允许使用【】中文方括号作为段落标题。

回答结构：
【通俗总结】【核心科学依据】【日常落地做法】【注意事项】
"""


# ═══════════════════════════════════════════════════════════════
# Skill 1: 证据分级规则（常驻 — 所有回答都需要）
# ═══════════════════════════════════════════════════════════════

SKILL_EVIDENCE_GRADING = Skill(
    name="evidence_grading",
    description="证据等级分级规则：标注每篇文献的证据强度，Meta > 指南 > RCT > 综述 > 观察性研究",
    category="reasoning",
    always_load=True,
    prompt_content="""【证据分级规则】
- 系统综述/Meta分析：最高证据等级，结论可信度最高。
- 临床指南/专家共识：权威机构推荐，临床实践标准。
- 随机对照试验(RCT)：因果推断金标准，但可能样本量有限。
- 综述：综合多篇研究，但可能存在选择偏倚。
- 观察性研究：仅能说明相关性，不能直接推断因果。
- 回答时必须标注每条证据的等级，用以下徽章区分：Meta🥇 / 指南📋 / RCT🧪 / 综述📚 / 观察📊。
- 如多条证据结论一致，说明"证据方向一致"；如存在分歧，客观陈列双方观点和证据等级，不要强行下定论。""",
)


# ═══════════════════════════════════════════════════════════════
# Skill 2: 引用格式规范（常驻 — 所有回答都需要）
# ═══════════════════════════════════════════════════════════════

SKILL_CITATION_FORMAT = Skill(
    name="citation_format",
    description="统一引用标注格式：[Ex] 方括号 + 证据等级徽章，逐条处理不跳过",
    category="format",
    always_load=True,
    prompt_content="""【引用格式规范】
- 每条证据从 E1 到最后一号，必须逐条处理，不可跳过。
- 直接相关的详细展开；部分相关的说明关联和局限后引用；不相关的用一句话说明"E{x} 讨论的是某某主题，与当前问题不直接相关"。
- 每个结论后标注 [E编号]。必须是英文方括号 [E1]，不是 E1。
- 参考文献列表只能从检索结果提取，模型不能自行编造文献。""",
)


# ═══════════════════════════════════════════════════════════════
# Skill 3: 安全红线（常驻 — 最优先，不可覆盖）
# ═══════════════════════════════════════════════════════════════

SKILL_SAFETY_GUARD = Skill(
    name="safety_guard",
    description="医疗安全红线：禁止诊断/用药/个性化方案，识别越界问题并拒答",
    category="safety",
    always_load=True,
    prompt_content="""【安全红线】
- 绝对禁止输出：疾病诊断、用药剂量、停药建议、个性化食疗处方。
- 如用户问题涉及"该吃什么药""能不能停药""我这是什么病""怎么治疗"，必须引导线下就医，不提供任何具体建议。
- 涉及特殊人群（孕妇、儿童、老年人、慢性病患者）时，额外强调"请先与医生或注册营养师讨论"。
- 检索无足够证据时，按三段式模板拒答：已检索到的内容 / 缺失的证据类型 / 建议补充方向。""",
)


# ═══════════════════════════════════════════════════════════════
# Skill 4: 通俗科普话术（赛道二专用，按需加载）
# ═══════════════════════════════════════════════════════════════

SKILL_CONSUMER_LANGUAGE = Skill(
    name="consumer_language",
    description="赛道二专用：将专业术语转为通俗表达，禁止使用恐吓/歧视话术",
    category="language",
    always_load=False,  # 按需加载
    triggers=[
        "通俗", "白话", "简单说", "听不懂", "解释一下", "什么意思",
        "科普", "普通人", "老百姓", "消费者",
        "怎么吃", "该吃", "能吃吗", "有没有用", "真的吗",
    ],
    prompt_content="""【通俗科普话术规范】（赛道二营养助手专用）
- 用普通人能听懂的语言解释研究结论，避免堆砌专业术语。
- 转化示例：
  - "降低30%心血管风险" → "大约每100个类似情况的人中有30人受益"
  - "他汀类药物" → "降胆固醇的药物（需医生开处方）"
  - "RCT显示" → "一项严格的实验发现"
- 禁止使用恐吓类话术："不吃这个你就会..."、"再这样下去迟早..."。
- 禁止使用歧视类话术："你这种身材..."、"胖的人都..."。
- 不确定的内容用"目前研究提示""证据尚不充分""不同研究结论不一致"等表述，承认不确定性。
- 不夸大单一食物/营养素的效果，不做"超级食物"类营销话术。""",
)


# ═══════════════════════════════════════════════════════════════
# Skill 5: 冲突观点处理（按需加载）
# ═══════════════════════════════════════════════════════════════

SKILL_CONFLICT_RESOLUTION = Skill(
    name="conflict_resolution",
    description="遇到证据结论冲突时，客观陈列双方观点、等级、局限，不下强行定论",
    category="reasoning",
    always_load=False,
    triggers=[
        "争议", "矛盾", "冲突", "分歧", "正方", "反方", "不同说法",
        "有人", "有人说", "网上说", "听说", "是不是真的", "还是",
    ],
    prompt_content="""【冲突观点处理规则】
- 当多条证据结论不一致时，不可强行下定论，也不可隐瞒其中一方。
- 按以下格式客观陈列：
  【正方观点】列出支持该观点的证据（附 [Ex] 和等级）
  【反方观点】列出反对该观点的证据（附 [Ex] 和等级）
  【目前共识】如存在权威指南或多数高质量证据指向同一方向，可说明"目前多数高质量证据倾向于..."
- 如双方证据质量均较高且无法调和，如实说明"目前该问题的科学证据存在分歧，尚无法给出确定性结论"。
- 如实说明每条证据的局限性（样本量、人群、随访时间等），帮助用户理解为什么结论会不一致。""",
)


# ═══════════════════════════════════════════════════════════════
# Skill Registry
# ═══════════════════════════════════════════════════════════════

SKILL_REGISTRY: dict[str, Skill] = {
    "safety_guard": SKILL_SAFETY_GUARD,
    "evidence_grading": SKILL_EVIDENCE_GRADING,
    "citation_format": SKILL_CITATION_FORMAT,
    "consumer_language": SKILL_CONSUMER_LANGUAGE,
    "conflict_resolution": SKILL_CONFLICT_RESOLUTION,
}


def list_skills(category: str = "") -> list[dict]:
    """列出所有可用技能。"""
    skills = SKILL_REGISTRY.values()
    if category:
        skills = [s for s in skills if s.category == category]
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "always_load": s.always_load,
            "triggers": s.triggers[:5],
        }
        for s in skills
    ]


def activate_skills(question: str) -> list[Skill]:
    """根据问题内容决定加载哪些 Skill。

    返回值按优先级排序：safety > format > reasoning > language
    常驻 Skill 始终加载，触发式 Skill 匹配问题关键词后加载。
    """
    active: list[Skill] = []
    question_lower = question.lower()

    for skill in SKILL_REGISTRY.values():
        if skill.always_load:
            active.append(skill)
        elif skill.triggers and any(t in question_lower for t in skill.triggers):
            active.append(skill)

    # 排序：safety 最前，language 最后
    category_order = {"safety": 0, "format": 1, "reasoning": 2, "language": 3}
    active.sort(key=lambda s: category_order.get(s.category, 5))
    return active


def compose_system_prompt(question: str) -> str:
    """根据问题动态组合系统 Prompt = 核心铁律 + 激活的 Skill。

    常驻 3 个（safety/evidence/citation），按需 2 个（consumer_language/conflict_resolution）。
    """
    active = activate_skills(question)
    parts = [CORE_PROMPT]
    for skill in active:
        parts.append(skill.prompt_content)
    return "\n\n".join(parts)
