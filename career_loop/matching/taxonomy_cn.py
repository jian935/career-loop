# -*- coding: utf-8 -*-
"""《中华人民共和国职业分类大典》大类 → career-loop 岗位族的启发式映射。

用途
----
1. 让「覆盖面」有外部权威骨架可对账：不是我们说自己覆盖了多少行业，
   而是能对到职业分类大典的 8 个大类、哪些中类已经有词表、哪些还是空白。
2. `scan` / `match` 报告里可以输出岗位所属的职业大类，便于跨行业比较。

诚实边界
--------
- 这是**启发式映射**，不是大典原文数据。中类名称参考 2022 年版公开表述，
  具体中类编号以官方出版物为准，本文件不声称逐条对齐。
- 映射靠关键词命中，命中不到就返回「未分类」，不做强行归类。
- 大类 7（军人）不在求职匹配场景内，保留占位但不建词表。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CategoryHit:
    code: str                       # 大类编号，如 "2"
    label: str                      # 大类名称，如 "专业技术人员"
    packs: list[str] = field(default_factory=list)   # 命中的 career_loop 岗位族
    matched: list[str] = field(default_factory=list)  # 命中的中类名称
    confidence: float = 0.0         # 0~1，命中中类数 / 该大类中类数的粗略比例


# 大类 → 中类（启发式整理，非官方逐条数据）
# 每条：(中类名称, [触发词], [对应 career_loop 岗位族])
OCCUPATION_TREE: dict[str, dict] = {
    "1": {
        "label": "党的机关、国家机关、群众团体和社会组织、企事业单位负责人",
        "mids": [
            ("企业负责人", ["总经理", "ceo", "创始人", "负责人", "事业部负责人"], ["project_mgmt", "consulting"]),
            ("事业单位负责人", ["院长", "校长", "所长", "行政负责人"], ["public_admin", "education"]),
            ("社会组织负责人", ["协会", "秘书长", "公益组织", "基金会"], ["social", "public_admin"]),
        ],
    },
    "2": {
        "label": "专业技术人员",
        "mids": [
            ("工程技术人员", ["工艺", "产线", "结构设计", "仿真", "施工图", "plc", "原理图"], ["mechanical", "electrical", "construction"]),
            ("农业技术人员", ["种植", "育种", "农艺", "养殖", "防疫"], ["agriculture"]),
            ("科学研究人员", ["课题", "实验室", "科研", "论文", "sci"], ["research"]),
            ("卫生专业技术人员", ["临床", "护理", "诊断", "药学", "病历"], ["healthcare"]),
            ("经济和金融专业人员", ["会计", "报表", "审计", "税务", "授信", "核保", "行研", "估值建模"], ["finance", "banking", "insurance", "securities", "asset_valuation"]),
            ("法律、社会和宗教专业人员", ["法务", "诉讼", "知识产权", "心理咨询", "社工"], ["legal", "psychology", "social"]),
            ("教学人员", ["教学", "授课", "备课", "教研", "班主任"], ["education"]),
            ("文学艺术、体育专业人员", ["编导", "拍摄", "剪辑", "翻译", "教练", "运动员"], ["film", "translation", "sports"]),
            ("新闻出版、文化专业人员", ["编辑", "校对", "稿件", "媒体关系", "新闻稿"], ["media"]),
            ("信息传输、软件和信息技术服务人员", ["后端开发", "前端", "微服务", "自动化测试", "运维", "渗透", "嵌入式", "大模型", "算法"], ["backend", "frontend", "qa", "devops", "security", "embedded", "it_systems", "ai_nlp", "ai_cv", "ai_recsys", "ai_mlops", "ai_solution", "ai_ops", "ai_compliance", "ai_speech", "ai_multimodal", "ai_robotics", "ai_data", "ai_testing"]),
        ],
    },
    "3": {
        "label": "办事人员和有关人员",
        "mids": [
            ("行政办公人员", ["行政", "办公用品", "固定资产", "档案", "会议组织"], ["admin"]),
            ("文秘、打字员", ["文秘", "速记", "打字", "纪要"], ["admin"]),
            ("客户服务办事员", ["客服", "呼叫中心", "工单", "窗口", "办事"], ["service", "public_admin"]),
            ("安全和消防人员", ["消防", "安防", "安保", "安全检查"], ["property"]),
        ],
    },
    "4": {
        "label": "社会生产服务和生活服务人员",
        "mids": [
            ("销售人员", ["销售", "客户开发", "拓客", "bd", "大客户", "门店", "导购"], ["sales", "retail"]),
            ("仓储和邮政业人员", ["仓储", "拣货", "配送", "运输", "关务"], ["logistics", "supply"]),
            ("住宿和餐饮业人员", ["酒店", "客房", "餐饮", "后厨", "前厅"], ["tourism", "catering"]),
            ("房地产和物业服务人员", ["物业", "楼盘", "租赁", "房地产"], ["property"]),
            ("居民服务人员", ["家政", "美容", "理发", "维修服务"], ["domestic"]),
            ("电力、燃气及水供应服务人员", ["电力", "电网", "变电站", "燃气"], ["energy"]),
            ("运输设备和通用工程机械操作人员", ["驾驶", "叉车", "起重机", "操作员"], ["transport_ops"]),
            ("文化和教育、体育服务人员", ["导游", "讲解", "健身", "私教", "培训"], ["tourism_cn", "sports", "hr"]),
            ("健康、社会保障服务人员", ["养老", "康复", "护理员", "社工"], ["social", "healthcare"]),
        ],
    },
    "5": {
        "label": "农、林、牧、渔业生产及辅助人员",
        "mids": [
            ("农业生产人员", ["种植", "栽培", "灌溉", "农机"], ["agriculture"]),
            ("林业和草原生产人员", ["造林", "森林", "林地", "草原"], ["agriculture"]),
            ("畜牧业生产人员", ["养殖", "饲养", "畜群", "兽医"], ["agriculture"]),
            ("渔业生产人员", ["捕捞", "养殖水面", "水产"], ["agriculture"]),
        ],
    },
    "6": {
        "label": "生产制造及有关人员",
        "mids": [
            ("机械制造加工人员", ["钣金", "注塑", "焊接", "装配", "数控"], ["mechanical", "manufacturing"]),
            ("电气、电子元器件和电子设备制造人员", ["pcb", "电路板", "电子装配", "三电", "电芯"], ["embedded", "automotive", "energy"]),
            ("化工产品生产人员", ["化工", "反应釜", "危化品", "配料"], ["energy"]),
            ("金属冶炼和轧制人员", ["冶炼", "轧制", "炼钢", "熔炼"], ["manufacturing"]),
            ("纺织、针织和印染人员", ["纺织", "印染", "针织", "织造"], ["manufacturing"]),
            ("食品、饮料生产加工人员", ["食品加工", "灌装", "烘焙", "食品安全"], ["catering"]),
            ("汽车制造人员", ["整车", "零部件", "车身", "底盘", "总装"], ["automotive"]),
            ("质量检验和计量人员", ["来料检验", "体系认证", "六西格玛", "不良", "计量"], ["quality", "manufacturing"]),
            ("生产辅助人员", ["排产", "生产计划", "物料", "交期"], ["supply"]),
        ],
    },
    "7": {
        "label": "军人",
        "mids": [],
    },
    "8": {
        "label": "不便分类的其他从业人员",
        "mids": [],
    },
}


def _hit_count(text_low: str, kws: list[str]) -> int:
    return sum(1 for k in kws if k.lower() in text_low)


def classify(text: str) -> CategoryHit | None:
    """按文本（JD 或简历）粗判所属职业大类与中类。命中不到返回 None。

    注意：只做粗判，供报告展示与覆盖面对账，不参与打分。
    """
    low = text.lower()
    best: CategoryHit | None = None
    for code, node in OCCUPATION_TREE.items():
        packs: list[str] = []
        matched: list[str] = []
        for mid_name, kws, mid_packs in node["mids"]:
            c = _hit_count(low, kws)
            if c:
                matched.append(mid_name)
                for p in mid_packs:
                    if p not in packs:
                        packs.append(p)
        if not matched:
            continue
        conf = len(matched) / max(1, len(node["mids"]))
        hit = CategoryHit(code=code, label=node["label"], packs=packs,
                          matched=matched, confidence=conf)
        # 命中中类数优先，其次置信度
        if best is None or (len(matched), conf) > (len(best.matched), best.confidence):
            best = hit
    return best


def packs_of(code: str) -> list[str]:
    """某大类下所有映射到的 career_loop 岗位族。"""
    out: list[str] = []
    for _, _, mid_packs in OCCUPATION_TREE.get(code, {}).get("mids", []):
        for p in mid_packs:
            if p not in out:
                out.append(p)
    return out


def coverage_matrix() -> list[dict]:
    """对账用：每个职业大类有多少中类、其中多少已经映射到了词表岗位族。"""
    from .schema import DOMAIN_PACKS
    rows = []
    for code, node in OCCUPATION_TREE.items():
        mids = node["mids"]
        mapped = [m for m in mids if m[2]]
        packs = [p for p in packs_of(code) if p in DOMAIN_PACKS]
        rows.append({
            "code": code,
            "label": node["label"],
            "mid_total": len(mids),
            "mid_mapped": len(mapped),
            "packs": packs,
            "gaps": [m[0] for m in mids if not m[2]],
        })
    return rows


def render_coverage() -> str:
    """生成对账表（Markdown）。"""
    lines = ["| 大类 | 名称 | 中类(已映射/总数) | 已建词表岗位族 | 空白中类 |",
             "|---|---|---|---|---|"]
    for r in coverage_matrix():
        packs = "、".join(r["packs"]) or "—"
        gaps = "、".join(r["gaps"]) or "—"
        lines.append(f"| {r['code']} | {r['label']} | {r['mid_mapped']}/{r['mid_total']} | {packs} | {gaps} |")
    return "\n".join(lines)
