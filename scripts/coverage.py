# -*- coding: utf-8 -*-
"""岗位覆盖度体检：AI 各细分 + 工商管理大类，量化抽取召回与兜底比例。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from career_loop import matching
from career_loop.matching.extract import _looks_like_requirement

CASES = [
    # ---------- AI 类 ----------
    ("AI", "AI 产品经理", "ai", ["大模型", "提示词", "RAG", "数据分析", "评估"], """
AI 产品经理（大模型方向）
岗位职责
- 负责大模型产品的需求设计与落地
- 搭建效果评估体系，用数据分析驱动迭代
任职要求
1. 熟悉大模型原理与边界，会做提示词工程
2. 有 RAG 或 Agent 项目经验
3. 能用 SQL 和看板做数据分析
"""),
    ("AI", "Agent 应用开发", "ai", ["Agent", "函数调用", "RAG", "Python", "部署"], """
Agent 应用开发工程师
岗位要求
1. 精通 Agent 框架，做过多智能体编排
2. 掌握函数调用 / 工具调用，重视参数校验
3. 有 RAG 经验，关注召回与重排
4. 用 Python 写过后端，能 Docker 部署
"""),
    ("AI", "RAG 工程师", "ai", ["RAG", "向量", "召回", "知识库", "评测"], """
RAG 工程师
任职要求
1. 熟悉向量检索与 embedding，能优化召回率
2. 有知识库构建经验，处理过文档切分
3. 能做检索效果评测，报 Recall 与幻觉率
"""),
    ("AI", "Prompt 工程师", "ai", ["提示词", "评测", "A/B", "大模型"], """
Prompt 工程师
岗位职责
- 设计并迭代大模型提示词，提升任务准确率
任职要求
1. 熟悉提示词工程与系统提示设计
2. 能做 A/B 测试和效果评测
3. 了解大模型的能力边界
"""),
    ("AI", "NLP 算法工程师", "ai", ["NLP", "Transformer", "微调", "PyTorch"], """
NLP 算法工程师
任职要求
1. 熟悉 NLP 常见任务，理解 Transformer 结构
2. 有 PyTorch 训练与微调经验
3. 能读论文并复现实验
"""),
    ("AI", "CV 算法工程师", "ai", ["图像", "目标检测", "分割", "OpenCV"], """
CV 算法工程师
任职要求
1. 熟悉图像分类、目标检测与语义分割
2. 熟练使用 OpenCV 与深度学习框架
3. 有模型压缩和推理加速经验
"""),
    ("AI", "推荐算法工程师", "ai", ["推荐", "召回", "排序", "特征工程"], """
推荐算法工程师
任职要求
1. 熟悉推荐系统召回与排序链路
2. 有特征工程和模型调优经验
3. 能用 SQL 做数据分析
"""),
    ("AI", "MLOps 工程师", "ai", ["模型部署", "推理", "监控", "Kubernetes"], """
MLOps 工程师
任职要求
1. 负责模型部署与推理服务，保障稳定性
2. 搭建模型监控与告警体系
3. 熟悉 Kubernetes 与 CI/CD
"""),
    ("AI", "AI 解决方案/售前", "ai", ["方案", "客户", "POC", "演示"], """
AI 解决方案顾问
岗位职责
- 面向客户设计 AI 解决方案，输出方案文档
- 支持售前 POC 与产品演示
任职要求
1. 具备较强的沟通与方案表达能力
2. 了解大模型应用与 Agent 场景
3. 能独立对接客户需求
"""),
    ("AI", "AI 运营/训练师", "ai", ["数据标注", "评测", "badcase", "运营"], """
AI 训练师 / 运营
岗位职责
- 负责数据标注与评测集建设，分析 badcase
任职要求
1. 细心耐心，能制定标注规范
2. 会做效果评测与问题归因
3. 有用户运营或内容运营经验
"""),

    # ---------- 工商管理大类 ----------
    ("工商管理", "市场营销", "marketing", ["品牌", "投放", "内容", "ROI", "转化率"], """
市场营销经理
岗位职责
- 负责品牌传播与内容营销，管理投放预算
任职要求
1. 有信息流投放经验，能优化 ROI
2. 熟悉小红书 / 抖音内容运营
3. 能用数据复盘转化率与留存
"""),
    ("工商管理", "销售/大客户", "sales", ["客户开发", "谈判", "CRM", "业绩"], """
