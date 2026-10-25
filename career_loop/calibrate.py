"""校准：模型的匹配分到底能不能预测真实结果。

这是整个项目最不像"玩具"的一块——它把"我觉得你很匹配"变成一个可被证伪的命题：
匹配分越高，真实拿到回复/面试的比例是否真的越高？如果不是，模型就该被怀疑。
"""

from __future__ import annotations

import random
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


# --------------------------------------------------------------------------
# 相关系数的置信区间：一个数字不能叫"可证伪"
# --------------------------------------------------------------------------

#: Bootstrap 默认重采样次数。2000 次在 n 几百的量级上两秒内跑完，
#: 再往上涨精度提升有限，但对低端机器不友好。
DEFAULT_N_BOOT = 2000
#: 少于这个样本量不给区间：n=6 时 bootstrap 的分布形状基本是假的，
#: 给个区间反而让人误以为它可靠。**宁可说"样本不够"，也不要给假精度。**
MIN_N_FOR_CI = 8


@dataclass
class CorrelationCI:
    """Pearson r 及其 95% 置信区间（bootstrap，成对重采样）。"""

    r: Optional[float] = None
    lo: Optional[float] = None
    hi: Optional[float] = None
    n: int = 0
    n_boot: int = 0
    valid: int = 0          # 有效重采样次数（全同组的重采样算不出 r，会被丢掉）
    note: str = ""

    @property
    def available(self) -> bool:
        return self.r is not None and self.lo is not None

    @property
    def text(self) -> str:
        if not self.available:
            return f"样本量 {self.n} 不足（需 ≥ {MIN_N_FOR_CI}），不给出置信区间"
        return f"r = {self.r:+.3f}　95% CI [{self.lo:+.3f}, {self.hi:+.3f}]　n={self.n}"

    @property
    def crosses_zero(self) -> bool:
        """区间跨 0 —— 这份数据**不能排除**「匹配分和结果毫无关系」。"""
        if not self.available:
            return True
        return self.lo <= 0 <= self.hi

    def verdict(self) -> str:
        """把区间翻译成一句能用的话。

        重点不是"r 有多大"，而是"这个 r 有没有把 0 排除掉"——
        后者才是「能不能拿它做投递优先级」的判据。
        """
        if not self.available:
            return (f"样本只有 {self.n} 条，不足 {MIN_N_FOR_CI} 条。"
                    "这个量级下任何 r 都可能来自一两份偶然的结果，"
                    "**先攒够样本再看，别拿它下结论**。")
        dropped = self.n_boot - self.valid
        extra = f"（{dropped} 次重采样因组内全同而被丢弃）" if dropped else ""
        if self.crosses_zero:
            return (f"95% 置信区间跨 0：这份数据**不能排除**「匹配分和结果毫无关系」。"
                    f"样本 {self.n} 条，先把关心的分组（比如某个行业）拆开单看，"
                    f"或者继续积累记录{extra}。")
        if self.lo > 0:
            return (f"置信区间整体在 0 以上：这份数据支持「匹配分越高，越容易拿到正反馈」，"
                    f"方向是稳的。但样本只有 {self.n} 条，区间仍然很宽，"
                    f"别把 r={self.r:+.3f} 当成一个精确值{extra}。")
        return (f"置信区间整体在 0 以下：方向是**反的**。先去逐条明细里看那些"
                f"「低分却拿到正反馈」的岗位——如果它们明显是门槛不高的岗位，"
                f"说明这批结果本身与契合度无关，而不是引擎打分反了{extra}。")


def pearson_ci(
    scores: list[float],
    positives: list[bool],
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = 20261025,
) -> CorrelationCI:
    """成对 bootstrap 求 r 的 95% 置信区间（百分位法）。

    为什么重采样必须**成对**：拆开独立重采样会破坏 x 与 y 的对应关系，
    得到的分布是「无关情形」的分布，区间会失真。

    seed 固定 → 同一个输入每次得到同一个区间（可对拍、可写进单测）。
    """
    n = len(scores)
    ys = [1.0 if p else 0.0 for p in positives]
    r = pearson(scores, ys)
    if n < MIN_N_FOR_CI:
        return CorrelationCI(
            r=round(r, 3) if r is not None else None,
            n=n, n_boot=0, valid=0,
            note=f"n={n} < {MIN_N_FOR_CI}，不计算区间",
        )
    rng = random.Random(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        br = pearson([scores[i] for i in idx], [ys[i] for i in idx])
        # 重采样后某一组全 0 或全 1 时 pearson 返回 None（分母为 0）——丢掉这次
        if br is not None:
            boots.append(br)
    if not boots:
        return CorrelationCI(
            r=round(r, 3) if r is not None else None,
            n=n, n_boot=n_boot, valid=0,
            note="每次重采样都落在同一组上，说明正负样本极不均衡，算不出区间",
        )
    boots.sort()
    lo = boots[max(0, int(0.025 * len(boots)))]
    hi = boots[min(len(boots) - 1, int(0.975 * len(boots)))]
    return CorrelationCI(
        r=round(r, 3) if r is not None else None,
        lo=round(lo, 3), hi=round(hi, 3),
        n=n, n_boot=n_boot, valid=len(boots),
    )
