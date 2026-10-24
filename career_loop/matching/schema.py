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

# 通用能力：任何岗位都适用（与 TAXONOMY 的 key 不重复）
GENERAL_DIMS: dict[str, dict] = {
    "exec_project": {"label": "执行与项目推进", "kw": ["项目管理", "项目推进", "统筹", "排期", "进度", "落地", "执行", "跟进", "交付"]},
    "problem_solving": {"label": "问题分析与解决", "kw": ["分析问题", "解决问题", "根因", "复盘", "逻辑分析", "优化流程", "排查"]},
    "learning": {"label": "学习与自驱", "kw": ["学习能力", "快速学习", "自驱", "主动学习", "钻研", "自学"]},
    "ownership": {"label": "责任心与抗压", "kw": ["责任心", "抗压", "细致", "严谨", "耐心", "踏实"]},
    "writing": {"label": "文档与表达", "kw": ["文档", "报告", "汇报", "写作", "文案", "ppt", "方案撰写"]},
    "customer": {"label": "客户/用户导向", "kw": ["客户", "服务意识", "满意度", "需求响应", "售后", "用户导向"]},
    "leadership": {"label": "领导力/带团队", "kw": ["带团队", "团队管理", "领导", "培养下属", "搭建团队", "统筹团队"]},
    "language": {"label": "外语能力", "kw": ["英语", "日语", "韩语", "雅思", "托福", "六级", "四级", "口语", "cet"]},
    "office": {"label": "办公软件", "kw": ["excel", "word", "ppt", "wps", "office", "表格", "文档处理"]},
}

# 常见岗位族词表：key 带前缀，避免与 AI 词表冲突
DOMAIN_PACKS: dict[str, dict] = {
    "product": {
        "prod_prd": {"label": "PRD/需求文档", "kw": ["prd", "需求文档", "需求分析", "原型", "axure", "墨刀"]},
        "prod_roadmap": {"label": "产品规划", "kw": ["产品规划", "路线图", "版本规划", "迭代规划"]},
    },
    "marketing": {
        "mkt_content": {"label": "内容/文案", "kw": ["文案", "内容运营", "选题", "脚本", "种草", "小红书", "抖音"]},
        "mkt_ads": {"label": "投放/广告", "kw": ["投放", "信息流", "sem", "千川", "roi", "cpa", "广告"]},
        "mkt_brand": {"label": "品牌/公关", "kw": ["品牌", "公关", "传播", "媒介", "危机公关"]},
        "mkt_private": {"label": "私域/社群", "kw": ["私域", "社群", "企微", "用户运营"]},
    },
    "sales": {
        "sales_bd": {"label": "客户开发/BD", "kw": ["客户开发", "拓客", "bd", "商务拓展", "渠道开发", "销售", "业绩", "大客户", "电话销售", "面销"]},
        "sales_negotiation": {"label": "商务谈判", "kw": ["谈判", "商务", "签约", "报价", "招投标"]},
        "sales_crm": {"label": "CRM/客户管理", "kw": ["crm", "客户管理", "客户维护", "续约", "回款"]},
    },
    "finance": {
        "fin_accounting": {"label": "会计核算", "kw": ["会计", "记账", "凭证", "总账", "应收应付", "核算", "账务"]},
        "fin_reporting": {"label": "财务报表", "kw": ["报表", "合并报表", "财务分析", "预算", "决算", "利润表", "资产负债表"]},
        "fin_tax": {"label": "税务", "kw": ["税务", "报税", "增值税", "汇算清缴", "纳税申报", "个税"]},
        "fin_audit": {"label": "审计/内控", "kw": ["审计", "内控", "合规", "风控"]},
        "fin_cert": {"label": "证书(CPA/ACCA)", "kw": ["cpa", "acca", "中级会计", "注会", "税务师"]},
        "fin_software": {"label": "财务软件(用友/金蝶/SAP)", "kw": ["用友", "金蝶", "sap", "erp", "财务软件"]},
    },
    "design": {
        "ds_visual": {"label": "视觉设计", "kw": ["视觉", "平面", "海报", "banner", "排版", "ui", "审美", "vi", "封面"]},
        "ds_ux": {"label": "交互/UX", "kw": ["交互", "ux", "用户体验", "信息架构", "原型图"]},
        "ds_tools": {"label": "设计工具", "kw": ["figma", "sketch", "c4d", "blender", "illustrator", "ps"]},
    },
    "operations": {
        "ops_activity": {"label": "活动运营", "kw": ["活动策划", "活动运营", "执行落地", "活动复盘"]},
        "ops_user": {"label": "用户运营", "kw": ["用户运营", "留存", "召回", "分层", "社群运营"]},
        "ops_content": {"label": "内容运营", "kw": ["内容运营", "选题", "编辑", "分发", "内容策划", "公众号"]},
    },
    "hr": {
        "hr_recruit": {"label": "招聘", "kw": ["招聘", "面试", "人才盘点", "招聘渠道"]},
        "hr_perf": {"label": "绩效/薪酬", "kw": ["绩效", "薪酬", "kpi", "okr", "激励"]},
        "hr_training": {"label": "培训/组织", "kw": ["培训", "组织发展", "企业文化", "员工关系"]},
    },
    "education": {
        "edu_teach": {"label": "教学/授课", "kw": ["教学", "授课", "备课", "课堂", "学员"]},
        "edu_curriculum": {"label": "课程/教研", "kw": ["课程", "教研", "教案", "课纲"]},
    },
    "healthcare": {
        "med_clinical": {"label": "临床/护理", "kw": ["临床", "护理", "诊断", "病历", "医嘱"]},
        "med_pharma": {"label": "药学/医学", "kw": ["药学", "药理", "医学", "gmp"]},
    },
    "legal": {
        "legal_contract": {"label": "合同/法务", "kw": ["合同", "法务", "诉讼", "仲裁", "合规审查"]},
    },
    "supply": {
        "scm_supply": {"label": "供应链/采购", "kw": ["供应链", "采购", "仓储", "物流", "库存"]},
    },
    "manufacturing": {
        "mfg_process": {"label": "工艺/生产", "kw": ["工艺", "生产", "设备", "质量", "cad", "solidworks"]},
    },
}

