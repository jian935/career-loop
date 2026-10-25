# -*- coding: utf-8 -*-
"""《中华人民共和国职业分类大典》中类 → career-loop 岗位族的映射与覆盖面对账。

用途
----
1. 让「覆盖面」有外部权威骨架可对账：不是一个人数说自己覆盖了多少行业，
   而是能对到大典的 8 个大类、**带编号的中类**，并逐个说清"有词表 / 没词表"。
2. `scan` / `match` 报告里可以输出岗位所属的职业大类，便于跨行业比较。

诚实边界（重要，改这个文件前请先读）
------------------------------------
- **映射是启发式的**，不是大典原文数据。中类编号与名称整理自公开的大典目录
  （大类 1~8；中类 1-01…8-00，共 79 个），本文件**不声称**与官方出版物逐条一致，
  也不保证每个中类的语义边界与官方定义完全重合。
- **"建立了词表"的判定很松**：只要该中类的事实 tables 里有能命中此行业的
  career-loop 岗位族就算支持。它回答的是"这个行业我能读出东西吗"，
  不等于"我把它做透了"（见 `note` 字段标出的部分支持）。
- 大类 7（军人）不在求职匹配场景内，**保留占位、不自欺地把词表填上**。

为什么这个文件的口径在 v0.8.26 重写过
--------------------------------------
旧版只整理了 39 个中类，且**全都有词表**，于是算出来就是 100% + 49%：
100% 的分母是我自己挑的那 39 个，49% 是 39/79。两个数都对，但都没回答问题：
读者真正想知道的是"大典里那么多行业，你到底能对付多少个"。

新版把中类**按编号整理进来**（不再挑挑拣拣），于是：
- `coverage`（头条）= 有词表支撑的中类 ÷ 79；
- `completeness` = 有词表支撑的 ÷ 本文件整理出来的；
- `enumeration_rate` = 本文件整理出的 ÷ 79（我这本目录抄全了没有）。

分母不再是自己定的，数字才会变小、也才真的有意义。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# 《职业分类大典（2022 年版）》公开表述中的中类总数（8 大类 / 79 中类 / 449 小类）。
# 这是**固定分母**，不由本仓库决定，用来算 `coverage`。
MIDS_IN_DICTIONARY_2022 = 79


@dataclass
class CategoryHit:
    code: str                       # 大类编号，如 "2"
    label: str                      # 大类名称，如 "专业技术人员"
    packs: list[str] = field(default_factory=list)   # 命中的 career_loop 岗位族
    matched: list[str] = field(default_factory=list)  # 命中的中类名称
    confidence: float = 0.0         # 0~1，命中中类数 / 该大类中类数的粗略比例


# 大类 → 中类。**中类名称与编号整理自公开的大典目录**（见模块 docstring 的边界说明）。
#
# 每条：
#   code  —— 中类编号（如 "2-04"）
#   name  —— 中类名称
#   kw    —— 触发词（启发式，命中即认为该 JD 属于这个中类）
#   packs —— 可用的 career-loop 岗位族；**空列表 = 承认没有词表**（会计入 gaps）
#   note  —— 可选，写清保守的地方（如"仅支持其中一半"）
OCCUPATION_TREE: dict[str, dict] = {
    "1": {
        "label": "党的机关、国家机关、群众团体和社会组织、企事业单位负责人",
        "mids": [
            {"code": "1-01", "name": "中国共产党机关负责人",
             "kw": ["党委书记", "党支部书记", "党务"], "packs": []},
            {"code": "1-02", "name": "国家机关负责人",
             "kw": ["国家机关负责人", "行政负责人", "局长", "厅长"], "packs": []},
            {"code": "1-03", "name": "民主党派和工商联负责人",
             "kw": ["民主党派", "工商联"], "packs": []},
            {"code": "1-04", "name": "人民团体和群众团体、社会组织及其他成员组织负责人",
             "kw": ["协会", "秘书长", "公益组织", "基金会", "社团"], "packs": ["social", "public_admin"]},
            {"code": "1-05", "name": "基层群众自治组织负责人",
             "kw": ["村委会", "居委会", "社区书记", "基层自治"], "packs": ["public_admin"]},
            {"code": "1-06", "name": "企事业单位负责人",
             "kw": ["总经理", "ceo", "创始人", "负责人", "事业部负责人", "院长", "校长", "所长"],
             "packs": ["project_mgmt", "consulting", "public_admin", "education"]},
        ],
    },
    "2": {
        "label": "专业技术人员",
        "mids": [
            {"code": "2-01", "name": "科学研究人员",
             "kw": ["课题", "实验室", "科研", "论文", "sci", "博士后"], "packs": ["research"]},
            {"code": "2-02", "name": "工程技术人员",
             "kw": ["工艺", "产线", "结构设计", "仿真", "施工图", "plc", "原理图", "技术交底"],
             "packs": ["mechanical", "electrical", "construction"]},
            {"code": "2-03", "name": "农业技术人员",
             "kw": ["种植", "育种", "农艺", "养殖", "防疫", "植保"], "packs": ["agriculture"]},
            {"code": "2-04", "name": "飞机和船舶技术人员",
             "kw": ["船舶", "轮机", "船务", "航运", "海运", "海事", "船级社", "坞修"],
             "packs": ["maritime"],
             "note": "大典这一中类同时含飞机与船舶；本仓库只建了**船舶**方向的词表，航空方向仍缺失"},
            {"code": "2-05", "name": "卫生专业技术人员",
             "kw": ["临床", "护理", "诊断", "药学", "病历", "医师"], "packs": ["healthcare"]},
            {"code": "2-06", "name": "经济和金融专业人员",
             "kw": ["会计", "报表", "审计", "税务", "授信", "核保", "行研", "估值建模"],
             "packs": ["finance", "banking", "insurance", "securities", "asset_valuation"]},
            {"code": "2-07", "name": "监察、法律、社会和宗教专业人员",
             "kw": ["法务", "诉讼", "知识产权", "心理咨询", "社工", "监察"], "packs": ["legal", "psychology", "social"]},
            {"code": "2-08", "name": "教学人员",
             "kw": ["教学", "授课", "备课", "教研", "班主任"], "packs": ["education"]},
            {"code": "2-09", "name": "文学艺术、体育专业人员",
             "kw": ["编导", "拍摄", "剪辑", "翻译", "教练", "运动员"], "packs": ["film", "translation", "sports"]},
            {"code": "2-10", "name": "新闻出版、文化专业人员",
             "kw": ["编辑", "校对", "稿件", "媒体关系", "新闻稿"], "packs": ["media"]},
            # 注意：大典把「信息传输、软件和信息技术服务人员」放在**大类 4（4-04）**，
            # 不在专业技术人员这边的目录里（这里只有 2-01…2-10 与 2-99）。
            # 早期的版本自己给它编了个号塞在大类 2，属于编造编号，已纠正。
            {"code": "2-99", "name": "其他专业技术人员", "kw": [], "packs": []},
        ],
    },
    "3": {
        "label": "办事人员和有关人员",
        "mids": [
            {"code": "3-01", "name": "行政办事及辅助人员",
             "kw": ["行政", "办公用品", "固定资产", "档案", "会议组织", "文秘", "速记", "纪要"],
             "packs": ["admin"]},
            {"code": "3-02", "name": "安全和消防及辅助人员",
             "kw": ["消防", "安防", "安保", "安全检查", "消控"], "packs": ["property"]},
            {"code": "3-03", "name": "法律事务及辅助人员",
             "kw": ["法律事务", "法务助理", "合规审查", "诉讼辅助", "仲裁"], "packs": ["legal"]},
            {"code": "3-99", "name": "其他办事人员和有关人员",
             "kw": ["窗口服务", "办事大厅", "综合柜员"], "packs": ["service", "public_admin"]},
        ],
    },
    "4": {
        "label": "社会生产服务和生活服务人员",
        "mids": [
            {"code": "4-01", "name": "批发与零售服务人员",
             "kw": ["门店", "导购", "零售", "批发", "客户开发", "拓客", "bd", "大客户"],
             "packs": ["sales", "retail"]},
            {"code": "4-02", "name": "交通运输、仓储物流和邮政业服务人员",
             "kw": ["仓储", "拣货", "配送", "运输", "关务", "货代", "快递"], "packs": ["logistics", "supply"]},
            {"code": "4-03", "name": "住宿和餐饮服务人员",
             "kw": ["酒店", "客房", "后厨", "前厅", "餐饮"], "packs": ["tourism", "catering"]},
            {"code": "4-04", "name": "信息传输、软件和信息技术服务人员",
             "kw": ["信息系统实施", "呼叫中心", "it服务", "企业信息化"], "packs": ["it_systems", "devops"]},
            {"code": "4-05", "name": "金融服务人员",
             "kw": ["柜面", "网点", "信贷", "理财顾问", "承保", "理赔"], "packs": ["banking", "insurance", "securities"]},
            {"code": "4-06", "name": "房地产服务人员",
             "kw": ["楼盘", "租赁", "房地产", "物业客服"], "packs": ["property"]},
            {"code": "4-07", "name": "租赁和商务服务人员",
             "kw": ["租赁", "商务服务", "商业分析", "咨询交付"], "packs": ["consulting", "asset_valuation"]},
            {"code": "4-08", "name": "技术辅助服务人员",
             "kw": ["检验检测", "计量校准", "测绘", "第三方检测"], "packs": ["quality"]},
            {"code": "4-09", "name": "水利、环境和公共设施管理服务人员",
             "kw": ["环保", "环评", "环境监测", "废水处理", "危废", "碳排放", "ehs", "职业健康"],
             "packs": ["environment"]},
            {"code": "4-10", "name": "居民服务人员",
             "kw": ["家政", "美容", "理发", "维修服务", "保洁"], "packs": ["domestic"]},
            {"code": "4-11", "name": "电力、燃气及水供应服务人员",
             "kw": ["电力", "电网", "变电站", "燃气", "供水"], "packs": ["energy"]},
            {"code": "4-12", "name": "修理及制作服务人员",
             "kw": ["维修保养", "家电维修", "设备维修", "售后维修"], "packs": ["domestic", "transport_ops"]},
            {"code": "4-13", "name": "文化、体育和娱乐服务人员",
             "kw": ["导游", "讲解", "健身", "私教", "娱乐"], "packs": ["tourism_cn", "sports", "film"]},
            {"code": "4-14", "name": "健康服务人员",
             "kw": ["养老", "康复", "护理员", "社工", "健康管理"], "packs": ["social", "healthcare"]},
            {"code": "4-99", "name": "其他社会生产和生活服务人员",
             "kw": [], "packs": []},
        ],
    },
    "5": {
        "label": "农、林、牧、渔业生产及辅助人员",
        "mids": [
            {"code": "5-01", "name": "农业生产人员",
             "kw": ["种植", "栽培", "灌溉", "农机", "大棚"], "packs": ["agriculture"]},
            {"code": "5-02", "name": "林业生产人员",
             "kw": ["造林", "森林", "林地", "草原", "林业"], "packs": ["agriculture"]},
            {"code": "5-03", "name": "畜牧业生产人员",
             "kw": ["养殖", "饲养", "畜群", "兽医", "猪场", "鸡场"], "packs": ["agriculture"]},
            {"code": "5-04", "name": "渔业生产人员",
             "kw": ["捕捞", "水产", "养殖水面", "渔船"], "packs": ["agriculture"]},
            {"code": "5-05", "name": "农、林、牧、渔业生产辅助人员",
             "kw": ["农资", "农产品收购", "农业基地"], "packs": ["agriculture", "supply"]},
            {"code": "5-99", "name": "其他农、林、牧、渔业生产辅助人员", "kw": [], "packs": []},
        ],
    },
    "6": {
        "label": "生产制造及有关人员",
        "mids": [
            {"code": "6-01", "name": "农副产品加工人员",
             "kw": ["食品加工", "屠宰", "粮油加工", "乳制品"], "packs": ["catering"]},
            {"code": "6-02", "name": "食品、饮料生产加工人员",
             "kw": ["灌装", "烘焙", "饮料生产", "食品安全", "配方工艺"], "packs": ["catering"]},
            {"code": "6-03", "name": "烟草及其制品加工人员",
             "kw": ["卷烟", "烟草加工"], "packs": []},
            {"code": "6-04", "name": "纺织、针织、印染人员",
             "kw": ["纺织", "印染", "针织", "织造", "面料"], "packs": ["manufacturing"]},
            {"code": "6-05", "name": "纺织品、服装和皮革、毛皮制品加工制作人员",
             "kw": ["成衣", "服装设计", "皮革", "裁剪"], "packs": ["manufacturing"]},
            {"code": "6-06", "name": "木材加工、家具与木制品制作人员",
             "kw": ["木材加工", "家具制造", "人造板"], "packs": []},
            {"code": "6-07", "name": "纸及纸制品生产加工人员",
             "kw": ["造纸", "纸制品", "制浆"], "packs": []},
            {"code": "6-08", "name": "印刷和记录媒介复制人员",
             "kw": ["印刷", "胶印", "印前", "模切", "彩盒"], "packs": []},
            {"code": "6-09", "name": "文教、工美、体育和娱乐用品制造人员",
             "kw": ["文具制造", "工艺品制作", "乐器制作"], "packs": []},
            {"code": "6-10", "name": "石油加工和炼焦、煤化工生产人员",
             "kw": ["炼油", "炼焦", "煤化工", "催化裂化"], "packs": ["energy"]},
            {"code": "6-11", "name": "化学原料和化学制品制造人员",
             "kw": ["化工", "反应釜", "危化品", "配料", "聚合"], "packs": ["energy"]},
            {"code": "6-12", "name": "医药制造人员",
             "kw": ["药品生产", "gmp", "无菌制剂", "原料药"], "packs": ["healthcare"]},
            {"code": "6-13", "name": "化学纤维制造人员",
             "kw": ["化纤", "涤纶", "纺丝"], "packs": ["manufacturing"]},
            {"code": "6-14", "name": "橡胶和塑料制品制造人员",
             "kw": ["橡胶", "注塑", "塑料制品", "挤出"], "packs": ["manufacturing"]},
            {"code": "6-15", "name": "非金属矿物制品制造人员",
             "kw": ["水泥", "玻璃", "陶瓷", "耐火材料"], "packs": ["manufacturing"]},
            {"code": "6-16", "name": "采矿人员",
             "kw": ["矿山", "采矿", "选矿", "矿井", "采掘", "矿石"], "packs": ["mining"]},
            {"code": "6-17", "name": "金属冶炼和压延加工人员",
             "kw": ["冶炼", "轧制", "炼钢", "熔炼", "连铸"], "packs": ["manufacturing"]},
            {"code": "6-18", "name": "机械制造基础加工人员",
             "kw": ["钣金", "焊接", "机加工", "数控", "车铣"], "packs": ["mechanical", "manufacturing"]},
            {"code": "6-19", "name": "金属制品制造人员",
             "kw": ["金属制品", "冲压", "紧固件", "热处理"], "packs": ["mechanical", "manufacturing"]},
            {"code": "6-20", "name": "通用设备制造人员",
             "kw": ["通用设备", "泵阀", "压缩机", "减速机"], "packs": ["mechanical", "manufacturing"]},
            {"code": "6-21", "name": "专用设备制造人员",
             "kw": ["专用设备", "非标设备", "生产线装备"], "packs": ["mechanical", "manufacturing"]},
            {"code": "6-22", "name": "汽车制造人员",
             "kw": ["整车", "零部件", "车身", "底盘", "总装", "三电"], "packs": ["automotive"]},
            {"code": "6-23", "name": "铁路、船舶、航空设备制造人员",
             "kw": ["造船", "船体", "船厂", "轨道交通装备"], "packs": ["maritime"],
             "note": "覆盖造船/船体方向；铁路与航空方向暂无词表"},
            {"code": "6-24", "name": "电气机械和器材制造人员",
             "kw": ["电机", "变压器", "配电柜", "线束", "pcb"], "packs": ["electrical", "embedded"]},
            {"code": "6-25", "name": "计算机、通信和其他电子设备制造人员",
             "kw": ["smt", "电子装配", "pcba", "通信设备", "模组"], "packs": ["embedded", "quality"]},
            {"code": "6-26", "name": "仪器仪表制造人员",
             "kw": ["仪器仪表", "传感器标定", "计量器具"], "packs": ["mechanical", "quality"]},
            {"code": "6-27", "name": "再生资源综合利用人员",
             "kw": ["再生资源", "固废", "资源综合利用", "报废回收"], "packs": ["environment"]},
            {"code": "6-28", "name": "电力、热力、气体、水生产和输配人员",
             "kw": ["发电", "热力", "供气", "污水处理厂", "管网巡检"], "packs": ["energy"]},
            {"code": "6-29", "name": "建筑施工人员",
             "kw": ["施工现场", "施工员", "安全员", "脚手架", "土建", "竣工验收", "建造师"],
             "packs": ["construction"]},
            {"code": "6-30", "name": "运输设备和通用工程机械操作人员及有关人员",
             "kw": ["驾驶", "叉车", "起重机", "操作员", "司机"], "packs": ["transport_ops"]},
            {"code": "6-31", "name": "生产辅助人员",
             "kw": ["排产", "生产计划", "物料", "交期"], "packs": ["supply"]},
            {"code": "6-99", "name": "其他生产制造及有关人员", "kw": [], "packs": []},
        ],
    },
    "7": {
        "label": "军人",
        "mids": [
            {"code": "7-00", "name": "军人", "kw": [], "packs": [],
             "note": "不在求职匹配场景内，刻意不建词表"},
        ],
    },
    "8": {
        "label": "不便分类的其他从业人员",
        "mids": [
            {"code": "8-00", "name": "不便分类的其他从业人员", "kw": [], "packs": []},
        ],
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
        for mid in node["mids"]:
            c = _hit_count(low, mid["kw"])
            if c:
                matched.append(mid["name"])
                for p in mid["packs"]:
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
    for mid in OCCUPATION_TREE.get(code, {}).get("mids", []):
        for p in mid["packs"]:
            if p not in out:
                out.append(p)
    return out


def mids_of(code: str) -> list[dict]:
    """某大类下的中类列表（含编号、是否已有词表）。"""
    return list(OCCUPATION_TREE.get(code, {}).get("mids", []))


def coverage_matrix() -> list[dict]:
    """对账用：每个职业大类有多少中类、其中多少已经有词表支撑。"""
    rows: list[dict] = []
    for code, node in OCCUPATION_TREE.items():
        mids = node["mids"]
        mapped = [m for m in mids if m["packs"]]
        rows.append({
            "code": code,
            "label": node["label"],
            "mid_total": len(mids),
            "mid_mapped": len(mapped),
            "packs": packs_of(code),
            # 没词表的中类（含编号），这就是"空白在哪"
            "gaps": [f"{m['code']} {m['name']}" for m in mids if not m["packs"]],
            "supported": [m["code"] for m in mapped],
        })
    return rows


def coverage_summary() -> dict:
    """三种口径，**必须一起给**，单独给任何一个都会误导。

    - `coverage`（头条）= 有词表支撑的中类 ÷ **大典全部中类（79）**。
      分母是外部权威给的，不是我自己挑的——这才是回答"能对付多少行业"的数。
    - `completeness` = 有词表支撑的 ÷ 本文件整理出来的中类。
      它回答的是"我抄进来的这份目录里还剩多少空白"。
    - `enumeration_rate` = 本文件整理出的中类 ÷ 79。
      小于 1 说明**连目录都没抄全**，这是在坦白我自己的清单也不完整。

    历史教训（别回退）：旧版只整理 39 个中类并且都有词表，于是算出
    100%（分母是自己挑的 39）与 49%（39/79）。两个数都对，但都没回答读者的
    问题——因为分母是我挑的。**分母不能自己定。**
    """
    rows = coverage_matrix()
    enumerated = sum(r["mid_total"] for r in rows)
    supported = sum(r["mid_mapped"] for r in rows)
    return {
        "enumerated": enumerated,
        "supported": supported,
        "dictionary_total": MIDS_IN_DICTIONARY_2022,
        "big_classes": len(rows),
        "completeness": supported / enumerated if enumerated else 0.0,
        "coverage": supported / MIDS_IN_DICTIONARY_2022,
        "enumeration_rate": enumerated / MIDS_IN_DICTIONARY_2022,
        "gaps": [g for r in rows for g in r["gaps"]],
        # 旧口径的别名，留给还没改口的调用方（网页 summary 里同步的是真名）
        "listed_total": enumerated,
        "listed_mapped": supported,
        "breadth": supported / MIDS_IN_DICTIONARY_2022,
    }


def render_coverage() -> str:
    """生成对账表（Markdown）。

    表头那个「已建词表/整理到」是 `completeness` 口径（分母是我整理的目录），
    表下的三个数字才是对外的真实口径，所以**必须**把 79 和 coverage 印在同一屏，
    有单测锁着（改文案也别把分母删了）。
    """
    s = coverage_summary()
    lines = [
        "| 大类 | 名称 | 已建词表/整理到 | 覆盖到的岗位族 | 尚无词表的中类 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in coverage_matrix():
        packs = "、".join(r["packs"]) or "—"
        gaps = "、".join(r["gaps"]) or "—"
        lines.append(f"| {r['code']} | {r['label']} | {r['mid_mapped']}/{r['mid_total']} "
                     f"| {packs} | {gaps} |")
    lines += [
        "",
        f"- **词表覆盖（头条）**：{s['supported']}/{s['dictionary_total']} = "
        f"{s['coverage']:.0%} —— **分母是大典全部 {s['dictionary_total']} 个中类**，不是我自己挑的。",
        f"- 完整度（分母＝本文件整理到的 {s['enumerated']} 个中类）："
        f"{s['supported']}/{s['enumerated']} = {s['completeness']:.0%}。",
        f"- 目录整理度：{s['enumerated']}/{s['dictionary_total']} = "
        f"{s['enumeration_rate']:.0%} —— 小于 100% 是在坦白**这份中类清单本身也没抄全**。",
        "",
        "> 映射是**启发式**的，不是官方逐条数据；「已建词表」只表示能读出东西，"
        "不代表做透了（部分中类只覆盖其中一个方向，见源码里的 note）。"
        "大类 7（军人）刻意不建词表。",
    ]
    return "\n".join(lines)
