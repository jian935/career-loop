# -*- coding: utf-8 -*-
"""Generate benchmark/cases_v0.jsonl (10 JD x profile pairs, labels empty).

Run from the repo root:
    python benchmark/build_v0.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import matching  # noqa: E402

OUT = Path(__file__).resolve().parent / "cases_v0.jsonl"

CS = """某双一流高校 计算机科学与技术 本科，2027 届
- 用 Flask 写了后端，MySQL 存数据，Docker 部署到学生机
- 用 DeepSeek API 做了提示词工程，把课件整理成知识库
- 用 LangChain 搭了简单的检索问答，但没有做向量检索
- 没有做任何评测，也没统计有多少人用"""

ACC = """会计学本科，2026 届
- 做过代理记账实习，用金蝶做凭证录入和纳税申报
- 编制过资产负债表和利润表
- 参与过月度预算编制"""

SALES = """市场营销本科，2026 届
- 做过电话销售实习，开发过 50 个客户
- 用 CRM 记录跟进，月度业绩排名前三
- 独立签过 3 个小单"""

DESIGN = """视觉传达设计本科，2026 届
- 用 Figma 做过校园活动海报和公众号封面
- 独立完成过品牌 VI 设计
- 熟悉 PS、AI，了解排版规范"""

SUPPLY = """物流管理本科，2026 届
- 在电商仓做过实习，负责采购下单与供应商对接
- 用 Excel 做过库存周转分析
- 熟悉仓储物流流程"""

ECOM = """电子商务本科，2026 届
- 运营过校园店铺，做过活动策划
- 用数据拆解 GMV 与转化率
- 做过直播助理，写详情页文案"""

PM = """工程管理本科，2026 届
- 参与过校园工程项目，负责进度跟进
- 做过项目计划与风险清单
- 用 Excel 做里程碑跟踪"""

CASES = [
    ("match-ai-pm", "ai", """AI 产品经理（大模型方向）
岗位职责
- 负责大模型产品的需求设计与落地
- 搭建效果评估体系，用数据分析驱动迭代
任职要求
1. 熟悉大模型原理与边界，会做提示词工程
2. 有 RAG 或 Agent 项目经验
3. 能用 SQL 和看板做数据分析""", CS),
    ("match-agent", "ai", """Agent 应用开发工程师
岗位要求
1. 精通 Agent 框架，做过多智能体编排
2. 掌握函数调用 / 工具调用，重视参数校验
3. 有 RAG 经验，关注召回与重排
4. 用 Python 写过后端，能 Docker 部署""", CS),
    ("match-rag", "ai", """RAG 工程师
任职要求
1. 熟悉向量检索与 embedding，能优化召回率
2. 有知识库构建经验，处理过文档切分
3. 能做检索效果评测，报 Recall 与幻觉率""", CS),
    ("match-accounting", "finance", """财务会计
岗位职责
- 负责日常账务处理，编制会计凭证与总账
- 编制月度财务报表，参与预算编制
任职要求
1. 熟悉国家税务政策，能独立完成纳税申报
2. 熟练使用用友、金蝶等财务软件
3. 有中级会计职称优先""", ACC),
    ("match-sales", "sales", """大客户销售
岗位职责
- 负责区域客户开发与维护，完成销售业绩
任职要求
1. 有较强的沟通谈判能力，能独立签约
2. 熟悉 CRM 系统，有 B2B 销售经验
3. 能接受出差""", SALES),
    ("match-design", "design", """视觉设计师
任职要求
1. 熟练使用 Figma、PS，有品牌视觉设计经验
2. 具备良好的审美与排版能力
3. 能独立完成海报、banner 设计""", DESIGN),
    ("match-audit", "finance", """审计专员
任职要求
1. 熟悉审计流程，能独立编制审计底稿
2. 了解内控与风险管理
3. 有 CPA 或会计师事务所经验优先""", ACC),
    ("match-supply", "supply", """供应链专员
任职要求
1. 负责采购下单与供应商管理
2. 熟悉库存周转与仓储物流
3. 能用 Excel 做数据分析""", SUPPLY),
    ("match-ecom", "ecommerce", """电商运营
岗位职责
- 负责店铺日常运营与活动策划
任职要求
1. 熟悉天猫 / 抖音店铺运营
2. 能拆解 GMV 并优化转化率
3. 有直播或内容运营经验优先""", ECOM),
    ("match-pm", "project_mgmt", """项目经理
任职要求
1. 负责项目计划制定与进度管控
2. 能识别项目风险并推动解决
3. 有跨部门协作与验收经验
4. 有 PMP 证书优先""", PM),
]


def main() -> None:
    rows = []
    for cid, family, jd, profile in CASES:
        reqs, _ = matching.extract_requirements(jd)
        rows.append({
            "id": cid,
            "language": "zh",
            "job_family": family,
            "jd": jd.strip(),
            "profile": profile.strip(),
            "requirements": [
                {"key": r.key, "label": r.label, "weight": r.weight, "line": r.quote}
                for r in reqs
            ],
            "labels": {},
        })
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} cases -> {OUT}")


if __name__ == "__main__":
    main()
