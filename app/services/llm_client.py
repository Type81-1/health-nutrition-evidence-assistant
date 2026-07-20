from __future__ import annotations

import os
import re

import httpx

from app.services.evidence_store import EvidenceChunk


SYSTEM_PROMPT = """你是面向普通消费者的健康营养科普助手。
只能使用给定证据回答，不得补充给定资料以外的医学事实，不得给出诊断或用药调整建议。
每个可核查的结论后都必须标注一个或多个 [E编号] 引用。若资料不足，请直接说证据不足。
用中文写出：先说结论、证据怎么说、可执行的小步骤、证据边界。不要编造文献或引用。"""


class OpenAICompatibleLlm:
    """可选的模型增强层。模型输出必须通过引用白名单校验后才会展示。"""

    def __init__(self) -> None:
        self.api_url = os.getenv("LLM_API_URL", "")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.api_key and self.model)

    def answer(self, question: str, evidence: list[EvidenceChunk]) -> str | None:
        if not self.configured:
            return None
        source_text = "\n\n".join(
            f"[E{index}] {item.title} ({item.year}, {item.evidence_level})\n{item.content}"
            for index, item in enumerate(evidence, start=1)
        )
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"问题：{question}\n\n可用证据：\n{source_text}"},
            ],
        }
        try:
            response = httpx.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=25,
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError):
            return None
        allowed = {str(index) for index in range(1, len(evidence) + 1)}
        cited = set(re.findall(r"\[E(\d+)\]", text))
        if not cited or not cited.issubset(allowed):
            return None
        return text
