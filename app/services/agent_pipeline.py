"""多 Agent 协作管线 —— 三角色串联，共享工具，只留终稿。

Researcher → Writer → Critic → 最终回答

约束：
- 最多 3 轮搜索，防止无止境检索
- 三个 Agent 共享 TOOL_REGISTRY
- 只返回 Critic 审核后的最终回答
- 中间产物（搜索日志、草稿、修改意见）存入 Trace，不返回用户
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from app.services.tools import TOOL_REGISTRY, list_tools
from app.services.llm_client import OpenAICompatibleLlm

# ═══════════════════════════════════════════════════════════════
# Agent 角色定义
# ═══════════════════════════════════════════════════════════════

RESEARCHER_PROMPT = """你是医学文献检索专家（Researcher Agent）。

任务：根据用户问题，调用 search_pubmed 检索最相关的文献。
约束：
- 最多执行 3 次搜索（含改写检索词重试）
- 每次搜索后判断结果是否相关：相关则停止，不相关则改写关键词重试
- 如果 3 次后仍无相关结果，诚实报告"未检索到直接相关证据"
- 最终输出：3-5 条最相关文献的 PMID + 标题 + 为什么相关（每条一句话）

不要写完整回答，不要给建议，不要诊断。你只负责找文献。"""

WRITER_PROMPT = """你是健康科普作家（Writer Agent）。

任务：基于 Researcher 提供的文献证据，写一份面向普通消费者的循证科普回答。
约束：
- 严格按照四段式：【通俗总结】【核心科学依据】【日常落地做法】【注意事项】
- 每条结论标注 [E编号]
- 用通俗语言，不堆砌术语
- 不编造任何 Researcher 没提供的文献
- 证据相关则详细展开，不相关则一句话说明"E{x} 讨论的是某某主题，与当前问题不直接相关"
- 结尾不加免责声明（Critic 会补充）

只输出最终回答文本，不要加任何解释、注释、或元信息。"""

CRITIC_PROMPT = """你是严格的医学审稿人（Critic Agent）。

任务：审查 Writer 的回答，逐条核查并修正。核查清单：
1. 每一条 [Ex] 引用是否能在 Researcher 提供的文献中找到？找不到的标注移除
2. 结论措辞是否过度声称？如"证明"→"提示"，"治愈"→"可能改善"
3. 是否遗漏安全声明？如缺则补充"本回答不替代专业医疗建议"
4. 可读性：是否有读者看不懂的术语？如有则添加括号解释
5. 是否有恐吓、歧视、营销话术？如有则删除重写

