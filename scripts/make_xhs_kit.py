#!/usr/bin/env python3
"""生成小红书图文笔记的后两张套图（图 3 证据墙、图 4 打开方式）。

图 1（封面）= docs/xhs-cover.png，由 make_social_cover.py 生成
图 2（产品实况）= .tmp/xhs/p1.png，Edge headless 直接截 1080x1440，无需加工
图 3 / 图 4 = 本脚本生成

证据墙裁切依赖 `.tmp/xhs/full.png`（1080x7000 整页图）。重新截图：
    msedge --headless=new --hide-scrollbars --window-size=1080,7000 \
           --screenshot=.tmp/xhs/full.png \
           "file:///<abs>/docs/standalone.html?s=0"
若整页图缺失，本脚本会自动跳过图 3 并提示，不会静默产出半成品。

用法：
    python scripts/make_xhs_kit.py
    python scripts/make_xhs_kit.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_social_cover as msc  # noqa: E402  复用配色/字体/背景

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp" / "xhs"
OUT_EV = ROOT / "docs" / "xhs-evidence.png"
OUT_HOW = ROOT / "docs" / "xhs-howto.png"

W, H, MARGIN = msc.W, msc.H, msc.MARGIN
LINK = "workbuddy.link/p/Jt3O7bi3SUFYI3SG1iOVDE"

# 证据墙在整页图中的位置（1080x7000 实测坐标）
# 顶部从 3540 起：3478 附近会带上上一区块「职业分类大典」的说明小字，很脏
EVIDENCE_BOX = (16, 3540, 1064, 4400)


def _label(d: ImageDraw.ImageDraw, text: str, y: int, color=msc.CYAN) -> None:
    f = msc._font(msc._pick(msc.FONT_CANDIDATES_BOLD), 30)
    d.text((MARGIN, y), text, font=f, fill=color)


def build_evidence() -> bool:
    src = TMP / "full.png"
    if not src.exists():
        print(f"SKIP 图3：缺少 {src.relative_to(ROOT)}（先按文件头的命令重新截整页图）")
        return False

    bold = msc._pick(msc.FONT_CANDIDATES_BOLD)
    reg = msc._pick(msc.FONT_CANDIDATES_REG)
    img = msc._background()
    d = ImageDraw.Draw(img)

    _label(d, "证据墙 · 这分数凭什么可信", 118)
    d.text((MARGIN, 168), "它说自己 93.6% 准，", font=msc._font(bold, 68), fill=msc.WHITE)
    d.text((MARGIN, 252), "也公开自己失效的地方", font=msc._font(bold, 68), fill=msc.CYAN)
    d.text((MARGIN, 352), "下面每个数字都能自己跑脚本复现，不是 PPT 里的截图。",
           font=msc._font(reg, 34), fill=msc.MUTED)

    shot = Image.open(src).convert("RGB").crop(EVIDENCE_BOX)
    target_w = W - 2 * 40
    shot = shot.resize((target_w, int(shot.height * target_w / shot.width)), Image.LANCZOS)
    y = 420
    # 细边框，让截图和底色之间有条分隔而不是糊在一起
    d.rounded_rectangle([40 - 2, y - 2, 40 + target_w + 2, y + shot.height + 2],
                        radius=18, outline=(52, 58, 82), width=2)
    img.paste(shot, (40, y))

    d.text((MARGIN, H - 108), "r = 0.193 · 2,000 对真实标注 · 公开数据集可一键复现",
           font=msc._font(reg, 28), fill=msc.MUTED)

    img.save(OUT_EV, optimize=True)
    print(f"wrote {OUT_EV.relative_to(ROOT)}  {img.size[0]}x{img.size[1]}")
    return True


def build_howto() -> bool:
    bold = msc._pick(msc.FONT_CANDIDATES_BOLD)
    reg = msc._pick(msc.FONT_CANDIDATES_REG)
    img = msc._background()
    d = ImageDraw.Draw(img)

    _label(d, "打开方式 · 不用下载", 118)
    d.text((MARGIN, 170), "一个链接，", font=msc._font(bold, 76), fill=msc.WHITE)
    d.text((MARGIN, 262), "手机也能直接跑", font=msc._font(bold, 76), fill=msc.CYAN)

    # 链接框：拆两行，保证手机上照着敲得下
    box = [MARGIN, 412, W - MARGIN, 640]
    d.rounded_rectangle(box, radius=24, fill=(20, 24, 38), outline=(70, 78, 110), width=2)
    d.text((MARGIN + 44, 448), "workbuddy.link",
           font=msc._font(bold, 62), fill=msc.WHITE)
    d.text((MARGIN + 44, 538), "/p/Jt3O7bi3SUFYI3SG1iOVDE",
           font=msc._font(bold, 54), fill=msc.PURPLE)

    steps = [
        ("1", "打开上面的链接"),
        ("2", "把 JD 和你的经历各粘一段"),
        ("3", "拿匹配分、逐项缺口、补强优先级"),
    ]
    y = 740
    for num, text in steps:
        d.ellipse([MARGIN, y + 4, MARGIN + 52, y + 56], outline=(120, 130, 165), width=2)
        nb = msc._font(bold, 30).getbbox(num)
        d.text((MARGIN + 26 - (nb[2] - nb[0]) / 2, y + 12), num,
               font=msc._font(bold, 30), fill=msc.CYAN)
        d.text((MARGIN + 78, y + 6), text, font=msc._font(reg, 42), fill=msc.WHITE)
        y += 96

    # 底部三行卖点
    d.line([(MARGIN, H - 300), (W - MARGIN, H - 300)], fill=(46, 52, 74), width=2)
    y = H - 258
    for t in ("纯前端 · 零依赖 · 数据不上传，全部在本机算",
              "内置 69 个岗位族，非技术岗也能用",
              "投完回填真实结果，它能自己校准准不准"):
        d.text((MARGIN, y), t, font=msc._font(reg, 32), fill=msc.MUTED)
        y += 62

    img.save(OUT_HOW, optimize=True)
    print(f"wrote {OUT_HOW.relative_to(ROOT)}  {img.size[0]}x{img.size[1]}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        bad = 0
        for p in (OUT_EV, OUT_HOW):
            if not p.exists():
                print(f"MISSING {p.name}")
                bad += 1
                continue
            with Image.open(p) as im:
                ok = im.size == (W, H)
                print(f"{'OK' if ok else 'BAD'} {p.name} {im.size[0]}x{im.size[1]}")
                bad += 0 if ok else 1
        return 1 if bad else 0

    ok_ev = build_evidence()
    ok_how = build_howto()
    return 0 if (ok_ev and ok_how) else 1


if __name__ == "__main__":
    sys.exit(main())
