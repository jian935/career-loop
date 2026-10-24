"""校准：模型的匹配分到底能不能预测真实结果。

这是整个项目最不像"玩具"的一块——它把"我觉得你很匹配"变成一个可被证伪的命题：
匹配分越高，真实拿到回复/面试的比例是否真的越高？如果不是，模型就该被怀疑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


@dataclass
class Bucket:
    lo: int
    hi: int
    n: int = 0
    positives: int = 0

    @property
    def positive_rate(self) -> float:
        return round(self.positives / self.n, 3) if self.n else 0.0


@dataclass
class CalibrationReport:
    n: int = 0
    correlation: Optional[float] = None
    positive_rate: float = 0.0
    buckets: list[Bucket] = field(default_factory=list)
    verdict: str = ""

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "correlation": self.correlation,
            "positive_rate": self.positive_rate,
            "buckets": [
                {"range": f"{b.lo}-{b.hi}", "n": b.n, "positive_rate": b.positive_rate}
                for b in self.buckets
            ],
            "verdict": self.verdict,
        }


def calibrate(scores: list[float], positives: list[bool]) -> CalibrationReport:
    n = len(scores)
    if n == 0:
        return CalibrationReport(verdict="没有足够数据，先去投几份。")

    pos = sum(1 for p in positives if p)
    buckets: list[Bucket] = [Bucket(lo, lo + 20) for lo in range(0, 100, 20)]
    for s, p in zip(scores, positives):
        idx = min(len(buckets) - 1, int(s // 20))
        buckets[idx].n += 1
        buckets[idx].positives += 1 if p else 0

    r = pearson(scores, [1.0 if p else 0.0 for p in positives])
    rate = round(pos / n, 3)

    if r is None or abs(r) < 0.15:
        verdict = (
            "匹配分和真实结果几乎无关（|r| < 0.15）。"
            "说明现在的匹配模型基本在猜——它打的高分没有转化为更多面试，"
            "下一步应该降低对它的信任，转去收集更多真实结果反推权重。"
        )
    elif r < 0.4:
        verdict = (
            "弱相关。匹配分方向大致对，但解释力有限。"
            "建议把预测误差最大的几类岗位（行业/职能）单独拆出来看，可能是它们拖低了相关性。"
        )
    else:
        verdict = (
            "中到强相关（|r| ≥ 0.4）。匹配分确实在预测真实结果，"
            "可以放心拿它做投递优先级，但仍要持续回流数据修正。"
        )

    return CalibrationReport(
        n=n, correlation=round(r, 3) if r is not None else None,
        positive_rate=rate, buckets=buckets, verdict=verdict,
    )