# 全量词表：AI 词表 + 通用能力 + 所有岗位族（用于文本命中；不改变原有 key）
ALL_DIMS: dict[str, dict] = {}
for _k, _v in TAXONOMY.items():
    ALL_DIMS[_k] = _v
for _k, _v in GENERAL_DIMS.items():
    ALL_DIMS.setdefault(_k, _v)
for _pack in DOMAIN_PACKS.values():
    for _k, _v in _pack.items():
        ALL_DIMS.setdefault(_k, _v)


def detect_domains(text: str) -> list[str]:
    """粗判岗位族，返回命中关键词最多的前几个（用于展示/裁剪词表）。"""
    low = text.lower()
    scores: dict[str, int] = {}
    for name, pack in DOMAIN_PACKS.items():
        c = sum(1 for spec in pack.values() for kw in spec["kw"] if kw in low)
        if c:
            scores[name] = c
    ai_hits = sum(1 for spec in TAXONOMY.values() for kw in spec["kw"] if kw.lower() in low)
    if ai_hits >= 2:
        scores["ai"] = ai_hits
    return [n for n, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))]


STATUS_LABEL = {"full": "已具备", "partial": "部分具备", "missing": "缺失"}
STATUS_ICON = {"full": "🟢", "partial": "🟡", "missing": "🔴"}


def canonical_hits(text: str, dims: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """返回 text 中命中的能力 key 及其命中的原始词。

    默认用全量词表（AI + 通用 + 各岗位族），因此非 AI 岗位也能命中。
    """
    table = dims if dims is not None else ALL_DIMS
    low = text.lower()
    hits: dict[str, list[str]] = {}
    for key, spec in table.items():
        found = [kw for kw in spec["kw"] if kw.lower() in low]
        if found:
            hits[key] = found
    return hits