修正方式：直接在原回答上修改，输出修正后的完整回答。
不要输出"修改意见"或"审查报告"，只输出修正后的最终回答。"""


# ═══════════════════════════════════════════════════════════════
# Agent 运行器
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgentTrace:
    """单个 Agent 的执行轨迹（内部记录，不返回用户）。"""
    agent: str
    tool_calls: list[dict] = field(default_factory=list)
    search_rounds: int = 0
    output_summary: str = ""  # 输出摘要（前 200 字）
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class AgentResult:
    """Agent 执行结果。"""
    output: str         # 纯文本输出（给下一个 Agent）
    trace: AgentTrace
    success: bool


class AgentRunner:
    """通用 Agent 运行器。

    支持两种模式：
    - 无工具模式（Writer/Critic）：单次 LLM 调用
    - 工具模式（Researcher）：LLM + 函数调用循环
    """

    def __init__(self, llm: OpenAICompatibleLlm):
        self.llm = llm

    async def _call_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        allowed_tools: list[str],
        max_rounds: int,
        agent_name: str,
    ) -> tuple[str, AgentTrace]:
        """带工具调用的 Agent 循环。"""
        trace = AgentTrace(agent=agent_name)
        t0 = time.perf_counter()
        full_output = ""

        # 构建工具 Schema（OpenAI function calling 格式）
        tool_defs = []
        for tname in allowed_tools:
            spec = TOOL_REGISTRY.get(tname)
            if spec:
                tool_defs.append({
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.input_schema,
                    },
                })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for round_num in range(max_rounds):
            payload = {
                "model": self.llm.model,
                "temperature": 0.1,
                "messages": messages,
                "tools": tool_defs if tool_defs else None,
                "tool_choice": "auto" if tool_defs else None,
            }
            # 清理 None 值
            payload = {k: v for k, v in payload.items() if v is not None}

            try:
                import httpx
                response = httpx.post(
                    self.llm.api_url,
                    headers={"Authorization": f"Bearer {self.llm.api_key}"},
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                result = response.json()
                choice = result["choices"][0]
                msg = choice["message"]

                # 是否有工具调用？
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = json.loads(tc["function"]["arguments"])

                        # 调用工具
                        from app.services.tools import call_tool
                        tool_result = await call_tool(func_name, func_args)

                        trace.tool_calls.append({
                            "round": round_num + 1,
                            "tool": func_name,
                            "args": func_args,
                            "success": tool_result.get("success", False),
                        })
                        trace.search_rounds = round_num + 1

                        # 把工具调用和结果加入消息
                        messages.append(msg)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(tool_result, ensure_ascii=False)[:2000],
                        })
                else:
                    # 无工具调用 → 最终输出
                    full_output = msg.get("content", "")
                    break

            except Exception as e:
                trace.error = f"Round {round_num + 1}: {type(e).__name__}: {e}"
                break

        if not full_output:
            # 兜底：用最后一条消息尝试获取内容
            last_content = messages[-1].get("content", "") if messages else ""
            if isinstance(last_content, str) and len(last_content) > 50:
                full_output = last_content

        trace.output_summary = full_output[:200]
        trace.duration_ms = (time.perf_counter() - t0) * 1000
        return full_output, trace

    async def _call_simple(
        self, system_prompt: str, user_message: str, agent_name: str
    ) -> tuple[str, AgentTrace]:
        """无工具的单次 LLM 调用（Writer / Critic）。"""
        trace = AgentTrace(agent=agent_name)
        t0 = time.perf_counter()

        try:
            result = self.llm._call_api(system_prompt, user_message, temperature=0.1)
            if result is None:
                trace.error = self.llm._last_error or "LLM 调用失败"
                trace.duration_ms = (time.perf_counter() - t0) * 1000
                return "", trace
            trace.output_summary = result[:200]
            trace.duration_ms = (time.perf_counter() - t0) * 1000
            return result, trace
        except Exception as e:
            trace.error = f"{type(e).__name__}: {e}"
            trace.duration_ms = (time.perf_counter() - t0) * 1000
            return "", trace

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        agent_name: str,
        allowed_tools: list[str] | None = None,
        max_rounds: int = 1,
    ) -> AgentResult:
        """运行一个 Agent。"""
        if allowed_tools and max_rounds > 1:
            output, trace = await self._call_with_tools(
                system_prompt, user_message, allowed_tools, max_rounds, agent_name
            )
        else:
            output, trace = await self._call_simple(
                system_prompt, user_message, agent_name
            )

        return AgentResult(
            output=output.strip(),
            trace=trace,
            success=bool(output and not trace.error),
        )


# ═══════════════════════════════════════════════════════════════
# 三 Agent 协作管线
# ═══════════════════════════════════════════════════════════════

@dataclass
class MultiAgentResult:
    """多 Agent 协作的最终输出。"""
    answer: str                    # 唯一返回给用户的内容
    success: bool
    researcher_trace: AgentTrace | None = None
    writer_trace: AgentTrace | None = None
    critic_trace: AgentTrace | None = None
    total_duration_ms: float = 0.0
    error: str = ""


class MultiAgentPipeline:
    """Researcher → Writer → Critic 三 Agent 协作。"""

    def __init__(self, llm: OpenAICompatibleLlm | None = None):
        self.llm = llm or OpenAICompatibleLlm()
        self.runner = AgentRunner(self.llm)

    async def run(self, question: str) -> MultiAgentResult:
        """执行完整的三 Agent 管线。"""
        t0 = time.perf_counter()

        if not self.llm.configured:
            return MultiAgentResult(
                answer="", success=False,
                error="LLM 未配置，无法运行多 Agent 管线",
            )

        # ─── Agent 1: Researcher ───
        # 先查本地 KB 再查 PubMed
        from app.services.evidence_store import EvidenceStore
        from app.services.llm_client import OpenAICompatibleLlm as Llm
        llm_tmp = Llm()
        search_q = llm_tmp.translate_to_pubmed_query(question) or question
        local_store = EvidenceStore()
        local_results = local_store.search(search_q, limit=5)

        local_summary = ""
        if local_results:
            local_summary = "【本地知识库预检索结果】\n"
            for i, c in enumerate(local_results, 1):
                local_summary += f"E{i}. PMID:{c.id.replace('kb-','').replace('pubmed-','')} | {c.title} | {c.evidence_level}\n"

        researcher_input = (
            f"用户问题：{question}\n\n"
            f"{local_summary}\n"
            f"---\n"
            f"以上为本地知识库的预检索结果。"
            f"如果本地结果已经足够相关（≥3条直接相关），直接整理输出。"
            f"如果不够，请调用 search_pubmed 补充检索。"
            f"最多 3 轮搜索（含改写重试）。"
            f"最终输出 3-5 条最相关文献的 PMID + 标题 + 相关性说明。"
        )

        researcher_result = await self.runner.run(
            system_prompt=RESEARCHER_PROMPT,
            user_message=researcher_input,
            agent_name="Researcher",
            allowed_tools=["search_pubmed"],
            max_rounds=3,
        )

        if not researcher_result.success:
            return MultiAgentResult(
                answer="", success=False,
                researcher_trace=researcher_result.trace,
                error=f"Researcher 失败: {researcher_result.trace.error}",
                total_duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # ─── Agent 2: Writer ───
        writer_input = (
            f"用户问题：{question}\n\n"
            f"以下为 Researcher 检索到的文献证据：\n\n{researcher_result.output}\n\n"
            f"请基于以上证据，写一份循证科普回答。"
        )

        writer_result = await self.runner.run(
            system_prompt=WRITER_PROMPT,
            user_message=writer_input,
            agent_name="Writer",
            allowed_tools=None,   # Writer 不用工具
            max_rounds=1,
        )

        if not writer_result.success:
            # Writer 失败 → 退回 Researcher 输出作为兜底
            return MultiAgentResult(
                answer=researcher_result.output,
                success=False,
                researcher_trace=researcher_result.trace,
                writer_trace=writer_result.trace,
                error=f"Writer 失败: {writer_result.trace.error}，退回检索结果",
                total_duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # ─── Agent 3: Critic ───
        critic_input = (
            f"用户问题：{question}\n\n"
            f"Researcher 检索到的文献证据：\n\n{researcher_result.output}\n\n"
            f"---\n"
            f"Writer 撰写的回答草稿：\n\n{writer_result.output}\n\n"
            f"---\n"
            f"请逐条核查引用、措辞、安全性、可读性，输出修正后的最终回答。"
        )

        critic_result = await self.runner.run(
            system_prompt=CRITIC_PROMPT,
            user_message=critic_input,
            agent_name="Critic",
            allowed_tools=None,   # Critic 不用工具，纯文本审查
            max_rounds=1,
        )

        # Critic 失败 → 退回 Writer 输出
        final_answer = critic_result.output if critic_result.success else writer_result.output

        return MultiAgentResult(
            answer=final_answer,
            success=True,
            researcher_trace=researcher_result.trace,
            writer_trace=writer_result.trace,
            critic_trace=critic_result.trace,
            total_duration_ms=(time.perf_counter() - t0) * 1000,
            error="" if critic_result.success else f"Critic 失败: {critic_result.trace.error}，退回 Writer 输出",
        )


# ═══════════════════════════════════════════════════════════════
# 单例 + 便捷函数
# ═══════════════════════════════════════════════════════════════

_agent_pipeline: MultiAgentPipeline | None = None


def get_agent_pipeline() -> MultiAgentPipeline:
    global _agent_pipeline
    if _agent_pipeline is None:
        _agent_pipeline = MultiAgentPipeline()
    return _agent_pipeline


async def run_multi_agent(question: str) -> dict:
    """便捷函数：运行多 Agent 管线，返回干净的结果字典。"""
    pipeline = get_agent_pipeline()
    result = await pipeline.run(question)

    # 只返回最终回答 + 简要元数据，不返回角色产物
    return {
        "answer": result.answer,
        "success": result.success,
        "error": result.error,
        "meta": {
            "pipeline": "Researcher → Writer → Critic",
            "total_ms": round(result.total_duration_ms),
            "researcher_rounds": result.researcher_trace.search_rounds if result.researcher_trace else 0,
            "researcher_tools_called": len(result.researcher_trace.tool_calls) if result.researcher_trace else 0,
            "critic_applied": result.critic_trace is not None and result.critic_trace.error == "",
        },
    }
