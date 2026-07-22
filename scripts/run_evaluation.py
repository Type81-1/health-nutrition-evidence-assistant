from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.answer_service import AnswerService
from app.services.evidence_store import EvidenceStore


root = Path(__file__).resolve().parents[1]
cases = json.loads((root / "data" / "evaluation_questions.json").read_text(encoding="utf-8"))
store = EvidenceStore(enable_chroma=False)
service = AnswerService(store)
passed = 0

for index, case in enumerate(cases, start=1):
    retrieved = store.search(case["question"])
    response = service.answer(case["question"])
    text = response.answer_markdown + response.safety_note
    checks = {needle: needle in text for needle in case["must_include"]}
    citations_are_retrieved = all(citation.label.startswith("E") for citation in response.citations)
    expected = set(case.get("expected_source_ids", []))
    retrieved_ids = [item.id for item in retrieved]
    expected_hits = expected.intersection(retrieved_ids)
    sources_are_relevant = not expected or bool(expected_hits)
    ok = all(checks.values()) and citations_are_retrieved and sources_are_relevant
    passed += int(ok)
    print(f"[{index}] {'PASS' if ok else 'FAIL'} {case['question']}")
    print(f"    引用数：{len(response.citations)}；检查：{checks}")
    print(f"    来源命中：{sorted(expected_hits) if expected else '未设置'}；前置来源：{retrieved_ids[:4]}")

print(f"\n通过 {passed}/{len(cases)}。")
raise SystemExit(0 if passed == len(cases) else 1)
