# -*- coding: utf-8 -*-
"""中文真实 JD 族识别检验（公开数据集 china_job）。

数据来源：HuggingFace `ngtranai09/china_job`（8,674 条真实招聘 JD，猎聘/智联/实习僧
等来源），约 9.3MB parquet，含 job_title / job_description / job_location。

## 为什么需要这个检验
现有公开检验 `real_eval_family.py` 覆盖的是**英文** JD（族识别 93.6%）。
career-loop 的词表以**中文**为主——用英文数据检验中文能力，等于没测。
这个脚本用**公开中文 JD + 公开映射**，任何人可下载复现。

## 标签从哪来（重要）
数据集自带 `searched_job_title`（采集时的行业搜索词），但实测**噪声很高**：
搜 "Program Development" 返回的 30 条里只有 1 条岗位名含该行业词（3%），
搜 "Management Consulting" 也只有 14%。拿它当 ground truth 会得出错误结论。

所以本脚本改用**岗位名 `job_title`** 做标注：只在岗位名本身明确指向某个族时
才计入检验（TITLE_TO_FAMILY）。这比搜索词干净得多，代价是样本量变小。

## 诚实边界
- 只统计**中文 JD**（中文字符占比 ≥ 15%），因为要检验的是中文词表；
- 只统计**岗位名明确可判**的记录，模糊的一律不计入（不猜、不硬凑）；
- 检验的是「族识别」，不是「能力项抽取准确率」——后者无人工标注，只报统计量。
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.extract import extract_by_rules
from career_loop.matching.schema import detect_domains

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "cn_eval", "china_job.parquet")

# 岗位名 → career-loop 岗位族集合。
# 只收「岗位名里出现这些词就基本确定是这一族」的情况，宁缺毋滥。
TITLE_TO_FAMILY: list[tuple[tuple[str, ...], set[str]]] = [
    # --- AI / 算法 ---
    (("算法工程师", "算法专家", "算法研究员", "推荐算法", "搜索算法", "大模型算法",
      "算法工程师(大模型)", "机器学习工程师", "深度学习工程师", "nlp工程师", "cv工程师"),
     {"ai_nlp", "ai_cv", "ai_recsys", "ai_multimodal", "ai"}),
    (("视觉设计师", "ui设计师", "交互设计师", "平面设计师", "网页设计师"), {"design"}),
    # --- 后端 / 前端 / 全栈 ---
    (("后端开发", "服务端开发", "后端工程师", "java开发", "go开发", "golang开发",
      "php开发", "python开发", "c++开发"), {"backend"}),
    (("前端开发", "前端工程师", "web前端", "网页开发", "h5开发"), {"frontend"}),
    (("全栈开发", "全栈工程师"), {"backend", "frontend"}),
    (("软件测试", "测试工程师", "测试开发", "qa工程师", "自动化测试"), {"qa"}),
    (("运维工程师", "运维开发", "sre工程师", "linux运维", "系统运维"), {"devops", "it_systems"}),
    (("实施工程师", "实施顾问", "erp实施", "软件实施"), {"it_systems", "consulting"}),
    (("技术支持工程师", "技术支持", "售前工程师", "售前顾问"), {"it_systems", "ai_solution", "consulting"}),
    # --- 数据 ---
    (("数据分析师", "数据工程师", "大数据开发", "数据挖掘", "商业分析", "bi工程师",
      "数据仓库", "数据治理"), {"data_analysis", "ai_data"}),
    # --- 产品 / 项目 ---
    (("产品经理", "产品运营", "产品助理"), {"product"}),
    (("项目经理", "项目专员", "pmp", "项目主管"), {"project_mgmt"}),
    # --- 设计 ---
    (("平面设计", "品牌设计", "包装设计", "服装设计", "室内设计", "景观设计",
      "工业设计", "造型设计"), {"design"}),
    # --- 销售 / 市场 ---
    (("销售经理", "销售代表", "销售顾问", "销售总监", "大客户经理", "海外销售",
      "电话销售", "医药代表", "区域销售"), {"sales"}),
    (("外贸业务员", "外贸经理", "外贸专员", "进出口专员"), {"trade", "sales"}),
    (("市场营销", "市场经理", "品牌经理", "市场专员", "策划经理", "品牌策划",
      "新媒体运营", "内容运营", "网站运营", "seo", "电商运营", "产品运营专员"),
     {"marketing", "operations", "ecommerce"}),
    (("商务拓展", "bd经理", "bd专员"), {"sales"}),
    # --- 人力 / 行政 ---
    (("人力资源", "hr专员", "hr经理", "招聘专员", "招聘经理", "人力资源经理",
      "人力资源专员", "薪酬绩效", "培训经理", "组织发展", "hrbp", "人力行政"),
     {"hr"}),
    (("行政文员", "行政主管", "行政经理", "总裁助理", "总经理助理", "总裁秘书",
      "董事长秘书", "前台", "文秘"), {"admin"}),
    # --- 财务 ---
    (("会计", "总账会计", "成本会计", "出纳", "财务经理", "财务主管", "财务专员",
      "财务总监", "税务", "审计师", "审计专员", "内部审计", "注册会计师"),
     {"finance"}),
    (("投资经理", "投资顾问", "投资岗", "投资分析师", "投资总监", "投资银行",
      "投行", "行业研究", "研究员(行业)", "融资专员", "融资总监", "投资合伙人",
      "基金经理", "私募"), {"securities", "finance", "banking"}),
    (("风控", "风险管理", "合规", "反洗钱", "授信", "信贷"), {"banking", "risk" if False else "banking"}),
    (("精算", "保险精算", "核保", "理赔", "保险经纪", "保险产品"), {"insurance"}),
    # --- 咨询 ---
    (("咨询顾问", "管理咨询", "战略咨询", "咨询经理", "顾问(咨询)", "行业顾问"), {"consulting"}),
    # --- 法务 / 合规 ---
    (("法务", "律师", "法务专员", "法务经理", "合规经理", "知识产权"), {"legal"}),
    # --- 物流 / 供应链 ---
    (("物流经理", "物流专员", "仓储经理", "仓储主管", "供应链经理", "供应链专员",
      "采购经理", "采购专员", "物料管理", "计划员", "跟单", "货运"), {"logistics", "supply"}),
    (("报关", "货代", "船务", "订舱"), {"logistics", "trade"}),
    # --- 制造 / 质量 / 工程 ---
    (("生产主管", "生产经理", "车间主任", "生产计划", "工艺工程师", "工艺员",
      "生产管理", "厂长"), {"manufacturing"}),
    (("质量工程师", "质量管理", "qa质量", "检验员", "品控", "质量主管", "体系工程师"),
     {"quality"}),
    (("机械工程师", "机械设计", "结构工程师", "结构设计", "设备工程师", "工艺装备"),
     {"mechanical", "manufacturing"}),
    (("电气工程师", "电气设计", "自动化工程师", "plc工程师", "电气工程师(自动化)",
      "硬件工程师", "电子工程师", "嵌入式工程师", "软件(嵌入式)", "fpga"), {"electrical", "embedded"}),
    (("土木工程师", "结构(建筑)", "施工员", "造价工程师", "建筑设计师", "市政"),
     {"construction"}),
    # --- 教育 / 传媒 / 医疗 ---
    (("教师", "教研", "课程顾问(教育)", "招生", "教务", "班主任"), {"education"}),
    (("编辑", "记者", "撰稿", "校对", "出版编辑", "文案编辑"), {"media"}),
    (("主播", "主持人", "编导", "影视制片", "制片人", "内容制片"), {"media", "film"}),
    (("平面设计(印刷)", "印刷"), {"manufacturing"}),
    (("医师", "医生", "临床", "护士", "药师", "医技", "医院管理", "CRO", "cra",
      "临床监查", "生物分析"), {"healthcare"}),
    (("公务员", "事业单位", "街道", "政府事务", "政策研究", "公共事务"), {"public_admin"}),
    (("翻译", "译员", "本地化", "字幕"), {"translation"}),
    (("旅游顾问", "导游", "旅行社", "酒店前台", "民宿"), {"tourism"}),
    (("农业", "种植", "养殖", "农艺", "农场", "技术经理(农业)", "兽医", "畜牧"),
     {"agriculture"}),
    (("能源", "电站", "光伏", "风电", "电气(能源)", "电池工程师", "储能"), {"energy"}),
    (("汽车", "整车", "底盘工程师", "车机", "座舱"), {"automotive"}),
    (("游戏策划", "游戏开发", "unity", "原神", "数值策划", "游戏美术"), {"game"}),
    (("物业", "设施管理", "工程管理(物业)", "商场运营", "招商主管", "店铺运营"),
     {"property", "retail"}),
    (("客服", "呼叫中心", "售后", "客户成功"), {"service"}),
    (("采购", "供应商管理"), {"supply"}),
    (("HR_行政",), {"hr", "admin"}),
]


def zh_ratio(s: str) -> float:
    if not s:
        return 0.0
    zh = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    return zh / len(s)


def label_of(title: str) -> set[str] | None:
    """用岗位名判族。判不出来就返回 None（不硬凑）。

    ASCII 关键词按词边界匹配。v0.8.14 修过一个真 bug：原来纯子串匹配，
    "Abercrombie & Fitch" 因为含子串 "cro"（CRO=临床研究外包）被标成
    healthcare，4 条服装导购 JD 混进了医疗族——标注错了，不是引擎错。
    """
    if not title:
        return None
    low = title.lower()
    for kws, fams in TITLE_TO_FAMILY:
        for kw in kws:
            kwl = kw.lower()
            if kwl.isascii():
                if re.search(r"(?<![a-z0-9])" + re.escape(kwl) + r"(?![a-z0-9])", low):
                    return fams
            elif kwl in low:
                return fams
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只取前 N 条（调试用）")
    ap.add_argument("--extract-stats", action="store_true",
                    help="附带统计中文 JD 的能力项抽取质量")
    ap.add_argument("--show-misses", type=int, default=10, help="列出前 N 个误判样例")
    args = ap.parse_args()

    if not os.path.exists(DATA):
        print(
            "\n[missing] 未找到中文 JD 数据集。请先运行：\n"
            "  python scripts/fetch_cn_eval_data.py\n"
            "（HuggingFace ngtranai09/china_job，约 9.3MB，不入库）\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        import pyarrow.parquet as pq
    except ImportError:
        print("\n[missing] 需要 pyarrow：pip install pyarrow\n", file=sys.stderr)
        raise SystemExit(1)

    rows = pq.read_table(DATA).to_pylist()
    if args.limit:
        rows = rows[: args.limit]

    total = 0
    hit = 0
    per = collections.Counter()
    per_hit = collections.Counter()
    pred_counter = collections.Counter()
    misses: list[tuple[str, str, str]] = []
    by_family_hit = collections.Counter()
    by_family_tot = collections.Counter()

    ext_total = ext_empty = ext_items = ext_custom = ext_jds = 0

    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue  # 只检验中文 JD
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue  # 岗位名判不出来的，不计入
        total += 1
        per[title] += 1

        preds = detect_domains(text)
        if preds:
            pred_counter[preds[0]] += 1
        if any(p in expected for p in preds):
            hit += 1
            per_hit[title] += 1
        else:
            misses.append((title, r.get("company_name") or "", text[:120]))

        for fam in expected:
            by_family_tot[fam] += 1
            if any(p in expected for p in preds):
                by_family_hit[fam] += 1

        if args.extract_stats:
            ext_jds += 1
            reqs = extract_by_rules(text)
            if not reqs:
                ext_empty += 1
            else:
                ext_total += 1
                ext_items += len(reqs)
                ext_custom += sum(1 for x in reqs if x.key.startswith("custom:"))

    if total == 0:
        print("没有可检验的记录")
        return

    print(f"可检验的中文 JD：{total} 条（岗位名可明确判族的记录）")
    print(f"**总体族识别准确率：{hit / total:.3f}**  ({hit}/{total})")
    print("\nTop 预测族（族名: 次数）:")
    for name, c in pred_counter.most_common(12):
        print(f"  {name:20s} {c}")

    print("\n按期望族统计（样本 ≥5）：")
    for fam, c in sorted(by_family_tot.items(), key=lambda kv: -kv[1]):
        if c < 5:
            continue
        print(f"  {fam:20s} {by_family_hit[fam]:4d}/{c:4d} = {by_family_hit[fam] / c:.3f}")

    if args.show_misses and misses:
        print(f"\n误判样例（前 {min(args.show_misses, len(misses))} 条）:")
        for title, comp, text in misses[: args.show_misses]:
            print(f"  [{title} | {comp}] 预测={[n for n,_ in []]}")
            print(f"      {text}")

    if args.extract_stats:
        print("\n=== 中文 JD 能力项抽取质量 ===")
        print(f"  样本 JD：{ext_jds} 条")
        print(f"  抽不出任何能力项：{ext_empty} 条（{ext_empty / max(1, ext_jds) * 100:.1f}%）")
        print(f"  平均能力项：{ext_items / max(1, ext_total):.2f} 个/JD")
        print(f"  custom（词表未覆盖）占比：{ext_custom / max(1, ext_items) * 100:.1f}%")


if __name__ == "__main__":
    main()