大客户销售
岗位职责
- 负责区域客户开发与维护，完成销售业绩
任职要求
1. 有较强的沟通谈判能力，能独立签约
2. 熟悉 CRM 系统，有 B2B 销售经验
3. 能接受出差
"""),
    ("工商管理", "会计", "finance", ["凭证", "报表", "纳税申报", "金蝶"], """
财务会计
岗位职责
- 负责日常账务处理，编制会计凭证与总账
- 编制月度财务报表，参与预算编制
任职要求
1. 熟悉国家税务政策，能独立完成纳税申报
2. 熟练使用用友、金蝶等财务软件
3. 有中级会计职称优先
"""),
    ("工商管理", "财务分析 FP&A", "finance", ["预算", "财务分析", "经营分析", "预测"], """
财务分析（FP&A）
任职要求
1. 负责年度预算编制与滚动预测
2. 能做财务分析和经营分析报告
3. 熟练使用 Excel 与 BI 工具
4. 有业财融合经验优先
"""),
    ("工商管理", "审计", "finance", ["审计", "内控", "底稿", "风险"], """
审计专员
任职要求
1. 熟悉审计流程，能独立编制审计底稿
2. 了解内控与风险管理
3. 有 CPA 或会计师事务所经验优先
"""),
    ("工商管理", "人力资源", "hr", ["招聘", "绩效", "薪酬", "员工关系"], """
人力资源专员
任职要求
1. 负责招聘全流程，能独立面试
2. 熟悉绩效与薪酬体系
3. 有员工关系处理经验
"""),
    ("工商管理", "行政管理", "admin", ["行政", "办公", "会议", "采购"], """
行政专员
岗位职责
- 负责办公用品采购与固定资产管理
- 组织会议与员工活动
任职要求
1. 熟练使用 Office，做事细致
2. 有行政后勤经验优先
"""),
    ("工商管理", "供应链/物流", "supply", ["采购", "库存", "物流", "供应商"], """
供应链专员
任职要求
1. 负责采购下单与供应商管理
2. 熟悉库存周转与仓储物流
3. 能用 Excel 做数据分析
"""),
    ("工商管理", "电商运营", "ecommerce", ["店铺", "GMV", "转化率", "活动"], """
电商运营
岗位职责
- 负责店铺日常运营与活动策划
任职要求
1. 熟悉天猫 / 抖音店铺运营
2. 能拆解 GMV 并优化转化率
3. 有直播或内容运营经验优先
"""),
    ("工商管理", "旅游/酒店管理", "tourism", ["酒店", "前台", "预订", "客户"], """
酒店前台主管
岗位职责
- 负责前台接待与客房预订管理
任职要求
1. 有酒店前台工作经验
2. 具备良好的客户服务意识
3. 能处理客户投诉与突发事件
"""),
    ("工商管理", "信息管理/IT 实施", "it_systems", ["系统", "数据库", "需求", "实施"], """
信息系统实施顾问
任职要求
1. 负责 ERP 系统的实施与配置
2. 能做需求调研与方案设计
3. 熟悉 SQL 与数据库
"""),
    ("工商管理", "项目管理", "project_mgmt", ["项目计划", "进度", "风险", "验收"], """
项目经理
任职要求
1. 负责项目计划制定与进度管控
2. 能识别项目风险并推动解决
3. 有跨部门协作与验收经验
4. 有 PMP 证书优先
"""),
    ("工商管理", "国际贸易", "trade", ["外贸", "报关", "海外客户", "英语"], """
外贸业务员
任职要求
1. 熟悉外贸流程与报关单据
2. 能独立开发海外客户
3. 英语可作为工作语言
"""),
    ("AI", "语音算法", "ai_speech", ["语音识别", "ASR", "TTS", "声学"], """
语音算法工程师
任职要求
1. 熟悉语音识别 ASR，做过声学模型
2. 有语音合成 TTS 经验
3. 了解唤醒词与降噪
"""),
    ("AI", "多模态算法", "ai_multimodal", ["多模态", "图文", "CLIP", "VLM"], """
多模态算法工程师
任职要求
1. 研究图文多模态与视觉语言模型
2. 了解 CLIP 与跨模态检索
3. 有 VLM 训练经验
"""),
    ("AI", "具身智能", "ai_robotics", ["机器人", "运动控制", "SLAM", "ROS"], """
