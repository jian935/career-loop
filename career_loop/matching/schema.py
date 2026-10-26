"""核心数据结构 + 能力词表（同时充当无 Key 时的规则基线）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .boilerplate import strip_boilerplate


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
        "kw": ["大模型", "llm", "gpt", "transformer", "微调", "token", "上下文窗口",
               "机器学习基础", "机器学习", "深度学习", "神经网络", "模型评估指标", "算法基础"],
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
        "kw": ["后端", "api", "部署", "docker", "数据库", "服务", "上线", "工程化", "工程落地", "工程能力", "工程实践"],
        "fix": "把项目做成一条命令能起（Dockerfile + README），让别人能复现。",
    },
    "communication": {
        "label": "跨团队沟通协作",
        "kw": ["沟通", "协作", "跨部门", "对齐", "表达", "推动"],
        "fix": "在 README 里写清『给非技术同学看的一页纸』，这本身就是沟通能力的证据。",
    },
    "domain": {
        "label": "业务/行业理解",
        "kw": ["业务", "场景", "行业", "流程", "痛点", "流失", "留存点", "成本结构"],
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
# 约定：禁止使用过泛的词（裸「转化率」「漏斗」「工程」「机械」「图纸」等），
# 否则会在其他族里误触发。已锁死的回归见 career_loop/tests/test_core.py。
DOMAIN_PACKS: dict[str, dict] = {
    "product": {
        "prod_prd": {"label": "PRD/需求文档", "kw": ["prd", "需求文档", "需求分析", "原型", "axure", "墨刀", "需求评审", "需求梳理", "功能设计", "原型图", "用户故事", "竞品分析"]},
        "prod_roadmap": {"label": "产品规划", "kw": ["产品规划", "路线图", "版本规划", "迭代规划", "产品设计", "产品迭代", "灰度发布", "上线复盘", "产品经理"]},
    },
    "marketing": {
        "mkt_content": {"label": "内容/文案", "kw": ["文案", "内容运营", "选题", "脚本", "种草", "小红书", "抖音"]},
        "mkt_ads": {"label": "投放/广告", "kw": ["投放", "信息流", "sem", "千川", "roi", "cpa", "广告", "海外投放", "预算调控", "投放定向", "买量", "广告素材"]},
        "mkt_brand": {"label": "品牌/公关", "kw": ["品牌", "公关", "传播", "媒介", "危机公关"]},
        "mkt_private": {"label": "私域/社群", "kw": ["私域", "社群", "企微", "用户运营"]},
    },
    "sales": {
        "sales_bd": {"label": "客户开发/BD", "kw": ["客户开发", "拓客", "bd", "商务拓展", "渠道开发", "销售", "业绩", "大客户", "电话销售", "面销", "lead generation", "prospecting", "new business", "business development", "b2b sales"]},
        "sales_negotiation": {"label": "商务谈判", "kw": ["谈判", "商务", "签约", "报价", "招投标", "negotiation", "closing", "contract", "quota"]},
        "sales_crm": {"label": "CRM/客户管理", "kw": ["crm", "客户管理", "客户维护", "续约", "回款", "customer relationship management", "account management", "customer engagement", "customer focus", "salesforce", "crm software"]},
    },
    "finance": {
        "fin_accounting": {"label": "会计核算", "kw": ["会计", "记账", "凭证", "总账", "应收应付", "核算", "账务"]},
        "fin_reporting": {"label": "财务报表", "kw": ["报表", "合并报表", "财务分析", "预算", "决算", "利润表", "资产负债表", "预测", "经营分析"]},
        "fin_tax": {"label": "税务", "kw": ["税务", "报税", "增值税", "汇算清缴", "纳税申报", "个税"]},
        "fin_audit": {"label": "审计/内控", "kw": ["审计", "内控", "合规", "风控", "风险", "底稿"]},
        "fin_cert": {"label": "证书(CPA/ACCA)", "kw": ["cpa", "acca", "中级会计", "注会", "税务师"]},
        "fin_software": {"label": "财务软件(用友/金蝶/SAP)", "kw": ["用友", "金蝶", "sap", "erp", "财务软件"]},
    },
    "design": {
        "ds_visual": {"label": "视觉设计", "kw": ["视觉", "平面", "海报", "banner", "排版", "审美", "封面"]},
        "ds_ux": {"label": "交互/UX", "kw": ["交互", "用户体验", "信息架构", "原型", "线框图", "交互逻辑"]},
        "ds_tools": {"label": "设计工具", "kw": ["figma", "sketch", "c4d", "blender", "illustrator"]},
        "ds_motion": {"label": "动效/三维", "kw": ["动效", "动画设计", "after effects", "lottie", "特效", "三维"]},
    },
    "operations": {
        "ops_activity": {"label": "活动运营", "kw": ["活动策划", "活动运营", "执行落地", "活动复盘", "活动提报", "用户触达", "投放素材", "商家运营", "分层运营"]},
        "ops_user": {"label": "用户运营", "kw": ["用户运营", "留存", "用户召回", "流失召回", "分层", "社群运营"]},
        "ops_content": {"label": "内容运营", "kw": ["内容运营", "选题", "编辑", "分发", "内容策划", "公众号", "短视频", "作者维护", "话题运营", "财经内容", "内容审核", "违规样本", "风控策略"]},
        # SEO/网站运营线（v0.8.14 补）：operations/marketing/ecommerce 三族共享的
        # 误判里，网站运营类 JD 只写「搜索引擎/关键词/建站」。
        "ops_seo": {"label": "SEO/网站运营", "kw": ["seo", "搜索引擎", "关键词", "网站优化", "建站", "网站架构", "搜索排名", "网站运营"]},
    },
    "hr": {
        "hr_recruit": {"label": "招聘", "kw": ["招聘", "面试", "人才盘点", "招聘渠道"]},
        "hr_perf": {"label": "绩效/薪酬", "kw": ["绩效", "薪酬", "kpi", "okr", "激励"]},
        "hr_training": {"label": "培训/组织", "kw": ["培训", "培训赋能", "组织发展", "企业文化", "员工关系"]},
        "hr_labor": {"label": "劳动法/社保用工", "kw": ["劳动法", "社保", "公积金", "用工", "劳动关系", "入离职"]},
    },
    "education": {
        "edu_teach": {"label": "教学/授课", "kw": ["教学", "授课", "备课", "课堂", "学员", "教师岗", "任课", "授课教师", "教研活动"]},
        "edu_curriculum": {"label": "课程/教研", "kw": ["课程", "教研", "教案", "课纲", "课程研发", "课程设计", "教材", "教研员"]},
        "edu_student": {"label": "学员/班级管理", "kw": ["班主任", "学生管理", "家校", "学员服务", "班级", "招生", "续费", "学员运营"]},
        "edu_exam": {"label": "考试/测评", "kw": ["考务", "阅卷", "考试组织", "学习效果", "测验"]},
    },
    "healthcare": {
        "med_clinical": {"label": "临床/护理", "kw": ["临床", "护理", "诊断", "病历", "医嘱", "科室", "儿科", "门诊", "住院", "外科", "手术"]},
        "med_pharma": {"label": "药学/医学", "kw": ["药学", "药理", "医学", "gmp"]},
        "med_device": {"label": "医疗器械/注册", "kw": ["医疗器械", "注册证", "临床试验", "器械注册"]},
        "med_public": {"label": "公共卫生/院感", "kw": ["公共卫生", "流行病", "疾控", "院感", "防疫"]},
    },
    "legal": {
        "legal_contract": {"label": "合同/法务", "kw": ["合同", "法务", "合规审查", "合同审核"]},
        "legal_litigation": {"label": "诉讼/争议解决", "kw": ["诉讼", "仲裁", "争议解决", "出庭", "举证", "律师", "律所", "案件", "法学", "办案", "案源"]},
        "legal_corp": {"label": "公司法/投融资", "kw": ["公司法", "股权", "股权结构", "并购", "投融资"]},
        "legal_ip": {"label": "知识产权", "kw": ["知识产权", "专利", "商标", "著作权", "侵权"]},
    },
    "supply": {
        "scm_supply": {"label": "供应链/库存", "kw": ["供应链", "仓储", "库存", "周转", "安全库存", "齐套"]},
        "scm_purchase": {"label": "采购/供应商", "kw": ["采购", "询价", "比价", "供应商", "降本", "议价"]},
        "scm_plan": {"label": "计划/排产", "kw": ["生产计划", "排产", "mrp", "产能", "交期", "物料需求"]},
    },
    "manufacturing": {
        "mfg_process": {"label": "工艺/生产", "kw": ["工艺", "生产", "产线", "工装", "cad", "solidworks", "作业指导"]},
        "mfg_quality": {"label": "制程质量", "kw": ["制程", "不良", "良率", "过程控制", "首件"]},
        "mfg_equipment": {"label": "设备/维保", "kw": ["设备维护", "设备保养", "稼动率", "故障维修", "点检"]},
        "mfg_metal": {"label": "冶炼/轧制", "kw": ["冶炼", "轧制", "熔炼", "炼钢", "连铸"]},
        "mfg_textile": {"label": "纺织/印染", "kw": ["纺织", "印染", "织造", "针织", "染整"]},
    },
    # ---- AI 子领域 ----
    "ai_nlp": {
        "nlp_text": {"label": "NLP/文本处理", "kw": ["nlp", "自然语言", "分词", "命名实体", "文本分类", "情感分析", "bert", "transformer", "微调", "pytorch", "tensorflow"]},
    },
    "ai_cv": {
        "cv_vision": {"label": "计算机视觉", "kw": ["图像", "目标检测", "语义分割", "ocr", "opencv", "yolo", "人脸识别", "pytorch", "tensorflow", "缺陷检测", "图像处理", "暗光", "hdr效果", "isp联调", "相机", "雷达感知", "图像算法", "标注数据集"]},
    },
    "ai_recsys": {
        "rec_ranking": {"label": "推荐/搜索", "kw": ["推荐系统", "推荐算法", "排序模型", "召回策略", "特征工程", "ctr", "搜索排序", "个性化推荐", "短视频推荐", "样本清洗", "离线实验"]},
    },
    "ai_mlops": {
        "mlops_serve": {"label": "MLOps/模型部署", "kw": ["模型部署", "模型推理", "推理服务", "推理加速", "模型监控", "mlops", "kubernetes", "triton", "serving", "模型压缩"]},
    },
    "ai_solution": {
        "sol_presales": {"label": "AI 解决方案/售前", "kw": ["解决方案", "售前", "poc", "方案演示", "客户需求", "投标", "方案设计", "需求分析", "技术方案", "解决方案设计", "标书"]},
    },
    "ai_ops": {
        "aiops_label": {"label": "AI 运营/数据标注", "kw": ["数据标注", "标注规范", "训练师", "badcase", "评测集", "问题归因"]},
    },
    "ai_compliance": {
        "aicomp_ethics": {"label": "AI 合规/伦理", "kw": ["算法备案", "ai 伦理", "数据合规", "隐私保护", "内容安全"]},
    },
    # ---- 工商管理大类补充 ----
    "admin": {
        "adm_office": {"label": "行政后勤", "kw": ["行政", "办公用品", "固定资产", "会议组织", "后勤", "前台", "员工活动", "会议安排", "日程", "行程安排", "总裁", "秘书", "发文"]},
        "adm_archive": {"label": "档案/证照", "kw": ["档案", "印章", "证照", "资质年检", "用印", "会议纪要", "纪要", "公文"]},
    },
    "ecommerce": {
        "ec_shop": {"label": "电商运营", "kw": ["店铺", "gmv", "天猫", "抖音小店", "详情页", "电商转化率", "商品运营"]},
        "ec_live": {"label": "直播/达人", "kw": ["直播", "达人", "mcn", "带货", "直播间"]},
        "ec_product": {"label": "选品/上架", "kw": ["选品", "sku", "上新", "标题优化", "主图"]},
    },
    "tourism": {
        "tour_hotel": {"label": "酒店/住宿", "kw": ["酒店", "客房", "预订", "前台接待", "民宿"]},
        "tour_travel": {"label": "旅游/计调", "kw": ["旅游", "导游", "线路", "计调", "地接", "组团"]},
    },
    "it_systems": {
        "its_impl": {"label": "信息系统实施", "kw": ["erp", "系统实施", "需求调研", "系统配置", "上线支持", "信息系统", "系统上线", "部署实施", "客户培训", "软件部署"]},
        "its_ops": {"label": "系统运维/工单", "kw": ["系统运维", "工单", "故障处理", "用户支持", "权限管理", "服务器运维", "系统管理", "it运维", "技术支持", "故障诊断", "售后支持"]},
    },
    "project_mgmt": {
        "pmg_deliver": {"label": "项目管理", "kw": ["项目计划", "进度管控", "项目风险", "验收", "pmp", "里程碑", "跨部门协作", "项目进度", "项目交付", "项目管理经验", "项目统筹", "项目跟进", "项目落地", "项目生命周期", "研发项目", "危机管理"]},
        "pmg_agile": {"label": "敏捷/迭代管理", "kw": ["敏捷", "scrum", "sprint", "迭代管理", "站立会"]},
    },
    "trade": {
        "trade_export": {"label": "国际贸易", "kw": ["外贸", "报关", "信用证", "海外客户", "进出口", "询盘"]},
        "trade_doc": {"label": "单证/结算", "kw": ["单证", "结汇", "提单", "报关单", "产地证"]},
    },
    "asset_valuation": {
        "av_valuation": {"label": "资产评估", "kw": ["资产评估", "尽调", "估值", "资产盘点", "评估报告"]},
        "av_disposal": {"label": "资产处置/不良资产", "kw": ["不良资产", "资产处置", "拍卖", "债权", "清收"]},
    },
    "ai_speech": {
        "speech_audio": {"label": "语音(ASR/TTS)", "kw": ["语音识别", "语音合成", "asr", "tts", "声学", "唤醒词"]},
    },
    "ai_multimodal": {
        "mm_vision_lang": {"label": "多模态", "kw": ["多模态", "图文", "视觉语言", "vlm", "clip", "跨模态"]},
    },
    "ai_robotics": {
        "robot_embodied": {"label": "具身智能/机器人", "kw": ["机器人", "具身", "ros", "运动控制", "slam", "机械臂"]},
    },
    "ai_data": {
        "data_pipeline": {"label": "数据工程", "kw": ["数据清洗", "etl", "数据管道", "数仓", "特征平台", "数据治理", "指标监控", "异常波动", "数据报送", "特征构建", "模型训练"]},
    },
    # 业务数据分析（v0.8.14 新建族）：此前 TITLE_TO_FAMILY 把「数据分析师」
    # 「商业分析师」标给 data_analysis，但词表里没有这个族——标签不可达，
    # 29 条期望只能靠 ai_data 的词搭车，准确率 20.7%。
    # 注意：「数据分析」本身精确率仅 14%（运营 JD 也到处写数据分析），
    # 按过泛词硬标准不收；只收 60% 以上的复合词（预检见 precheck_new_words.py）。
    "data_analysis": {
        "da_report": {"label": "业务数据分析", "kw": ["业务分析", "数据分析方法", "报表体系", "tableau", "商业分析师"]},
    },
    "ai_testing": {
        "ai_qa": {"label": "AI 测试/质量", "kw": ["模型测试", "ai 测试", "效果测试", "评测方案", "质量保障", "交付质量", "模型监控", "漂移分析", "模型评估"]},
    },
    "property": {
        "prop_estate": {"label": "物业/房地产", "kw": ["物业", "房地产", "楼盘", "招商", "租赁", "业主"]},
        "prop_facility": {"label": "设施/工程维保", "kw": ["设施管理", "设备维保", "消防", "安防", "能耗管理"]},
    },
    "construction": {
        "con_build": {"label": "工程管理", "kw": ["施工", "工程管理", "招投标", "监理", "bim", "竣工验收"]},
        "con_cost": {"label": "造价/预算", "kw": ["造价", "工程量", "清单计价", "广联达", "结算审核"]},
        "con_design": {"label": "设计/深化", "kw": ["施工图", "建筑设计", "结构计算", "深化设计", "总平"]},
    },
    # ---- 研发/工程类 ----
    "backend": {
        "be_lang": {"label": "服务端语言", "kw": ["java", "golang", "c++", "node.js", "服务端", "后端开发", "rust", "go语言", "c语言"]},
        "be_arch": {"label": "架构/分布式", "kw": ["微服务", "分布式", "高并发", "架构设计", "消息队列", "kafka", "redis", "缓存", "etcd", "rpc", "tcp", "流媒体", "多租户"]},
        "be_db": {"label": "数据库/存储", "kw": ["mysql", "postgres", "oracle", "数据库设计", "索引优化", "分库分表", "redis", "etcd", "存储组件", "文件系统", "io路径"]},
    },
    "frontend": {
        "fe_framework": {"label": "前端框架", "kw": ["vue", "react", "angular", "前端框架", "组件化", "typescript", "组件封装", "浏览器渲染"]},
        "fe_mobile": {"label": "移动端/小程序", "kw": ["小程序", "uni-app", "flutter", "react native", "移动端", "h5", "移动端适配", "android sdk", "车载安卓"]},
        "fe_build": {"label": "构建/性能", "kw": ["webpack", "vite", "构建优化", "首屏", "前端性能", "埋点", "性能优化", "profiler"]},
    },
    "qa": {
        "qa_functional": {"label": "功能测试", "kw": ["功能测试", "测试用例", "黑盒", "兼容性", "回归测试", "版本自测", "bug闭环", "测试规范", "测试报告"]},
        "qa_auto": {"label": "自动化测试", "kw": ["自动化测试", "selenium", "playwright", "接口测试", "脚本化", "测试程序"]},
        "qa_perf": {"label": "性能/压力测试", "kw": ["性能测试", "压力测试", "jmeter", "loadrunner", "稳定性测试", "压测", "可靠性测试", "耐久测试", "高低温"]},
    },
    "devops": {
        "devops_linux": {"label": "Linux/服务器运维", "kw": ["linux", "shell脚本", "服务器", "运维", "nginx", "脚本运维", "slurm", "作业调度", "集群监控"]},
        "devops_container": {"label": "容器/编排", "kw": ["容器", "helm", "集群", "容器化", "swarm", "k8s", "kubernetes", "云原生", "编排"]},
        "devops_monitor": {"label": "监控/告警", "kw": ["监控告警", "监控体系", "告警体系", "prometheus", "grafana", "日志分析", "故障排查", "告警日志", "性能调优"]},
        "devops_ci": {"label": "CI/CD 流水线", "kw": ["jenkins", "gitlab ci", "流水线", "发布流程", "灰度发布", "版本合入"]},
    },
    "security": {
        "sec_pentest": {"label": "渗透/漏洞", "kw": ["渗透", "漏洞", "安全测试", "owasp", "ctf", "代码审计", "漏洞挖掘", "poc编写", "安全周报"]},
        "sec_compliance": {"label": "等保/安全合规", "kw": ["等保", "等级保护", "iso27001", "数据脱敏", "个人信息保护"]},
        "sec_ops": {"label": "安全运营", "kw": ["安全运营", "应急响应", "防火墙", "入侵检测", "威胁情报", "攻击链路", "siem", "威胁事件"]},
    },
    "embedded": {
        "emb_mcu": {"label": "单片机/固件", "kw": ["单片机", "stm32", "嵌入式", "rtos", "驱动开发", "固件", "mcu", "外设驱动", "蓝牙通信", "蓝牙协议", "芯片验证", "读写逻辑"]},
        "emb_circuit": {"label": "电路/PCB", "kw": ["原理图", "pcb", "硬件设计", "altium", "电路设计", "示波器", "频谱仪", "射频", "ota测试", "调试工具", "测试设备", "测试仪器"]},
        "emb_bus": {"label": "总线/通信协议", "kw": ["can 总线", "modbus", "串口", "spi", "i2c", "485", "工业总线", "jni", "aosp"]},
    },
    "electrical": {
        "elec_plc": {"label": "PLC/电气控制", "kw": ["plc", "梯形图", "伺服", "变频器", "电气控制"]},
        "elec_design": {"label": "供配电设计", "kw": ["供配电", "配电柜", "继电保护", "eplan", "电气设计"]},
        "elec_auto": {"label": "工业自动化", "kw": ["dcs", "scada", "产线自动化", "组态", "工控"]},
    },
    "mechanical": {
        "mech_design": {"label": "结构设计", "kw": ["结构设计", "钣金", "注塑", "传动", "非标设计", "装配图"]},
        "mech_sim": {"label": "仿真/有限元", "kw": ["有限元", "仿真", "ansys", "力学分析", "热设计"]},
        "mech_draw": {"label": "出图/工艺文件", "kw": ["工程图", "公差", "bom", "工艺文件", "三维建模"]},
    },
    "quality": {
        "qm_system": {"label": "质量体系", "kw": ["质量管理体系", "iso9001", "体系认证", "内审", "iatf"]},
        "qm_inspect": {"label": "检验/统计", "kw": ["来料检验", "出货检验", "fmea", "spc", "抽检", "不合格品", "质量检验"]},
        "qm_improve": {"label": "持续改进", "kw": ["六西格玛", "持续改进", "质量改善", "8d", "pdca", "精益"]},
    },
    # ---- 金融/专业服务 ----
    "banking": {
        "bank_credit": {"label": "信贷/授信", "kw": ["信贷", "授信", "贷前", "贷后", "征信", "放款", "信用卡", "消费信贷", "小微贷款", "银行客户经理", "贷款", "逾期"]},
        "bank_retail": {"label": "零售/网点", "kw": ["理财", "存款", "网点", "柜面", "零售银行", "客户经理", "手机银行", "网银", "理财经理", "存款营销", "普惠金融"]},
        "bank_risk": {"label": "信用风险", "kw": ["信用风险", "拨备", "不良贷款", "风险分类", "贷后管理", "风险控制", "合规审查", "反洗钱", "资产质量"]},
        # 投行/股权投资线（v0.8.14 补）：中文真实 JD 里 banking/securities 的
        # 误判 60/39 条几乎全是投资经理/融资总监类岗位，原词表只有银行运营词。
        # 每个词都过了公开数据集的精确率预检（见 scripts/precheck_new_words.py）。
        "bank_invest": {"label": "投行/股权投资", "kw": ["投行", "投资银行", "投融资", "尽职调查", "股权投资", "投后管理", "投资经理", "融资", "股权", "投资项目", "募资", "承做", "ipo", "并购", "增资", "减资"]},
    },
    "insurance": {
        "ins_underwrite": {"label": "核保/承保", "kw": ["核保", "承保", "费率", "再保", "投保"]},
        "ins_claim": {"label": "理赔/查勘", "kw": ["理赔", "查勘", "定损", "结案", "赔付"]},
        "ins_product": {"label": "保险产品/精算", "kw": ["保险产品", "精算", "条款设计", "保额", "险种"]},
    },
    "securities": {
        "sec_research": {"label": "行业研究", "kw": ["行业研究", "行研", "公司研究", "调研纪要", "深度报告"]},
        "sec_valuation": {"label": "估值建模", "kw": ["估值建模", "dcf", "财务模型", "可比公司", "wind"]},
        "sec_invest": {"label": "投资/交易", "kw": ["投研", "组合管理", "二级市场", "路演", "投资建议", "投资", "融资", "股权", "投后管理", "投资经理", "投资项目", "募资"]},
    },
    "consulting": {
        "csl_industry": {"label": "商业分析/研究", "kw": ["管理咨询", "商业分析", "战略咨询", "市场研究", "咨询顾问", "咨询公司", "咨询项目", "咨询服务", "咨询方案", "咨询岗"]},
        "csl_delivery": {"label": "咨询交付", "kw": ["咨询项目", "客户访谈", "汇报材料", "驻场", "顾问项目", "客户需求调研", "咨询顾问", "咨询公司", "咨询服务", "咨询团队", "咨询业务"]},
        "csl_strategy": {"label": "战略/组织", "kw": ["战略规划", "商业模式", "组织设计", "流程再造", "对标分析"]},
    },
    # ---- 内容/传媒/文娱 ----
    "media": {
        "med_pr": {"label": "公关/媒体关系", "kw": ["媒体关系", "新闻稿", "舆情", "发布会", "媒体投放", "品牌传播", "媒体资源", "危机公关", "广告投放"]},
        "med_edit": {"label": "编辑/校对", "kw": ["编辑", "校对", "稿件", "选题策划", "内容审核", "文案撰", "内容创作", "文章撰写", "图文编辑", "推文", "资讯编辑"]},
    },
    "film": {
        "film_shoot": {"label": "拍摄/编导", "kw": ["拍摄", "分镜", "编导", "导演", "脚本策划", "制片", "影视", "节目制作", "综艺", "影视制作", "摄影"]},
        "film_post": {"label": "剪辑/后期", "kw": ["剪辑", "后期", "调色", "字幕", "成片", "影视后期", "特效", "包装", "调音"]},
        # 直播/演艺线（v0.8.14 补）：中文集里 film/media 的 miss 多是语音/秀场
        # 主播类 JD——文本写「直播/才艺/脱口秀」而不出现「主播」二字。
        "film_stream": {"label": "直播/演艺", "kw": ["主播", "直播", "才艺", "脱口秀", "艺人", "公会", "播音"]},
    },
    "game": {
        "game_design": {"label": "游戏策划", "kw": ["游戏策划", "关卡", "数值", "玩法", "系统策划", "游戏开发", "游戏引擎", "手游", "游戏项目", "游戏客户端"]},
        "game_ops": {"label": "游戏运营", "kw": ["游戏运营", "版本更新", "付费率", "arpu", "玩家社区"]},
    },
    "translation": {
        "tr_written": {"label": "笔译/本地化", "kw": ["笔译", "译文", "术语", "本地化", "翻译稿", "技术文档翻译"]},
        "tr_oral": {"label": "口译", "kw": ["口译", "同传", "交传", "陪同翻译"]},
        "tr_cat": {"label": "CAT 工具", "kw": ["trados", "cat 工具", "语料", "译后编辑", "memoq"]},
    },
    # ---- 服务/零售/生活 ----
    "service": {
        "cs_hotline": {"label": "客服/工单", "kw": ["客服", "呼叫中心", "在线客服", "话术", "接线", "客服专员", "客服代表", "在线服务", "咨询解答", "客户咨询", "工单处理", "客服中心"]},
        "cs_complaint": {"label": "投诉/异常处理", "kw": ["投诉", "客诉", "异常处理", "退款", "赔付", "售后", "退换货", "纠纷", "客户问题处理"]},
        "cs_quality": {"label": "服务质检", "kw": ["质检", "录音抽检", "服务标准", "满意度回访", "服务培训", "客户满意度", "回访", "服务态度"]},
    },
    "retail": {
        "rt_store": {"label": "门店/连锁", "kw": ["门店", "连锁", "陈列", "导购", "巡店", "店长"]},
        "rt_inventory": {"label": "进销存", "kw": ["进销存", "补货", "盘点", "毛利", "动销"]},
        "rt_franchise": {"label": "加盟/选址", "kw": ["加盟", "选址", "开店", "商圈", "招商拓展"]},
    },
    "catering": {
        "cat_ops": {"label": "餐饮运营", "kw": ["餐饮", "出餐", "前厅", "后厨", "翻台", "排班"]},
        "cat_hygiene": {"label": "食品安全", "kw": ["食品安全", "卫生", "haccp", "健康证", "消杀"]},
    },
    "tourism_cn": {
        "tour_guide": {"label": "导游/讲解", "kw": ["讲解", "带团", "景区", "游客服务"]},
    },
    # ---- 制造/能源/汽车/农林 ----
    "energy": {
        "en_power": {"label": "电力/电网", "kw": ["电力", "电网", "变电站", "输配电", "配电自动化", "发电", "电厂", "输变电"]},
        "en_chem": {"label": "化工/工艺安全", "kw": ["化工", "反应釜", "危化品", "化工安全", "工艺包"]},
        "en_battery": {"label": "新能源/储能", "kw": ["储能", "锂电", "光伏", "电芯", "bms", "逆变器"]},
    },
    "automotive": {
        "auto_vehicle": {"label": "整车/零部件", "kw": ["整车", "零部件", "底盘", "车身", "动力总成"]},
        "auto_nev": {"label": "三电/新能源车", "kw": ["三电", "电池包", "电机", "电控", "整车控制"]},
        "auto_test": {"label": "台架/路试", "kw": ["台架", "路试", "标定", "整车试验", "nvh"]},
    },
    "agriculture": {
        "ag_plant": {"label": "种植/农艺", "kw": ["种植", "栽培", "育种", "病虫害", "农艺"]},
        "ag_breed": {"label": "养殖/防疫", "kw": ["养殖", "饲养", "防疫", "兽医", "畜群"]},
        "ag_tech": {"label": "智慧农业", "kw": ["农机", "灌溉", "土壤", "无人机植保", "智慧农业"]},
        "ag_forestry": {"label": "林业/草原", "kw": ["造林", "森林", "林地", "草原", "抚育采伐"]},
        "ag_fishery": {"label": "渔业/水产", "kw": ["捕捞", "水产养殖", "渔船", "育苗", "水质调控"]},
        # 农产品/食品加工线（v0.8.14 补）：中文集里 agriculture 的 miss 是
        # 农业产业园/团餐/预制菜类岗位。
        "ag_product": {"label": "农产品/食品", "kw": ["农产品", "农业产业园", "农产品加工", "冷链物流", "预制菜", "中央厨房", "团餐", "农业行业"]},
    },
    "domestic": {
        "dm_housekeeping": {"label": "家政/保洁", "kw": ["家政", "保洁", "保姆", "月嫂", "收纳"]},
        "dm_beauty": {"label": "美容/美发", "kw": ["美容", "美发", "美甲", "护肤", "造型"]},
        "dm_repair": {"label": "维修服务", "kw": ["家电维修", "水电维修", "上门维修", "设备维修服务"]},
    },
    "transport_ops": {
        "top_vehicle": {"label": "驾驶/车辆调度", "kw": ["驾驶", "驾照", "车辆调度", "货运驾驶", "班车"]},
        "top_machine": {"label": "叉车/起重", "kw": ["叉车", "起重", "吊装", "挖掘机", "特种设备作业"]},
    },
    # ---- v0.8.26 新增三族：词都是拿真实中文 JD（china_job 公开集）逐个审过的 ----
    # 入选标准（沿用本仓库 v0.8.14 的硬口径）：全库命中条数 + 其中「岗位名确实属于
    # 该职业」的比例。审计工具见 scripts/audit_new_pack_words.py，低于 50% 的词一律
    # 没收——候选阶段确实有词被刷掉（港口 46%、提单 29%、航空类几乎全军覆没），
    # 所以航空、半导体等方向这轮**没有**化成词表，也不对外宣称。
    "maritime": {
        # 只用复合词 / 领域独有名词，**不收「船舶」这种裸名词**：裸名词不是在
        # 辨别人会不会，而是在辨认这段文字有没有出现这个字——
        # 「任职要求：船舶制造类相关专业」也会被判成会开船（真事，eval_real_jd
        # 的负例 N07 就是这么被抓出来的）。
        "mar_ops": {"label": "船舶/航运操作", "kw": ["船舶营运调度", "船舶动态跟踪", "船舶配载", "船队调度", "船员管理"]},
        "mar_eng": {"label": "船舶与海洋工程", "kw": ["轮机工程", "船舶与海洋工程", "船体结构", "船级社", "坞修", "舾装"]},
    },
    "mining": {
        "mi_ops": {"label": "采矿/井下作业", "kw": ["矿山开采", "井下作业", "采掘工作面", "矿山生产管理"]},
        "mi_geo": {"label": "地质勘查/选矿", "kw": ["矿产勘查", "选矿工艺", "钻探施工", "储量核实"]},
        "mi_safety": {"label": "矿山安全", "kw": ["矿山安全", "尾矿库", "矿井通风"]},
    },
    "environment": {
        "env_assess": {"label": "环评/环保合规", "kw": ["环境影响评价", "环评报告", "排污许可", "环保验收", "环境监测"]},
        "env_treat": {"label": "三废治理", "kw": ["废水处理", "污水处理", "废气治理", "危废处置", "固废处置"]},
        "env_carbon": {"label": "双碳/碳资产", "kw": ["碳排放核算", "碳核查", "碳资产管理", "清洁生产审核"]},
        "env_ehs": {"label": "EHS/职业健康", "kw": ["职业健康安全", "安全生产标准化", "ehs体系"]},
    },
    # ---- 科研/公共/社会服务 ----
    "research": {
        "rs_paper": {"label": "论文/文献", "kw": ["学术论文", "发表论文", "sci", "期刊", "文献检索", "论文写作"]},
        "rs_exp": {"label": "课题/实验", "kw": ["课题", "实验设计", "实验室", "科研", "科研项目"]},
        "rs_method": {"label": "研究方法/统计", "kw": ["统计方法", "计量模型", "计量经济学", "spss", "stata", "r 语言", "问卷"]},
    },
    "public_admin": {
        "pub_document": {"label": "公文/政策", "kw": ["公文", "行文", "政务", "汇报材料", "政策法规", "政策研究", "政府关系", "政府事务", "政策制定", "立法", "人大", "政协", "地方政府", "地方经济"]},
        "pub_service": {"label": "窗口/基层服务", "kw": ["窗口服务", "办事大厅", "群众", "基层", "公共服务", "街道办", "社区工作", "网格员", "政务服务"]},
    },
    "social": {
        "soc_case": {"label": "个案/社区工作", "kw": ["个案", "小组工作", "社区", "帮扶", "走访"]},
        "soc_project": {"label": "公益项目", "kw": ["公益项目", "资助", "志愿服务", "ngo", "募款"]},
    },
    "psychology": {
        "psy_counsel": {"label": "心理咨询", "kw": ["心理咨询", "个案咨询", "共情", "倾听", "心理疏导"]},
        "psy_assess": {"label": "测评/干预", "kw": ["心理测评", "量表", "筛查", "干预", "危机干预"]},
    },
    "sports": {
        "sp_coach": {"label": "教练/训练", "kw": ["教练", "训练计划", "体能", "赛事组织", "运动损伤"]},
        "sp_fitness": {"label": "健身/私教", "kw": ["健身", "私教", "体测", "会员", "课程销售"]},
    },
    "logistics": {
        "log_warehouse": {"label": "仓储/分拣", "kw": ["仓储", "拣货", "盘点", "库内", "出库", "入库"]},
        "log_transport": {"label": "运输/配送", "kw": ["运输", "配送", "干线", "城配", "运费", "时效"]},
        "log_customs": {"label": "关务/报关", "kw": ["关务", "清关", "关税", "保税", "舱单"]},
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


# 英文别名层：让引擎能识别英文 JD / 简历。
# 仅覆盖真实评测集（job-resume-matching 数据集）有数据的岗位族 + 通用维度；
# 其余族英文支持为「待补」，不夸大覆盖。
# 严格只用复合英文词（如 "project management"），绝不用过泛单字
# （单独 management/analysis/development/design 等会跨族误判，与中文词表同一铁律）。
EN_VOCAB: dict[str, list[str]] = {
    # ---- 通用维度 ----
    "exec_project": ["project management", "program management", "project planning", "project coordination", "deliverables", "timeline"],
    "problem_solving": ["problem solving", "root cause", "troubleshooting", "critical thinking", "process improvement", "analytical thinking"],
    "learning": ["self-motivated", "quick learner", "continuous learning", "proactive learning"],
    "ownership": ["adaptability", "flexibility", "attention to detail", "reliability", "integrity", "confidentiality"],
    "writing": ["report writing", "documentation", "presentation skills", "proposal", "technical writing", "business writing"],
    "customer": ["customer focus", "customer relationship", "client relationship", "user experience", "customer satisfaction"],
    "leadership": ["leadership", "team management", "people management", "mentoring", "coaching", "team leadership"],
    "language": ["english", "bilingual", "fluent english"],
    "office": ["microsoft office", "microsoft excel", "excel", "ms office", "powerpoint", "word"],
    # ---- AI 维度 ----
    "python": ["python", "pandas", "numpy", "fastapi", "django"],
    "llm_basics": ["gpt", "large language model", "transformer"],
    "prompt_eng": ["prompt engineering"],
    "rag": ["retrieval augmented", "vector database", "reranking"],
    "agent": ["multi-agent", "orchestration"],
    "product_sense": ["user interview", "product design", "product sense", "requirements analysis", "customer discovery"],
    "data_analysis": ["metrics", "kpi", "sql", "dashboard", "funnel", "retention", "attribution", "data analytics"],
    "eval": ["evaluation", "a/b testing", "ab testing", "benchmark"],
    "engineering": ["backend", "api", "deployment", "docker", "database", "service", "devops"],
    "communication": ["cross-functional", "stakeholder", "collaboration"],
    "domain": ["business process", "industry", "cost structure", "pain point"],
    # ---- FINANCE ----
    "fin_accounting": ["accounting", "bookkeeping", "general ledger", "accounts payable", "accounts receivable"],
    "fin_reporting": ["financial reporting", "financial statements", "financial analysis", "financial modeling", "budgeting", "forecasting", "p&l", "balance sheet", "variance analysis"],
    "fin_tax": ["tax", "taxation", "tax filing", "vat", "corporate tax"],
    "fin_audit": ["audit", "internal control", "internal audit", "sox", "risk management"],
    "fin_cert": ["cpa", "acca", "cfa"],
    "fin_software": ["sap", "oracle financials", "quickbooks", "hyperion"],
    # ---- HR ----
    "hr_recruit": ["recruitment", "recruiting", "sourcing", "talent acquisition", "hiring"],
    "hr_perf": ["performance management", "compensation", "benefits", "payroll", "incentive"],
    "hr_training": ["training", "learning and development", "organizational development", "employee engagement"],
    "hr_labor": ["labor law", "employment law", "employee relations", "onboarding", "offboarding", "hr compliance"],
    # ---- SALES ----
    "sales_bd": ["business development", "lead generation", "prospecting", "new business", "revenue generation", "sales representative", "account executive", "sales manager", "account manager", "sales rep", "salesperson", "quota"],
    "sales_negotiation": ["negotiation", "closing", "contract negotiation"],
    "sales_crm": ["crm", "customer relationship management", "account management", "renewal"],
    # ---- MARKETING ----
    "mkt_content": ["content marketing", "copywriting", "social media", "blog"],
    "mkt_ads": ["advertising", "sem", "ppc", "paid media", "campaign", "cpa"],
    "mkt_brand": ["branding", "public relations", "communications"],
    # ---- CONSULTING ----
    "csl_industry": ["market research", "commercial analysis", "strategy consulting", "business analysis"],
    "csl_strategy": ["strategic planning", "business strategy", "organizational design", "benchmarking"],
    # ---- IT / ENGINEERING ----
    "its_impl": ["system implementation", "erp implementation", "system configuration"],
    "its_ops": ["system administration", "active directory", "help desk", "technical support", "ticketing", "incident management", "vendor management", "networking"],
    "devops_linux": ["linux", "shell scripting", "server administration"],
    "devops_container": ["docker", "kubernetes", "container", "helm"],
    "devops_monitor": ["monitoring", "prometheus", "grafana", "alerting"],
    "devops_ci": ["ci/cd", "jenkins", "gitlab ci", "pipeline"],
    "be_lang": ["golang", "java", "c++", "node.js", "backend development", "rust"],
    "be_arch": ["microservices", "distributed systems", "rest api", "message queue", "kafka", "redis", "caching"],
    "be_db": ["mysql", "postgresql", "oracle", "database design", "index optimization"],
    "fe_framework": ["react", "vue", "angular", "typescript", "javascript", "frontend"],
    "fe_mobile": ["flutter", "react native", "mobile development", "h5"],
    "fe_build": ["webpack", "vite", "frontend performance"],
    "qa_functional": ["functional testing", "test cases", "black box", "compatibility testing", "regression testing"],
    "qa_auto": ["automation testing", "selenium", "playwright", "api testing"],
    "qa_perf": ["performance testing", "load testing", "jmeter", "stress testing"],
    "sec_pentest": ["penetration testing", "vulnerability", "owasp", "code review", "ctf"],
    "sec_compliance": ["iso 27001", "data masking", "personal information protection", "security compliance"],
    "sec_ops": ["security operations", "incident response", "firewall", "intrusion detection", "threat intelligence"],
    "emb_mcu": ["firmware", "rtos", "microcontroller", "stm32", "embedded development"],
    "emb_circuit": ["pcb", "circuit design", "hardware design", "altium"],
    "emb_bus": ["can bus", "modbus", "spi", "i2c"],
}
for _k, _en in EN_VOCAB.items():
    if _k in ALL_DIMS:
        _existing = {w.lower() for w in ALL_DIMS[_k]["kw"]}
        for _w in _en:
            _w = _w.lower()
            if _w not in _existing:
                ALL_DIMS[_k]["kw"].append(_w)
                _existing.add(_w)


# AI 硬核词：只有命中这些才计入「AI 岗位」判定，避免通用业务词
# （business process / kpi / sql 等）把任意岗位误判成 AI。
AI_CORE_KW = [
    "python", "pandas", "numpy", "fastapi", "django", "gpt", "large language model", "llm",
    "transformer", "prompt engineering", "rag", "retrieval augmented", "vector database",
    "reranking", "agent", "multi-agent", "orchestration", "mlops", "fine-tuning", "pytorch",
    "tensorflow", "langchain", "langgraph", "nlp", "natural language processing", "computer vision",
    "object detection", "recommender", "model deployment", "kubernetes", "etl", "data pipeline",
    "embedding", "大模型", "微调", "智能体", "检索增强", "提示词", "函数调用", "多智能体",
]


# 岗位族中文名（v0.8.17 从 cli.DOMAIN_CN 下沉，供 LLM 提示词/CLI/网页共用）。
# 单测锁住「FAMILY_CN 的键必须恰好覆盖 DOMAIN_PACKS + ai 父族」——
# 新增族忘起名字时，测试会红，不会静默漏进提示词。
FAMILY_CN: dict[str, str] = {
    "product": "产品", "marketing": "市场", "sales": "销售", "finance": "财务",
    "design": "设计", "operations": "运营", "hr": "人力", "education": "教育",
    "healthcare": "医疗", "legal": "法务", "supply": "供应链", "manufacturing": "制造",
    "ai": "AI/算法",
    "ai_nlp": "NLP", "ai_cv": "CV", "ai_recsys": "推荐/搜索", "ai_mlops": "MLOps",
    "ai_solution": "AI方案/售前", "ai_ops": "AI运营/标注", "ai_compliance": "AI合规",
    "ai_speech": "语音", "ai_multimodal": "多模态", "ai_robotics": "具身/机器人",
    "ai_data": "数据工程", "ai_testing": "AI测试", "data_analysis": "数据分析",
    "admin": "行政", "ecommerce": "电商", "tourism": "旅游/酒店",
    "it_systems": "信息管理", "project_mgmt": "项目管理", "trade": "外贸",
    "asset_valuation": "资产评估",
    "property": "物业/房地产", "construction": "工程管理",
    "backend": "后端", "frontend": "前端", "qa": "测试", "devops": "运维",
    "security": "信息安全", "embedded": "嵌入式", "electrical": "电气",
    "mechanical": "机械设计", "quality": "质量",
    "banking": "银行", "insurance": "保险", "securities": "证券",
    "consulting": "咨询", "media": "传媒", "film": "影视", "game": "游戏",
    "translation": "翻译", "service": "客服", "retail": "零售",
    "catering": "餐饮", "tourism_cn": "导游/讲解", "domestic": "居民服务",
    "transport_ops": "运输操作",
    "maritime": "船舶/航运", "mining": "采矿/地质", "environment": "环保/EHS",
    "energy": "能源化工", "automotive": "汽车", "agriculture": "农林牧渔",
    "research": "科研", "public_admin": "公务/公共事务", "social": "社工",
    "psychology": "心理", "sports": "体育", "logistics": "物流",
}


def detect_domains(text: str) -> list[str]:
    """粗判岗位族，返回命中关键词最多的前几个（用于展示/裁剪词表）。

    先剥平台样板（来源声明/反诈免责声明）——否则「招聘」「证照」等词
    会被样板句带着在 75%/41% 的 JD 上误命中（详见 boilerplate.py）。
    """
    low = strip_boilerplate(text).lower()
    scores: dict[str, int] = {}
    for name, pack in DOMAIN_PACKS.items():
        c = sum(1 for spec in pack.values() for kw in spec["kw"] if kw.lower() in low)
        if c:
            scores[name] = c
    ai_hits = sum(1 for k in AI_CORE_KW if k in low)
    # 任一 ai_* 子族命中即视为 AI 岗（父族由子族推导）：
    # 「推荐算法工程师」命中 ai_recsys 但不含两个 AI_CORE_KW，
    # 此前判不出 ai，对照集上两个 AI 岗位族识别 MISS 就是这个原因。
    sub_ai = [n for n in scores if n.startswith("ai_")]
    if ai_hits >= 2 or sub_ai:
        scores["ai"] = ai_hits if ai_hits >= 2 else max(scores[n] for n in sub_ai)
    return [n for n, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))]


STATUS_LABEL = {"full": "已具备", "partial": "部分具备", "missing": "缺失"}
STATUS_ICON = {"full": "🟢", "partial": "🟡", "missing": "🔴"}


# ---------------------------------------------------------------------------
# 过泛词的语境约束（v0.8.13，真实中文 JD 实测得出）
# ---------------------------------------------------------------------------
# 问题：某些词单独看太泛，命中它们不等于命中该能力项。
#   「服务」在 465 条真实中文 JD 里是"服务质量/服务标准/服务团队"（物流运营语境），
#   不是"工程落地与部署"；「证照」多是"资质证件"而非"档案管理"。
#   实测误抽率：engineering 精确率仅 44%、adm_archive 仅 8%。
#
# 为什么不用"直接删词"：删了会连带漏掉真正需要它的句子
# （「需要把项目服务化部署」「要做证照年审」）。
#
# 规则：下面这些词**只有在同一行还出现语境词时**才算命中该能力项。
# 语境词用「任一命中」即可，命中不到就不算——宁可漏，不可乱报。
#
# ⚠️ 语境词表里**不能包含该能力项自己的泛词**，
# 否则等于没约束（"业务"既是 domain 的泛词、又在语境表里 → 永远通过）。
# 所以每张表只列**强语境词**。

# 人力族共用的强信号复合词语境（见下方 CONTEXT_REQUIRED 的 hr 注释）。
# 这些词只真 HR 岗说，非 HR 岗的通用模板不出现——实测在 1,838 条真实中文 JD 上
# 精确率 50%~100%，是门控「培训 / 绩效 / 薪酬 / 招聘 / 用工」这类泛词的可靠依据。
_HR_CONTEXT = (
    "招聘渠道", "人才盘点", "面试安排", "简历筛选", "职位发布", "招聘流程",
    "招聘计划", "招聘工作", "招聘需求", "人才招聘", "校招", "社招", "猎头",
    "员工关系", "劳动关系", "劳资", "入离职", "社保公积金",
    "薪酬管理", "薪酬体系", "绩效体系", "绩效管理", "绩效考核",
    "培训体系", "培训管理", "内训师", "培训平台", "培训计划", "培训课程", "培训需求",
    "组织发展", "人力资源", "人事管理", "hrbp", "hr",
)

CONTEXT_REQUIRED: dict[str, tuple[str, ...]] = {
    # engineering：泛词「服务」「上线」需伴随工程语境
    "engineering": (
        "后端", "前端", "全栈", "微服务", "服务化", "docker", "容器", "k8s",
        "kubernetes", "数据库", "数据仓库", "架构", "接口", "api", "代码",
        "编程", "服务器", "运维", "部署", "工程化", "工程落地",
        "工程能力", "工程实践", "开发", "研发", "技术栈",
    ),
    # adm_archive：泛词「证照」需伴随档案/用印语境
    "adm_archive": (
        "档案", "归档", "存档", "印章", "用印", "盖章", "证照管理", "证照年审",
        "资质年检", "年检", "许可证", "营业执照",
    ),
    # domain：泛词「业务」「场景」「行业」「流程」需伴随理解语境。
    # 注意「痛点/留存/流失/成本结构」本身就是 domain 的**专有词**，
    # 它们出现时说明文本确实在谈业务理解，不需要额外语境。
    "domain": (
        "业务场景", "行业场景", "业务流程", "业务痛点", "业务模式", "业务理解",
        "行业理解", "业务分析", "行业分析", "场景设计", "痛点", "留存",
        "流失", "成本结构", "商业模式", "梳理", "理解",
    ),
    # product_sense：泛词「需求」「访谈」需伴随产品语境
    "product_sense": (
        "产品需求", "需求文档", "需求分析", "需求评审", "需求梳理", "需求调研",
        "用户需求", "用户洞察", "用户调研", "用户访谈", "访谈用户",
        "产品设计", "产品规划", "交互", "原型", "prd", "场景设计",
    ),
    # hr：中文 JD 里「培训 / 绩效 / 薪酬 / 激励 / 招聘 / 用工」几乎是**全员通用模板词**
    # （任何岗位都写"提供培训 / 绩效奖金 / 五险一金 / 我们正在招聘"），单独出现不等于
    # 这是人力岗。这些词只有在伴随**岗位专属复合词**时才算命中人力族——
    # 真 HR 岗说"培训体系 / 招聘渠道 / 薪酬管理 / 员工关系 / 劳动关系 / 组织发展"，
    # 非 HR 岗的"提供培训 / 绩效奖金"不出现这些。
    # 语境表刻意只用强信号复合词，不用「员工 / 入职 / 社保」这类同样全民通用的词
    # （否则门控等于没拦）。各 key 的**自有具体词**也列进表里，使它们免门控、照常放行。
    "hr_recruit": _HR_CONTEXT + ("面试", "人才盘点", "招聘渠道"),
    "hr_perf": _HR_CONTEXT + ("kpi", "okr"),
    "hr_training": _HR_CONTEXT + ("组织发展", "企业文化", "员工关系",
                                  "培训赋能", "培训及考核"),
    "hr_labor": _HR_CONTEXT + ("劳动法", "社保", "公积金", "劳动关系", "入离职"),
}


def _context_ok(key: str, line_low: str, doc_low: str = "") -> bool:
    """该能力项在这行是否成立（过泛词需要语境支撑）。

    语境词在**同一行**找不到时，再退一步看**整篇文档**——
    JD 里常见「要求行」和「说明行」分开写的情况：
    「需要深入理解某业务场景的痛点与流程」这行本身没有强语境词，
    但「业务场景」「痛点」已经足够表意，不该判成缺失。
    """
    req = CONTEXT_REQUIRED.get(key)
    if not req:
        return True
    if any(w.lower() in line_low for w in req):
        return True
    if doc_low and any(w.lower() in doc_low for w in req):
        return True
    return False


def canonical_hits(
    text: str, dims: dict[str, dict] | None = None, doc: str = ""
) -> dict[str, list[str]]:
    """返回 text 中命中的能力 key 及其命中的原始词。

    默认用全量词表（AI + 通用 + 各岗位族），因此非 AI 岗位也能命中。

    过泛词按**语境**判定：`CONTEXT_REQUIRED` 里列的能力项，
    泛词只有在同行（或整篇文档 `doc`）伴随语境词时才算命中——
    避免"服务质量"被当成工程能力、"证照"被当成档案管理。

    `doc` 传全文时，语境判定会放宽到整篇；
    只传单行时则严格按同行判定（更保守，适合逐行认领）。
    """
    table = dims if dims is not None else ALL_DIMS
    low = text.lower()
    doc_low = doc.lower() if doc else low
    hits: dict[str, list[str]] = {}
    for key, spec in table.items():
        found: list[str] = []
        for kw in spec["kw"]:
            if kw.lower() not in low:
                continue
            if CONTEXT_REQUIRED.get(key) and not _context_ok(key, low, doc_low):
                continue
            found.append(kw)
        if found:
            hits[key] = found
    return hits
