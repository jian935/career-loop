"""岗位族识别的可选 LLM 后端（v0.8.17）。

为什么需要它：规则基线 `detect_domains` 在**短 JD**（一句话的客服/项目类岗位）
上召回不足——中文公开集总体 86.0%，service 族仅约 52%（W9 证据链：
scripts/cn_eval_family.py / docs/evidence.md）。W9 已确认纯词表路线补不动
（短语级「售后服务」精确率 43.8% 不过 60% 闸），换语义通道是唯一现实路径。

设计约束（与项目「可证伪」纪律一致）：
1. **可选**：没配 Key 时一切行为与之前逐字节一致（回退规则）；
2. **同输入**：LLM 看到的文本与规则完全一致（同一字段、同样剥平台样板），
   不允许把岗位名喂给模型——标签恰恰来自岗位名，喂了就是自欺欺人；
3. **封闭集**：提示词里给出全部岗位族 key + 中文名 + 代表维度，
   模型只能从表里选，并镜像规则的「ai_* 子族 → ai 父族」推导；
4. **失败可见**：任何失败（无 Key / 网络 / 非法 JSON）都回退规则结果，
   且把回退原因带在 note 里，调用方如实展示走了哪条路。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm import LLM, LLMError
from .schema import DOMAIN_PACKS, FAMILY_CN, detect_domains
from .boilerplate import strip_boilerplate

MAX_JD_CHARS = 12000  # 控制成本：deepseek-flash 上下文 64k，这个截断对中文 JD 基本无感

FAMILY_SYSTEM = """你是岗位族分类器。给你一份招聘 JD 的正文，判断它属于哪个或哪些岗位族。

规则：
1. 只能从下面列表里选，族 key 原样输出，不要自造族名；
2. 可以多选，按相关程度从高到低排列；
3. 只依据 JD 正文判断，不要臆测正文没写的技能；
4. 严格输出 JSON：{"families": ["族key"], "confidence": 0.0到1.0}，不要输出任何其他文字。

岗位族列表：
"""


@dataclass
class FamilyVerdict:
    """族识别结果 + 走了哪条路（used） + 回退原因（note）。"""

    families: list[str] = field(default_factory=list)
    used: str = "rules"          # rules | llm | rules+llm
    note: str = ""               # 例如「LLM 失败回退规则：HTTP 401」


def _taxonomy_lines() -> str:
    """把 DOMAIN_PACKS 渲染成提示词里的族清单（key + 中文名 + 代表维度）。"""
    lines = []
    for key, pack in DOMAIN_PACKS.items():
        dims = "、".join(spec["label"] for spec in pack.values())
        lines.append(f"- {key}：{FAMILY_CN.get(key, key)}（{dims}）")
    # ai 是父族：规则侧由 ai_* 子族推导，提示词里显式给出，避免模型漏选
    lines.append(f"- ai：{FAMILY_CN['ai']}（父族：任一 AI 子族命中即包含）")
    return "\n".join(lines)


_SYSTEM_CACHE: str | None = None


def family_system_prompt() -> str:
    global _SYSTEM_CACHE
    if _SYSTEM_CACHE is None:
        _SYSTEM_CACHE = FAMILY_SYSTEM + _taxonomy_lines()
    return _SYSTEM_CACHE


def _normalize(families: object) -> list[str]:
    """过滤出合法族 key；顺手把模型可能输出的中文名映射回 key。"""
    valid = set(DOMAIN_PACKS) | {"ai"}
    cn_to_key = {v: k for k, v in FAMILY_CN.items()}
    out: list[str] = []
    if not isinstance(families, list):
        return out
    for f in families:
        if not isinstance(f, str):
            continue
        key = f.strip().lower()
        if key in cn_to_key:          # 模型偶尔输出中文名
            key = cn_to_key[key]
        if key in valid and key not in out:
            out.append(key)
    # 镜像规则的父族推导：命中任一 ai_* 子族即包含 ai
    if any(k.startswith("ai_") for k in out) and "ai" not in out:
        out.append("ai")
    return out


def detect_family_llm(text: str, llm: LLM) -> list[str]:
    """只用 LLM 判族。调用方负责处理 LLMError。"""
    body = strip_boilerplate(text)[:MAX_JD_CHARS]
    data = llm.json(family_system_prompt(), f"JD 正文：\n{body}")
    fams = data.get("families")
    if not isinstance(fams, list):
        # 解析成功但没有 families 字段 = 模型没按格式答，算失败而不是算「没族」
        raise LLMError(f"模型未返回 families 列表：{str(data)[:120]}")
    return _normalize(fams)


def detect_families(text: str, llm: LLM | None = None, mode: str = "blend") -> FamilyVerdict:
    """族识别入口。mode: rules / llm / auto / blend（默认 blend）。

    公开中文集实测（1,838 条，scripts/llm_family_eval.py，any-in / top-1）：

    | 模式 | 做法 | any-in | top-1 | 平均族数 |
    |---|---|---|---|---|
    | rules | 纯词表 | 86.0% | 56.6% | 4.88 |
    | llm | 纯模型 | 86.5% | 73.5% | 2.20 |
    | auto | 规则先判，空结果才问模型 | 87.0% | 57.6% | 4.90 |
    | blend | **LLM 首选优先 + 规则补充** | **93.4%** | **73.5%** | 5.49 |

    - blend 是实测最优：并集保召回、LLM 的首选保top-1；代价是每次一条 LLM 调用
      （deepseek-flash 约 ¥0.005），批量场景可用 auto 省调用；
    - llm 单独用**不是**规则替代品：它对「咨询/实施/售前」类 JD 有系统性盲区
      （判成 sales/service，consulting 28% / it_systems 32% / ai_solution 22%），
      规则在这些族上反而强——两者盲区几乎不重叠，这是 blend 有效的原因；
    - 任何失败（无 Key / 网络 / 非法 JSON）都回退规则结果，note 里带原因。
    """
    rules = detect_domains(text)
    if mode == "rules":
        return FamilyVerdict(rules, "rules")
    if llm is None or not llm.available:
        return FamilyVerdict(rules, "rules", note="未配置 LLM（回退规则）")
    if mode == "auto" and rules:
        return FamilyVerdict(rules, "rules")
    try:
        fams = detect_family_llm(text, llm)
    except (LLMError, KeyError, ValueError) as exc:
        return FamilyVerdict(rules, "rules", note=f"LLM 失败回退规则：{exc}")
    if mode == "llm":
        return FamilyVerdict(fams, "llm")
    if mode == "auto":
        return FamilyVerdict(fams, "rules+llm")
    # blend：LLM 的首选排前面（top-1 准），规则的命中补后面（召回全）
    return FamilyVerdict(fams + [f for f in rules if f not in fams], "llm+rules")