具身智能算法工程师
任职要求
1. 负责机器人运动控制与 SLAM
2. 熟悉 ROS 与机械臂控制
3. 有强化学习经验
"""),
    ("AI", "数据工程", "ai_data", ["数据清洗", "ETL", "数仓", "数据治理"], """
数据工程师
任职要求
1. 负责数据清洗与 ETL 管道
2. 搭建数仓与特征平台
3. 熟悉数据治理
"""),
    ("AI", "AI 测试", "ai_testing", ["模型测试", "效果测试", "评测方案", "质量"], """
AI 测试工程师
任职要求
1. 负责模型测试与效果测试
2. 制定评测方案，保障交付质量
3. 有自动化测试经验
"""),
    ("工商管理", "物业/房地产", "property", ["物业", "楼盘", "业主", "招商"], """
物业项目经理
任职要求
1. 负责楼盘物业管理与业主服务
2. 有招商租赁经验
3. 能处理突发事件
"""),
    ("工商管理", "工程管理/造价", "construction", ["施工", "工程造价", "招投标", "BIM"], """
工程管理 / 造价
任职要求
1. 负责施工进度与工程管理
2. 能编制工程造价与招投标文件
3. 了解 BIM 与监理流程
"""),
]


def line_coverage(jd):
    """JD 里看起来是要求的行，有多少被抽成了 requirement。"""
    from career_loop.matching.extract import _split_sections
    req_lines = [ln for _, ln in _split_sections(jd) if _looks_like_requirement(ln)]
    return len(req_lines)


def main():
    rows = []
    for cat, name, dom_exp, expected, jd in CASES:
        reqs, _ = matching.extract_requirements(jd)
        doms = matching.detect_domains(jd)
        canon = [r for r in reqs if not r.key.startswith("custom:")]
        custom = [r for r in reqs if r.key.startswith("custom:")]
        from career_loop.matching.schema import canonical_hits
        quotes = {r.quote.strip() for r in reqs}
        req_keys = {r.key for r in reqs}
        def covered(term):
            for raw in jd.splitlines():
                line = raw.strip()
                if term.lower() in line.lower():
                    if line[:120] in quotes or any(line[:120] in q for q in quotes):
                        return True
                    if any(k in req_keys for k in canonical_hits(line)):
                        return True
            return False
        hit = [t for t in expected if covered(t)]
        miss = [t for t in expected if not covered(t)]
        n_lines = line_coverage(jd)
        rows.append({
            "cat": cat, "name": name, "dom_exp": dom_exp, "doms": doms,
            "n_req": len(reqs), "n_canon": len(canon), "n_custom": len(custom),
            "n_lines": n_lines, "recall": f"{len(hit)}/{len(expected)}",
            "recall_v": len(hit) / len(expected), "miss": miss,
        })

    print(f"{'类':<6}{'岗位':<18}{'族(期望/实际)':<20}{'要求':>4}{'标准':>4}{'兜底':>4}{'召回':>7}  漏掉")
    print("-" * 100)
    for r in rows:
        dom_ok = "OK" if r["dom_exp"] in r["doms"] else "MISS"
        dom = f"{r['dom_exp']}->{','.join(r['doms'][:2]) or '-'}[{dom_ok}]"
        print(f"{r['cat']:<6}{r['name']:<18}{dom:<20}{r['n_req']:>4}{r['n_canon']:>4}{r['n_custom']:>4}{r['recall']:>7}  {', '.join(r['miss']) or '-'}")

    print("-" * 100)
    for cat in ("AI", "工商管理"):
        sub = [r for r in rows if r["cat"] == cat]
        rec = sum(r["recall_v"] for r in sub) / len(sub)
        dom_ok = sum(1 for r in sub if r["dom_exp"] in r["doms"]) / len(sub)
        cust = sum(r["n_custom"] for r in sub) / max(1, sum(r["n_req"] for r in sub))
        print(f"{cat}: 平均召回 {rec:.0%} | 岗位族识别 {dom_ok:.0%} | 兜底占比 {cust:.0%}")
    print(f"总体平均召回 {sum(r['recall_v'] for r in rows)/len(rows):.0%}")


if __name__ == "__main__":
    main()
