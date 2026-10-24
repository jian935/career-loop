"""评测集：用人工标注的数据，给匹配引擎打分。

为什么需要它：任何声称"匹配更准"的模型，都得有一份固定、公开、可复现的评测集来对照，
否则"更准"只是感觉。这里每条样本标注的是「在要求某能力 K 的 JD 下，该候选对此能力应有的状态」，
直接测匹配引擎对单能力的判断正确率。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalSummary:
    total: int = 0
    correct: int = 0
    per_capability: dict[str, dict] = field(default_factory=dict)
    badcases: list[dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 3) if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "per_capability": self.per_capability,
            "badcase_count": len(self.badcases),
        }


def load_dataset(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def run_eval(dataset: list[dict], matcher) -> EvalSummary:
    """matcher: callable(jd_text, profile_text) -> dict[capability_key] -> status.

    matcher 包装了规则基线或 LLM 模式。"""
    summary = EvalSummary()
    for row in dataset:
        cap = row["capability"]
        expected = row["expected"]
        predicted = matcher(row["jd"], row["profile"]).get(cap, "missing")
        summary.total += 1
        correct = predicted == expected
        summary.correct += 1 if correct else 0

        slot = summary.per_capability.setdefault(
            cap, {"total": 0, "correct": 0}
        )
        slot["total"] += 1
        slot["correct"] += 1 if correct else 0

        if not correct:
            summary.badcases.append(
                {
                    "id": row.get("id"),
                    "capability": cap,
                    "expected": expected,
                    "predicted": predicted,
                    "jd": row["jd"],
                    "profile": row["profile"],
                }
            )
    for slot in summary.per_capability.values():
        slot["accuracy"] = round(slot["correct"] / slot["total"], 3) if slot["total"] else 0.0
    return summary
