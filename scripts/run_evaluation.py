from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.answer_service import AnswerService
from app.services.evidence_store import EvidenceStore


root = Path(__file__).resolve().parents[1]
cases = json.loads((root / "data" / "evaluation_questions.json").read_text(encoding="utf-8"))
service = AnswerService(EvidenceStore())
passed = 0

for index, case in enumerate(cases, start=1):
    response = service.answer(case["question"])
    text = response.answer_markdown + response.safety_note
    checks = {needle: needle in text for needle in case["must_include"]}
    citations_are_retrieved = all(citation.label.startswith("E") for citation in response.citations)
    ok = all(checks.values()) and citations_are_retrieved
    passed += int(ok)
    print(f"[{index}] {'PASS' if ok else 'FAIL'} {case['question']}")
    print(f"    引用数：{len(response.citations)}；检查：{checks}")

print(f"\n通过 {passed}/{len(cases)}。")
raise SystemExit(0 if passed == len(cases) else 1)
