# -*- coding: utf-8 -*-
"""新增词预检：对每个准备加入词表的词，测它在真实中文 JD 里的族精确率。

用途：加词之前先体检，避免把 v0.8.7 踩过的坑（直接加过泛词导致别的族掉分）
再踩一遍。判定标准与 analyze_kw_precision.py 一致：
  prec = 出现在本族期望 JD 的次数 / 出现在所有 JD 的次数
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.cn_eval_family import DATA, label_of, zh_ratio

# (目标族, 词) —— 与 schema.py 的修改一一对应
PROPOSED: list[tuple[str, str]] = [
    # banking 投行线
    ("banking", "投行"), ("banking", "投资银行"), ("banking", "投融资"),
    ("banking", "尽职调查"), ("banking", "股权投资"), ("banking", "投后管理"),
    ("banking", "投资经理"), ("banking", "融资"), ("banking", "股权"),
    ("banking", "投资项目"), ("banking", "募资"), ("banking", "承做"),
    ("banking", "ipo"), ("banking", "并购"), ("banking", "增资"),
    ("banking", "减资"), ("banking", "定增"),
    # securities 投资线
    ("securities", "投资"), ("securities", "融资"), ("securities", "股权"),
    ("securities", "投后管理"), ("securities", "投资经理"), ("securities", "投资项目"),
    ("securities", "募资"), ("securities", "定增"), ("securities", "减持"),
    ("securities", "增持"), ("securities", "研报"),
    # data_analysis 新族
    ("data_analysis", "数据分析"), ("data_analysis", "商业分析"), ("data_analysis", "数据报表"),
    ("data_analysis", "指标体系"), ("data_analysis", "数据透视"), ("data_analysis", "tableau"),
    ("data_analysis", "powerbi"), ("data_analysis", "数据可视化"), ("data_analysis", "数据看板"),
    ("data_analysis", "驾驶舱"), ("data_analysis", "数据监测"), ("data_analysis", "统计分析"),
    ("data_analysis", "数据提取"), ("data_analysis", "取数"), ("data_analysis", "商业智能"),
    ("data_analysis", "数据支持"),
    # legal 律所线
    ("legal", "律师"), ("legal", "律所"), ("legal", "案件"), ("legal", "法学"),
    ("legal", "办案"), ("legal", "案源"),
    # healthcare 临床线
    ("healthcare", "科室"), ("healthcare", "儿科"), ("healthcare", "门诊"),
    ("healthcare", "住院"), ("healthcare", "主治医师"), ("healthcare", "眼科"),
    ("healthcare", "外科"), ("healthcare", "手术"), ("healthcare", "查房"),
    # healthcare 医学事务线
    ("healthcare", "学术推广"), ("healthcare", "医学信息"), ("healthcare", "学术会议"),
    ("healthcare", "药企"), ("healthcare", "医学事务"), ("healthcare", "临床学术"),
    # game
    ("game", "游戏开发"), ("game", "游戏引擎"), ("game", "unity"), ("game", "ue"),
    ("game", "ue4"), ("game", "ue5"), ("game", "手游"), ("game", "端游"),
    ("game", "游戏项目"), ("game", "游戏客户端"), ("game", "游戏服务端"),
    # film 直播/艺人线
    ("film", "主播"), ("film", "直播"), ("film", "才艺"), ("film", "秀场"),
    ("film", "语音直播"), ("film", "脱口秀"), ("film", "艺人"), ("film", "公会"),
    ("film", "配音"), ("film", "播音"), ("film", "播客"), ("film", "网红"),
    # operations SEO 线
    ("operations", "seo"), ("operations", "搜索引擎"), ("operations", "关键词"),
    ("operations", "网站优化"), ("operations", "建站"), ("operations", "网站架构"),
    ("operations", "搜索排名"), ("operations", "网站运营"),
    # energy 发电线
    ("energy", "发电"), ("energy", "电厂"), ("energy", "发电机组"),
    ("energy", "汽轮机"), ("energy", "风机"), ("energy", "输变电"),
    # agriculture 农产品线
    ("agriculture", "农产品"), ("agriculture", "农业产业园"), ("agriculture", "农产品加工"),
    ("agriculture", "冷链物流"), ("agriculture", "预制菜"), ("agriculture", "中央厨房"),
    ("agriculture", "团餐"), ("agriculture", "农业行业"),
    # logistics 冷链
    ("logistics", "冷链"), ("logistics", "冷链物流"),
    # quality
    ("quality", "质量检验"), ("quality", "巡检"), ("quality", "品质管理"),
    ("quality", "检验计划"),
    # it_systems 现场线
    ("it_systems", "故障诊断"), ("it_systems", "售后支持"), ("it_systems", "现场支持"),
    ("it_systems", "安装调试"), ("it_systems", "现场调试"),
    # project_mgmt
    ("project_mgmt", "项目生命周期"), ("project_mgmt", "项目全周期"),
    ("project_mgmt", "研发项目"), ("project_mgmt", "危机管理"),
    ("project_mgmt", "项目执行"), ("project_mgmt", "项目协调"),
    ("project_mgmt", "项目汇报"), ("project_mgmt", "项目总结"),
    ("project_mgmt", "项目实施"), ("project_mgmt", "项目文档"),
    # public_admin
    ("public_admin", "地方政府"), ("public_admin", "地方经济"),
    # service
    ("service", "客户服务"), ("service", "售后客服"), ("service", "客户维护"),
    ("service", "客户维系"), ("service", "咨询电话"), ("service", "客服工作"),
]


def main() -> None:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    recs: list[tuple[str, set[str]]] = []
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        exp = label_of(r.get("job_title") or "")
        if not exp:
            continue
        recs.append((text.lower(), exp))
    print(f"可检验记录 {len(recs)} 条\n")

    print(f"{'族':16s} {'词':12s} {'occ':>5s} {'own':>5s} {'prec':>7s}  判定")
    bad = []
    for fam, kw in PROPOSED:
        occ = own = 0
        for low, exp in recs:
            if kw in low:
                occ += 1
                if fam in exp:
                    own += 1
        prec = own / occ if occ else 0.0
        if occ < 3:
            verdict = "样本不足"
        elif prec >= 0.6:
            verdict = "✅ 收"
        elif prec >= 0.4:
            verdict = "⚠️ 边缘"
        else:
            verdict = "❌ 过泛，不收"
            bad.append((fam, kw, occ, own, prec))
        print(f"{fam:16s} {kw!r:12s} {occ:5d} {own:5d} {prec*100:6.1f}%  {verdict}")
    print(f"\n过泛词 {len(bad)} 个（不加）:")
    for fam, kw, occ, own, prec in bad:
        print(f"  [{fam}] {kw!r} occ={occ} own={own} prec={prec*100:.0f}%")


if __name__ == "__main__":
    main()
