"""核心数据结构 + 能力词表（同时充当无 Key 时的规则基线）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Requirement:
    key: str
    label: str
    weight: int          # 3 = 核心硬要求, 2 = 一般要求, 1 = 加分项
    kind: str            # must | nice
    quote: str = ""      # JD 原文依据
    section: str = ""    # 岗位职责 / 任职要求 / 优先条件


@dataclass
class MatchResult:
    key: str
    status: str          # full | partial | missing
    evidence: str = ""
    note: str = ""


@dataclass
class Assessment:
    requirements: list[Requirement] = field(default_factory=list)
    matches: dict[str, MatchResult] = field(default_factory=dict)
    score: float = 0.0
    jd_title: str = "目标岗位"
    mode: str = "rule"   # rule | llm

    def status_of(self, req: Requirement) -> str:
        hit = self.matches.get(req.key)
        return hit.status if hit else "missing"


# 能力词表：canonical key -> (中文标签, 触发词, 缺口补法)
TAXONOMY: dict[str, dict] = {
    "python": {
        "label": "Python 工程能力",
        "kw": ["python", "pandas", "fastapi", "flask"],
        "fix": "用一个真实需求写完整脚本：读数据→调模型→落库→出报告，别停留在 notebook。",
    },
    "llm_basics": {
        "label": "大模型原理与边界",
        "kw": ["大模型", "llm", "gpt", "transformer", "微调", "token", "上下文窗口"],
        "fix": "写一份你自己的『模型能力边界实测』：同一个任务在 3 个模型上的失败模式差异。",
    },
    "prompt_eng": {
        "label": "提示词工程",
        "kw": ["提示词", "prompt", "提示工程", "系统提示"],
        "fix": "把一个提示词迭代 5 版，每版记录改了什么、指标涨没涨，做成对照表。",
    },
    "rag": {
        "label": "RAG / 检索增强",
        "kw": ["rag", "检索增强", "知识库", "向量", "embedding", "召回", "重排", "rerank"],
        "fix": "做一个小型 RAG（100 篇文档以内），必须报 Recall@k 和幻觉率，不能只演示问答。",
    },
    "agent": {
        "label": "Agent / 智能体",
        "kw": ["agent", "智能体", "工作流", "多智能体", "编排", "tool use"],
        "fix": "做一个只解决一件事的 Agent，把它的失败轨迹录下来当评测集。",
    },
    "function_calling": {
        "label": "函数调用 / 工具调用",
        "kw": ["函数调用", "function calling", "工具调用", "mcp", "tool calling", "封装成工具", "api 调用"],
        "fix": "把一个真实 API 封装成工具，重点做参数校验和失败重试，而不是 happy path。",
    },
    "framework": {
        "label": "Agent 框架使用",
        "kw": ["langchain", "langgraph", "dify", "coze", "crewai", "n8n", "autogen", "扣子", "框架"],
        "fix": "选一个框架做同样的任务，和手写版对比：省了多少代码、多了多少不可控。",
    },
    "coding_tools": {
        "label": "AI 编程工具（Claude Code / Cursor）",
        "kw": ["claude code", "cursor", "copilot", "codex", "windsurf", "trae", "编程工具", "ai 编程"],
        "fix": "用 Claude Code 或 Cursor 从零到发布跑通一个项目，把过程写成一篇复盘。",
    },
    "product_sense": {
        "label": "需求洞察与产品设计",
        "kw": ["需求", "用户洞察", "产品设计", "交互逻辑", "prd", "用户调研", "访谈", "场景设计"],
        "fix": "对你选定的场景做 10 次真实用户访谈，输出一份带原话引用的需求清单。",
    },
    "data_analysis": {
        "label": "数据分析与指标体系",
        "kw": ["数据分析", "指标", "漏斗", "转化率", "留存", "sql", "看板", "归因", "复盘"],
        "fix": "给项目定 3 个指标（效果/成本/体验各一个），每天记一次，画成趋势线。",
    },
    "eval": {
        "label": "效果评估体系",
        "kw": ["评估", "评测", "指标", "效果", "ab test", "abtest", "回归", "badcase"],
        "fix": "人工标注 50 条评测集，报准确率 + 误判类型分布，这是你和别人最大的差距。",
    },
    "engineering": {
        "label": "工程落地与部署",
        "kw": ["后端", "api", "部署", "docker", "数据库", "服务", "上线", "工程"],
        "fix": "把项目做成一条命令能起（Dockerfile + README），让别人能复现。",
    },
    "communication": {
        "label": "跨团队沟通协作",
        "kw": ["沟通", "协作", "跨部门", "对齐", "表达", "推动"],
        "fix": "在 README 里写清『给非技术同学看的一页纸』，这本身就是沟通能力的证据。",
    },
    "domain": {
        "label": "业务/行业理解",
        "kw": ["业务", "场景", "行业", "流程", "痛点", "岗位", "流失", "留存点", "成本结构"],
        "fix": "把你选定场景的完整业务流程图画出来，标出人力和耗时最贵的三步。",
    },
}

STATUS_LABEL = {"full": "已具备", "partial": "部分具备", "missing": "缺失"}
STATUS_ICON = {"full": "🟢", "partial": "🟡", "missing": "🔴"}


def canonical_hits(text: str) -> dict[str, list[str]]:
    """返回 text 中命中的能力 key 及其命中的原始词。"""
    low = text.lower()
    hits: dict[str, list[str]] = {}
    for key, spec in TAXONOMY.items():
        found = [kw for kw in spec["kw"] if kw.lower() in low]
        if found:
            hits[key] = found
    return hits
