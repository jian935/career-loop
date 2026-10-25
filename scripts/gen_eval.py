"""生成 data/eval_sample.jsonl —— 人工标注的匹配评测集。

每条样本标注：在要求某能力 K 的 JD 下，候选人对 K 应有的状态（full/partial/missing）。
这是给匹配引擎打分用的固定基准，可复现、可审计。改了匹配逻辑就重跑本脚本。
"""

from __future__ import annotations

import json
from pathlib import Path

# (capability_key, jd_句子, profile_句子, expected)
# 约定：full 的 profile 必须含该能力关键词 + 一个"动作动词"；
#        partial 的 profile 含关键词但只用"认知动词"(了解/知道/看过…)，无动作动词；
#        missing 的 profile 不含关键词。这样规则基线测的是"证据归因是否正确"。
CASES = [
    # python
    ("python", "任职要求：精通 Python，能独立开发和调试。", "用 Python 写了后端服务，部署到服务器跑了三个月。", "full"),
    ("python", "要求熟悉 Python 编程。", "在课程里了解过 Python 语法，知道它的基本用途。", "partial"),
    ("python", "要求熟练掌握 Python。", "主要负责产品文档，没写过代码。", "missing"),
    # llm_basics
    ("llm_basics", "需要理解大模型的能力边界与适用场景。", "做过三个大模型在同一任务上的失败模式对比分析。", "full"),
    ("llm_basics", "要求了解大模型基本原理。", "知道大模型是什么，能大概说清用途。", "partial"),
    ("llm_basics", "需要深入理解大模型原理。", "完全没接触过相关技术。", "missing"),
    # prompt_eng
    ("prompt_eng", "需要设计系统提示词与多轮提示策略。", "把提示词迭代了五个版本，每版记录指标变化。", "full"),
    ("prompt_eng", "要求会基本的提示词工程。", "了解提示词工程，知道要让模型按格式回复。", "partial"),
    ("prompt_eng", "需要提示词工程能力。", "没做过相关工作。", "missing"),
    # rag
    ("rag", "要求有 RAG / 检索增强的落地经验。", "用向量库做了知识库问答，报了 Recall@k 和幻觉率。", "full"),
    ("rag", "需要了解 RAG 技术。", "知道 RAG 是检索增强生成，看过科普。", "partial"),
    ("rag", "需要 RAG 落地经验。", "只做过直接调用大模型问答，没有检索。", "missing"),
    # agent
    ("agent", "需要设计并实现 Agent 工作流。", "做了一个只解决排障的 Agent，录了失败轨迹当评测集。", "full"),
    ("agent", "要求理解 Agent / 智能体概念。", "了解 Agent 是能自主完成任务的智能体。", "partial"),
    ("agent", "需要 Agent 开发经验。", "主要负责产品文档，没写过代码。", "missing"),
    # function_calling
    ("function_calling", "需要把真实 API 封装成工具并做参数校验。", "用函数调用把天气 API 封装成工具，做了参数校验和失败重试。", "full"),
    ("function_calling", "要求理解函数调用机制。", "知道 function calling 是让模型调工具，没实际封装过。", "partial"),
    ("function_calling", "需要函数调用开发经验。", "没做过相关工作。", "missing"),
    # framework
    ("framework", "要求熟练使用 Agent 框架搭建应用。", "用 LangGraph 搭了一个带状态的多步工作流。", "full"),
    ("framework", "要求了解 Agent 框架。", "看过 Dify 的文档，知道它是低代码平台。", "partial"),
    ("framework", "需要熟练使用 Agent 框架。", "只用过纯手写调用，没碰过平台。", "missing"),
    # coding_tools
    ("coding_tools", "要求熟悉 Claude Code / Cursor 等 AI 编程工具。", "用 Cursor 从零到发布做完了一个项目，写了复盘。", "full"),
    ("coding_tools", "要求会用 AI 编程工具。", "了解 Cursor 是 AI 编辑器，装过但没怎么用。", "partial"),
    ("coding_tools", "要求熟练使用 AI 编程工具。", "没用过任何 AI 编程工具。", "missing"),
    # product_sense
    ("product_sense", "需要独立完成需求洞察与产品设计。", "做了十次用户访谈，整理出带原话引用的需求清单。", "full"),
    ("product_sense", "要求有产品设计意识。", "了解需求调研的方法，知道要先访谈用户。", "partial"),
    ("product_sense", "需要需求洞察能力。", "从没做过这方面的工作。", "missing"),
    # data_analysis
    ("data_analysis", "需要建立指标体系并通过数据指导迭代。", "给项目定了三个指标，每天记录并画趋势线。", "full"),
    ("data_analysis", "要求有数据分析思维。", "了解数据驱动决策，知道要跟踪指标。", "partial"),
    ("data_analysis", "需要数据分析能力。", "对相关方向完全没有概念。", "missing"),
    # eval
    ("eval", "需要建立效果评估体系并迭代。", "人工标注了 50 条评测集，报准确率和误判类型。", "full"),
    ("eval", "要求理解效果评估。", "了解评估的重要性，知道要算准确率。", "partial"),
    ("eval", "需要效果评估体系经验。", "模型跑通就上线了。", "missing"),
    # engineering
    ("engineering", "需要能把项目部署上线并稳定运行。", "用 Docker 部署了服务，配置了监控和告警。", "full"),
    ("engineering", "要求有基础工程能力。", "了解部署概念，知道要上服务器。", "partial"),
    ("engineering", "需要工程落地能力。", "只写算法，没碰过线上。", "missing"),
    # communication
    ("communication", "需要高效推动跨团队对齐与协作。", "主导了研发、设计、运营三方对齐，把需求推上线。", "full"),
    ("communication", "要求沟通协作能力。", "了解跨团队协作的必要性，知道要同步进度。", "partial"),
    ("communication", "需要跨团队协作能力。", "习惯自己闷头做，不擅长协调。", "missing"),
    # domain
    ("domain", "需要深入理解某业务场景的痛点与流程。", "梳理了客服业务全流程，标出人力和耗时最贵的三步。", "full"),
    ("domain", "要求理解业务场景。", "了解业务流程大概，知道要找痛点。", "partial"),
    ("domain", "需要业务理解能力。", "对相关方向完全没有概念。", "missing"),
    # ---- W6：通用能力（GENERAL_DIMS）+ 8 条边界样本 ----
    # 这 18 条是评测集扩到 60 条时补的：writing / exec_project 属通用能力层，
    # llm_basics / agent 各留了「同一句 JD、不同经历写法」的边界样本，
    # 用来锁住"证据归因"在同义改写下不被误判。
    ("writing", "任职要求：良好的文档与报告撰写能力，能输出 PRD。", "独立撰写过 3 份产品 PRD 和项目复盘报告，给团队传阅。", "full"),
    ("writing", "要求具备文档写作与汇报能力。", "了解文档写作的基本格式和逻辑，但缺少独立产出的经验。", "partial"),
    ("writing", "需要有良好的文案与文档撰写能力。", "完全没有写过正式文档，平时都是口头沟通。", "missing"),
    ("exec_project", "需要有项目管理和落地推进经验，负责过排期与交付。", "主导过两个项目的排期、资源协调与最终交付，按时上线。", "full"),
    ("exec_project", "要求有项目推进与统筹能力。", "对项目管理有概念性了解，跟过别人的项目流程。", "partial"),
    ("exec_project", "需要有项目落地与执行能力。", "从没独立负责过项目，都是执行别人安排的任务。", "missing"),
    ("llm_basics", "要求精通大模型原理与微调经验，理解 Transformer。", "了解过 GPT 这类大模型，但没训过模型，也没做过微调，只停留在概念层面。", "missing"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "知道 Agent 的基本概念和工作原理，仅停留在理论了解阶段。", "partial"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "了解 Agent 的基本概念，跟过教程但没自己独立搭建过工作流。", "partial"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "没搭建过多智能体工作流，只在课程作业里跑通过单 Agent 例子。", "partial"),
    ("exec_project", "需要有项目管理和落地推进经验，负责过排期与交付。", "没独立负责过项目交付，都是执行别人安排的任务。", "partial"),
    ("writing", "需要有良好的文案与文档撰写能力。", "没写过正式文档，平时都是口头沟通。", "partial"),
    ("llm_basics", "要求精通大模型原理与微调经验。", "未使用过大模型 API，只停留在概念层面。", "partial"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "独立搭建过多智能体 Agent 工作流并上线，负责调度与评测。", "full"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "不仅实现了 Agent 工作流，还落地到生产环境并持续迭代。", "full"),
    ("writing", "需要有良好的文案与文档撰写能力。", "撰写过 3 份 PRD 与项目复盘报告，给团队传阅。", "full"),
    ("writing", "需要有良好的文案与文档撰写能力。", "没写过正式文档，但独立落地过内容运营项目。", "partial"),
    ("agent", "需要有 Agent 开发经验，能搭建多智能体工作流。", "不同渠道搭建过多智能体工作流，累计上线 3 个业务场景。", "full"),
]


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "eval_sample.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, (cap, jd, profile, expected) in enumerate(CASES, 1):
            row = {
                "id": i,
                "capability": cap,
                "jd": jd,
                "profile": profile,
                "expected": expected,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(CASES)} rows -> {out}")


if __name__ == "__main__":
    main()
